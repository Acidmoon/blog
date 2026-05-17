import re
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
