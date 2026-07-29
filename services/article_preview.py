"""编辑器实时预览：按已发布文章页的结构组合标题、封面、目录与正文。

复用与 ``templates/article.html`` 相同的 class，让预览直接继承文章页的
排版样式；目录在服务端从渲染后的 h2-h4 提取，和文章页 JS 的规则一致。
"""

from __future__ import annotations

import html
import re
from datetime import datetime

from features.articles.content_store import count_words
from services.articles import _normalize_cover_image, render_md

_HEADING_RE = re.compile(r'<h([234]) id="([^"]+)">(.*?)</h\1>', re.S)
_TAG_RE = re.compile(r'<[^>]+>')


def _extract_toc(body_html: str) -> list[dict]:
    """提取 h2-h4 目录项；与文章页 TOC 一样只取带 id 的标题。"""
    items = []
    for level, anchor, inner in _HEADING_RE.findall(body_html):
        text = html.unescape(_TAG_RE.sub('', inner)).strip()
        if not text:
            continue
        items.append({'level': int(level), 'id': anchor, 'text': text})
    return items


def _render_toc_nav(items: list[dict]) -> str:
    if not items:
        return '<span class="toc-empty">暂无目录</span>'
    links = []
    for item in items:
        cls = 'toc-item'
        if item['level'] == 3:
            cls += ' toc-h3'
        elif item['level'] == 4:
            cls += ' toc-h4'
        links.append(
            f'<a href="#{html.escape(item["id"], quote=True)}" class="{cls}"'
            f' data-heading="{html.escape(item["id"], quote=True)}">'
            f'{html.escape(item["text"])}</a>'
        )
    return ''.join(links)


def _render_meta(word_count: int, tags: list[str]) -> str:
    now = datetime.now()
    parts = [f'<time>{now.year}年{now.month}月{now.day}日 {now:%H:%M:%S}</time>']
    if word_count:
        parts.append(f'· <span class="article-words">{word_count} 字</span>')
    if tags:
        tag_html = ''.join(
            f'<span class="tag-sm">{html.escape(tag)}</span>' for tag in tags
        )
        parts.append(f'<span class="article-tags">{tag_html}</span>')
    return '<div class="article-meta">' + '\n'.join(parts) + '</div>'


def render_editor_preview(
    title: str,
    tags: str,
    content: str,
    cover_image: str = '',
    cover_alt: str = '',
) -> dict:
    """组合整页预览 HTML，返回给编辑器实时预览面板。"""
    title = str(title or '').strip() or '未命名文章'
    tag_list = [t.strip() for t in str(tags or '').split(',') if t.strip()]
    cover_image = _normalize_cover_image(cover_image)
    cover_alt = str(cover_alt or '').strip()
    body_html = render_md(content)
    word_count = count_words(str(content or ''))
    toc_items = _extract_toc(body_html)
    meta_html = _render_meta(word_count, tag_list)

    if cover_image:
        cover_url = '/static/' + cover_image.lstrip('/')
        header_html = f'''
      <section class="article-cover-hero">
        <div class="cover-hero-image">
          <img src="{html.escape(cover_url, quote=True)}" alt="{html.escape(cover_alt, quote=True)}" loading="lazy">
          <div class="cover-hero-overlay"></div>
        </div>
        <div class="cover-hero-content">
          <h1 class="article-title-lg">{html.escape(title)}</h1>
          {meta_html}
        </div>
      </section>'''
    else:
        header_html = f'''
      <header class="article-header">
        <h1 class="article-title-lg">{html.escape(title)}</h1>
        {meta_html}
      </header>'''

    toc_html = ''
    if toc_items:
        toc_html = f'''
      <div class="preview-toc">
        <h4 class="toc-title">目录</h4>
        <nav class="toc-nav">{_render_toc_nav(toc_items)}</nav>
      </div>'''

    full_html = f'''<article class="article-full preview-article">{header_html}
      {toc_html}
      <div class="article-body preview-article-body">
        {body_html}
      </div>
    </article>'''
    return {'html': full_html, 'word_count': word_count, 'toc_count': len(toc_items)}
