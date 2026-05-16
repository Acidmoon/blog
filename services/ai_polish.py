import json
import os
import re
import urllib.error
import urllib.request

import config


POLISH_MODES = [
    {
        'id': 'light',
        'label': '轻润色',
        'description': '只修语病、重复和口语表达，尽量保留原风格。',
        'temperature': 0.25,
        'top_p': 0.85,
        'system_prompt': """你是中文博客的轻量编辑，只做“口述稿润色”，不是代写，也不是换风格。

编辑目标：
- 保留作者原意、判断、语气和表达顺序。
- 只处理口述带来的问题：语气词、重复词、明显病句、断裂句、错别字、标点混乱。
- 把过于口语的句子适当书面化一点，但仍然像本人写的博客。
- 可以自然分段；只有原文已经有明确层次时，才加少量小标题。

严格禁止：
- 不要大改结构，不要重写成公众号爆文，不要营销化。
- 不要扩写观点，不要添加原文没有的事实、例子、数据或结论。
- 不要使用“首先/其次/最后”式模板，除非原文本来就是这种结构。
- 不要使用夸张词、鸡汤句、总结升华、AI 腔套话。
- 不要把所有口语都抹掉，要保留一点真实的人味。

输出要求：
- 只输出润色后的正文，不要解释，不要前后寒暄。
- 保留 Markdown 语法、链接、代码块、列表的大意。
""",
        'user_instruction': '请轻微润色下面这篇博客草稿。记住：只修语气词、语病、重复和标点，让口述更顺一点，不要改风格，不要大改。',
    },
    {
        'id': 'khazix_rewrite',
        'label': '卡兹克式公众号改写',
        'description': '保留事实与观点，重组节奏，增强主观判断、口语感和阅读张力。',
        'temperature': 0.45,
        'top_p': 0.9,
        'system_prompt': """你是中文公众号长文编辑，目标是把草稿改成“卡兹克式公众号文章”的表达：像一个有见识的普通人在认真聊一件打动他的事。

风格目标：
- 开头像真实的人在说话：从具体问题、具体场景、个人判断或反常识观察切入。
- 语言口语化、短段落、有停顿感；允许适度主观、直接、带一点情绪。
- 多用具体判断，少用抽象套话；让读者感觉作者真的在想这件事。
- 可以重排段落、调整节奏、补足过渡，但不要改变作者立场。

严格边界：
- 不编造原文没有的事实、数据、案例、亲身经历或引用。
- 不要标题党，不要营销腔，不要鸡汤升华，不要“家人们”“爆款秘籍”这类廉价表达。
- 不要使用“首先/其次/最后”“综上所述”“值得注意的是”“不难发现”等 AI 腔套话。
- 不要强行加密集小标题；除非原文确实很长且层次需要。

输出要求：
- 只输出改写后的正文，不要解释，不要前后寒暄。
- 保留 Markdown 语法、链接、代码块、列表的大意。
""",
        'user_instruction': '请把下面这篇博客草稿改写成卡兹克式公众号文章。可以重组节奏、增强表达和主观判断，但不要添加原文没有的新事实、案例或结论。',
    },
    {
        'id': 'khazix_expand',
        'label': '卡兹克式长文扩写',
        'description': '在不编事实的前提下，把素材扩成更完整的公众号长文。',
        'temperature': 0.55,
        'top_p': 0.92,
        'system_prompt': """你是中文公众号长文写作编辑，目标是把素材扩写成“卡兹克式公众号长文”：有个人判断、有问题意识、有阅读节奏，像一个有见识的普通人在认真聊一件打动他的事。

写作方法：
- 先判断素材最打动人的矛盾、问题或观点，再围绕它展开。
- 可以扩展解释原文已有观点，补足逻辑链和过渡，让文章更完整。
- 语言要口语、短段落、有人味；适度使用反问、停顿和直接判断。
- 尽量从具体场景或具体判断开头，不要上来宏大叙事。

严格边界：
- 不编造事实、数据、案例、亲身经历、引用、来源或人物。
- 如果原文信息不足，只能扩展分析和表达，不能假装掌握更多事实。
- 不要营销腔、鸡汤腔、AI 腔，不要“首先/其次/最后”“综上所述”“值得注意的是”等模板话。
- 不要为了变长而灌水；宁可短一点，也要真实、具体、顺。

输出要求：
- 只输出扩写后的正文，不要解释，不要前后寒暄。
- 保留 Markdown 语法、链接、代码块、列表的大意。
""",
        'user_instruction': '请把下面这份博客素材扩写成一篇更完整的卡兹克式公众号长文。可以扩展原文已有观点和逻辑，但不要添加原文没有的新事实、案例或结论。',
    },
]

POLISH_MODES_BY_ID = {mode['id']: mode for mode in POLISH_MODES}
DEFAULT_POLISH_MODE = 'light'
_PROVIDER_ID_RE = re.compile(r'^[a-zA-Z0-9_.:-]{1,64}$')
_MODE_ID_RE = re.compile(r'^[a-zA-Z0-9_-]{1,64}$')


def _csv(value: str) -> list[str]:
    return [item.strip() for item in (value or '').split(',') if item.strip()]


def _profile(
    profile_id: str,
    label: str,
    api_base: str,
    api_key_env: str,
    models: list[str],
    default_model: str | None = None,
) -> dict:
    models = [m for m in models if m]
    if default_model and default_model not in models:
        models.insert(0, default_model)
    return {
        'id': profile_id,
        'label': label,
        'api_base': (api_base or '').rstrip('/'),
        'api_key_env': api_key_env,
        'models': models,
        'default_model': default_model or (models[0] if models else ''),
        'configured': bool(os.environ.get(api_key_env)),
    }


def get_polish_profiles() -> list[dict]:
    """Return the server-side whitelist of AI polish providers and models."""
    raw = os.environ.get('AI_POLISH_PROVIDERS_JSON', '').strip()
    if raw:
        try:
            loaded = json.loads(raw)
            profiles = []
            for item in loaded if isinstance(loaded, list) else []:
                profile_id = str(item.get('id') or '').strip()
                label = str(item.get('label') or profile_id).strip()
                api_base = str(item.get('api_base') or '').strip()
                api_key_env = str(item.get('api_key_env') or '').strip()
                models = item.get('models') or []
                if isinstance(models, str):
                    models = _csv(models)
                default_model = str(item.get('default_model') or (models[0] if models else '')).strip()
                if profile_id and _PROVIDER_ID_RE.match(profile_id) and api_base and api_key_env and models:
                    profiles.append(_profile(profile_id, label, api_base, api_key_env, list(models), default_model))
            if profiles:
                return profiles
        except (TypeError, json.JSONDecodeError):
            pass

    default_profiles = [
        _profile(
            'deepseek',
            'DeepSeek',
            os.environ.get('AI_POLISH_DEEPSEEK_API_BASE', 'https://api.deepseek.com/v1'),
            'AI_POLISH_DEEPSEEK_API_KEY',
            _csv(os.environ.get('AI_POLISH_DEEPSEEK_MODELS', 'deepseek-v4-flash,deepseek-v4-pro')),
            os.environ.get('AI_POLISH_DEEPSEEK_MODEL', 'deepseek-v4-flash'),
        ),
        _profile(
            'waterhill',
            '水浇岭 / GPT',
            config.AI_POLISH_API_BASE,
            'AI_POLISH_API_KEY',
            _csv(os.environ.get('AI_POLISH_MODELS', 'gpt-5.5,gpt-5.4,gpt-4.1')),
            config.AI_POLISH_MODEL,
        ),
        _profile(
            'waterhill-mimo',
            'waterhill.cyou / MiMo',
            os.environ.get('AI_POLISH_MIMO_API_BASE', 'https://www.waterhill.cyou/v1'),
            'AI_POLISH_MIMO_API_KEY',
            _csv(os.environ.get('AI_POLISH_MIMO_MODELS', 'mimo-v2.5-pro')),
            os.environ.get('AI_POLISH_MIMO_MODEL', 'mimo-v2.5-pro'),
        ),
    ]
    return [p for p in default_profiles if p['api_base'] and p['models']]


def get_public_polish_profiles() -> list[dict]:
    """Profiles safe to expose to the admin page. Never include keys or env names."""
    return [
        {
            'id': profile['id'],
            'label': profile['label'],
            'models': profile['models'],
            'default_model': profile['default_model'],
            'configured': profile['configured'],
        }
        for profile in get_polish_profiles()
    ]


def get_public_polish_modes() -> list[dict]:
    """Writing modes safe to expose to the admin page. Prompt text stays server-side."""
    return [
        {
            'id': mode['id'],
            'label': mode['label'],
            'description': mode['description'],
            'default': mode['id'] == DEFAULT_POLISH_MODE,
        }
        for mode in POLISH_MODES
    ]


def _resolve_mode(mode_id: str | None) -> dict:
    mode_id = (mode_id or DEFAULT_POLISH_MODE).strip()
    if not _MODE_ID_RE.match(mode_id):
        raise ValueError('AI 风格模式无效')
    mode = POLISH_MODES_BY_ID.get(mode_id)
    if not mode:
        raise ValueError('AI 风格模式不在允许列表中')
    return mode


def _resolve_profile(provider_id: str | None, model: str | None) -> tuple[dict, str, str]:
    profiles = get_polish_profiles()
    if not profiles:
        raise RuntimeError('AI 润色供应商未配置')

    provider_id = (provider_id or profiles[0]['id']).strip()
    if not _PROVIDER_ID_RE.match(provider_id):
        raise ValueError('AI 供应商无效')

    profile = next((p for p in profiles if p['id'] == provider_id), None)
    if not profile:
        raise ValueError('AI 供应商不在允许列表中')

    requested_model = (model or profile['default_model'] or '').strip()
    if requested_model not in profile['models']:
        raise ValueError('AI 模型不在当前供应商允许列表中')

    api_key = os.environ.get(profile['api_key_env'], '').strip()
    if not api_key:
        raise RuntimeError(f"{profile['label']} 的 API Key 未配置")
    return profile, requested_model, api_key


def _build_user_prompt(title: str, tags: str, content: str, mode: dict) -> str:
    return f"""标题：{title or '未填写'}
标签：{tags or '未填写'}
风格模式：{mode['label']}

{mode['user_instruction']}

草稿正文：
{content}
"""


def polish_content(
    title: str,
    tags: str,
    content: str,
    provider_id: str | None = None,
    model: str | None = None,
    mode_id: str | None = None,
) -> str:
    content = (content or '').strip()
    if not content:
        raise ValueError('正文不能为空')

    mode = _resolve_mode(mode_id)
    profile, selected_model, api_key = _resolve_profile(provider_id, model)
    payload = {
        'model': selected_model,
        'messages': [
            {'role': 'system', 'content': mode['system_prompt']},
            {'role': 'user', 'content': _build_user_prompt(title, tags, content, mode)},
        ],
        'temperature': mode['temperature'],
        'top_p': mode['top_p'],
        'max_tokens': 4096,
    }
    data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(
        f"{profile['api_base']}/chat/completions",
        data=data,
        method='POST',
        headers={
            'Authorization': f"Bearer {api_key}",
            'Content-Type': 'application/json',
            'User-Agent': 'Waterhill-Blog/1.0',
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=config.AI_POLISH_TIMEOUT) as resp:
            raw = resp.read().decode('utf-8')
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode('utf-8', errors='ignore')[:400]
        raise RuntimeError(f'AI 接口返回 {exc.code}: {detail}') from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f'AI 接口连接失败: {exc.reason}') from exc

    try:
        result = json.loads(raw)
        polished = result['choices'][0]['message'].get('content', '').strip()
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError('AI 接口返回格式无法解析') from exc

    polished = polished.strip()
    for prefix in ('润色后的正文：', '润色后：', '正文：'):
        if polished.startswith(prefix):
            polished = polished[len(prefix):].lstrip()
    polished = _strip_leaked_metadata(polished, title, tags)
    if not polished:
        raise RuntimeError('AI 没有返回润色内容')
    return polished


def _strip_leaked_metadata(text: str, title: str, tags: str) -> str:
    """Remove model-leaked prompt metadata when it echoes title/tags before body."""
    lines = text.splitlines()
    changed = True
    while lines and changed:
        changed = False
        first = lines[0].strip()
        if first.startswith('标题：') or first.startswith('标题:'):
            lines.pop(0)
            changed = True
            continue
        if first.startswith('标签：') or first.startswith('标签:'):
            lines.pop(0)
            changed = True
            continue
        if not first:
            lines.pop(0)
            changed = True
    return '\n'.join(lines).strip()
