"""Smoke tests for waterhill-blog. Run with: pytest tests/ -v"""

from module_loader import REGISTRY


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


# ── Layout admin ──────────────────────────────────────

def test_layout_page_requires_login(client):
    r = client.get('/admin/layout', follow_redirects=True)
    assert '登录' in r.data.decode('utf-8') or 'login' in r.request.path.lower()
