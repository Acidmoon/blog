"""FTS and immutable activity-event regression coverage."""

from __future__ import annotations

import uuid

from models import get_db
from services import articles
from services.activity_heatmap import build_month_activity_heatmap
from services.search import ensure_article_search_index, rebuild_article_search_index, search_articles_page


def _days(heatmap: dict) -> list[dict]:
    return [day for week in heatmap['weeks'] for day in week]


def test_article_write_syncs_fts_index_and_public_search_paginates(app):
    """A public search reads only matching FTS rows and keeps legacy ordering."""
    with app.app_context():
        marker = uuid.uuid4().hex[:12]
        article = articles.create_article_draft(f"索引标题 {marker}", "FTS", f"正文 {marker}")
        articles.publish_article(article['slug'])
        try:
            stored = get_db().execute(
                "SELECT article_id, title, content FROM article_search WHERE article_id=?",
                (article['id'],),
            ).fetchone()
            assert stored is not None
            assert marker in stored['title']
            assert marker in stored['content']

            results, total = search_articles_page(marker, page=1, per_page=10)
            assert total == 1
            assert [item[0]['slug'] for item in results] == [article['slug']]
        finally:
            articles.delete_article(article['slug'])
            articles.delete_article_file(article['slug'], content_key=article['content_key'])


def test_explicit_fts_rebuild_recovers_a_missing_derived_row(app):
    """The maintenance command can repair derived search data without touching content."""
    with app.app_context():
        article = articles.create_article_draft(
            f"重建索引 {uuid.uuid4().hex[:8]}",
            "FTS",
            "重建测试正文",
        )
        try:
            get_db().execute('DELETE FROM article_search WHERE article_id=?', (article['id'],))
            get_db().commit()

            report = rebuild_article_search_index()
            restored = get_db().execute(
                'SELECT 1 FROM article_search WHERE article_id=?',
                (article['id'],),
            ).fetchone()

            assert report['indexed'] >= 1
            assert restored is not None
        finally:
            articles.delete_article(article['slug'])
            articles.delete_article_file(article['slug'], content_key=article['content_key'])


def test_ensure_fts_index_does_not_rebuild_when_another_worker_already_finished(app, monkeypatch):
    """The normal startup path rechecks under the writer lock before rebuilding."""
    with app.app_context():
        marker = uuid.uuid4().hex[:8]
        article = articles.create_article_draft(f"索引确认 {marker}", "FTS", "正文")
        try:
            def unexpected_sync(*args, **kwargs):
                raise AssertionError('当前索引不应再次全量重建')

            monkeypatch.setattr('services.search.sync_article_search', unexpected_sync)
            report = ensure_article_search_index()

            assert report is None
        finally:
            articles.delete_article(article['slug'])
            articles.delete_article_file(article['slug'], content_key=article['content_key'])


def test_activity_events_preserve_multiple_updates_on_one_day(app):
    """Heatmaps count each committed edit instead of collapsing current snapshots."""
    with app.app_context():
        article = articles.create_article_draft(
            f"活动事件 {uuid.uuid4().hex[:8]}",
            "活动",
            "第一版正文",
        )
        articles.publish_article(article['slug'])
        updated = articles.update_article(article['slug'], article['title'], "活动", "第二版正文更多内容")
        latest = articles.update_article(updated['slug'], updated['title'], "活动", "第三版正文更多更多内容")
        try:
            event_count = int(
                get_db().execute(
                    "SELECT COUNT(*) FROM article_activity_events WHERE article_id=? AND visible=1",
                    (article['id'],),
                ).fetchone()[0]
            )
            heatmap = build_month_activity_heatmap()
            today = next(day for day in _days(heatmap) if day['is_today'])

            assert event_count >= 3
            assert today['count'] >= 3
        finally:
            articles.delete_article(article['slug'])
            for content_key in (article['content_key'], updated['content_key'], latest['content_key']):
                path = articles._content_path(content_key)
                if path.exists():
                    articles.delete_article_file(article['slug'], content_key=content_key)
