"""Focused SQLite locking and like-toggle concurrency regression coverage."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import uuid

import pytest

from models import SQLITE_BUSY_TIMEOUT_MS, _new_connection, get_db
from services.comments import LikeUnavailableError, count_likes, toggle_like


def _create_social_rows(app) -> tuple[str, int, int]:
    """Create isolated article and visitor rows for one like mutation test."""
    suffix = uuid.uuid4().hex[:12]
    slug = f'like-concurrency-{suffix}'
    with app.app_context():
        conn = get_db()
        user_id = conn.execute(
            """
            INSERT INTO visitor_users (username, password_hash, created_at)
            VALUES (?, 'test-hash', '2026-01-01T00:00:00')
            """,
            (f'like-user-{suffix}',),
        ).lastrowid
        article_id = conn.execute(
            """
            INSERT INTO articles (slug, title, tags, created_at, updated_at, published, word_count)
            VALUES (?, '点赞并发测试', '', '2026-01-01T00:00:00', '2026-01-01T00:00:00', 1, 0)
            """,
            (slug,),
        ).lastrowid
        conn.commit()
    return slug, int(article_id), int(user_id)


def _remove_social_rows(app, article_id: int, user_id: int) -> None:
    """Remove only the test-owned rows after foreign-key cascades clear likes."""
    with app.app_context():
        conn = get_db()
        conn.execute('DELETE FROM articles WHERE id=?', (article_id,))
        conn.execute('DELETE FROM visitor_users WHERE id=?', (user_id,))
        conn.commit()


def test_database_connections_enable_the_configured_busy_wait(app):
    """The Python connection timeout is reinforced by SQLite's per-connection pragma."""
    connection = _new_connection()
    try:
        assert connection.execute('PRAGMA busy_timeout').fetchone()[0] == SQLITE_BUSY_TIMEOUT_MS
    finally:
        connection.close()


@pytest.mark.parametrize(
    ('use_visitor', 'ip'),
    [
        (True, ''),
        (False, '198.51.100.87'),
    ],
)
def test_concurrent_like_toggles_linearize_without_unique_index_errors(app, use_visitor, ip):
    """Both visitor and anonymous unique indexes turn rapid clicks into toggles."""
    _, article_id, user_id = _create_social_rows(app)
    start = Barrier(2)
    actor_id = user_id if use_visitor else None

    def toggle_from_independent_request_context() -> dict:
        with app.app_context():
            start.wait(timeout=5)
            return toggle_like(article_id, actor_id, ip)

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = [
                future.result(timeout=15)
                for future in (
                    executor.submit(toggle_from_independent_request_context),
                    executor.submit(toggle_from_independent_request_context),
                )
            ]
        assert {result['liked'] for result in results} == {True, False}
        assert sorted(result['count'] for result in results) == [0, 1]
        with app.app_context():
            assert count_likes(article_id) == 0
    finally:
        _remove_social_rows(app, article_id, user_id)


def test_like_route_maps_lock_contention_to_a_retryable_json_response(client, app, monkeypatch):
    """A busy SQLite writer is a retryable API response rather than an HTML 500."""
    slug, article_id, user_id = _create_social_rows(app)

    def raise_busy(*_args, **_kwargs):
        raise LikeUnavailableError('点赞操作繁忙，请稍后重试')

    monkeypatch.setattr('routes.public_social.toggle_like', raise_busy)
    try:
        response = client.post(f'/api/article/{slug}/like')
        assert response.status_code == 503
        assert response.get_json() == {'error': '点赞操作繁忙，请稍后重试'}
    finally:
        _remove_social_rows(app, article_id, user_id)
