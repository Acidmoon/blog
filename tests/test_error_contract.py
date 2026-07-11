"""Regression tests for the public HTML and API error-response contracts."""

from __future__ import annotations

import json

import pytest
from flask import abort


@pytest.fixture
def error_app(test_runtime_paths):
    """Create a disposable configured app with deterministic failing endpoints."""
    from app import create_app

    application = create_app({"TESTING": True, "PROPAGATE_EXCEPTIONS": False})

    @application.route("/__error-contract/bad-request")
    def bad_html_request():
        abort(400, description="private bad request marker")

    @application.route("/__error-contract/raise")
    def raise_html_error():
        raise RuntimeError("private html exception marker")

    @application.route("/api/__error-contract/bad-request")
    def bad_api_request():
        abort(400, description="private API bad request marker")

    @application.route("/api/__error-contract/raise")
    def raise_api_error():
        raise RuntimeError("private API exception marker")

    return application


@pytest.mark.parametrize(
    ("path", "status_code", "title", "forbidden_marker"),
    [
        ("/__error-contract/bad-request", 400, "请求无法处理", "private bad request marker"),
        ("/__error-contract/missing", 404, "页面未找到", "private missing marker"),
        ("/__error-contract/raise", 500, "服务暂时不可用", "private html exception marker"),
    ],
)
def test_html_page_errors_use_friendly_templates(error_app, path, status_code, title, forbidden_marker):
    """Browser navigation errors remain HTML and never echo an exception description."""
    response = error_app.test_client().get(path)

    assert response.status_code == status_code
    assert response.mimetype == "text/html"
    assert not response.is_json
    html = response.get_data(as_text=True)
    assert title in html
    assert "返回首页" in html
    assert forbidden_marker not in html


@pytest.mark.parametrize(
    ("path", "status_code", "message", "forbidden_marker"),
    [
        ("/api/__error-contract/bad-request", 400, "请检查输入后重试。", "private API bad request marker"),
        ("/api/__error-contract/missing", 404, "你访问的地址不存在，或内容已被移动。", "private missing marker"),
        ("/api/__error-contract/raise", 500, "服务遇到了问题，请稍后再试。", "private API exception marker"),
    ],
)
def test_api_errors_keep_the_json_error_envelope(error_app, path, status_code, message, forbidden_marker):
    """Formal API paths always return the established one-key JSON error envelope."""
    response = error_app.test_client().get(path)

    assert response.status_code == status_code
    assert response.mimetype == "application/json"
    assert response.get_json() == {"error": message}
    assert forbidden_marker not in json.dumps(response.get_json(), ensure_ascii=False)


def test_csrf_form_failure_keeps_the_existing_json_contract(error_app):
    """CSRF rejects are direct security responses and remain JSON for existing clients."""
    error_app.config["CSRF_PROTECTION_ENABLED"] = True

    response = error_app.test_client().post("/login", data={"action": "login"})

    assert response.status_code == 400
    assert response.mimetype == "application/json"
    assert response.get_json() == {"error": "CSRF 校验失败，请刷新页面后重试"}
