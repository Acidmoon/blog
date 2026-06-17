import re
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

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
    return dict(row) if row else None


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


def create_article_draft(title: str, tags: str, content: str) -> dict:
    """Create a draft article and its markdown file as one service operation."""
    title = str(title or '').strip()
    tags = str(tags or '').strip()
    content = str(content or '').strip()
    if not title or not content:
        raise ValueError('标题和内容不能为空')

    base_slug = slugify(title)
    now = datetime.now().isoformat()
    word_count = _count_words(content)
    conn = get_db()
    slug = base_slug
    for attempt in range(8):
        try:
            conn.execute(
                """
                INSERT INTO articles (slug, title, tags, created_at, updated_at, published, word_count)
                VALUES (?, ?, ?, ?, ?, 0, ?)
                """,
                (slug, title, tags, now, now, word_count),
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


def update_article(slug: str, title: str, tags: str, content: str) -> dict:
    """Update article metadata and markdown content."""
    article = get_article_meta(slug, published_only=False)
    if not article:
        raise LookupError('文章不存在')
    title = str(title or '').strip()
    tags = str(tags or '').strip()
    content = str(content or '').strip()
    if not title or not content:
        raise ValueError('标题和内容不能为空')

    now = datetime.now().isoformat()
    conn = get_db()
    conn.execute(
        "UPDATE articles SET title=?, tags=?, updated_at=?, word_count=? WHERE slug=?",
        (title, tags, now, _count_words(content), slug),
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
        article = dict(row)
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
    return [dict(row) for row in rows]


def list_drafts():
    """Return draft articles (published=0), newest first."""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM articles WHERE published=0 ORDER BY created_at DESC"
    ).fetchall()
    return [dict(row) for row in rows]


def publish_article(slug):
    """Set article to published=1."""
    conn = get_db()
    conn.execute("UPDATE articles SET published=1, updated_at=? WHERE slug=?", 
                 (datetime.now().isoformat(), slug))
    conn.commit()
