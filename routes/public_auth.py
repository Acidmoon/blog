"""Visitor login/logout and inline auth API routes."""

from flask import flash, jsonify, make_response, redirect, render_template, request, url_for

import config
from routes.public_utils import client_ip
from services.auth import (
    AuthRateLimitError,
    check_auth_rate_limit,
    clear_admin_session,
    current_identity,
    mark_admin_authenticated,
    record_auth_failure,
    record_auth_success,
    safe_next_url,
)
from services.request_security import rotate_csrf_token
from services.visitor_auth import (
    VisitorAuthError,
    clear_visitor_cookie,
    current_visitor,
    login_existing_visitor,
    register_visitor,
    revoke_current_visitor_token,
    set_visitor_cookie,
)


def _auth_mode(raw_mode: str | None) -> str:
    return 'register' if raw_mode == 'register' else 'login'


def _public_auth_scope(mode: str) -> str:
    return 'visitor_register' if mode == 'register' else 'visitor_login'


def _rate_limit_public_auth(scope: str, ip: str) -> None:
    check_auth_rate_limit(
        scope,
        ip,
        config.VISITOR_AUTH_MAX_ATTEMPTS,
        config.VISITOR_AUTH_WINDOW_SECONDS,
    )


def _requires_admin(next_url: str) -> bool:
    return next_url == '/admin' or next_url.startswith('/admin/')


def register_routes(bp):
    @bp.route('/login', methods=['GET', 'POST'])
    def login():
        default_next = url_for('public.index')
        next_url = safe_next_url(request.values.get('next'), default_next)
        if current_identity().is_admin:
            return redirect(safe_next_url(request.args.get('next'), url_for('admin.dashboard')))
        if current_visitor() and not _requires_admin(next_url):
            return redirect(safe_next_url(request.args.get('next'), default_next))
        error = ''
        mode = _auth_mode(request.form.get('action') if request.method == 'POST' else request.args.get('mode'))
        if request.method == 'POST':
            username = request.form.get('username', '')
            password = request.form.get('password', '')
            scope = _public_auth_scope(mode)
            ip = client_ip()
            try:
                _rate_limit_public_auth(scope, ip)
                if mode == 'register':
                    visitor, token, expires_at = register_visitor(username, password)
                else:
                    visitor, token, expires_at = login_existing_visitor(username, password)
            except AuthRateLimitError as exc:
                error = str(exc)
                return render_template(
                    'login.html',
                    error=error,
                    next_url=next_url,
                    auth_mode=mode,
                ), 429
            except VisitorAuthError as exc:
                record_auth_failure(scope, ip, config.VISITOR_AUTH_WINDOW_SECONDS)
                error = str(exc)
            else:
                record_auth_success(scope, ip)
                if visitor.get('is_admin'):
                    mark_admin_authenticated()
                else:
                    clear_admin_session()
                    if _requires_admin(next_url):
                        error = '当前账号没有管理员权限'
                        return render_template(
                            'login.html',
                            error=error,
                            next_url=next_url,
                            auth_mode='login',
                            admin_context=True,
                        ), 403
                response = make_response(redirect(next_url))
                rotate_csrf_token()
                set_visitor_cookie(response, token, expires_at)
                flash(f'欢迎，{visitor["username"]}', 'success')
                return response
        return render_template(
            'login.html',
            error=error,
            next_url=next_url,
            auth_mode=mode,
        )

    @bp.route('/logout', methods=['POST'])
    def logout():
        revoke_current_visitor_token()
        clear_admin_session()
        response = make_response(redirect(url_for('public.login')))
        clear_visitor_cookie(response)
        return response

    @bp.route('/api/auth/<action>', methods=['POST'])
    def api_auth(action):
        if action not in {'register', 'login'}:
            return jsonify({'error': '未知操作'}), 404
        data = request.get_json(silent=True) or {}
        username = data.get('username', '')
        password = data.get('password', '')
        next_url = safe_next_url(data.get('next'), '')
        scope = _public_auth_scope(action)
        ip = client_ip()
        try:
            _rate_limit_public_auth(scope, ip)
            if action == 'register':
                visitor, token, expires_at = register_visitor(username, password)
            else:
                visitor, token, expires_at = login_existing_visitor(username, password)
        except AuthRateLimitError as exc:
            return jsonify({'error': str(exc)}), 429
        except VisitorAuthError as exc:
            record_auth_failure(scope, ip, config.VISITOR_AUTH_WINDOW_SECONDS)
            return jsonify({'error': str(exc)}), 400
        record_auth_success(scope, ip)
        is_admin = bool(visitor.get('is_admin'))
        if is_admin:
            mark_admin_authenticated()
        else:
            clear_admin_session()
            if _requires_admin(next_url):
                return jsonify({'error': '当前账号没有管理员权限'}), 403
        response = make_response(jsonify({
            'ok': True,
            'username': visitor['username'],
            'is_admin': is_admin,
            'redirect': next_url or None,
        }))
        rotate_csrf_token()
        set_visitor_cookie(response, token, expires_at)
        return response
