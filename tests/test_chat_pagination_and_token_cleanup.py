"""Bounded chat history and periodic visitor-token maintenance coverage."""

from __future__ import annotations

import time
import uuid

import pytest

from models import get_db
from services.chat_sessions import append_chat_message, create_chat_session, list_chat_message_page
from services.visitor_auth import maybe_purge_expired_visitor_tokens


def _create_visitor_id() -> int:
    """Create a disposable visitor row without coupling this test to auth routes."""
    now = '2026-01-01T00:00:00'
    cursor = get_db().execute(
        """
        INSERT INTO visitor_users (username, password_hash, created_at)
        VALUES (?, 'test-hash', ?)
        """,
        (f'page{uuid.uuid4().hex[:10]}', now),
    )
    get_db().commit()
    return int(cursor.lastrowid)


def test_chat_message_page_returns_latest_messages_then_a_stable_older_cursor(app):
    """Long histories are read in bounded chronological slices without duplicates."""
    with app.app_context():
        visitor_id = _create_visitor_id()
        session = create_chat_session(visitor_id, '分页测试')
        for index in range(7):
            append_chat_message(session['id'], 'user', f'消息 {index}')

        latest = list_chat_message_page(visitor_id, session['id'], limit=3)
        older = list_chat_message_page(
            visitor_id,
            session['id'],
            before_id=latest['next_before_id'],
            limit=3,
        )

        assert [item['content'] for item in latest['messages']] == ['消息 4', '消息 5', '消息 6']
        assert latest['has_more'] is True
        assert [item['content'] for item in older['messages']] == ['消息 1', '消息 2', '消息 3']
        assert older['has_more'] is True


def test_chat_message_page_rejects_unbounded_client_limits(app):
    """A client cannot turn the pagination endpoint back into an unlimited query."""
    with app.app_context():
        visitor_id = _create_visitor_id()
        session = create_chat_session(visitor_id, '限制测试')
        with pytest.raises(ValueError, match='消息数量'):
            list_chat_message_page(visitor_id, session['id'], limit=201)


def test_periodic_token_cleanup_is_bounded_and_removes_expired_rows(app, monkeypatch):
    """Expired tokens are reclaimed on normal traffic without repeated writes."""
    import services.visitor_auth as visitor_auth

    with app.app_context():
        visitor_id = _create_visitor_id()
        get_db().execute(
            """
            INSERT INTO visitor_tokens (user_id, token_hash, expires_at, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (visitor_id, uuid.uuid4().hex, 10.0, '2026-01-01T00:00:00'),
        )
        get_db().commit()
        monkeypatch.setattr(visitor_auth, '_last_token_purge_at', 0.0)
        monkeypatch.setattr(visitor_auth.config, 'VISITOR_TOKEN_PURGE_INTERVAL_SECONDS', 60)

        assert maybe_purge_expired_visitor_tokens(now=100.0) == 1
        assert maybe_purge_expired_visitor_tokens(now=120.0) == 0
        remaining = get_db().execute('SELECT COUNT(*) FROM visitor_tokens WHERE user_id=?', (visitor_id,)).fetchone()[0]
        assert remaining == 0
