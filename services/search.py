import html
import re
import argparse

from models import get_db
from services.article_index import article_search_terms, sync_article_search
from services.articles import _count_words, read_article_file


MAX_SEARCH_QUERY_LENGTH = 200


def highlight_text(text, query):
    """Escape untrusted text, then wrap matching fragments in controlled markup."""
    source = str(text or '')
    needle = str(query or '')
    if not needle:
        return html.escape(source)

    pattern = re.compile(re.escape(needle), re.IGNORECASE)
    parts = []
    cursor = 0
    for match in pattern.finditer(source):
        parts.append(html.escape(source[cursor:match.start()]))
        parts.append(f'<mark>{html.escape(match.group(0))}</mark>')
        cursor = match.end()
    parts.append(html.escape(source[cursor:]))
    return ''.join(parts)


def _validate_search_query(query: object) -> str:
    """Normalize bounded user text before it is used in an FTS phrase query."""
    query = str(query or '').strip()
    if not query:
        return ''
    if len(query) > MAX_SEARCH_QUERY_LENGTH:
        raise ValueError(f'搜索词不能超过 {MAX_SEARCH_QUERY_LENGTH} 个字符')
    return query


def _fts_phrase(query: str) -> str | None:
    """Use a literal phrase so search punctuation never becomes FTS syntax."""
    terms = article_search_terms(query)
    if not terms:
        return None
    return '"' + ' '.join(terms).replace('"', '""') + '"'


def _search_index_counts(conn) -> tuple[int, int]:
    """Return source/index counts used to detect an initial or interrupted build."""
    article_count = int(conn.execute('SELECT COUNT(*) FROM articles').fetchone()[0])
    index_count = int(conn.execute('SELECT COUNT(*) FROM article_search').fetchone()[0])
    return article_count, index_count


def ensure_article_search_index() -> dict[str, int] | None:
    """Backfill legacy article bodies once, then keep future writes incremental.

    Article create/update/delete flows call ``sync_article_search`` in their own
    transactions. This function only rebuilds when an older database has no
    matching number of FTS rows, and rechecks after taking the writer lock.
    """
    conn = get_db()
    article_count, index_count = _search_index_counts(conn)
    if article_count == index_count:
        return
    if conn.in_transaction:
        raise RuntimeError('无法在现有事务中重建文章搜索索引')
    conn.execute('BEGIN IMMEDIATE')
    try:
        # Another worker may have completed the initial backfill while this
        # worker waited for the lock, so recheck before deleting FTS rows.
        article_count, index_count = _search_index_counts(conn)
        if article_count != index_count:
            indexed = _rebuild_article_search_index_in_transaction(conn)
        else:
            indexed = index_count
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return {'articles': article_count, 'indexed': indexed}


def _rebuild_article_search_index_in_transaction(conn) -> int:
    """Replace FTS rows while the caller already owns a SQLite write lock."""
    conn.execute('DELETE FROM article_search')
    rows = conn.execute('SELECT id, slug, content_key, title, tags FROM articles').fetchall()
    for row in rows:
        content = read_article_file(row['slug'], row['content_key']) or ''
        sync_article_search(conn, row['id'], row['title'], row['tags'], content)
    return len(rows)


def rebuild_article_search_index() -> dict[str, int]:
    """Rebuild all FTS rows from committed article bodies in one transaction."""
    conn = get_db()
    if conn.in_transaction:
        raise RuntimeError('无法在现有事务中重建文章搜索索引')
    conn.execute('BEGIN IMMEDIATE')
    try:
        indexed = _rebuild_article_search_index_in_transaction(conn)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return {'articles': indexed, 'indexed': indexed}


def _matching_rows(query: str, *, limit: int, offset: int):
    """Query FTS first and read Markdown only for the requested result page."""
    ensure_article_search_index()
    conn = get_db()
    phrase = _fts_phrase(query)
    if phrase is None:
        # A punctuation-only search has no FTS token. Keep a bounded metadata
        # fallback rather than reading every Markdown file just to search symbols.
        pattern = query.lower()
        total = int(
            conn.execute(
                """
                SELECT COUNT(*) FROM articles
                WHERE published=1
                  AND (instr(lower(title), ?) > 0 OR instr(lower(tags), ?) > 0)
                """,
                (pattern, pattern),
            ).fetchone()[0]
        )
        rows = conn.execute(
            """
            SELECT articles.*, CASE WHEN instr(lower(title), ?) > 0 THEN 1 ELSE 0 END AS title_match
            FROM articles
            WHERE published=1
              AND (instr(lower(title), ?) > 0 OR instr(lower(tags), ?) > 0)
            ORDER BY title_match DESC, created_at DESC
            LIMIT ? OFFSET ?
            """,
            (pattern, pattern, pattern, limit, offset),
        ).fetchall()
        return rows, total
    total = int(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM articles
            JOIN article_search ON article_search.article_id = articles.id
            WHERE articles.published=1 AND article_search MATCH ?
            """,
            (phrase,),
        ).fetchone()[0]
    )
    rows = conn.execute(
        """
        SELECT articles.*,
               CASE WHEN instr(lower(articles.title), lower(?)) > 0 THEN 1 ELSE 0 END AS title_match
        FROM articles
        JOIN article_search ON article_search.article_id = articles.id
        WHERE articles.published=1 AND article_search MATCH ?
        ORDER BY title_match DESC, articles.created_at DESC
        LIMIT ? OFFSET ?
        """,
        (query, phrase, limit, offset),
    ).fetchall()
    return rows, total


def _render_search_result(row, query: str):
    """Create safe presentation fragments from one FTS-matched article row."""
    q = query.lower()
    article = dict(row)
    title_match = q in article['title'].lower()
    tag_match = q in (article['tags'] or '').lower()
    content = read_article_file(article['slug'], article.get('content_key', ''))
    article['current_word_count'] = _count_words(content) if content else 0
    content_match = bool(content) and q in content.lower()
    snippet = ''
    if content_match and content:
        idx = content.lower().find(q)
        start = max(0, idx - 60)
        end = min(len(content), idx + len(q) + 120)
        snippet = content[start:end].strip()
        if start > 0:
            snippet = '…' + snippet
        if end < len(content):
            snippet = snippet + '…'
        snippet = highlight_text(snippet, query)
    elif tag_match:
        snippet = f'标签包含「{html.escape(query)}」'
    else:
        snippet = '标题匹配'
    title_html = highlight_text(article['title'], query)
    return article, snippet, title_html, title_match


def search_articles_page(query: object, *, page: int, per_page: int) -> tuple[list[tuple], int]:
    """Return one bounded page and a total without scanning every Markdown body."""
    normalized_query = _validate_search_query(query)
    if not normalized_query:
        return [], 0
    rows, total = _matching_rows(
        normalized_query,
        limit=per_page,
        offset=(page - 1) * per_page,
    )
    return [_render_search_result(row, normalized_query) for row in rows], total


def search_articles(query):
    """Compatibility helper for internal callers that need all matched rows.

    Public routes use ``search_articles_page`` so normal requests never expand
    all article bodies merely to render a first page.
    """
    normalized_query = _validate_search_query(query)
    if not normalized_query:
        return []
    rows, _ = _matching_rows(normalized_query, limit=100_000, offset=0)
    return [_render_search_result(row, normalized_query) for row in rows]


def main() -> int:
    """Offer an explicit offline-safe command for rebuilding derived FTS data."""
    parser = argparse.ArgumentParser(description='重建博客文章全文搜索索引')
    parser.add_argument('--rebuild', action='store_true', help='从已提交文章正文重建 FTS 索引')
    args = parser.parse_args()
    if not args.rebuild:
        parser.error('请指定 --rebuild')
    from models import init_db

    config.ensure_directories()
    init_db()
    report = rebuild_article_search_index()
    print(f"indexed={report['indexed']} articles={report['articles']}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
