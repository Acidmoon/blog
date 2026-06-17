from __future__ import annotations

import time
from dataclasses import dataclass
from functools import wraps
from threading import Lock
from urllib.parse import urlsplit

from flask import g, jsonify, redirect, request, session, url_for

import config


ADMIN_SESSION_KEY = 'logged_in'
ADMIN_SESSION_AT_KEY = 'admin_login_at'
AUTH_RATE_LIMIT_MESSAGE = '操作过于频繁，请稍后再试'

_RATE_LIMIT_LOCK = Lock()
_RATE_LIMITS: dict[tuple[str, str], list[float]] = {}


@dataclass(frozen=True)
class AuthIdentity:
    visitor: dict | None
    is_admin: bool
    admin_session_active: bool


class AuthRateLimitError(ValueError):
    pass


def safe_next_url(raw_next: str | None, default_url: str) -> str:
    candidate = str(raw_next or '').strip()
    if not candidate:
        return default_url
    if '\r' in candidate or '\n' in candidate:
        return default_url
    parsed = urlsplit(candidate)
    if parsed.scheme or parsed.netloc:
        return default_url
    if not candidate.startswith('/') or candidate.startswith('//'):
        return default_url
    return candidate


def _rate_limit_key(scope: str, client_key: str | None) -> tuple[str, str]:
    return str(scope or 'auth'), str(client_key or '').strip() or 'unknown'


def _pruned_attempts(attempts: list[float], now_ts: float, window_seconds: int) -> list[float]:
    cutoff = now_ts - max(1, int(window_seconds))
    return [attempt for attempt in attempts if attempt >= cutoff]


def check_auth_rate_limit(
    scope: str,
    client_key: str | None,
    max_attempts: int,
    window_seconds: int,
    now: float | None = None,
) -> None:
    now_ts = time.time() if now is None else now
    key = _rate_limit_key(scope, client_key)
    limit = max(1, int(max_attempts))
    window = max(1, int(window_seconds))
    with _RATE_LIMIT_LOCK:
        attempts = _pruned_attempts(_RATE_LIMITS.get(key, []), now_ts, window)
        _RATE_LIMITS[key] = attempts
        if len(attempts) >= limit:
            raise AuthRateLimitError(AUTH_RATE_LIMIT_MESSAGE)


def record_auth_failure(scope: str, client_key: str | None, window_seconds: int, now: float | None = None) -> None:
    now_ts = time.time() if now is None else now
    key = _rate_limit_key(scope, client_key)
    window = max(1, int(window_seconds))
    with _RATE_LIMIT_LOCK:
        attempts = _pruned_attempts(_RATE_LIMITS.get(key, []), now_ts, window)
        attempts.append(now_ts)
        _RATE_LIMITS[key] = attempts


def record_auth_success(scope: str, client_key: str | None) -> None:
    with _RATE_LIMIT_LOCK:
        _RATE_LIMITS.pop(_rate_limit_key(scope, client_key), None)


def reset_auth_rate_limits() -> None:
    with _RATE_LIMIT_LOCK:
        _RATE_LIMITS.clear()


def mark_admin_authenticated() -> None:
    session[ADMIN_SESSION_KEY] = True
    session[ADMIN_SESSION_AT_KEY] = time.time()
    session.permanent = True


def clear_admin_session() -> None:
    session.pop(ADMIN_SESSION_KEY, None)
    session.pop(ADMIN_SESSION_AT_KEY, None)


def is_admin_authenticated(now: float | None = None) -> bool:
    if not session.get(ADMIN_SESSION_KEY):
        return False
    now_ts = time.time() if now is None else now
    login_at = session.get(ADMIN_SESSION_AT_KEY)
    if login_at is None:
        session[ADMIN_SESSION_AT_KEY] = now_ts
        return True
    try:
        login_at_ts = float(login_at)
    except (TypeError, ValueError):
        clear_admin_session()
        return False
    if now_ts - login_at_ts > config.ADMIN_SESSION_MAX_AGE_SECONDS:
        clear_admin_session()
        return False
    return True


def current_identity() -> AuthIdentity:
    cached = getattr(g, 'auth_identity', None)
    if cached is not None:
        return cached
    from services.visitor_auth import current_visitor

    visitor = current_visitor()
    admin_session_active = is_admin_authenticated()
    identity = AuthIdentity(
        visitor=visitor,
        is_admin=admin_session_active,
        admin_session_active=admin_session_active,
    )
    g.auth_identity = identity
    return identity


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if is_admin_authenticated():
            return f(*args, **kwargs)
        if request.path.startswith('/admin/api/') or request.is_json:
            return jsonify({'error': '请先登录管理员账号'}), 401
        next_url = safe_next_url(request.full_path.rstrip('?'), url_for('admin.dashboard'))
        return redirect(url_for('admin.login', next=next_url))

    return wrapper


login_required = admin_required
