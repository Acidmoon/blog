import logging
import os
import re
import sqlite3
import tempfile
import threading
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import bleach
import markdown as md_lib

import config
from models import get_db
from services.article_events import record_article_activity
from services.article_index import delete_article_search, sync_article_search
from services.tagging import normalize_tag_filter, normalize_tags, serialize_tags


_ARTICLE_LOCK = threading.RLock()
_CONTENT_KEY_PATTERN = re.compile(r'^[0-9a-f]{32}$')
logger = logging.getLogger(__name__)


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
    """Keep stored cover references relative to Flask's static directory."""
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


_MARKDOWN_ALLOWED_TAGS = {
    'a', 'b', 'blockquote', 'br', 'code', 'del', 'div', 'em', 'h1', 'h2',
    'h3', 'h4', 'h5', 'h6', 'hr', 'i', 'img', 'li', 'ol', 'p', 'pre',
    's', 'span', 'strong', 'sub', 'sup', 'table', 'tbody', 'td', 'th',
    'thead', 'tr', 'ul',
}
_MARKDOWN_ALLOWED_ATTRIBUTES = {
    '*': {'class'},
    'a': {'href', 'title'},
    'code': {'class'},
    'h1': {'id'},
    'h2': {'id'},
    'h3': {'id'},
    'h4': {'id'},
    'h5': {'id'},
    'h6': {'id'},
    'img': {'src', 'alt', 'title'},
}
_MARKDOWN_ALLOWED_PROTOCOLS = {'http', 'https', 'mailto'}


def render_md(text: str) -> str:
    """Render Markdown into HTML that is safe to insert into trusted templates."""
    rendered = md_lib.markdown(
        str(text or ''),
        extensions=['fenced_code', 'codehilite', 'tables', 'toc', 'nl2br',
                    'pymdownx.arithmatex'],
        extension_configs={
            'codehilite': {'css_class': 'highlight'},
            'pymdownx.arithmatex': {'generic': True},
        },
    )
    return bleach.clean(
        rendered,
        tags=_MARKDOWN_ALLOWED_TAGS,
        attributes=_MARKDOWN_ALLOWED_ATTRIBUTES,
        protocols=_MARKDOWN_ALLOWED_PROTOCOLS,
        strip=True,
        strip_comments=True,
    )


def get_article_meta(slug, published_only=True):
    conn = get_db()
    if published_only:
        row = conn.execute(
            "SELECT * FROM articles WHERE slug=? AND published=1", (slug,)
        ).fetchone()
    else:
        row = conn.execute("SELECT * FROM articles WHERE slug=?", (slug,)).fetchone()
    article = dict(row) if row else None
    if article and 'cover_image' in article:
        article['cover_image'] = _normalize_cover_image(article.get('cover_image'))
    return article


def _plain_excerpt(markdown_text: str, limit: int = 112) -> str:
    """Build the compact copy used by the remote featured-article carousel."""
    text = str(markdown_text or '')
    text = re.sub(r'```.*?```', ' ', text, flags=re.S)
    text = re.sub(r'`([^`]*)`', r'\1', text)
    text = re.sub(r'!\[[^\]]*\]\([^)]+\)', ' ', text)
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'^[#>\-\*\+\d\.\)\s]+', '', text, flags=re.M)
    text = re.sub(r'[*_~>#\[\]()]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text if len(text) <= limit else text[:limit].rstrip('，。,.、；;：: ') + '…'


def list_featured_articles(configured=None, limit: int = 5) -> list[dict]:
    """Return the configured remote-carousel articles with safe body lookups."""
    limit = max(1, int(limit or 5))
    requested = []
    for item in configured or []:
        slug = item.strip() if isinstance(item, str) else str((item or {}).get('slug') or '').strip()
        if slug and slug not in requested:
            requested.append(slug)

    conn = get_db()
    rows = []
    seen = set()
    for slug in requested:
        row = conn.execute('SELECT * FROM articles WHERE slug=? AND published=1', (slug,)).fetchone()
        if row:
            rows.append(row)
            seen.add(slug)
        if len(rows) >= limit:
            break
    if len(rows) < limit:
        candidates = conn.execute(
            """
            SELECT * FROM articles WHERE published=1 AND COALESCE(word_count, 0) > 0
            ORDER BY CASE WHEN TRIM(COALESCE(cover_image, '')) != '' THEN 0 ELSE 1 END, created_at DESC
            LIMIT ?
            """,
            (limit * 3,),
        ).fetchall()
        rows.extend(row for row in candidates if row['slug'] not in seen)

    featured = []
    for row in rows:
        article = dict(row)
        article['cover_image'] = _normalize_cover_image(article.get('cover_image'))
        content = read_article_file(article['slug'], article.get('content_key', '')) or ''
        article['current_word_count'] = _count_words(content)
        article['summary'] = _plain_excerpt(content) or '暂无摘要'
        featured.append(article)
        if len(featured) >= limit:
            break
    return featured


def _replace_article_tags(conn, article_id: int, tags: list[str]) -> None:
    """Keep the normalized relation synchronized with the compatibility field."""
    conn.execute('DELETE FROM article_tags WHERE article_id=?', (article_id,))
    conn.executemany(
        'INSERT INTO article_tags (article_id, tag) VALUES (?, ?)',
        [(article_id, tag) for tag in tags],
    )


def _articles_directory() -> Path:
    """Return the resolved article directory and create it when first needed."""
    directory = Path(config.ARTICLES_DIR).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _validate_slug(slug: str) -> str:
    """Reject path-like legacy slugs before they can address article files."""
    normalized = str(slug or '').strip()
    if not normalized or '\x00' in normalized or '/' in normalized or '\\' in normalized:
        raise ValueError('文章标识无效')
    return normalized


def _legacy_article_path(slug: str) -> Path:
    directory = _articles_directory()
    path = (directory / f'{_validate_slug(slug)}.md').resolve()
    try:
        path.relative_to(directory)
    except ValueError as exc:
        raise ValueError('文章标识无效') from exc
    return path


def _content_path(content_key: str) -> Path:
    key = str(content_key or '').strip().lower()
    if not _CONTENT_KEY_PATTERN.fullmatch(key):
        raise ValueError('文章正文版本无效')
    return _articles_directory() / f'{key}.md'


def _sync_directory(directory: Path) -> None:
    """Persist directory metadata on POSIX after replacing or removing a file."""
    if os.name == 'nt':
        return
    try:
        descriptor = os.open(str(directory), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def _atomic_write_text(path: Path, content: str) -> None:
    """Write fully flushed UTF-8 content, then atomically publish it at ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f'.{path.name}.',
        suffix='.tmp',
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8', newline='') as handle:
            handle.write(str(content))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        _sync_directory(path.parent)
    finally:
        if temporary_path.exists():
            try:
                temporary_path.unlink()
            except OSError as exc:
                logger.warning('无法清理文章临时文件 %s：%s', temporary_path.name, exc)


def _remove_file(path: Path) -> None:
    """Remove a file if present and persist the directory change."""
    try:
        path.unlink()
    except FileNotFoundError:
        return
    _sync_directory(path.parent)


def _begin_article_transaction(conn) -> None:
    """Acquire SQLite's writer lock and release it if transaction setup fails."""
    started_transaction = False
    try:
        if not conn.in_transaction:
            conn.execute('BEGIN IMMEDIATE')
            started_transaction = True
    except Exception:
        if started_transaction:
            conn.rollback()
        raise


def _discard_unreferenced_content(conn, content_key: str) -> None:
    """Delete a failed write only when no committed article points at it."""
    try:
        referenced = conn.execute(
            'SELECT 1 FROM articles WHERE content_key=?',
            (content_key,),
        ).fetchone()
    except sqlite3.Error:
        return
    if referenced is None:
        try:
            _remove_file(_content_path(content_key))
        except OSError as exc:
            logger.warning('无法清理未引用文章版本 %s：%s', content_key, exc)


def read_article_file(slug: str, content_key: str | None = None) -> str | None:
    """Read a committed body, querying the current key only when none is supplied."""
    if content_key is None:
        row = get_db().execute(
            'SELECT content_key FROM articles WHERE slug=?',
            (slug,),
        ).fetchone()
        content_key = row['content_key'] if row else ''
    try:
        path = _content_path(content_key) if content_key else _legacy_article_path(slug)
    except ValueError:
        return None
    if not path.exists():
        return None
    return path.read_text(encoding='utf-8')


def write_article_file(slug: str, content: str, *, content_key: str = '') -> None:
    """Atomically write a legacy body or a new immutable content version."""
    path = _content_path(content_key) if content_key else _legacy_article_path(slug)
    _atomic_write_text(path, content)


def delete_article_file(slug: str, *, content_key: str = '') -> None:
    """Remove an explicit article body file when an offline cleanup job requests it."""
    path = _content_path(content_key) if content_key else _legacy_article_path(slug)
    _remove_file(path)


def create_article_draft(
    title: str,
    tags: str,
    content: str,
    cover_image: str = '',
    cover_alt: str = '',
) -> dict:
    """Create metadata and a new immutable Markdown version in one operation."""
    title = str(title or '').strip()
    content = str(content or '').strip()
    if not title or not content:
        raise ValueError('标题和内容不能为空')
    normalized_tags = normalize_tags(tags)
    tags = serialize_tags(normalized_tags)
    cover_image = _normalize_cover_image(cover_image)
    cover_alt = str(cover_alt or '').strip()

    base_slug = slugify(title)
    now = datetime.now().isoformat()
    word_count = _count_words(content)
    conn = get_db()
    slug = base_slug
    with _ARTICLE_LOCK:
        for attempt in range(8):
            content_key = uuid.uuid4().hex
            _begin_article_transaction(conn)
            if conn.execute('SELECT 1 FROM articles WHERE slug=?', (slug,)).fetchone():
                conn.rollback()
                if attempt == 7:
                    raise sqlite3.IntegrityError('文章标识已存在')
                slug = f'{base_slug}-{uuid.uuid4().hex[:4]}'
                continue

            try:
                write_article_file(slug, content, content_key=content_key)
                article_cursor = conn.execute(
                    """
                    INSERT INTO articles (
                        slug, title, tags, created_at, updated_at, published, word_count, content_key,
                        cover_image, cover_alt
                    )
                    VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, ?)
                    """,
                    (slug, title, tags, now, now, word_count, content_key, cover_image, cover_alt),
                )
                _replace_article_tags(conn, article_cursor.lastrowid, normalized_tags)
                sync_article_search(conn, article_cursor.lastrowid, title, tags, content)
                record_article_activity(
                    conn,
                    article_cursor.lastrowid,
                    'created',
                    now,
                    word_delta=word_count,
                    visible=False,
                )
                conn.commit()
            except sqlite3.IntegrityError:
                conn.rollback()
                _discard_unreferenced_content(conn, content_key)
                if attempt == 7:
                    raise
                slug = f'{base_slug}-{uuid.uuid4().hex[:4]}'
                continue
            except Exception:
                conn.rollback()
                _discard_unreferenced_content(conn, content_key)
                raise
            else:
                break
    return get_article_meta(slug, published_only=False)


def update_article(
    slug: str,
    title: str,
    tags: str,
    content: str,
    cover_image: str = '',
    cover_alt: str = '',
) -> dict:
    """Publish a new body version and atomically point metadata at that version."""
    title = str(title or '').strip()
    content = str(content or '').strip()
    if not title or not content:
        raise ValueError('标题和内容不能为空')
    normalized_tags = normalize_tags(tags)
    tags = serialize_tags(normalized_tags)
    cover_image = _normalize_cover_image(cover_image)
    cover_alt = str(cover_alt or '').strip()

    now = datetime.now().isoformat()
    conn = get_db()
    with _ARTICLE_LOCK:
        _begin_article_transaction(conn)
        article = conn.execute(
            'SELECT id, published, word_count FROM articles WHERE slug=?',
            (slug,),
        ).fetchone()
        if not article:
            conn.rollback()
            raise LookupError('文章不存在')

        content_key = uuid.uuid4().hex
        try:
            write_article_file(slug, content, content_key=content_key)
            new_word_count = _count_words(content)
            conn.execute(
                '''
                UPDATE articles
                SET title=?, tags=?, updated_at=?, word_count=?, content_key=?, cover_image=?, cover_alt=?
                WHERE slug=?
                ''',
                (title, tags, now, new_word_count, content_key, cover_image, cover_alt, slug),
            )
            _replace_article_tags(conn, article['id'], normalized_tags)
            sync_article_search(conn, article['id'], title, tags, content)
            record_article_activity(
                conn,
                article['id'],
                'updated',
                now,
                word_delta=new_word_count - int(article['word_count'] or 0),
                visible=bool(article['published']),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            _discard_unreferenced_content(conn, content_key)
            raise
    return get_article_meta(slug, published_only=False)


def delete_article(slug: str) -> None:
    """Delete metadata while retaining immutable files for concurrent readers."""
    conn = get_db()
    with _ARTICLE_LOCK:
        _begin_article_transaction(conn)
        try:
            article = conn.execute('SELECT id FROM articles WHERE slug=?', (slug,)).fetchone()
            if article:
                delete_article_search(conn, article['id'])
            conn.execute('DELETE FROM articles WHERE slug=?', (slug,))
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def list_all_tags():
    conn = get_db()
    rows = conn.execute(
        '''
        SELECT DISTINCT article_tags.tag
        FROM article_tags
        JOIN articles ON articles.id = article_tags.article_id
        WHERE articles.published=1
        ORDER BY article_tags.tag COLLATE NOCASE
        '''
    ).fetchall()
    return [row['tag'] for row in rows]


def list_all_tags_admin():
    """Return all tags from ALL articles (including drafts), for admin hero config."""
    conn = get_db()
    rows = conn.execute(
        'SELECT DISTINCT tag FROM article_tags ORDER BY tag COLLATE NOCASE'
    ).fetchall()
    return [row['tag'] for row in rows]


def list_published_articles(page=1, tag=''):
    conn = get_db()
    raw_tag = str(tag or '').strip()
    if raw_tag:
        try:
            tag_filter = normalize_tag_filter(raw_tag)
        except ValueError:
            return [], 0
        if not tag_filter:
            return [], 0
        rows = conn.execute(
            '''
            SELECT articles.*
            FROM articles
            JOIN article_tags ON article_tags.article_id = articles.id
            WHERE articles.published=1 AND article_tags.tag=? COLLATE NOCASE
            ORDER BY articles.created_at DESC
            LIMIT ? OFFSET ?
            ''',
            (tag_filter, config.ARTICLES_PER_PAGE, (page - 1) * config.ARTICLES_PER_PAGE),
        ).fetchall()
        total = conn.execute(
            '''
            SELECT COUNT(*)
            FROM articles
            JOIN article_tags ON article_tags.article_id = articles.id
            WHERE articles.published=1 AND article_tags.tag=? COLLATE NOCASE
            ''',
            (tag_filter,),
        ).fetchone()[0]
    else:
        total = conn.execute("SELECT COUNT(*) FROM articles WHERE published=1").fetchone()[0]
        rows = conn.execute(
            "SELECT * FROM articles WHERE published=1 ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (config.ARTICLES_PER_PAGE, (page - 1) * config.ARTICLES_PER_PAGE)
        ).fetchall()
    result = []
    for row in rows:
        article = dict(row)
        content = read_article_file(article['slug'], article.get('content_key', ''))
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
    with _ARTICLE_LOCK:
        _begin_article_transaction(conn)
        try:
            article = conn.execute(
                'SELECT id, published FROM articles WHERE slug=?',
                (slug,),
            ).fetchone()
            if article is None:
                conn.rollback()
                raise LookupError('文章不存在')
            now = datetime.now().isoformat()
            conn.execute(
                'UPDATE articles SET published=1, updated_at=? WHERE slug=?',
                (now, slug),
            )
            if not article['published']:
                record_article_activity(
                    conn,
                    article['id'],
                    'published',
                    now,
                    visible=True,
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
