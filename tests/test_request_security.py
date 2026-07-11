"""Focused regression coverage for request-origin and proxy trust boundaries."""

from __future__ import annotations

import re
import uuid

import pytest

from services.request_security import CSRF_HEADER, CSRF_SESSION_KEY, client_ip


CSRF_TOKEN_RE = re.compile(r'<meta name="csrf-token" content="([^"]+)">')


@pytest.fixture
def strict_csrf_client(app):
    """Create a normal test client while explicitly enforcing production CSRF."""
    original = app.config.get("CSRF_PROTECTION_ENABLED")
    app.config["CSRF_PROTECTION_ENABLED"] = True
    try:
        yield app.test_client()
    finally:
        app.config["CSRF_PROTECTION_ENABLED"] = original


def _csrf_token(response) -> str:
    match = CSRF_TOKEN_RE.search(response.get_data(as_text=True))
    assert match, "页面必须公开当前会话的 CSRF 令牌"
    return match.group(1)


def test_form_and_json_state_changes_require_a_session_csrf_token(strict_csrf_client):
    """A production-mode client cannot submit a form or JSON mutation blindly."""
    form_page = strict_csrf_client.get("/admin/login")
    token = _csrf_token(form_page)
    assert 'name="csrf_token"' in form_page.get_data(as_text=True)

    missing_form = strict_csrf_client.post("/admin/login", data={"password": "admin123"})
    assert missing_form.status_code == 400
    assert missing_form.get_json()["error"] == "CSRF 校验失败，请刷新页面后重试"

    missing_json = strict_csrf_client.post(
        "/api/auth/register",
        json={"username": f"csrf{uuid.uuid4().hex[:8]}", "password": "abc123"},
    )
    assert missing_json.status_code == 400
    assert missing_json.get_json()["error"] == "CSRF 校验失败，请刷新页面后重试"

    authenticated = strict_csrf_client.post(
        "/admin/login",
        data={"password": "admin123", "csrf_token": token},
        follow_redirects=False,
    )
    assert authenticated.status_code in {302, 303}
    with strict_csrf_client.session_transaction() as session_data:
        assert session_data[CSRF_SESSION_KEY] != token


def test_json_csrf_header_allows_browser_auth_and_rotates_token(strict_csrf_client):
    """The browser header contract remains usable for the inline auth modal."""
    page = strict_csrf_client.get("/login")
    token = _csrf_token(page)
    response = strict_csrf_client.post(
        "/api/auth/register",
        json={"username": f"api{uuid.uuid4().hex[:8]}", "password": "abc123"},
        headers={CSRF_HEADER: token},
    )
    assert response.status_code == 200
    assert response.get_json()["ok"] is True
    with strict_csrf_client.session_transaction() as session_data:
        assert session_data[CSRF_SESSION_KEY] != token


def test_logout_is_post_only_and_requires_csrf(strict_csrf_client):
    """A cross-site navigation cannot silently revoke a visitor's login."""
    login_page = strict_csrf_client.get("/login")
    token = _csrf_token(login_page)
    login_response = strict_csrf_client.post(
        "/login",
        data={
            "username": f"logout{uuid.uuid4().hex[:6]}",
            "password": "abc123",
            "action": "register",
            "csrf_token": token,
        },
        follow_redirects=False,
    )
    assert login_response.status_code in {302, 303}
    with strict_csrf_client.session_transaction() as session_data:
        rotated_token = session_data[CSRF_SESSION_KEY]

    assert strict_csrf_client.get("/logout").status_code == 405
    assert strict_csrf_client.post("/logout").status_code == 400
    assert strict_csrf_client.post(
        "/logout",
        headers={CSRF_HEADER: rotated_token},
        follow_redirects=False,
    ).status_code in {302, 303}


def test_client_ip_ignores_xff_from_untrusted_direct_peers(app, monkeypatch):
    """An internet client cannot select its own rate-limit or audit IP with XFF."""
    monkeypatch.setitem(app.config, "TRUSTED_PROXY_CIDRS", "")
    with app.test_request_context(
        "/",
        environ_base={"REMOTE_ADDR": "198.51.100.23"},
        headers={"X-Forwarded-For": "203.0.113.99"},
    ):
        assert client_ip() == "198.51.100.23"


def test_client_ip_walks_only_configured_trusted_proxy_chain(app, monkeypatch):
    """Trusted ingress can forward clients without trusting user-supplied hops."""
    monkeypatch.setitem(app.config, "TRUSTED_PROXY_CIDRS", "127.0.0.1/32,10.0.0.0/8")
    with app.test_request_context(
        "/",
        environ_base={"REMOTE_ADDR": "127.0.0.1"},
        headers={"X-Forwarded-For": "198.51.100.24, 10.1.2.3"},
    ):
        assert client_ip() == "198.51.100.24"

    with app.test_request_context(
        "/",
        environ_base={"REMOTE_ADDR": "127.0.0.1"},
        headers={"X-Forwarded-For": "not-an-ip"},
    ):
        assert client_ip() == "127.0.0.1"
