import json
import os
import re
import urllib.error
import urllib.request

import config


ACIDMOON_BLOG_STYLE_PROMPT = """Acidmoon / 水浇岭博客长期风格约束：

身份与方向：
- 这是作者自己的博客，不要模仿固定作者、公众号模板或营销号模板。
- 作者更像独立开发者、技术产品 Builder；内容可以混合博客/分享、技术笔记、独立开发日志、产品观察、AI 情报、学习记录、赚钱/运营复盘、个人随笔。
- 受众不需要限定太窄，可以让技术用户、AI 玩家、开发者、学生和普通读者都能读懂。

语言声音：
- 保留第一人称、真实动机、具体场景和个人判断。
- 可以保留自然口语和轻微吐槽，例如“说回”“这么一搞”“我这个人吧”“真的懒得”“这玩意比想象中麻烦”。
- 吐槽必须来自原文或真实上下文，不要为了显得有个性硬加梗。
- 文字可以顺一点，但不要被磨成过度平滑、没有个人感的 AI 润色稿。

标题与结构：
- 标题偏直接、清楚，不要标题党，不要故作高级。
- 文章默认可以按：直接说主题 → 真实背景/动机 → 过程/体验/踩坑/判断 → 必要技术细节 → 简短总结 + 一点个人感受。
- 结尾不要强行升华，不要鸡汤；用简短总结和一点真实感受收住。

产品/设计/运营：
- 产品判断标准：界面简洁、能用、不出 bug；更在意颜值、功能、稳定性。
- 讨厌花里胡哨但找不到功能、功能还弱的产品。
- 写赚钱/运营复盘时，可以偏详细记录过程、成本、收入、利润、决策和踩坑，但不要写成成功学。

技术/学习/研究：
- 技术文章可以混合教程、记录、复盘、笔记、观点；代码/命令和解释比例看具体内容。
- 部署/排障/复现多写命令和验证；概念学习多写解释；复盘多写原因、权衡和踩坑；观点文多写真实使用场景和判断。
- 涉及 CV、单目深度估计、ViT、DPT、扩散模型、论文/研究内容时要更严谨：区分论文结论、作者当前理解和不确定部分；不要乱讲结论。

硬性避雷：
- 强避免“不是……而是……”句式；除非原文已有且必须保留，否则不要生成。
- 不要营销腔、鸡汤腔、爹味教程、装深度、标题党、过度排版、空泛术语。
- 不要使用“赋能”“打造”“闭环”“生态”“高质量内容”等空词，除非原文明确写了。
- 不要用“首先/其次/最后”“综上所述”“值得注意的是”“不难发现”等模板话来凑结构，除非原文确实是这种结构。
"""


POLISH_MODES = [
    {
        'id': 'light',
        'label': '轻润色',
        'description': '理解原意后做分段、标点、重点标注和轻度整理，输出可直接发布的 Markdown。',
        'temperature': 0.25,
        'top_p': 0.85,
        'system_prompt': """你是中文博客的轻量编辑，任务是把作者的口述/草稿整理成“可以直接发布的 Markdown 博客正文”。你不是代写，不是换风格，也不是改成公众号爆文。

核心原则：
- 先理解作者真正想表达的意思，再整理文字；如果原文含混，优先按上下文补足语序和指代，而不是另起炉灶。
- 最大限度贴合原文：保留作者原意、判断、语气、表达顺序和个人口吻。
- 只处理口述或草稿带来的问题：语气词、重复词、明显病句、断裂句、错别字、标点缺失/混乱、长句不清。
- 可以把过于口语的句子适当书面化一点，但仍然要像作者本人写的博客。

整理要求：
- 根据语义自然分段，让每段只表达一个相对完整的意思。
- 补全必要的中文标点符号，让句子清楚、停顿自然。
- 可以用 Markdown 标题（## / ###）梳理明显层次，但不要为了形式强行加标题。
- 可以用 **加粗** 标出少量真正重要的关键词、判断或结论；不要整段加粗，不要滥用重点。
- 保留原文已有的 Markdown、链接、代码块、引用、列表等结构；必要时把散乱内容整理成 Markdown 列表。

严格禁止：
- 不要大改结构，不要重写成营销文、公众号爆文或 AI 范文。
- 不要扩写观点，不要添加原文没有的事实、例子、数据、经历或结论。
- 不要使用“首先/其次/最后”式模板，除非原文本来就是这种结构。
- 不要使用夸张词、鸡汤句、总结升华、AI 腔套话。
- 不要把所有口语都抹掉，要保留一点真实的人味。

输出要求：
- 只输出最终 Markdown 正文，不要解释，不要前后寒暄，不要包裹在代码块里。
- 输出应当是一份可直接保存为 .md 并发布到博客的正文。
- 不要输出“润色后的正文：”“以下是”等提示语。
""" + "\n\n" + ACIDMOON_BLOG_STYLE_PROMPT,
        'user_instruction': '请把下面这篇博客草稿整理润色成可直接发布的 Markdown 正文。重点是理解我的原意，尽量贴合原文；补标点、自然分段、适度标画重点，必要时加少量 Markdown 小标题，但不要改写成另一篇文章。润色时必须遵守 Acidmoon / 水浇岭博客长期风格约束。',
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
""" + "\n\n" + ACIDMOON_BLOG_STYLE_PROMPT,
        'user_instruction': '请把下面这篇博客草稿改写成卡兹克式公众号文章。可以重组节奏、增强表达和主观判断，但不要添加原文没有的新事实、案例或结论。即使使用公众号改写模式，也必须尽量保留 Acidmoon / 水浇岭博客的个人声音和硬性避雷。',
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
""" + "\n\n" + ACIDMOON_BLOG_STYLE_PROMPT,
        'user_instruction': '请把下面这份博客素材扩写成一篇更完整的卡兹克式公众号长文。可以扩展原文已有观点和逻辑，但不要添加原文没有的新事实、案例或结论。即使扩写，也必须遵守 Acidmoon / 水浇岭博客长期风格约束，保留作者自己的口吻。',
    },
]

POLISH_MODES_BY_ID = {mode['id']: mode for mode in POLISH_MODES}
DEFAULT_POLISH_MODE = 'light'
_PROVIDER_ID_RE = re.compile(r'^[a-zA-Z0-9_.:-]{1,64}$')
_MODE_ID_RE = re.compile(r'^[a-zA-Z0-9_-]{1,64}$')

ORGANIZE_SPOKEN_DRAFT_SYSTEM_PROMPT = """你是中文博客的口述稿整理编辑。你的任务不是润色成品文，而是在正式润色之前，把作者口语化、断裂、跳跃的草稿先理顺成一份“意思更清楚、结构更顺、仍然很接近原文”的中间稿。

工作边界：
- 先理解文章在讲什么、作者想表达什么，再按语义整理。
- 尽量保留原文措辞、语气、观点、顺序和信息量；不要改成另一篇文章。
- 只修复口语输入造成的问题：重复词、口头禅、断句混乱、指代不清、语序不顺、明显错别字、同一意思反复绕圈。
- 可以把过长段落拆成自然段；可以把明显属于同一层意思的句子放到一起。
- 不要增加事实、例子、数据、经历、结论或新观点。
- 不要做强风格化润色，不要加标题党表达，不要公众号腔，不要 AI 腔。
- 保留已有 Markdown、链接、代码块、列表、引用的大意和结构。
- 遵守 Acidmoon / 水浇岭博客长期风格约束：保留作者自己的口吻、真实动机、具体场景和个人判断；强避免“不是……而是……”等 AI 味句式。

输出要求：
- 只输出理顺后的正文，不要解释，不要前后寒暄，不要包裹代码块。
- 这是给下一步 AI 润色使用的中间稿，所以要清楚、顺畅、贴近原文，而不是最终改写稿。
"""

ORGANIZE_SPOKEN_DRAFT_USER_INSTRUCTION = '请先把下面这篇口语/草稿正文按原意理顺。重点是理解我想说什么，修复断裂、重复和语序问题，自然分段，但尽量不要改我的原文表达，也不要新增内容。'


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
            _csv(os.environ.get('AI_POLISH_DEEPSEEK_MODELS', 'deepseek-v4-pro,deepseek-v4-flash')),
            os.environ.get('AI_POLISH_DEEPSEEK_MODEL', 'deepseek-v4-pro'),
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


def _build_organize_prompt(title: str, tags: str, content: str) -> str:
    return f"""标题：{title or '未填写'}
标签：{tags or '未填写'}

{ORGANIZE_SPOKEN_DRAFT_USER_INSTRUCTION}

草稿正文：
{content}
"""


def _call_chat_completion(profile: dict, api_key: str, payload: dict) -> str:
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
        content = result['choices'][0]['message'].get('content', '').strip()
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError('AI 接口返回格式无法解析') from exc

    return content.strip()


def polish_content(
    title: str,
    tags: str,
    content: str,
    provider_id: str | None = None,
    model: str | None = None,
    mode_id: str | None = None,
    organize_first: bool = False,
) -> str:
    content = (content or '').strip()
    if not content:
        raise ValueError('正文不能为空')

    mode = _resolve_mode(mode_id)
    profile, selected_model, api_key = _resolve_profile(provider_id, model)
    if organize_first:
        organize_payload = {
            'model': selected_model,
            'messages': [
                {'role': 'system', 'content': ORGANIZE_SPOKEN_DRAFT_SYSTEM_PROMPT},
                {'role': 'user', 'content': _build_organize_prompt(title, tags, content)},
            ],
            'temperature': 0.18,
            'top_p': 0.82,
            'max_tokens': 4096,
        }
        organized = _call_chat_completion(profile, api_key, organize_payload)
        organized = _strip_leaked_metadata(organized, title, tags)
        if not organized:
            raise RuntimeError('AI 没有返回理顺后的内容')
        content = organized

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
    polished = _call_chat_completion(profile, api_key, payload)
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
