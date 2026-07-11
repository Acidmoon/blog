"""Failure-path coverage for SQLite metadata and immutable Markdown versions."""

from __future__ import annotations

import sqlite3
import uuid

import pytest

import config
from models import get_db, init_db
from services import articles


def _new_article(title_prefix: str = '文章持久化测试') -> dict:
    """Create one disposable draft with a globally unique title."""
    return articles.create_article_draft(
        f'{title_prefix} {uuid.uuid4().hex[:8]}',
        '测试,持久化',
        '旧版本正文',
    )


def _remove_article_and_versions(article: dict, *content_keys: str) -> None:
    """Remove test-only metadata and every immutable body created by a test."""
    articles.delete_article(article['slug'])
    for content_key in content_keys:
        if content_key:
            articles.delete_article_file(article['slug'], content_key=content_key)


def test_create_file_failure_does_not_insert_article_metadata(app, monkeypatch):
    """A failed file write must leave no visible database article behind."""
    title = f'创建失败测试 {uuid.uuid4().hex[:8]}'

    def fail_file_write(slug: str, content: str, *, content_key: str = '') -> None:
        raise OSError('模拟磁盘写入失败')

    monkeypatch.setattr(articles, 'write_article_file', fail_file_write)
    with app.app_context(), pytest.raises(OSError, match='模拟磁盘写入失败'):
        articles.create_article_draft(title, '测试', '不会被保存')

    with app.app_context():
        row = get_db().execute('SELECT slug FROM articles WHERE title=?', (title,)).fetchone()
        assert row is None


def test_update_file_failure_preserves_prior_metadata_and_body(app, monkeypatch):
    """A failed replacement leaves the committed pointer and old body untouched."""
    with app.app_context():
        article = _new_article()
        original_meta = articles.get_article_meta(article['slug'], published_only=False)

        def fail_file_write(slug: str, content: str, *, content_key: str = '') -> None:
            raise OSError('模拟磁盘写入失败')

        monkeypatch.setattr(articles, 'write_article_file', fail_file_write)
        with pytest.raises(OSError, match='模拟磁盘写入失败'):
            articles.update_article(article['slug'], '新标题', '新标签', '新版本正文')

        restored_meta = articles.get_article_meta(article['slug'], published_only=False)
        assert restored_meta['title'] == original_meta['title']
        assert restored_meta['tags'] == original_meta['tags']
        assert restored_meta['content_key'] == original_meta['content_key']
        assert articles.read_article_file(article['slug'], restored_meta['content_key']) == '旧版本正文'
        _remove_article_and_versions(article, original_meta['content_key'])


def test_update_publishes_new_immutable_body_version(app):
    """Readers using the previous pointer keep a complete old body after an edit."""
    with app.app_context():
        article = _new_article('版本切换测试')
        original_key = article['content_key']
        updated = articles.update_article(article['slug'], '新标题', '新标签', '新版本正文')

        assert updated['content_key'] != original_key
        assert articles.read_article_file(article['slug'], original_key) == '旧版本正文'
        assert articles.read_article_file(article['slug'], updated['content_key']) == '新版本正文'
        assert articles._content_path(updated['content_key']).name == f"{updated['content_key']}.md"
        _remove_article_and_versions(article, original_key, updated['content_key'])


def test_delete_keeps_committed_body_for_inflight_readers(app):
    """Deleting metadata does not make a previously committed body disappear."""
    with app.app_context():
        article = _new_article('删除版本测试')
        content_key = article['content_key']
        articles.delete_article(article['slug'])

        assert articles.get_article_meta(article['slug'], published_only=False) is None
        assert articles.read_article_file(article['slug'], content_key) == '旧版本正文'
        articles.delete_article_file(article['slug'], content_key=content_key)


def test_legacy_slug_file_remains_readable_until_edited(app):
    """Existing installations continue reading rows that have no content pointer."""
    slug = f'legacy-{uuid.uuid4().hex[:8]}'
    with app.app_context():
        articles.write_article_file(slug, '旧版兼容正文')
        get_db().execute(
            '''
            INSERT INTO articles (slug, title, tags, created_at, updated_at, published, word_count)
            VALUES (?, ?, '', '2026-01-01T00:00:00', '2026-01-01T00:00:00', 0, 0)
            ''',
            (slug, '旧版兼容文章'),
        )
        get_db().commit()

        assert articles.read_article_file(slug, '') == '旧版兼容正文'
        articles.delete_article(slug)
        articles.delete_article_file(slug)


def test_long_chinese_slug_uses_a_fixed_length_body_filename(app):
    """An 80-character CJK slug cannot overflow a Linux filename component."""
    with app.app_context():
        article = articles.create_article_draft('长' * 80, '测试', '正文')
        content_key = article['content_key']

        assert len(article['slug'].encode('utf-8')) == 240
        assert len(articles._content_path(content_key).name.encode('utf-8')) == 35
        _remove_article_and_versions(article, content_key)


def test_init_db_adds_content_key_to_existing_article_database(tmp_path, monkeypatch):
    """Deploying this change upgrades an existing SQLite database in place."""
    database_path = tmp_path / 'legacy.db'
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            '''
            CREATE TABLE articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slug TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                tags TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                published INTEGER DEFAULT 1
            )
            '''
        )

    monkeypatch.setattr(config, 'DATABASE', str(database_path))
    init_db()

    with sqlite3.connect(database_path) as connection:
        columns = {row[1] for row in connection.execute('PRAGMA table_info(articles)')}
    assert {'word_count', 'content_key'} <= columns
