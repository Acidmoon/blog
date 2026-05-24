"""Smoke tests for waterhill-blog. Run with: pytest tests/ -v"""

from __future__ import annotations

import pytest

from module_loader import REGISTRY
from models import get_db
from services.access_settings import get_access_settings
from services.ai_chat import (
    ChatAPIError,
    ChatRateLimitError,
    ChatTimeoutError,
    ChatValidationError,
    MAX_CHAT_MESSAGES,
    MAX_USER_MESSAGE_CHARS,
    check_rate_limit,
    get_public_chat_settings,
    reset_rate_limits,
    render_chat_markdown,
    save_public_chat_settings,
    validate_chat_messages,
)
from services.site_settings import delete_settings, get_setting, set_settings


TABLES_TO_SNAPSHOT = [
    'public_chat_ip_auth',
    'visitor_users',
    'visitor_tokens',
    'chat_sessions',
    'chat_messages',
    'chat_files',
]
TABLE_DELETE_ORDER = [
    'chat_files',
    'chat_messages',
    'chat_sessions',
    'visitor_tokens',
    'visitor_users',
    'public_chat_ip_auth',
]
TABLE_INSERT_ORDER = [
    'public_chat_ip_auth',
    'visitor_users',
    'visitor_tokens',
    'chat_sessions',
    'chat_messages',
    'chat_files',
]


def _snapshot_tables(db):
    snapshots = {}
    for table in TABLES_TO_SNAPSHOT:
        rows = db.execute(f"SELECT * FROM {table}").fetchall()
        snapshots[table] = [dict(row) for row in rows]
    return snapshots


def _restore_table(db, table, rows):
    if not rows:
        return
    columns = list(rows[0].keys())
    placeholders = ','.join('?' for _ in columns)
    column_sql = ','.join(columns)
    values = [[row[column] for column in columns] for row in rows]
    db.executemany(
        f"INSERT INTO {table} ({column_sql}) VALUES ({placeholders})",
        values,
    )


@pytest.fixture
def reset_settings(app):
    keys = [
        'public_chat_enabled',
        'public_chat_api_base',
        'public_chat_api_key',
        'public_chat_model',
        'public_chat_system_prompt',
        'public_chat_rate_limit_minute',
        'public_chat_rate_limit_day',
        'visitor_login_enabled',
        'visitor_login_days',
        'chat_file_upload_enabled',
        'chat_file_max_mb',
        'chat_user_storage_mb',
        'chat_session_file_limit',
        'chat_file_retention_days',
    ]
    with app.app_context():
        original = {key: get_setting(key, None) for key in keys}
        db = get_db()
        original_tables = _snapshot_tables(db)
        for table in TABLE_DELETE_ORDER:
            db.execute(f"DELETE FROM {table}")
        set_settings({
            'public_chat_enabled': '0',
            'public_chat_api_base': 'https://www.waterhill.cyou/v1',
            'public_chat_api_key': '',
            'public_chat_model': 'gpt-5.5',
            'public_chat_system_prompt': 'test prompt',
            'public_chat_rate_limit_minute': '5',
            'public_chat_rate_limit_day': '100',
            'visitor_login_enabled': '1',
            'visitor_login_days': '7',
            'chat_file_upload_enabled': '0',
            'chat_file_max_mb': '10',
            'chat_user_storage_mb': '100',
            'chat_session_file_limit': '5',
            'chat_file_retention_days': '30',
        })
        db.commit()
        reset_rate_limits()
    yield
    with app.app_context():
        set_settings({key: value for key, value in original.items() if value is not None})
        delete_settings([key for key, value in original.items() if value is None])
        db = get_db()
        for table in TABLE_DELETE_ORDER:
            db.execute(f"DELETE FROM {table}")
        for table in TABLE_INSERT_ORDER:
            _restore_table(db, table, original_tables[table])
        db.commit()
        reset_rate_limits()


def _visitor_login(client, username='alice1', password='abc123'):
    return client.post('/login', data={'username': username, 'password': password, 'next': '/'}, follow_redirects=False)


def _enable_public_chat(app):
    with app.app_context():
        set_settings({
            'public_chat_enabled': '1',
            'public_chat_api_key': 'test-key',
            'public_chat_api_base': 'https://www.waterhill.cyou/v1',
        })


def _login_visitor(client, username='alice1', password='abc123'):
    r = _visitor_login(client, username=username, password=password)
    assert r.status_code in (302, 303)
    return client


def test_homepage_redirects_when_visitor_login_enabled(client, reset_settings):
    r = client.get('/')
    assert r.status_code in (302, 303)
    assert '/login' in r.location


def test_login_page_returns_200(client, reset_settings):
    r = client.get('/login')
    assert r.status_code == 200
    assert '访客登录' in r.data.decode('utf-8')


def test_new_visitor_can_register_and_login(client, reset_settings):
    r = _visitor_login(client, username='user1', password='abc123')
    assert r.status_code in (302, 303)
    assert 'visitor_token' in r.headers.get('Set-Cookie', '')


def test_existing_visitor_wrong_password_rejected(client, reset_settings):
    _visitor_login(client, username='user1', password='abc123')
    fresh_client = client.application.test_client()
    r = _visitor_login(fresh_client, username='user1', password='zzz999')
    assert r.status_code == 200
    html = r.data.decode('utf-8')
    assert '密码错误' in html or '重新输入' in html


def test_username_password_validation(client, reset_settings):
    r = _visitor_login(client, username='中文', password='abc123')
    assert r.status_code == 200
    html = r.data.decode('utf-8')
    assert '用户名只能使用英文字母和数字' in html

    r = _visitor_login(client, username='user2', password='超长密码123456')
    assert r.status_code == 200
    assert '密码只能使用英文字母和数字' in r.data.decode('utf-8')


def test_admin_login_page_not_blocked(client, reset_settings):
    r = client.get('/admin/login')
    assert r.status_code == 200


def test_admin_routes_still_require_admin_login(client, reset_settings):
    r = client.get('/admin', follow_redirects=True)
    assert '登录' in r.data.decode('utf-8')


def test_all_core_modules_registered():
    expected = {'activity_heatmap', 'article_list', 'daily_quote', 'pagination', 'tag_filter'}
    actual = set(REGISTRY.home_sections.keys())
    assert expected == actual


def test_static_css_served(client, reset_settings):
    r = client.get('/static/css/style.css')
    assert r.status_code == 200
    assert '@import' in r.data.decode('utf-8')


def test_public_chat_page_requires_login(client, reset_settings):
    _enable_public_chat(client.application)
    r = client.get('/chat')
    assert r.status_code in (302, 303)


def test_chat_page_contains_rail_toggle_and_history_shell(client, reset_settings):
    _enable_public_chat(client.application)
    _login_visitor(client)
    r = client.get('/chat')
    assert r.status_code == 200
    html = r.data.decode('utf-8')
    assert 'chatRailToggle' in html
    assert 'chatSessionList' in html
    assert 'chatRailDrawer' in html


def test_public_chat_api_requires_login(client, reset_settings):
    _enable_public_chat(client.application)
    r = client.post('/api/chat', json={'content': 'hello'})
    assert r.status_code == 401


def test_public_chat_disabled_returns_403(client, reset_settings):
    _login_visitor(client)
    r = client.post('/api/chat', json={'content': 'hello'})
    assert r.status_code == 403


def test_public_chat_mock_success(client, monkeypatch, reset_settings):
    _enable_public_chat(client.application)
    _login_visitor(client)

    def fake_completion(messages, client_ip, extra_system_context=''):
        assert messages[-1]['role'] == 'user'
        assert extra_system_context == ''
        return 'mock answer'

    monkeypatch.setattr('routes.public.chat_completion', fake_completion)
    monkeypatch.setattr('routes.public.generate_chat_session_title', lambda messages: 'hello')
    r = client.post('/api/chat', json={'content': 'hello'})
    assert r.status_code == 200
    body = r.get_json()
    assert body['content'] == 'mock answer'
    assert '<p>mock answer</p>' in body['html']


def test_public_chat_mock_success_generates_session_title(client, monkeypatch, reset_settings):
    _enable_public_chat(client.application)
    _login_visitor(client)

    def fake_completion(messages, client_ip, extra_system_context=''):
        return 'mock answer'

    captured = {}

    def fake_generate_title(messages):
        captured['messages'] = messages
        assert len(messages) == 2
        assert messages[0]['role'] == 'user'
        assert messages[1]['role'] == 'assistant'
        assert messages[0]['content'] == 'hello'
        assert messages[1]['content'] == 'mock answer'
        return '怎么给会话起标题'

    monkeypatch.setattr('routes.public.chat_completion', fake_completion)
    monkeypatch.setattr('routes.public.generate_chat_session_title', fake_generate_title)
    r = client.post('/api/chat', json={'content': 'hello'})
    assert r.status_code == 200
    body = r.get_json()
    assert body['session']['title'] == '怎么给会话起标题'
    assert captured['messages'][0]['content'] == 'hello'
    sessions = client.get('/api/chat/sessions').get_json()['sessions']
    assert sessions[0]['title'] == '怎么给会话起标题'


def test_public_chat_title_generation_failure_does_not_block_chat(client, monkeypatch, reset_settings):
    _enable_public_chat(client.application)
    _login_visitor(client)

    def fake_completion(messages, client_ip, extra_system_context=''):
        return 'mock answer'

    def fake_generate_title(messages):
        raise ChatAPIError('AI 接口返回格式无法解析')

    monkeypatch.setattr('routes.public.chat_completion', fake_completion)
    monkeypatch.setattr('routes.public.generate_chat_session_title', fake_generate_title)
    r = client.post('/api/chat', json={'content': 'hello'})
    assert r.status_code == 200
    body = r.get_json()
    assert body['session']['title'] == 'hello'


def test_public_chat_api_error_returns_json(client, monkeypatch, reset_settings):
    _enable_public_chat(client.application)
    _login_visitor(client)

    def fake_completion(messages, client_ip, extra_system_context=''):
        raise ChatAPIError('AI 接口返回格式无法解析')

    monkeypatch.setattr('routes.public.chat_completion', fake_completion)
    r = client.post('/api/chat', json={'content': 'hello'})
    assert r.status_code == 502
    assert r.get_json()['error'] == 'AI 接口返回格式无法解析'


def test_public_chat_timeout_returns_json(client, monkeypatch, reset_settings):
    _enable_public_chat(client.application)
    _login_visitor(client)

    def fake_completion(messages, client_ip, extra_system_context=''):
        raise ChatTimeoutError('AI 接口请求超时')

    monkeypatch.setattr('routes.public.chat_completion', fake_completion)
    r = client.post('/api/chat', json={'content': 'hello'})
    assert r.status_code == 504
    assert r.get_json()['error'] == 'AI 接口请求超时'


def test_chat_session_is_owned_by_visitor(client, reset_settings, monkeypatch):
    _enable_public_chat(client.application)
    _login_visitor(client, username='alice1', password='abc123')
    r = client.post('/api/chat/sessions', json={'title': 'A'})
    session_id = r.get_json()['session']['id']
    client.get('/logout')
    _login_visitor(client, username='bob1', password='abc123')
    r2 = client.get(f'/api/chat/sessions/{session_id}/messages')
    assert r2.status_code == 404


def test_chat_upload_disabled_by_default(client, reset_settings):
    _login_visitor(client)
    r = client.post('/api/chat/sessions', json={'title': 'A'})
    session_id = r.get_json()['session']['id']
    r2 = client.post(f'/api/chat/sessions/{session_id}/files', data={})
    assert r2.status_code == 400 or r2.status_code == 404


def test_chat_session_delete_works_for_owner(client, reset_settings):
    _enable_public_chat(client.application)
    _login_visitor(client)
    r = client.post('/api/chat/sessions', json={'title': 'A'})
    session_id = r.get_json()['session']['id']
    r2 = client.delete(f'/api/chat/sessions/{session_id}')
    assert r2.status_code == 200
    r3 = client.get(f'/api/chat/sessions/{session_id}/messages')
    assert r3.status_code == 404


def test_site_settings_defaults_and_api_key_preserved(app, reset_settings):
    with app.app_context():
        settings = get_public_chat_settings()
        assert settings['model'] == 'gpt-5.5'
        set_settings({'public_chat_api_key': 'old-key'})
        save_public_chat_settings({
            'api_base': 'https://example.com/v1',
            'api_key': '',
            'model': 'gpt-5.5',
            'system_prompt': 'hello',
            'rate_limit_minute': '3',
            'rate_limit_day': '9',
        })
        assert get_setting('public_chat_api_key') == 'old-key'


def test_access_settings_defaults(app, reset_settings):
    with app.app_context():
        settings = get_access_settings()
        assert settings['visitor_login_enabled'] is True
        assert settings['visitor_login_days'] == 7
        assert settings['chat_file_upload_enabled'] is False


def test_validate_chat_messages_limits():
    messages = [{'role': 'user', 'content': str(i)} for i in range(MAX_CHAT_MESSAGES + 3)]
    assert len(validate_chat_messages(messages)) == MAX_CHAT_MESSAGES
    with pytest.raises(ChatValidationError):
        validate_chat_messages([{'role': 'system', 'content': 'bad'}])
    with pytest.raises(ChatValidationError):
        validate_chat_messages([{'role': 'user', 'content': 'x' * (MAX_USER_MESSAGE_CHARS + 1)}])


def test_rate_limit_exceeded():
    reset_rate_limits()
    settings = {'rate_limit_minute': 1, 'rate_limit_day': 100}
    check_rate_limit('127.0.0.1', settings, now=1000)
    with pytest.raises(ChatRateLimitError):
        check_rate_limit('127.0.0.1', settings, now=1001)


def test_render_chat_markdown_sanitizes_html():
    html = render_chat_markdown('**bold** $x^2$ <script>alert(1)</script>')
    assert '<strong>bold</strong>' in html
    assert 'arithmatex' in html
    assert '<script>' not in html


def test_public_pages_blocked_for_guests(client, reset_settings):
    for path in ['/', '/search?q=博客', '/article/这是我的博客的第一篇文章', '/chat']:
        r = client.get(path)
        assert r.status_code in (302, 303)


def test_admin_login_open_to_guests(client, reset_settings):
    r = client.get('/admin/login')
    assert r.status_code == 200


def test_nav_and_layout_pages_require_admin_login(client, reset_settings):
    for path in ['/admin/layout', '/admin/chat-settings', '/admin/access-settings']:
        r = client.get(path, follow_redirects=True)
        assert '登录' in r.data.decode('utf-8')


def test_chat_settings_page_for_logged_in_admin(login, reset_settings):
    r = login.get('/admin/chat-settings')
    assert r.status_code == 200
    assert 'AI 对话设置' in r.data.decode('utf-8')


def test_access_settings_page_for_logged_in_admin(login, reset_settings):
    r = login.get('/admin/access-settings')
    assert r.status_code == 200
    assert '访问设置' in r.data.decode('utf-8')
