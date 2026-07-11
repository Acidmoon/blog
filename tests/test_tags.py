"""Exact normalized tag behavior and legacy migration coverage."""

from __future__ import annotations

import sqlite3
import uuid
from urllib.parse import quote

import config
from flask import render_template
from models import get_db, init_db
from services import articles
from services.search import search_articles
from services.tagging import MAX_TAG_LENGTH, MAX_TAGS_PER_ARTICLE


def _new_published_article(title_prefix: str, tags: str) -> dict:
    """Create a unique published article for tag-query assertions."""
    article = articles.create_article_draft(
        f'{title_prefix}-{uuid.uuid4().hex[:8]}',
        tags,
        '标签测试正文',
    )
    articles.publish_article(article['slug'])
    return articles.get_article_meta(article['slug'], published_only=False)


def _remove_article(article: dict) -> None:
    """Remove test metadata and the immutable body produced for it."""
    articles.delete_article(article['slug'])
    articles.delete_article_file(article['slug'], content_key=article['content_key'])


SPECIAL_URL_TAGS = ('R&D', 'C#', '100%', '两个 单词')


def _assert_tag_urls_are_encoded(html: str) -> None:
    """Assert every special tag appears as a one-parameter-safe link."""
    for tag in SPECIAL_URL_TAGS:
        encoded_tag = quote(tag, safe='')
        assert f'href="/?tag={encoded_tag}"' in html


def test_tag_filter_is_exact_and_handles_sql_wildcard_characters(app):
    """Tag filters use normalized equality rather than a user-controlled LIKE pattern."""
    with app.app_context():
        ai_article = _new_published_article('精确AI', 'AI, Python, AI')
        aigc_article = _new_published_article('相近AIGC', 'AIGC')
        percent_article = _new_published_article('百分号', '100%')
        try:
            ai_results, ai_total = articles.list_published_articles(tag='AI')
            percent_results, percent_total = articles.list_published_articles(tag='100%')

            assert ai_total == 1
            assert [article['slug'] for article in ai_results] == [ai_article['slug']]
            assert percent_total == 1
            assert [article['slug'] for article in percent_results] == [percent_article['slug']]
            assert {'AI', 'Python', 'AIGC', '100%'} <= set(articles.list_all_tags())
        finally:
            _remove_article(ai_article)
            _remove_article(aigc_article)
            _remove_article(percent_article)


def test_update_replaces_the_normalized_tag_relation(app):
    """Editing tags updates both the compatibility string and indexed relation together."""
    with app.app_context():
        article = _new_published_article('标签更新', '旧标签, 重复, 重复')
        old_key = article['content_key']
        updated = articles.update_article(article['slug'], article['title'], '新标签, 新标签', '更新正文')
        try:
            old_results, old_total = articles.list_published_articles(tag='旧标签')
            new_results, new_total = articles.list_published_articles(tag='新标签')

            assert updated['tags'] == '新标签'
            assert old_total == 0
            assert old_results == []
            assert new_total == 1
            assert [item['slug'] for item in new_results] == [article['slug']]
        finally:
            articles.delete_article(article['slug'])
            articles.delete_article_file(article['slug'], content_key=old_key)
            articles.delete_article_file(article['slug'], content_key=updated['content_key'])


def test_tag_links_encode_reserved_query_characters(client, app):
    """Every rendered tag link preserves reserved characters as one tag value."""
    with app.app_context():
        article = _new_published_article('特殊标签链接', ', '.join(SPECIAL_URL_TAGS))
    try:
        home_response = client.get('/')
        article_response = client.get(f"/article/{article['slug']}")
        search_response = client.get('/search', query_string={'q': article['title']})

        assert home_response.status_code == 200
        assert article_response.status_code == 200
        assert search_response.status_code == 200
        _assert_tag_urls_are_encoded(home_response.get_data(as_text=True))
        _assert_tag_urls_are_encoded(article_response.get_data(as_text=True))
        _assert_tag_urls_are_encoded(search_response.get_data(as_text=True))

        for tag in SPECIAL_URL_TAGS:
            filtered_response = client.get('/', query_string={'tag': tag})
            assert filtered_response.status_code == 200
            assert article['title'] in filtered_response.get_data(as_text=True)

        with app.app_context():
            for tag in SPECIAL_URL_TAGS:
                pagination_html = render_template(
                    'home_sections/pagination.html',
                    page=1,
                    total_pages=2,
                    current_tag=tag,
                )
                assert f'?page=2&tag={quote(tag, safe="")}' in pagination_html
    finally:
        with app.app_context():
            _remove_article(article)


def test_init_db_rebuilds_legacy_tag_relations_deterministically(tmp_path, monkeypatch):
    """Migration keeps valid legacy tags and removes stale relation rows."""
    database_path = tmp_path / 'legacy-tags.db'
    oversized_tag = 'x' * (MAX_TAG_LENGTH + 1)
    too_many_tags = ', '.join(f'tag-{index}' for index in range(MAX_TAGS_PER_ARTICLE + 3))
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            '''
            CREATE TABLE articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slug TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                tags TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                published INTEGER DEFAULT 1
            );
            CREATE TABLE article_tags (
                article_id INTEGER NOT NULL,
                tag TEXT NOT NULL COLLATE NOCASE,
                PRIMARY KEY (article_id, tag)
            );
            '''
        )
        connection.executemany(
            """
            INSERT INTO articles (id, slug, title, tags, created_at, updated_at, published)
            VALUES (?, ?, ?, ?, '2026-01-01', '2026-01-01', 1)
            """,
            [
                (1, 'legacy-mixed', '混合旧标签', f'AI, {oversized_tag}, AIGC, ai'),
                (2, 'legacy-many', '超额旧标签', too_many_tags),
                (3, 'legacy-empty', '空旧标签', ''),
            ],
        )
        connection.executemany(
            'INSERT INTO article_tags (article_id, tag) VALUES (?, ?)',
            [(1, '过期标签'), (2, '旧关系'), (3, '幽灵标签'), (999, '孤儿关系')],
        )

    monkeypatch.setattr(config, 'DATABASE', str(database_path))
    init_db()

    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            'SELECT article_id, tag FROM article_tags ORDER BY article_id, rowid'
        ).fetchall()
    tags_by_article: dict[int, list[str]] = {}
    for article_id, tag in rows:
        tags_by_article.setdefault(article_id, []).append(tag)
    assert tags_by_article[1] == ['AI', 'AIGC']
    assert tags_by_article[2] == [f'tag-{index}' for index in range(MAX_TAGS_PER_ARTICLE)]
    assert 3 not in tags_by_article
    assert 999 not in tags_by_article

    # The one-time legacy repair is now recorded as a deployment migration,
    # rather than being repeated by every web-worker startup.
    with sqlite3.connect(database_path) as connection:
        migration_versions = [
            row[0]
            for row in connection.execute('SELECT version FROM schema_migrations ORDER BY version')
        ]
    assert migration_versions == [1, 2, 3, 4, 5, 6]


def test_search_prioritizes_title_matches_then_newest_articles(app):
    """Search results keep relevance first and use descending creation time as a tie-breaker."""
    with app.app_context():
        older_title = _new_published_article('排序关键词旧标题', '测试')
        newer_title = _new_published_article('排序关键词新标题', '测试')
        content_only = articles.create_article_draft('正文命中', '测试', '这里有排序关键词')
        articles.publish_article(content_only['slug'])
        content_only = articles.get_article_meta(content_only['slug'], published_only=False)
        try:
            conn = get_db()
            conn.execute('UPDATE articles SET created_at=? WHERE slug=?', ('2025-01-01T00:00:00', older_title['slug']))
            conn.execute('UPDATE articles SET created_at=? WHERE slug=?', ('2026-01-01T00:00:00', newer_title['slug']))
            conn.execute('UPDATE articles SET created_at=? WHERE slug=?', ('2027-01-01T00:00:00', content_only['slug']))
            conn.commit()

            results = search_articles('排序关键词')
            assert [item[0]['slug'] for item in results] == [
                newer_title['slug'],
                older_title['slug'],
                content_only['slug'],
            ]
        finally:
            _remove_article(older_title)
            _remove_article(newer_title)
            _remove_article(content_only)
