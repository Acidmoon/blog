import json
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


def _build_user_prompt(title: str, tags: str, content: str) -> str:
    return f"""标题：{title or '未填写'}
标签：{tags or '未填写'}

请轻微润色下面这篇博客草稿。记住：只修语气词、语病、重复和标点，让口述更顺一点，不要改风格，不要大改。

草稿正文：
{content}
"""


def polish_content(title: str, tags: str, content: str) -> str:
    content = (content or '').strip()
    if not content:
        raise ValueError('正文不能为空')
    if not config.AI_POLISH_API_KEY:
        raise RuntimeError('AI_POLISH_API_KEY 未配置')

    payload = {
        'model': config.AI_POLISH_MODEL,
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
        f"{config.AI_POLISH_API_BASE}/chat/completions",
        data=data,
        method='POST',
        headers={
            'Authorization': f"Bearer {config.AI_POLISH_API_KEY}",
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
