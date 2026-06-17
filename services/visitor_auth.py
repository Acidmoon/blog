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

import config
from models import get_db
from services.access_settings import get_access_settings, is_public_site_login_required


VISITOR_COOKIE_NAME = 'visitor_token'
VISITOR_USERNAME_RE = re.compile(r'^[A-Za-z0-9]{1,12}$')
# 密码已哈希存储，不限制字符；仅设一个宽松上限防止超长输入拖慢哈希
MAX_PASSWORD_LENGTH = 128


class VisitorAuthError(ValueError):
    pass


def normalize_username(username: str) -> str:
    return str(username or '').strip().lower()


def validate_visitor_credentials(username: str, password: str) -> tuple[str, str]:
    normalized_username = normalize_username(username)
    # 密码原样保留（含特殊字符、空格、大小写），不做 strip 或字符限制
    raw_password = str(password or '')
    if not VISITOR_USERNAME_RE.fullmatch(normalized_username):
        raise VisitorAuthError('用户名只能使用英文字母和数字，长度 1-12 位')
    if not raw_password:
        raise VisitorAuthError('密码不能为空')
    if len(raw_password) > MAX_PASSWORD_LENGTH:
        raise VisitorAuthError(f'密码太长了，最多 {MAX_PASSWORD_LENGTH} 位')
    return normalized_username, raw_password


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode('utf-8')).hexdigest()


def _now_text() -> str:
    return datetime.now().isoformat(timespec='seconds')


def _client_ip() -> str:
    return request.headers.get('X-Forwarded-For', request.remote_addr or '').split(',')[0].strip()


def _parse_seen_at(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)).timestamp()
    except ValueError:
        return None


def _row_get(row, key: str, default=None):
    if isinstance(row, dict):
        return row.get(key, default)
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return default


def _should_touch_activity(row: dict, client_ip: str, now_ts: float) -> bool:
    if client_ip and client_ip != (_row_get(row, 'last_ip') or ''):
        return True
    last_seen_ts = _parse_seen_at(_row_get(row, 'last_seen_at'))
    if last_seen_ts is None:
        return True
    return now_ts - last_seen_ts >= config.VISITOR_LAST_SEEN_WRITE_INTERVAL_SECONDS


def _create_visitor(username: str, password: str, client_ip: str = '') -> dict:
    password_hash = generate_password_hash(password)
    now = _now_text()
    conn = get_db()
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
        'is_admin': False,
        'created_at': now,
        'last_ip': client_ip,
        'last_seen_at': now,
    }


def _authenticate_existing_visitor(username: str, password: str, client_ip: str = '') -> dict:
    username, password = validate_visitor_credentials(username, password)
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM visitor_users WHERE username=?",
        (username,),
    ).fetchone()
    if not row:
        raise VisitorAuthError('用户名不存在，请先注册')
    now = _now_text()
    if not check_password_hash(row['password_hash'], password):
        raise VisitorAuthError('密码错误，请重新输入')
    is_configured_admin = is_admin_username(username)
    conn.execute(
        "UPDATE visitor_users SET is_admin=?, last_ip=?, last_seen_at=? WHERE id=?",
        (1 if is_configured_admin else int(row['is_admin']), client_ip, now, row['id']),
    )
    conn.commit()
    visitor = dict(row)
    visitor['is_admin'] = bool(is_configured_admin or visitor.get('is_admin'))
    return visitor


def _visitor_exists(username: str) -> bool:
    conn = get_db()
    row = conn.execute(
        "SELECT 1 FROM visitor_users WHERE username=?",
        (username,),
    ).fetchone()
    return row is not None


def authenticate_or_create_visitor(username: str, password: str, client_ip: str = '') -> dict:
    """Backward-compatible name for explicit visitor sign-in."""
    return _authenticate_existing_visitor(username, password, client_ip)


def purge_expired_visitor_tokens(now: float | None = None) -> None:
    now_ts = time.time() if now is None else now
    conn = get_db()
    conn.execute("DELETE FROM visitor_tokens WHERE expires_at<=?", (now_ts,))
    conn.commit()


def issue_visitor_token(user_id: int, client_ip: str = '', now: float | None = None, days: int | None = None) -> tuple[str, float]:
    now_ts = time.time() if now is None else now
    if days is None:
        days = get_access_settings()['visitor_login_days']
    expires_at = now_ts + max(1, int(days)) * 24 * 60 * 60
    raw_token = secrets.token_urlsafe(32)
    token_hash = _hash_token(raw_token)
    now_text = _now_text()
    purge_expired_visitor_tokens(now_ts)
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
        secure=config.COOKIE_SECURE,
        samesite='Lax',
        path='/',
    )
    return response


def clear_visitor_cookie(response):
    response.delete_cookie(VISITOR_COOKIE_NAME, path='/', samesite='Lax')
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
            vu.is_admin AS is_admin,
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
    client_ip = _client_ip()
    if _should_touch_activity(row, client_ip, now_ts):
        now_text = _now_text()
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
        'is_admin': bool(row['is_admin']),
        'created_at': row['created_at'],
        'last_ip': row['last_ip'],
        'last_seen_at': row['last_seen_at'],
    }


def current_visitor() -> dict | None:
    if hasattr(g, 'visitor_user'):
        return g.visitor_user
    visitor = get_visitor_from_token(request.cookies.get(VISITOR_COOKIE_NAME))
    if visitor is None:
        from services.auth import is_admin_authenticated

        if is_admin_authenticated():
            visitor = _ensure_admin_visitor(_client_ip())
    g.visitor_user = visitor
    return visitor


def visitor_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not is_public_site_login_required():
            return f(*args, **kwargs)
        if not current_visitor():
            if request.path.startswith('/api/'):
                return {'error': '请先登录'}, 401
            from services.auth import safe_next_url

            next_url = safe_next_url(request.full_path.rstrip('?'), url_for('public.index'))
            return redirect(url_for('public.login', next=next_url))
        return f(*args, **kwargs)
    return wrapper


def login_visitor(username: str, password: str) -> tuple[dict, str, float]:
    return login_existing_visitor(username, password)


def register_visitor(username: str, password: str) -> tuple[dict, str, float]:
    """Explicit sign-up: fail if the username is already taken."""
    if is_admin_username(username):
        raise VisitorAuthError('该用户名为系统保留，请换一个')
    username, password = validate_visitor_credentials(username, password)
    conn = get_db()
    existing = conn.execute(
        "SELECT 1 FROM visitor_users WHERE username=?",
        (username,),
    ).fetchone()
    if existing:
        raise VisitorAuthError('该用户名已被注册，请直接登录或换一个')
    client_ip = _client_ip()
    visitor = _create_visitor(username, password, client_ip)
    token, expires_at = issue_visitor_token(visitor['id'], client_ip)
    return visitor, token, expires_at


def login_existing_visitor(username: str, password: str) -> tuple[dict, str, float]:
    """Explicit sign-in: fail if the username does not exist."""
    username, password = validate_visitor_credentials(username, password)
    client_ip = _client_ip()
    try:
        visitor = _authenticate_existing_visitor(username, password, client_ip)
    except VisitorAuthError as exc:
        if is_admin_username(username):
            try:
                return authenticate_admin(username, password)
            except VisitorAuthError:
                pass
        raise exc
    token, expires_at = issue_visitor_token(visitor['id'], client_ip)
    return visitor, token, expires_at


def is_admin_username(username: str) -> bool:
    """The admin username is reserved; logging in as it requires the admin password."""
    return normalize_username(username) == config.ADMIN_USERNAME


def _ensure_admin_visitor(client_ip: str = '') -> dict:
    """Create or fetch the admin's visitor_users row so the admin shares one
    identity for comments/likes. The stored password hash is kept in sync with
    the current ADMIN_PASSWORD so a changed admin password still authenticates."""
    conn = get_db()
    now = _now_text()
    row = conn.execute(
        "SELECT * FROM visitor_users WHERE username=?",
        (config.ADMIN_USERNAME,),
    ).fetchone()
    password_hash = generate_password_hash(config.ADMIN_PASSWORD)
    if row:
        conn.execute(
            "UPDATE visitor_users SET password_hash=?, is_admin=1, last_ip=?, last_seen_at=? WHERE id=?",
            (password_hash, client_ip, now, row['id']),
        )
        conn.commit()
        return {'id': row['id'], 'username': config.ADMIN_USERNAME, 'is_admin': True}
    cur = conn.execute(
        """
        INSERT INTO visitor_users (username, password_hash, is_admin, created_at, last_ip, last_seen_at)
        VALUES (?, ?, 1, ?, ?, ?)
        """,
        (config.ADMIN_USERNAME, password_hash, now, client_ip, now),
    )
    conn.commit()
    return {'id': cur.lastrowid, 'username': config.ADMIN_USERNAME, 'is_admin': True}


def ensure_configured_admin_user(client_ip: str = '') -> dict:
    """Ensure the configured admin account exists and has admin privileges."""
    return _ensure_admin_visitor(client_ip)


def authenticate_admin(username: str, password: str | None = None) -> tuple[dict, str, float]:
    """Authenticate the configured admin account.

    Raises VisitorAuthError if the password is wrong. On success, syncs the
    admin's visitor_users row and issues a visitor token.
    """
    if password is None:
        password = username
        username = config.ADMIN_USERNAME
    if not is_admin_username(username):
        raise VisitorAuthError('管理员用户名错误')
    if not secrets.compare_digest(str(password or ''), str(config.ADMIN_PASSWORD or '')):
        raise VisitorAuthError('管理密码错误')
    client_ip = _client_ip()
    visitor = _ensure_admin_visitor(client_ip)
    token, expires_at = issue_visitor_token(visitor['id'], client_ip)
    return visitor, token, expires_at


def revoke_current_visitor_token() -> None:
    raw_token = request.cookies.get(VISITOR_COOKIE_NAME)
    if not raw_token:
        return
    conn = get_db()
    conn.execute("DELETE FROM visitor_tokens WHERE token_hash=?", (_hash_token(raw_token),))
    conn.commit()
