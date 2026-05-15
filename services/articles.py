import re
import uuid
from pathlib import Path

import markdown as md_lib

import config
from models import get_db


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
    conn.close()
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
    conn.close()
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
    conn.close()
    return [dict(row) for row in rows], total


def list_admin_articles():
    conn = get_db()
    rows = conn.execute("SELECT * FROM articles ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(row) for row in rows]
