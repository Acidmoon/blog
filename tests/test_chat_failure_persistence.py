"""Chat persistence behavior when the upstream model call fails."""

import sqlite3
import uuid

import pytest

from services.ai_chat import ChatAPIError
from services.chat_orchestrator import send_public_chat_message
from services.site_settings import delete_settings, set_settings


def _enable_chat(app) -> None:
    """Enable a configured chat provider inside the isolated test database."""
    with app.app_context():
        set_settings({
            'public_chat_enabled': '1',
            'public_chat_api_key': 'test-key',
            'public_chat_api_base': 'https://example.test/v1',
        })


def _login_visitor(client) -> None:
    """Create a disposable visitor session for chat API calls."""
    username = f'cf{uuid.uuid4().hex[:10]}'
    response = client.post(
        '/login',
        data={'username': username, 'password': 'abc123', 'action': 'register'},
        follow_redirects=False,
    )
    assert response.status_code in (302, 303)


def _fail_completion(*args, **kwargs):
    """Stand in for an unavailable upstream provider."""
    raise ChatAPIError('上游失败')


def _successful_completion(*args, **kwargs):
    """Return a deterministic response without making a network request."""
    return '模型回复'


def _current_visitor_id(app) -> int:
    """Look up the visitor created by the current test client."""
    from models import get_db

    with app.app_context():
        row = get_db().execute(
            'SELECT id FROM visitor_users ORDER BY id DESC LIMIT 1',
        ).fetchone()
    assert row is not None
    return row['id']


def _fail_assistant_message_insert(monkeypatch) -> None:
    """Make the second insert fail after the user-message insert has executed."""
    import services.chat_sessions as chat_sessions

    original_insert = chat_sessions._insert_chat_message

    def fail_on_assistant(conn, session_id, role, content, html, created_at):
        if role == 'assistant':
            raise sqlite3.OperationalError('simulated assistant insert failure')
        return original_insert(conn, session_id, role, content, html, created_at)

    monkeypatch.setattr(chat_sessions, '_insert_chat_message', fail_on_assistant)


@pytest.fixture
def chat_enabled(client):
    """Provide enabled chat settings without depending on smoke-test fixtures."""
    _enable_chat(client.application)
    yield
    with client.application.app_context():
        delete_settings([
            'public_chat_enabled',
            'public_chat_api_key',
            'public_chat_api_base',
        ])


def test_failed_first_chat_request_creates_no_empty_session_or_message(client, chat_enabled, monkeypatch):
    """A provider error before success must not leave an invisible draft behind."""
    _login_visitor(client)
    monkeypatch.setattr('features.chat.application.chat_completion', _fail_completion)

    response = client.post('/api/chat', json={'content': '会失败的问题'})

    assert response.status_code == 502
    assert client.get('/api/chat/sessions').get_json()['sessions'] == []


def test_failed_chat_request_preserves_existing_session_history(client, chat_enabled, monkeypatch):
    """A retryable provider error does not append a stray user turn to an existing session."""
    _login_visitor(client)
    session = client.post('/api/chat/sessions', json={'title': '已有会话'}).get_json()['session']
    monkeypatch.setattr('features.chat.application.chat_completion', _fail_completion)

    response = client.post('/api/chat', json={'session_id': session['id'], 'content': '会失败的问题'})
    history = client.get(f"/api/chat/sessions/{session['id']}/messages").get_json()['messages']

    assert response.status_code == 502
    assert history == []


def test_persistence_failure_rolls_back_new_session_and_both_messages(client, chat_enabled, monkeypatch):
    """A post-model write error cannot leave a newly-created draft or first message."""
    _login_visitor(client)
    visitor_id = _current_visitor_id(client.application)
    monkeypatch.setattr('features.chat.application.chat_completion', _successful_completion)
    monkeypatch.setattr('features.chat.application.generate_chat_session_title', lambda messages: '完整标题')
    _fail_assistant_message_insert(monkeypatch)

    with client.application.app_context(), pytest.raises(sqlite3.OperationalError):
        send_public_chat_message(
            visitor_id=visitor_id,
            content='会触发写入失败的问题',
            session_id=None,
            client_ip='127.0.0.1',
        )

    assert client.get('/api/chat/sessions').get_json()['sessions'] == []


def test_persistence_failure_preserves_existing_session_title_and_history(client, chat_enabled, monkeypatch):
    """A failed initial-title update rolls back both new messages on an existing session."""
    _login_visitor(client)
    visitor_id = _current_visitor_id(client.application)
    session = client.post('/api/chat/sessions', json={'title': '新的对话'}).get_json()['session']
    monkeypatch.setattr('features.chat.application.chat_completion', _successful_completion)
    monkeypatch.setattr('features.chat.application.generate_chat_session_title', lambda messages: '完整标题')

    from models import get_db

    with client.application.app_context():
        conn = get_db()
        conn.execute(
            """
            CREATE TRIGGER test_chat_title_update_failure
            BEFORE UPDATE OF title ON chat_sessions
            WHEN NEW.title = '完整标题'
            BEGIN
                SELECT RAISE(ABORT, 'simulated title update failure');
            END
            """,
        )
        conn.commit()
        try:
            with pytest.raises(sqlite3.IntegrityError):
                send_public_chat_message(
                    visitor_id=visitor_id,
                    content='会触发写入失败的问题',
                    session_id=session['id'],
                    client_ip='127.0.0.1',
                )
        finally:
            conn.execute('DROP TRIGGER IF EXISTS test_chat_title_update_failure')
            conn.commit()

    current_session = client.get('/api/chat/sessions').get_json()['sessions'][0]
    history = client.get(f"/api/chat/sessions/{session['id']}/messages").get_json()['messages']
    assert current_session['title'] == '新的对话'
    assert history == []
