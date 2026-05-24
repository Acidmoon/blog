"""Visitor username/password auth for private blog access."""

from __future__ import annotations

import hashlib
import re
import secrets
import time
from datetime import datetime
from functools import wraps

from flask import g, redirect, request, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from models import get_db
from services.access_settings import get_access_settings, is_visitor_login_enabled


VISITOR_COOKIE_NAME = 'visitor_token'
VISITOR_CREDENTIAL_RE = re.compile(r'^[A-Za-z0-9]{1,12}$')


class VisitorAuthError(ValueError):
    pass


def normalize_username(username: str) -> str:
    return str(username or '').strip().lower()


def validate_visitor_credentials(username: str, password: str) -> tuple[str, str]:
    normalized_username = normalize_username(username)
    normalized_password = str(password or '').strip()
    if not VISITOR_CREDENTIAL_RE.fullmatch(normalized_username):
        raise VisitorAuthError('用户名只能使用英文字母和数字，长度 1-12 位')
    if not VISITOR_CREDENTIAL_RE.fullmatch(normalized_password):
        raise VisitorAuthError('密码只能使用英文字母和数字，长度 1-12 位')
    return normalized_username, normalized_password


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode('utf-8')).hexdigest()


def _now_text() -> str:
    return datetime.now().isoformat(timespec='seconds')


def _client_ip() -> str:
    return request.headers.get('X-Forwarded-For', request.remote_addr or '').split(',')[0].strip()


def authenticate_or_create_visitor(username: str, password: str, client_ip: str = '') -> dict:
    username, password = validate_visitor_credentials(username, password)
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM visitor_users WHERE username=?",
        (username,),
    ).fetchone()
    now = _now_text()
    if row:
        if not check_password_hash(row['password_hash'], password):
            raise VisitorAuthError('密码错误，请重新输入')
        conn.execute(
            "UPDATE visitor_users SET last_ip=?, last_seen_at=? WHERE id=?",
            (client_ip, now, row['id']),
        )
        conn.commit()
        return dict(row)

    password_hash = generate_password_hash(password)
    cur = conn.execute(
        """
        INSERT INTO visitor_users (username, password_hash, created_at, last_ip, last_seen_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (username, password_hash, now, client_ip, now),
    )
    conn.commit()
    return {
        'id': cur.lastrowid,
        'username': username,
        'password_hash': password_hash,
        'created_at': now,
        'last_ip': client_ip,
        'last_seen_at': now,
    }


def issue_visitor_token(user_id: int, client_ip: str = '', now: float | None = None, days: int | None = None) -> tuple[str, float]:
    now_ts = time.time() if now is None else now
    if days is None:
        days = get_access_settings()['visitor_login_days']
    expires_at = now_ts + max(1, int(days)) * 24 * 60 * 60
    raw_token = secrets.token_urlsafe(32)
    token_hash = _hash_token(raw_token)
    now_text = _now_text()
    conn = get_db()
    conn.execute(
        """
        INSERT INTO visitor_tokens (user_id, token_hash, expires_at, created_at, last_seen_at, last_ip)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (user_id, token_hash, expires_at, now_text, now_text, client_ip),
    )
    conn.commit()
    return raw_token, expires_at


def set_visitor_cookie(response, token: str, expires_at: float):
    max_age = max(0, int(expires_at - time.time()))
    response.set_cookie(
        VISITOR_COOKIE_NAME,
        token,
        max_age=max_age,
        httponly=True,
        samesite='Lax',
    )
    return response


def clear_visitor_cookie(response):
    response.delete_cookie(VISITOR_COOKIE_NAME, samesite='Lax')
    return response


def get_visitor_from_token(raw_token: str | None, now: float | None = None) -> dict | None:
    if not raw_token:
        return None
    now_ts = time.time() if now is None else now
    conn = get_db()
    row = conn.execute(
        """
        SELECT
            vt.id AS token_id,
            vt.expires_at,
            vu.id AS user_id,
            vu.username AS username,
            vu.created_at AS created_at,
            vu.last_ip AS last_ip,
            vu.last_seen_at AS last_seen_at
        FROM visitor_tokens vt
        JOIN visitor_users vu ON vu.id = vt.user_id
        WHERE vt.token_hash=?
        """,
        (_hash_token(raw_token),),
    ).fetchone()
    if not row:
        return None
    if float(row['expires_at']) <= now_ts:
        conn.execute("DELETE FROM visitor_tokens WHERE id=?", (row['token_id'],))
        conn.commit()
        return None
    now_text = _now_text()
    client_ip = _client_ip()
    conn.execute(
        "UPDATE visitor_tokens SET last_seen_at=?, last_ip=? WHERE id=?",
        (now_text, client_ip, row['token_id']),
    )
    conn.execute(
        "UPDATE visitor_users SET last_seen_at=?, last_ip=? WHERE id=?",
        (now_text, client_ip, row['user_id']),
    )
    conn.commit()
    return {
        'id': row['user_id'],
        'username': row['username'],
        'created_at': row['created_at'],
        'last_ip': row['last_ip'],
        'last_seen_at': row['last_seen_at'],
    }


def current_visitor() -> dict | None:
    if hasattr(g, 'visitor_user'):
        return g.visitor_user
    visitor = get_visitor_from_token(request.cookies.get(VISITOR_COOKIE_NAME))
    g.visitor_user = visitor
    return visitor


def visitor_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not is_visitor_login_enabled():
            return f(*args, **kwargs)
        if not current_visitor():
            if request.path.startswith('/api/'):
                return {'error': '请先登录'}, 401
            return redirect(url_for('public.login', next=request.full_path.rstrip('?')))
        return f(*args, **kwargs)
    return wrapper


def login_visitor(username: str, password: str) -> tuple[dict, str, float]:
    visitor = authenticate_or_create_visitor(username, password, _client_ip())
    token, expires_at = issue_visitor_token(visitor['id'], _client_ip())
    return visitor, token, expires_at


def revoke_current_visitor_token() -> None:
    raw_token = request.cookies.get(VISITOR_COOKIE_NAME)
    if not raw_token:
        return
    conn = get_db()
    conn.execute("DELETE FROM visitor_tokens WHERE token_hash=?", (_hash_token(raw_token),))
    conn.commit()
