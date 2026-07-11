import html
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from services.articles import render_md


BLOCK_TAGS = {
    'p', 'div', 'section', 'article', 'header', 'footer', 'main',
    'blockquote', 'pre', 'ul', 'ol', 'li', 'table', 'thead', 'tbody',
    'tr', 'td', 'th', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'figure',
}

INLINE_TAGS = {'a', 'span', 'strong', 'em', 'b', 'i', 'code', 'br', 'img', 'sub', 'sup'}
VOID_TAGS = {'br', 'hr', 'img'}
SUPPORTED_TAGS = BLOCK_TAGS | INLINE_TAGS | {'hr', 's', 'del'}
SAFE_URL_SCHEMES = {'http', 'https', 'mailto'}


def _strip_markdown(markdown_text: str) -> str:
    text = re.sub(r'```.*?```', ' ', markdown_text, flags=re.S)
    text = re.sub(r'!\[[^\]]*\]\([^\)]*\)', ' ', text)
    text = re.sub(r'\[[^\]]*\]\([^\)]*\)', ' ', text)
    text = re.sub(r'[#>*_`~\-]+', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def build_digest(markdown_text: str, limit: int = 120) -> str:
    text = _strip_markdown(markdown_text)
    return text[:limit]


def _safe_url(value: str) -> str:
    """Return only absolute safe-scheme or relative URLs for exported HTML."""
    normalized = html.unescape(str(value or '')).strip()
    if not normalized:
        return ''
    compact = re.sub(r'[\x00-\x20]+', '', normalized)
    scheme = urlsplit(compact).scheme.lower()
    if scheme and scheme not in SAFE_URL_SCHEMES:
        return ''
    return normalized


def _absolute_url(value: str, base_url: str) -> str:
    safe_value = _safe_url(value)
    if not safe_value:
        return ''
    if urlsplit(safe_value).scheme:
        return safe_value
    safe_base = _safe_url(base_url)
    if urlsplit(safe_base).scheme in {'http', 'https'}:
        return urljoin(safe_base.rstrip('/') + '/', safe_value)
    return safe_value


def _style_open_tag(tag: str, attrs: list[tuple[str, str | None]], base_style: str) -> str:
    attrs_dict = {str(key).lower(): value for key, value in attrs if value is not None}
    safe_attrs: dict[str, str] = {}
    if tag == 'a':
        href = _safe_url(attrs_dict.get('href', ''))
        if href:
            safe_attrs['href'] = href
            safe_attrs['target'] = '_blank'
            safe_attrs['rel'] = 'noopener noreferrer'
        if attrs_dict.get('title'):
            safe_attrs['title'] = str(attrs_dict['title'])
    elif tag == 'img':
        src = _safe_url(attrs_dict.get('src', ''))
        if src:
            safe_attrs['src'] = src
        if attrs_dict.get('alt'):
            safe_attrs['alt'] = str(attrs_dict['alt'])
        if attrs_dict.get('title'):
            safe_attrs['title'] = str(attrs_dict['title'])
        safe_attrs['referrerpolicy'] = 'no-referrer'
        safe_attrs['loading'] = 'lazy'
    elif tag in {'h1', 'h2', 'h3', 'h4', 'h5', 'h6'} and attrs_dict.get('id'):
        safe_attrs['id'] = str(attrs_dict['id'])

    style = base_style.strip().rstrip(';')
    if style:
        safe_attrs['style'] = style
    parts = []
    for key, value in safe_attrs.items():
        parts.append(f'{key}="{html.escape(str(value), quote=True)}"')
    return f'<{tag} ' + ' '.join(parts) + '>' if parts else f'<{tag}>'


class _WechatHTMLTransformer(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__(convert_charrefs=False)
        self.base_url = base_url.rstrip('/') + '/' if base_url and not base_url.endswith('/') else base_url
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        attrs = list(attrs)
        if tag not in SUPPORTED_TAGS:
            return
        if tag == 'h1':
            self.parts.append(_style_open_tag(tag, attrs, 'font-size: 24px; line-height: 1.35; font-weight: 700; margin: 28px 0 16px; color: #222;'))
        elif tag == 'h2':
            self.parts.append(_style_open_tag(tag, attrs, 'font-size: 20px; line-height: 1.4; font-weight: 700; margin: 24px 0 14px; color: #222;'))
        elif tag in {'h3', 'h4', 'h5', 'h6'}:
            self.parts.append(_style_open_tag(tag, attrs, 'font-size: 18px; line-height: 1.45; font-weight: 700; margin: 20px 0 12px; color: #222;'))
        elif tag == 'p':
            self.parts.append(_style_open_tag(tag, attrs, 'margin: 0 0 1em; line-height: 1.9; font-size: 16px; color: #333;'))
        elif tag == 'blockquote':
            self.parts.append(_style_open_tag(tag, attrs, 'margin: 1em 0; padding: 12px 16px; border-left: 4px solid #d8b46a; background: #faf7ef; color: #555; line-height: 1.85;'))
        elif tag == 'pre':
            self.parts.append(_style_open_tag(tag, attrs, 'margin: 1em 0; padding: 14px 16px; background: #f6f7f8; border-radius: 8px; overflow-x: auto; white-space: pre-wrap; word-break: break-word; line-height: 1.7; font-size: 14px;'))
        elif tag == 'code':
            self.parts.append(_style_open_tag(tag, attrs, 'font-family: Menlo, Monaco, Consolas, monospace; font-size: 0.95em; background: #f6f7f8; padding: 0.12em 0.35em; border-radius: 4px;'))
        elif tag == 'a':
            attrs_dict = dict(attrs)
            href = _absolute_url(attrs_dict.get('href', ''), self.base_url)
            link_attrs = [('href', href)] if href else []
            if attrs_dict.get('title'):
                link_attrs.append(('title', attrs_dict['title']))
            self.parts.append(_style_open_tag(tag, link_attrs, 'color: #1a73e8; text-decoration: none;'))
        elif tag == 'img':
            attrs_dict = dict(attrs)
            src = _absolute_url(attrs_dict.get('src', ''), self.base_url)
            image_attrs = [('src', src)] if src else []
            for name in ('alt', 'title'):
                if attrs_dict.get(name):
                    image_attrs.append((name, attrs_dict[name]))
            self.parts.append(_style_open_tag(tag, image_attrs, 'max-width:100%; height:auto; display:block; margin:16px auto;'))
        elif tag in {'ul', 'ol'}:
            self.parts.append(_style_open_tag(tag, attrs, 'margin: 0 0 1em 1.4em; padding: 0; line-height: 1.9;'))
        elif tag == 'li':
            self.parts.append(_style_open_tag(tag, attrs, 'margin: 0.35em 0; line-height: 1.8;'))
        elif tag == 'table':
            self.parts.append(_style_open_tag(tag, attrs, 'width: 100%; border-collapse: collapse; margin: 1em 0; font-size: 14px;'))
        elif tag in {'thead', 'tbody', 'tr', 'td', 'th'}:
            style_map = {
                'thead': 'background: #fafafa;',
                'tbody': '',
                'tr': 'border-bottom: 1px solid #eee;',
                'td': 'padding: 8px 10px; border: 1px solid #eee; vertical-align: top;',
                'th': 'padding: 8px 10px; border: 1px solid #eee; background: #fafafa; font-weight: 700; text-align: left;',
            }
            self.parts.append(_style_open_tag(tag, attrs, style_map.get(tag, '')))
        elif tag == 'hr':
            self.parts.append('<hr style="border: none; border-top: 1px solid #eee; margin: 1.5em 0;">')
        elif tag == 'br':
            self.parts.append('<br>')
        else:
            self.parts.append(_style_open_tag(tag, attrs, ''))

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag not in SUPPORTED_TAGS or tag in VOID_TAGS:
            return
        self.parts.append(f'</{tag}>')

    def handle_startendtag(self, tag, attrs):
        tag = tag.lower()
        if tag in VOID_TAGS:
            self.handle_starttag(tag, attrs)

    def handle_data(self, data):
        self.parts.append(html.escape(data, quote=False))

    def handle_entityref(self, name):
        self.parts.append(f'&{name};')

    def handle_charref(self, name):
        self.parts.append(f'&#{name};')

    def handle_comment(self, data):
        return

    def get_html(self):
        return ''.join(self.parts)


def render_wechat_html(title: str, markdown_text: str, base_url: str = '', source_url: str = '', author: str = '', tags: str = '') -> dict:
    rendered = render_md(markdown_text or '')
    transformer = _WechatHTMLTransformer(base_url or '')
    transformer.feed(rendered)
    transformer.close()
    body_html = transformer.get_html()
    wrapper_style = (
        'font-family: -apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif; '
        'font-size: 16px; line-height: 1.9; color: #333; padding: 0 4px; word-break: break-word;'
    )
    meta = []
    if author:
        meta.append(f'作者：{html.escape(str(author))}')
    if tags:
        meta.append(f'标签：{html.escape(str(tags))}')
    safe_source_url = _safe_url(source_url)
    if safe_source_url:
        source = html.escape(safe_source_url, quote=True)
        meta.append(f'原文：<a href="{source}" target="_blank" rel="noopener noreferrer" style="color:#1a73e8;text-decoration:none;">{source}</a>')
    meta_html = ''
    if meta:
        meta_html = '<div style="margin: 12px 0 20px; font-size: 13px; color: #888; line-height: 1.8;">' + '<br>'.join(meta) + '</div>'
    html_doc = f'''<section style="{wrapper_style}">
  <h1 style="font-size: 24px; line-height: 1.35; font-weight: 700; margin: 0 0 12px; color: #222;">{html.escape(str(title or ''))}</h1>
  {meta_html}
  {body_html}
</section>'''
    plain_text = _strip_markdown(markdown_text or '')
    return {
        'title': title,
        'html': html_doc,
        'plain_text': plain_text,
    }
