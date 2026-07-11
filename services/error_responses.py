"""Public error-response policy shared by HTML pages and JSON APIs."""

from __future__ import annotations

from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import HTTPException


_ERROR_COPY = {
    400: ("请求无法处理", "请检查输入后重试。"),
    401: ("需要登录", "请登录后继续操作。"),
    403: ("没有访问权限", "你没有权限执行此操作。"),
    404: ("页面未找到", "你访问的地址不存在，或内容已被移动。"),
    405: ("请求方法不被允许", "请使用页面提供的操作方式重试。"),
    413: ("请求内容过大", "请缩小提交内容后重试。"),
    429: ("操作过于频繁", "请稍后再试。"),
    500: ("服务暂时不可用", "服务遇到了问题，请稍后再试。"),
    502: ("上游服务暂时不可用", "请稍后再试。"),
    503: ("服务暂时不可用", "请稍后再试。"),
    504: ("服务响应超时", "请稍后再试。"),
}


def is_api_request() -> bool:
    """Return whether the current request targets one of the public API prefixes."""
    path = request.path
    return (
        path == "/api"
        or path.startswith("/api/")
        or path == "/admin/api"
        or path.startswith("/admin/api/")
    )


def public_error_copy(status_code: int) -> tuple[str, str]:
    """Return fixed user-facing copy without exposing exception descriptions."""
    return _ERROR_COPY.get(status_code, _ERROR_COPY[500])


def error_response(status_code: int):
    """Render the stable JSON envelope for APIs and a friendly page elsewhere."""
    title, message = public_error_copy(status_code)
    if is_api_request():
        return jsonify({"error": message}), status_code
    return render_template(
        "errors/http_error.html",
        status_code=status_code,
        title=title,
        message=message,
    ), status_code


def register_error_handlers(app: Flask) -> None:
    """Register request error handlers without allowing exception details into responses."""
    @app.errorhandler(HTTPException)
    def handle_http_exception(error: HTTPException):
        return error_response(error.code or 500)

    @app.errorhandler(Exception)
    def handle_unexpected_exception(error: Exception):
        # Keep the traceback in server logs while returning only fixed public copy.
        app.logger.error("Unhandled request error", exc_info=error)
        return error_response(500)
