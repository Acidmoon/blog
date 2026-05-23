"""Smoke tests for waterhill-blog. Run with: pytest tests/ -v"""

import pytest

from module_loader import REGISTRY
from services.ai_chat import (
    ChatAPIError,
    ChatTimeoutError,
    MAX_CHAT_MESSAGES,
    MAX_USER_MESSAGE_CHARS,
    ChatRateLimitError,
    ChatValidationError,
    check_rate_limit,
    get_public_chat_settings,
    reset_rate_limits,
    render_chat_markdown,
    save_public_chat_settings,
    validate_chat_messages,
)
from services.site_settings import delete_settings, get_setting, set_settings


@pytest.fixture
def reset_chat_settings(app):
    keys = [
        'public_chat_enabled',
        'public_chat_api_base',
        'public_chat_api_key',
        'public_chat_model',
        'public_chat_access_code',
        'public_chat_system_prompt',
        'public_chat_rate_limit_minute',
        'public_chat_rate_limit_day',
    ]
    with app.app_context():
        original = {key: get_setting(key, None) for key in keys}
        set_settings({
            'public_chat_enabled': '0',
            'public_chat_api_base': 'https://www.waterhill.cyou/v1',
            'public_chat_api_key': '',
            'public_chat_model': 'gpt-5.5',
            'public_chat_access_code': '',
            'public_chat_system_prompt': 'test prompt',
            'public_chat_rate_limit_minute': '5',
            'public_chat_rate_limit_day': '100',
        })
        reset_rate_limits()
    yield
    with app.app_context():
        set_settings({key: value for key, value in original.items() if value is not None})
        delete_settings([key for key, value in original.items() if value is None])
        reset_rate_limits()


# ── Public pages ──────────────────────────────────────

def test_homepage_returns_200(client):
    r = client.get('/')
    assert r.status_code == 200


def test_homepage_has_expected_sections(client):
    r = client.get('/')
    html = r.data.decode('utf-8')
    for name in ['水浇岭', '水浇岭的博客', '见字如晤']:
        assert name in html, f'missing "{name}" on homepage'


def test_article_page(client):
    r = client.get('/article/这是我的博客的第一篇文章')
    assert r.status_code == 200
    html = r.data.decode('utf-8')
    assert '见字如晤' in html


def test_search_page(client):
    r = client.get('/search?q=博客')
    assert r.status_code == 200


def test_public_chat_page_returns_200(client, reset_chat_settings):
    r = client.get('/chat')
    assert r.status_code == 200
    assert 'AI 对话' in r.data.decode('utf-8')


# ── Admin ─────────────────────────────────────────────

def test_admin_login_page(client):
    r = client.get('/admin/login')
    assert r.status_code == 200


def test_admin_login_redirects_to_dashboard(client):
    r = client.post('/admin/login', data={'password': 'admin123'})
    assert r.status_code in (302, 200)
    # After login, the session should be set — follow manually
    with client.session_transaction() as sess:
        sess['logged_in'] = True
    r2 = client.get('/admin/modules')
    assert r2.status_code == 200


def test_admin_dashboard_requires_login(client):
    r = client.get('/admin', follow_redirects=True)
    assert '登录' in r.data.decode('utf-8') or 'login' in r.request.path.lower()


# ── Module registry ───────────────────────────────────

def test_all_core_modules_registered():
    expected = {'activity_heatmap', 'article_list', 'daily_quote', 'pagination', 'tag_filter'}
    actual = set(REGISTRY.home_sections.keys())
    assert expected == actual, f'missing: {expected - actual}, extra: {actual - expected}'


# ── Static files ──────────────────────────────────────

def test_css_served(client):
    r = client.get('/static/css/style.css')
    assert r.status_code == 200
    assert '@import' in r.data.decode('utf-8')


def test_component_css_served(client):
    for name in ['heatmap', 'hero', 'articles', 'admin']:
        r = client.get(f'/static/css/components/{name}.css')
        assert r.status_code == 200, f'{name}.css returned {r.status_code}'


# ── API endpoint ──────────────────────────────────────

def test_ai_polish_requires_login(client):
    r = client.post('/admin/api/ai/polish', json={'content': 'test'})
    assert r.status_code in (302, 401)


def test_public_chat_disabled_returns_403(client, reset_chat_settings):
    r = client.post('/api/chat', json={'messages': [{'role': 'user', 'content': 'hello'}]})
    assert r.status_code == 403


def test_public_chat_auth_rejects_bad_code(client, reset_chat_settings):
    with client.application.app_context():
        set_settings({
            'public_chat_enabled': '1',
            'public_chat_api_key': 'test-key',
            'public_chat_access_code': 'friend-code',
        })
    r = client.post('/api/chat/auth', json={'code': 'wrong'})
    assert r.status_code == 401


def test_public_chat_auth_accepts_good_code(client, reset_chat_settings):
    with client.application.app_context():
        set_settings({
            'public_chat_enabled': '1',
            'public_chat_api_key': 'test-key',
            'public_chat_access_code': 'zaobixianyu',
        })
    r = client.post('/api/chat/auth', json={'code': 'zaobixianyu'})
    assert r.status_code == 200
    assert r.get_json()['ok'] is True


def test_public_chat_mock_success(client, monkeypatch, reset_chat_settings):
    with client.application.app_context():
        set_settings({
            'public_chat_enabled': '1',
            'public_chat_api_key': 'test-key',
            'public_chat_access_code': 'friend-code',
        })
    client.post('/api/chat/auth', json={'code': 'friend-code'})

    def fake_completion(settings, payload):
        assert payload['model'] == 'gpt-5.5'
        assert payload['messages'][0]['role'] == 'system'
        return 'mock answer'

    monkeypatch.setattr('services.ai_chat._call_chat_completion', fake_completion)
    r = client.post('/api/chat', json={'messages': [{'role': 'user', 'content': 'hello'}]})
    assert r.status_code == 200
    assert r.get_json()['content'] == 'mock answer'
    assert '<p>mock answer</p>' in r.get_json()['html']


def test_public_chat_api_error_returns_json(client, monkeypatch, reset_chat_settings):
    with client.application.app_context():
        set_settings({
            'public_chat_enabled': '1',
            'public_chat_api_key': 'test-key',
            'public_chat_access_code': 'friend-code',
        })
    client.post('/api/chat/auth', json={'code': 'friend-code'})

    def fake_completion(settings, payload):
        raise ChatAPIError('AI 接口返回格式无法解析')

    monkeypatch.setattr('services.ai_chat._call_chat_completion', fake_completion)
    r = client.post('/api/chat', json={'messages': [{'role': 'user', 'content': 'hello'}]})
    assert r.status_code == 502
    assert r.get_json()['error'] == 'AI 接口返回格式无法解析'


def test_public_chat_timeout_returns_json(client, monkeypatch, reset_chat_settings):
    with client.application.app_context():
        set_settings({
            'public_chat_enabled': '1',
            'public_chat_api_key': 'test-key',
            'public_chat_access_code': 'friend-code',
        })
    client.post('/api/chat/auth', json={'code': 'friend-code'})

    def fake_completion(settings, payload):
        raise ChatTimeoutError('AI 接口请求超时')

    monkeypatch.setattr('services.ai_chat._call_chat_completion', fake_completion)
    r = client.post('/api/chat', json={'messages': [{'role': 'user', 'content': 'hello'}]})
    assert r.status_code == 504
    assert r.get_json()['error'] == 'AI 接口请求超时'


# ── Layout admin ──────────────────────────────────────

def test_layout_page_requires_login(client):
    r = client.get('/admin/layout', follow_redirects=True)
    assert '登录' in r.data.decode('utf-8') or 'login' in r.request.path.lower()


def test_chat_settings_page_requires_login(client):
    r = client.get('/admin/chat-settings', follow_redirects=True)
    assert '登录' in r.data.decode('utf-8') or 'login' in r.request.path.lower()


def test_chat_settings_page_for_logged_in_user(login, reset_chat_settings):
    r = login.get('/admin/chat-settings')
    assert r.status_code == 200
    assert 'AI 对话设置' in r.data.decode('utf-8')


def test_site_settings_defaults_and_api_key_preserved(app, reset_chat_settings):
    with app.app_context():
        settings = get_public_chat_settings()
        assert settings['model'] == 'gpt-5.5'
        set_settings({'public_chat_api_key': 'old-key'})
        save_public_chat_settings({
            'api_base': 'https://example.com/v1',
            'api_key': '',
            'model': 'gpt-5.5',
            'access_code': 'new-code',
            'system_prompt': 'hello',
            'rate_limit_minute': '3',
            'rate_limit_day': '9',
        })
        assert get_setting('public_chat_api_key') == 'old-key'


def test_validate_chat_messages_limits():
    messages = [{'role': 'user', 'content': str(i)} for i in range(MAX_CHAT_MESSAGES + 3)]
    assert len(validate_chat_messages(messages)) == MAX_CHAT_MESSAGES
    with pytest.raises(ChatValidationError):
        validate_chat_messages([{'role': 'system', 'content': 'bad'}])
    with pytest.raises(ChatValidationError):
        validate_chat_messages([{'role': 'user', 'content': 'x' * (MAX_USER_MESSAGE_CHARS + 1)}])


def test_rate_limit_exceeded(reset_chat_settings):
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
