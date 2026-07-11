"""Smoke tests for waterhill-blog. Run with: pytest tests/ -v"""

from __future__ import annotations

import json
import time
import uuid
from urllib.parse import unquote

import pytest

import config
from module_loader import get_module_registry
from models import get_db
from services.access_settings import get_access_settings
from services.admin_modules import build_admin_nav, build_admin_nav_groups
from services.articles import (
    create_article_draft,
    delete_article as svc_delete_article,
    get_article_meta,
    publish_article,
    read_article_file,
)
from services.auth import reset_auth_rate_limits
from services.site_settings import delete_settings, get_setting, set_settings


TABLES_TO_SNAPSHOT = [
    'visitor_users',
    'visitor_tokens',
]
TABLE_DELETE_ORDER = [
    'visitor_tokens',
    'visitor_users',
]
TABLE_INSERT_ORDER = [
    'visitor_users',
    'visitor_tokens',
]


def _table_exists(db, table):
    row = db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _snapshot_tables(db):
    snapshots = {}
    for table in TABLES_TO_SNAPSHOT:
        if not _table_exists(db, table):
            continue
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
        'public_site_login_required',
        'visitor_login_enabled',
        'visitor_login_days',
    ]
    with app.app_context():
        original = {key: get_setting(key, None) for key in keys}
        db = get_db()
        original_tables = _snapshot_tables(db)
        for table in TABLE_DELETE_ORDER:
            if _table_exists(db, table):
                db.execute(f"DELETE FROM {table}")
        set_settings({
            'public_site_login_required': '0',
            'visitor_login_enabled': '0',
            'visitor_login_days': '7',
        })
        db.commit()
        reset_auth_rate_limits()
    yield
    with app.app_context():
        set_settings({key: value for key, value in original.items() if value is not None})
        delete_settings([key for key, value in original.items() if value is None])
        db = get_db()
        for table in TABLE_DELETE_ORDER:
            if _table_exists(db, table):
                db.execute(f"DELETE FROM {table}")
        for table in TABLE_INSERT_ORDER:
            _restore_table(db, table, original_tables.get(table, []))
        db.commit()
        reset_auth_rate_limits()


def _visitor_login(client, username='alice1', password='abc123', next_url='/', action='login'):
    return client.post(
        '/login',
        data={'username': username, 'password': password, 'next': next_url, 'action': action},
        follow_redirects=False,
    )


def _visitor_register(client, username='alice1', password='abc123', next_url='/'):
    return _visitor_login(client, username=username, password=password, next_url=next_url, action='register')


def _login_visitor(client, username='alice1', password='abc123'):
    r = _visitor_register(client, username=username, password=password)
    assert r.status_code in (302, 303)
    return client


def _admin_login(client):
    r = _visitor_login(client, username='Acidmoon', password='admin123', next_url='/admin')
    assert r.status_code in (302, 303)
    return client


def test_homepage_is_public_by_default(client, reset_settings):
    r = client.get('/')
    assert r.status_code == 200


def test_homepage_redirects_when_public_site_login_required(client, reset_settings):
    with client.application.app_context():
        set_settings({'public_site_login_required': '1'})
    r = client.get('/')
    assert r.status_code in (302, 303)
    assert '/login' in r.location


def test_login_page_returns_200(client, reset_settings):
    r = client.get('/login')
    assert r.status_code == 200
    html = r.data.decode('utf-8')
    assert '账号登录' in html
    assert '注册' in html
    assert 'current-password' in html
    assert client.get('/login?mode=register').status_code == 200
    assert 'new-password' in client.get('/login?mode=register').data.decode('utf-8')


def test_new_visitor_can_register_and_login(client, reset_settings):
    r = _visitor_register(client, username='user1', password='abc123')
    assert r.status_code in (302, 303)
    assert 'visitor_token' in r.headers.get('Set-Cookie', '')
    client.post('/logout')
    r = _visitor_login(client, username='user1', password='abc123')
    assert r.status_code in (302, 303)
    assert 'visitor_token' in r.headers.get('Set-Cookie', '')


def test_login_does_not_create_new_visitor(client, reset_settings):
    r = _visitor_login(client, username='missing1', password='abc123')
    assert r.status_code == 200
    assert '用户名不存在' in r.data.decode('utf-8')


def test_existing_visitor_wrong_password_rejected(client, reset_settings):
    _visitor_register(client, username='user1', password='abc123')
    fresh_client = client.application.test_client()
    r = _visitor_login(fresh_client, username='user1', password='zzz999')
    assert r.status_code == 200
    html = r.data.decode('utf-8')
    assert '密码错误' in html or '重新输入' in html


def test_username_password_validation(client, reset_settings):
    r = _visitor_register(client, username='中文', password='abc123')
    assert r.status_code == 200
    html = r.data.decode('utf-8')
    assert '用户名只能使用英文字母和数字' in html

    r = _visitor_register(client, username='user2', password='超长密码123456')
    assert r.status_code in (302, 303)
    assert 'visitor_token' in r.headers.get('Set-Cookie', '')

    fresh_client = client.application.test_client()
    r = _visitor_register(fresh_client, username='user3', password='x' * 129)
    assert r.status_code == 200
    assert '密码太长了' in r.data.decode('utf-8')


def test_login_next_url_rejects_external_redirect(client, reset_settings):
    r = _visitor_register(client, username='safe1', password='abc123', next_url='https://evil.example/')
    assert r.status_code in (302, 303)
    assert r.location == '/'


def test_public_auth_api_rate_limited_by_ip(client, reset_settings, monkeypatch):
    monkeypatch.setattr(config, 'VISITOR_AUTH_MAX_ATTEMPTS', 2)
    monkeypatch.setattr(config, 'VISITOR_AUTH_WINDOW_SECONDS', 900)
    payload = {'username': 'missing1', 'password': 'abc123'}
    for _ in range(2):
        r = client.post('/api/auth/login', json=payload)
        assert r.status_code == 400
    r = client.post('/api/auth/login', json=payload)
    assert r.status_code == 429
    assert r.get_json()['error'] == '操作过于频繁，请稍后再试'


def test_secure_cookie_attributes_for_auth(client, reset_settings, monkeypatch):
    monkeypatch.setattr(config, 'COOKIE_SECURE', True)
    original_session_cookie_secure = client.application.config['SESSION_COOKIE_SECURE']
    client.application.config['SESSION_COOKIE_SECURE'] = True
    try:
        r = _visitor_login(client, username='Acidmoon', password='admin123', next_url='/admin')
        cookies = r.headers.getlist('Set-Cookie')
        visitor_cookie = next(cookie for cookie in cookies if cookie.startswith('visitor_token='))
        session_cookie = next(cookie for cookie in cookies if cookie.startswith('session='))
        assert 'HttpOnly' in visitor_cookie
        assert 'Secure' in visitor_cookie
        assert 'SameSite=Lax' in visitor_cookie
        assert 'HttpOnly' in session_cookie
        assert 'Secure' in session_cookie
        assert 'SameSite=Lax' in session_cookie
    finally:
        client.application.config['SESSION_COOKIE_SECURE'] = original_session_cookie_secure


def test_expired_visitor_token_is_rejected_and_deleted(client, reset_settings):
    slug = None
    with client.application.app_context():
        article = create_article_draft(
            f'过期登录测试 {uuid.uuid4().hex[:8]}',
            '测试',
            '需要登录评论',
        )
        slug = article['slug']
        publish_article(slug)
    _login_visitor(client, username='expire1', password='abc123')
    with client.application.app_context():
        db = get_db()
        db.execute("UPDATE visitor_tokens SET expires_at=0")
        db.commit()
    try:
        r = client.post(f'/api/article/{slug}/comments', json={'content': '过期登录评论'})
        assert r.status_code == 401
        assert r.get_json()['error'] == '请先登录'
        with client.application.app_context():
            db = get_db()
            assert db.execute("SELECT COUNT(*) AS c FROM visitor_tokens").fetchone()['c'] == 0
    finally:
        if slug:
            with client.application.app_context():
                svc_delete_article(slug)


def test_visitor_last_seen_update_is_throttled(client, reset_settings):
    _login_visitor(client, username='touch1', password='abc123')
    with client.application.app_context():
        db = get_db()
        db.execute("UPDATE visitor_users SET last_seen_at=?, last_ip=?", ('2099-01-01T00:00:00', '127.0.0.1'))
        db.execute("UPDATE visitor_tokens SET last_seen_at=?, last_ip=?", ('2099-01-01T00:00:00', '127.0.0.1'))
        db.commit()
    r = client.get('/')
    assert r.status_code == 200
    with client.application.app_context():
        db = get_db()
        assert db.execute("SELECT last_seen_at FROM visitor_users WHERE username='touch1'").fetchone()['last_seen_at'] == '2099-01-01T00:00:00'
        db.execute("UPDATE visitor_users SET last_seen_at=?", ('2000-01-01T00:00:00',))
        db.execute("UPDATE visitor_tokens SET last_seen_at=?", ('2000-01-01T00:00:00',))
        db.commit()
    r = client.get('/')
    assert r.status_code == 200
    with client.application.app_context():
        db = get_db()
        assert db.execute("SELECT last_seen_at FROM visitor_users WHERE username='touch1'").fetchone()['last_seen_at'] != '2000-01-01T00:00:00'


def test_admin_login_page_not_blocked(client, reset_settings):
    r = client.get('/admin/login')
    assert r.status_code == 200


def test_admin_routes_still_require_admin_login(client, reset_settings):
    r = client.get('/admin', follow_redirects=True)
    assert '登录' in r.data.decode('utf-8')


def test_acidmoon_user_is_admin(client, reset_settings):
    _admin_login(client)
    r = client.get('/admin')
    assert r.status_code == 200
    assert '后台' in r.data.decode('utf-8')


def test_config_admin_password_resets_existing_acidmoon(client, reset_settings):
    _visitor_register(client, username='Acidmoon', password='oldpass')
    client.post('/logout')
    _admin_login(client)
    r = client.get('/admin')
    assert r.status_code == 200
    assert '后台' in r.data.decode('utf-8')


def test_regular_user_cannot_access_admin(client, reset_settings):
    _visitor_register(client, username='user1', password='abc123')
    r = client.get('/admin', follow_redirects=False)
    assert r.status_code in (302, 303)
    assert '/login' in r.location
    r = _visitor_login(client, username='user1', password='abc123', next_url='/admin')
    assert r.status_code == 403
    assert '当前账号没有管理员权限' in r.data.decode('utf-8')


def test_admin_login_next_url_rejects_external_redirect(client, reset_settings):
    r = client.post(
        '/login',
        data={'username': 'Acidmoon', 'password': 'admin123', 'next': 'https://evil.example/', 'action': 'login'},
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    assert r.location == '/'


def test_unified_login_rate_limited_by_ip(client, reset_settings, monkeypatch):
    monkeypatch.setattr(config, 'VISITOR_AUTH_MAX_ATTEMPTS', 2)
    monkeypatch.setattr(config, 'VISITOR_AUTH_WINDOW_SECONDS', 900)
    for _ in range(2):
        r = _visitor_login(client, username='Acidmoon', password='wrong', next_url='/admin')
        assert r.status_code == 200
    r = _visitor_login(client, username='Acidmoon', password='wrong', next_url='/admin')
    assert r.status_code == 429
    assert '操作过于频繁' in r.data.decode('utf-8')


def test_admin_session_expires(client, reset_settings, monkeypatch):
    monkeypatch.setattr(config, 'ADMIN_SESSION_MAX_AGE_SECONDS', 1)
    _admin_login(client)
    with client.session_transaction() as sess:
        sess['admin_login_at'] = time.time() - 10
    r = client.get('/admin', follow_redirects=False)
    assert r.status_code in (302, 303)
    assert '/login' in r.location


def test_all_core_modules_registered(app):
    expected = {'activity_heatmap', 'article_list', 'daily_quote', 'pagination', 'tag_filter'}
    registry = get_module_registry(app)
    actual = set(registry.home_sections.keys())
    assert expected == actual
    assert registry.admin_modules['daily_quote'].handler is not None


def test_admin_nav_groups_keep_flat_nav_compatible(app):
    with app.app_context():
        groups = build_admin_nav_groups()
        flat_nav = build_admin_nav()
    assert [group['id'] for group in groups] == ['content', 'home', 'access', 'system']
    flat = [item for group in groups for item in group['items']]
    assert flat_nav == flat


def test_static_css_served(client, reset_settings):
    r = client.get('/static/css/style.css')
    assert r.status_code == 200
    assert '@import' in r.data.decode('utf-8')


def test_feature_scripts_are_served(client, reset_settings):
    for path in [
        '/static/js/auth-modal.js',
        '/static/js/article-social.js',
        '/static/js/editor.js',
    ]:
        r = client.get(path)
        assert r.status_code == 200
        assert 'function' in r.data.decode('utf-8')

def test_public_chat_routes_are_registered(client, reset_settings):
    assert client.get('/chat').status_code in {200, 302}
    assert client.get('/api/chat/sessions').status_code == 401


def test_library_is_not_linked_or_mounted(client, reset_settings):
    for path in ['/']:
        r = client.get(path)
        assert r.status_code == 200
        html = r.data.decode('utf-8')
        assert '/library/' not in html
        assert '图书馆' not in html

    _admin_login(client)
    for path in ['/admin', '/admin/access-settings', '/admin/modules/daily_quote']:
        r = client.get(path)
        assert r.status_code == 200
        html = r.data.decode('utf-8')
        assert '/library/' not in html
        assert '图书馆' not in html

    assert client.get('/library/').status_code == 404


def test_access_settings_defaults(app, reset_settings):
    with app.app_context():
        settings = get_access_settings()
        assert settings['public_site_login_required'] is False
        assert settings['visitor_login_enabled'] is False
        assert settings['visitor_login_days'] == 7


def test_access_settings_reads_legacy_visitor_login_key(app, reset_settings):
    with app.app_context():
        delete_settings(['public_site_login_required'])
        set_settings({'visitor_login_enabled': '1'})
        settings = get_access_settings()
        assert settings['public_site_login_required'] is True

def test_public_pages_open_to_guests_by_default(client, reset_settings):
    for path in ['/', '/search?q=博客', '/article/这是我的博客的第一篇文章']:
        r = client.get(path)
        assert r.status_code == 200

def test_public_pages_blocked_when_public_site_login_required(client, reset_settings):
    with client.application.app_context():
        set_settings({'public_site_login_required': '1'})
    for path in ['/', '/search?q=博客', '/article/这是我的博客的第一篇文章']:
        r = client.get(path)
        assert r.status_code in (302, 303)


def test_admin_login_open_to_guests(client, reset_settings):
    r = client.get('/admin/login')
    assert r.status_code == 200


def test_nav_and_layout_pages_require_admin_login(client, reset_settings):
    for path in ['/admin/layout', '/admin/access-settings']:
        r = client.get(path, follow_redirects=True)
        assert '登录' in r.data.decode('utf-8')


def test_chat_settings_page_available_for_logged_in_admin(login, reset_settings):
    r = login.get('/admin/chat-settings')
    assert r.status_code == 200


def test_access_settings_page_for_logged_in_admin(login, reset_settings):
    r = login.get('/admin/access-settings')
    assert r.status_code == 200
    assert '访问设置' in r.data.decode('utf-8')


def test_admin_article_commands_round_trip(client, reset_settings):
    _admin_login(client)
    title = f'测试草稿 {uuid.uuid4().hex[:8]}'
    r = client.post(
        '/admin/new',
        data={'title': title, 'tags': '测试,架构', 'content': '第一版内容'},
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    slug = unquote(r.location.rstrip('/').rsplit('/', 1)[-1])
    try:
        with client.application.app_context():
            article = get_article_meta(slug, published_only=False)
            assert article is not None
            assert article['title'] == title
            assert read_article_file(slug) == '第一版内容'

        r = client.post(
            f'/admin/edit/{slug}',
            data={'title': title + ' 更新', 'tags': '测试', 'content': '第二版内容'},
            follow_redirects=False,
        )
        assert r.status_code in (302, 303)
        with client.application.app_context():
            article = get_article_meta(slug, published_only=False)
            assert article['title'] == title + ' 更新'
            assert read_article_file(slug) == '第二版内容'
    finally:
        client.post(f'/admin/delete/{slug}', follow_redirects=False)
        with client.application.app_context():
            assert get_article_meta(slug, published_only=False) is None
            assert read_article_file(slug) is None


def test_home_layout_save_round_trip(client, reset_settings):
    _admin_login(client)
    path = config.HOME_LAYOUT_PATH
    original = path.read_text(encoding='utf-8') if path.exists() else None
    try:
        r = client.post(
            '/admin/layout',
            data={
                'hero_label': '测试标签',
                'hero_title': '测试标题',
                'hero_subtitle': '测试副标题',
                'section_order': 'article_list\npagination',
                'section_enabled_article_list': 'on',
                'section_enabled_pagination': 'on',
                'quotes': '测试一言',
            },
            follow_redirects=False,
        )
        assert r.status_code in (302, 303)
        saved = json.loads(path.read_text(encoding='utf-8'))
        assert saved['hero']['_default']['title'] == '测试标题'
        assert saved['quotes'] == ['测试一言']
        assert saved['section_visibility']['article_list'] is True
    finally:
        if original is None:
            path.unlink(missing_ok=True)
        else:
            path.write_text(original, encoding='utf-8')


def test_comment_post_requires_login_when_site_is_public(client, reset_settings):
    slug = None
    with client.application.app_context():
        article = create_article_draft(
            f'评论登录测试 {uuid.uuid4().hex[:8]}',
            '测试',
            '公开浏览，评论登录',
        )
        slug = article['slug']
        publish_article(slug)
    try:
        assert client.get(f'/article/{slug}').status_code == 200
        r = client.post(f'/api/article/{slug}/comments', json={'content': '匿名评论'})
        assert r.status_code == 401
        assert r.get_json()['error'] == '请先登录'
    finally:
        if slug:
            with client.application.app_context():
                svc_delete_article(slug)


def test_comment_delete_forbidden_for_non_author(client, reset_settings):
    slug = None
    with client.application.app_context():
        article = create_article_draft(
            f'评论权限测试 {uuid.uuid4().hex[:8]}',
            '测试',
            '可评论内容',
        )
        slug = article['slug']
        publish_article(slug)
    try:
        _login_visitor(client, username='aliceperm', password='abc123')
        r = client.post(f'/api/article/{slug}/comments', json={'content': '只有作者可删'})
        assert r.status_code == 200
        comment_id = r.get_json()['comment']['id']
        client.post('/logout')
        _login_visitor(client, username='bobperm', password='abc123')
        r = client.delete(f'/api/comments/{comment_id}')
        assert r.status_code == 403
    finally:
        if slug:
            with client.application.app_context():
                svc_delete_article(slug)


def test_like_toggle_for_logged_in_visitor(client, reset_settings):
    slug = None
    with client.application.app_context():
        article = create_article_draft(
            f'点赞测试 {uuid.uuid4().hex[:8]}',
            '测试',
            '可点赞内容',
        )
        slug = article['slug']
        publish_article(slug)
    try:
        _login_visitor(client, username='likeuser', password='abc123')
        r = client.post(f'/api/article/{slug}/like')
        assert r.status_code == 200
        assert r.get_json() == {'liked': True, 'count': 1}
        r = client.post(f'/api/article/{slug}/like')
        assert r.status_code == 200
        assert r.get_json() == {'liked': False, 'count': 0}
    finally:
        if slug:
            with client.application.app_context():
                svc_delete_article(slug)
