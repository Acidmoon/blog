import json
import os
import re
import urllib.error
import urllib.request

import config


POLISH_SYSTEM_PROMPT = """你是中文博客的轻量编辑，只做“口述稿润色”，不是代写，也不是换风格。

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
"""

_PROVIDER_ID_RE = re.compile(r'^[a-zA-Z0-9_.:-]{1,64}$')


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
        _profile(
            'deepseek',
            'DeepSeek',
            os.environ.get('AI_POLISH_DEEPSEEK_API_BASE', 'https://api.deepseek.com/v1'),
            'AI_POLISH_DEEPSEEK_API_KEY',
            _csv(os.environ.get('AI_POLISH_DEEPSEEK_MODELS', 'deepseek-v4-flash,deepseek-v4-pro')),
            os.environ.get('AI_POLISH_DEEPSEEK_MODEL', 'deepseek-v4-flash'),
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


def _build_user_prompt(title: str, tags: str, content: str) -> str:
    return f"""标题：{title or '未填写'}
标签：{tags or '未填写'}

请轻微润色下面这篇博客草稿。记住：只修语气词、语病、重复和标点，让口述更顺一点，不要改风格，不要大改。

草稿正文：
{content}
"""


def polish_content(title: str, tags: str, content: str, provider_id: str | None = None, model: str | None = None) -> str:
    content = (content or '').strip()
    if not content:
        raise ValueError('正文不能为空')

    profile, selected_model, api_key = _resolve_profile(provider_id, model)
    payload = {
        'model': selected_model,
        'messages': [
            {'role': 'system', 'content': POLISH_SYSTEM_PROMPT},
            {'role': 'user', 'content': _build_user_prompt(title, tags, content)},
        ],
        'temperature': 0.25,
        'top_p': 0.85,
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
