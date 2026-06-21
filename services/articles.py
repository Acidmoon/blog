import re
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import markdown as md_lib

import config
from models import get_db


def _count_words(text: str) -> int:
    """Count Chinese characters + English words in a text."""
    cjk = len(re.findall(r'[\u4e00-\u9fff\u3400-\u4dbf]', text))
    en_words = len(re.findall(r'[a-zA-Z0-9]+', text))
    return cjk + en_words


def slugify(text):
    text = text.strip().lower()
    text = re.sub(r'[^\w\u4e00-\u9fff\s-]', '', text)
    text = re.sub(r'[-\s]+', '-', text)
    return text[:80] or str(uuid.uuid4())[:8]


def _normalize_cover_image(value: str) -> str:
    """Store static image filenames, not already-built /static/... URLs."""
    value = str(value or '').strip()
    if not value:
        return ''
    parsed = urlparse(value)
    if parsed.scheme and parsed.netloc:
        value = parsed.path
    value = value.lstrip('/')
    if value.startswith('static/'):
        value = value[len('static/'):]
    return value


def _article_from_row(row):
    article = dict(row) if row else None
    if article and 'cover_image' in article:
        article['cover_image'] = _normalize_cover_image(article.get('cover_image'))
    return article


def render_md(text):
    return md_lib.markdown(
        text,
        extensions=['fenced_code', 'codehilite', 'tables', 'toc', 'nl2br',
                    'pymdownx.arithmatex'],
        extension_configs={
            'codehilite': {'css_class': 'highlight'},
            'pymdownx.arithmatex': {'generic': True},
        },
    )


def get_article_meta(slug, published_only=True):
    conn = get_db()
    if published_only:
        row = conn.execute(
            "SELECT * FROM articles WHERE slug=? AND published=1", (slug,)
        ).fetchone()
    else:
        row = conn.execute("SELECT * FROM articles WHERE slug=?", (slug,)).fetchone()
    return _article_from_row(row)


def read_article_file(slug):
    path = Path(config.ARTICLES_DIR) / f"{slug}.md"
    if not path.exists():
        return None
    return path.read_text(encoding='utf-8')


def write_article_file(slug, content):
    path = Path(config.ARTICLES_DIR) / f"{slug}.md"
    path.write_text(content, encoding='utf-8')


def delete_article_file(slug):
    path = Path(config.ARTICLES_DIR) / f"{slug}.md"
    if path.exists():
        path.unlink()


def _plain_excerpt(markdown_text: str, limit: int = 112) -> str:
    """Build a compact text teaser from markdown content."""
    text = str(markdown_text or '')
    text = re.sub(r'```.*?```', ' ', text, flags=re.S)
    text = re.sub(r'`([^`]*)`', r'\1', text)
    text = re.sub(r'!\[[^\]]*\]\([^)]+\)', ' ', text)
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'^[#>\-\*\+\d\.\)\s]+', '', text, flags=re.M)
    text = re.sub(r'[*_~>#\[\]()]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip('，。,.、；;：: ') + '…'


def _configured_featured_slugs(value) -> list[str]:
    slugs = []
    for item in value or []:
        if isinstance(item, str):
            slug = item.strip()
        elif isinstance(item, dict):
            slug = str(item.get('slug') or '').strip()
        else:
            continue
        if slug and slug not in slugs:
            slugs.append(slug)
    return slugs


def _feature_article_from_row(row, summary_limit: int = 112, allow_empty: bool = False):
    article = _article_from_row(row)
    if not article:
        return None
    content = read_article_file(article['slug'])
    word_count = _count_words(content) if content else 0
    if word_count <= 0 and not allow_empty:
        return None
    article['current_word_count'] = word_count
    article['summary'] = _plain_excerpt(content, summary_limit) if content else ''
    if not article['summary']:
        article['summary'] = '暂无摘要'
    return article


def list_featured_articles(configured=None, limit: int = 5) -> list[dict]:
    """Return homepage featured articles, honoring configured slugs first."""
    limit = max(1, int(limit or 5))
    conn = get_db()
    result = []
    seen = set()

    for slug in _configured_featured_slugs(configured):
        row = conn.execute(
            "SELECT * FROM articles WHERE slug=? AND published=1",
            (slug,),
        ).fetchone()
        article = _feature_article_from_row(row, allow_empty=True)
        if not article or article['slug'] in seen:
            continue
        seen.add(article['slug'])
        result.append(article)
        if len(result) >= limit:
            return result

    rows = conn.execute(
        """
        SELECT * FROM articles
        WHERE published=1 AND COALESCE(word_count, 0) > 0
        ORDER BY
          CASE WHEN cover_image IS NOT NULL AND TRIM(cover_image) != '' THEN 0 ELSE 1 END,
          created_at DESC
        LIMIT ?
        """,
        (limit * 3,),
    ).fetchall()
    for row in rows:
        article = _feature_article_from_row(row)
        if not article or article['slug'] in seen:
            continue
        seen.add(article['slug'])
        result.append(article)
        if len(result) >= limit:
            break
    return result


def create_article_draft(title: str, tags: str, content: str, cover_image: str = '', cover_alt: str = '') -> dict:
    """Create a draft article and its markdown file as one service operation."""
    title = str(title or '').strip()
    tags = str(tags or '').strip()
    content = str(content or '').strip()
    cover_image = _normalize_cover_image(cover_image)
    cover_alt = str(cover_alt or '').strip()
    if not title or not content:
        raise ValueError('标题和内容不能为空')
    word_count = _count_words(content)
    if word_count <= 0:
        raise ValueError('正文至少需要包含文字')

    base_slug = slugify(title)
    now = datetime.now().isoformat()
    conn = get_db()
    slug = base_slug
    for attempt in range(8):
        try:
            conn.execute(
                """
                INSERT INTO articles (slug, title, tags, created_at, updated_at, published, word_count, cover_image, cover_alt)
                VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?)
                """,
                (slug, title, tags, now, now, word_count, cover_image, cover_alt),
            )
            conn.commit()
            break
        except sqlite3.IntegrityError:
            if attempt == 7:
                raise
            slug = f"{base_slug}-{uuid.uuid4().hex[:4]}"
    try:
        write_article_file(slug, content)
    except Exception:
        conn.execute("DELETE FROM articles WHERE slug=?", (slug,))
        conn.commit()
        raise
    return get_article_meta(slug, published_only=False)


def update_article(slug: str, title: str, tags: str, content: str, cover_image: str = '', cover_alt: str = '') -> dict:
    """Update article metadata and markdown content."""
    article = get_article_meta(slug, published_only=False)
    if not article:
        raise LookupError('文章不存在')
    title = str(title or '').strip()
    tags = str(tags or '').strip()
    content = str(content or '').strip()
    cover_image = _normalize_cover_image(cover_image)
    cover_alt = str(cover_alt or '').strip()
    if not title or not content:
        raise ValueError('标题和内容不能为空')
    word_count = _count_words(content)
    if word_count <= 0:
        raise ValueError('正文至少需要包含文字')

    now = datetime.now().isoformat()
    conn = get_db()
    conn.execute(
        "UPDATE articles SET title=?, tags=?, updated_at=?, word_count=?, cover_image=?, cover_alt=? WHERE slug=?",
        (title, tags, now, word_count, cover_image, cover_alt, slug),
    )
    conn.commit()
    write_article_file(slug, content)
    return get_article_meta(slug, published_only=False)


def delete_article(slug: str) -> None:
    """Delete an article row and its markdown file."""
    conn = get_db()
    conn.execute("DELETE FROM articles WHERE slug=?", (slug,))
    conn.commit()
    delete_article_file(slug)


def list_all_tags():
    all_tags = set()
    conn = get_db()
    for article in conn.execute("SELECT tags FROM articles WHERE published=1").fetchall():
        for tag in (article['tags'] or '').split(','):
            tag = tag.strip()
            if tag:
                all_tags.add(tag)
    return sorted(all_tags)


def list_all_tags_admin():
    """Return all tags from ALL articles (including drafts), for admin hero config."""
    all_tags = set()
    conn = get_db()
    for article in conn.execute("SELECT tags FROM articles").fetchall():
        for tag in (article['tags'] or '').split(','):
            tag = tag.strip()
            if tag:
                all_tags.add(tag)
    return sorted(all_tags)


def list_published_articles(page=1, tag=''):
    conn = get_db()
    if tag:
        rows = conn.execute(
            "SELECT * FROM articles WHERE published=1 AND tags LIKE ? ORDER BY created_at DESC",
            (f'%{tag}%',)
        ).fetchall()
        total = len(rows)
        start = (page - 1) * config.ARTICLES_PER_PAGE
        end = page * config.ARTICLES_PER_PAGE
        rows = rows[start:end]
    else:
        total = conn.execute("SELECT COUNT(*) FROM articles WHERE published=1").fetchone()[0]
        rows = conn.execute(
            "SELECT * FROM articles WHERE published=1 ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (config.ARTICLES_PER_PAGE, (page - 1) * config.ARTICLES_PER_PAGE)
        ).fetchall()
    result = []
    for row in rows:
        article = _article_from_row(row)
        content = read_article_file(article['slug'])
        article['current_word_count'] = _count_words(content) if content else 0
        result.append(article)
    return result, total


def list_admin_articles():
    """Return published articles for admin dashboard, newest first."""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM articles WHERE published=1 ORDER BY created_at DESC"
    ).fetchall()
    return [_article_from_row(row) for row in rows]


def list_drafts():
    """Return draft articles (published=0), newest first."""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM articles WHERE published=0 ORDER BY created_at DESC"
    ).fetchall()
    return [_article_from_row(row) for row in rows]


def publish_article(slug):
    """Set article to published=1."""
    article = get_article_meta(slug, published_only=False)
    if not article:
        raise LookupError('文章不存在')
    content = read_article_file(slug)
    if content is None or _count_words(content) <= 0:
        raise ValueError('正文至少需要包含文字后才能发布')
    conn = get_db()
    conn.execute("UPDATE articles SET published=1, updated_at=? WHERE slug=?", 
                 (datetime.now().isoformat(), slug))
    conn.commit()
