import re

from flask import Flask

from routes.admin_ai import preview_markdown
from services.articles import render_md
from services.search import highlight_text
from services.wechat_export import render_wechat_html


MALICIOUS_MARKDOWN = '''
<script>alert("script")</script>
<img src="x" onerror="alert('image')">
<a href="javascript:alert('link')" onclick="alert('click')">bad link</a>
[bad markdown link](java&#x0A;script:alert('markdown-link'))
![bad markdown image](javascript:alert('markdown-image'))
<svg onload="alert('svg')"><a href="javascript:alert('nested')">nested</a></svg>
<p style="background:url(javascript:alert('style'))">styled</p>
'''


def _assert_no_executable_markup(rendered_html: str) -> None:
    lowered = rendered_html.lower()
    assert '<script' not in lowered
    assert '<svg' not in lowered
    assert not re.search(r'<[^>]*\s(?:onerror|onload|onclick)\s*=', lowered)
    assert 'javascript:' not in lowered
    assert not re.search(r'<[^>]*\sstyle\s*=', lowered)


def test_render_md_sanitizes_raw_html_and_unsafe_urls():
    rendered = render_md(MALICIOUS_MARKDOWN)

    _assert_no_executable_markup(rendered)
    assert 'bad link' in rendered
    assert 'nested' in rendered


def test_render_md_preserves_safe_markdown_features():
    rendered = render_md(
        '''# 标题

| 名称 | 值 |
| --- | --- |
| 表格 | 内容 |

[安全链接](https://example.com/docs "文档")
![插图](/static/images/example.png "说明")

```python
print("<script>literal</script>")
```

$x^2 + y^2$
'''
    )

    assert '<table>' in rendered
    assert 'href="https://example.com/docs"' in rendered
    assert 'src="/static/images/example.png"' in rendered
    assert 'highlight' in rendered
    assert 'arithmatex' in rendered
    assert '&lt;script&gt;literal&lt;/script&gt;' in rendered


def test_admin_preview_uses_the_shared_safe_renderer():
    app = Flask(__name__)
    with app.test_request_context('/admin/api/preview', method='POST', json={'content': MALICIOUS_MARKDOWN}):
        response = preview_markdown.__wrapped__()

    assert response.status_code == 200
    _assert_no_executable_markup(response.get_json()['html'])


def test_search_highlight_escapes_article_text_before_marking_matches():
    highlighted = highlight_text('<img src=x onerror=alert(1)> Match', 'match')

    assert '&lt;img src=x onerror=alert(1)&gt;' in highlighted
    assert '<mark>Match</mark>' in highlighted
    assert '<img' not in highlighted


def test_wechat_export_rejects_unsafe_markup_and_urls():
    export = render_wechat_html(
        title='<img src=x onerror=alert(1)> 标题',
        markdown_text=MALICIOUS_MARKDOWN + '\n[安全链接](/article/safe)\n![安全图](/static/images/example.png)',
        base_url='https://blog.example',
        source_url='javascript:alert(1)',
        author='<script>alert(1)</script>',
        tags='<img src=x onerror=alert(1)>',
    )
    lowered = export['html'].lower()

    assert '<script' not in lowered
    assert '<svg' not in lowered
    assert not re.search(r'<[^>]*\s(?:onerror|onload|onclick)\s*=', lowered)
    assert 'javascript:' not in lowered
    assert 'src="https://blog.example/static/images/example.png"' in export['html']
    assert 'target="_blank" rel="noopener noreferrer"' in export['html']
