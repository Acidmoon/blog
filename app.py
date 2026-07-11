import os
import sqlite3
from pathlib import Path

from flask import Flask, jsonify, redirect, request, url_for

import config
from models import close_db, init_db
from module_loader import load_modules
from routes import register_blueprints
from services.admin_modules import build_admin_nav, build_admin_nav_groups
from services.ai_chat import is_public_chat_enabled
from services.access_settings import is_public_site_login_required
from services.auth import current_identity, safe_next_url
from services.error_responses import register_error_handlers
from services.request_security import (
    CSRF_SAFE_METHODS,
    csrf_failure_response,
    csrf_protection_enabled,
    csrf_request_is_valid,
    csrf_token,
)
from services.search import ensure_article_search_index
from services.visitor_auth import current_visitor


def _healthcheck_data_paths() -> bool:
    """Check required runtime paths without creating or modifying anything."""
    directories = (
        Path(config.DATA_DIR),
        Path(config.ARTICLES_DIR),
        Path(config.UPLOAD_DIR),
        Path(config.CHAT_UPLOAD_DIR),
    )
    for directory in directories:
        if not directory.is_dir() or not os.access(directory, os.R_OK | os.X_OK):
            return False
    layout_path = Path(config.HOME_LAYOUT_PATH)
    return layout_path.is_file() and os.access(layout_path, os.R_OK)


def _healthcheck_database() -> bool:
    """Run a minimal SQLite query through a read-only connection."""
    database_path = Path(config.DATABASE)
    if not database_path.is_file() or not os.access(database_path, os.R_OK):
        return False
    database_uri = f'{database_path.resolve().as_uri()}?mode=ro'
    connection = sqlite3.connect(database_uri, uri=True)
    try:
        connection.execute('SELECT 1').fetchone()
    finally:
        connection.close()
    return True


def create_app(test_config: dict | None = None):
    app = Flask(__name__)
    app.config.from_object(config)
    if test_config:
        app.config.update(test_config)
    config.validate_security_config(testing=bool(app.config.get('TESTING')))
    app.secret_key = app.config['SECRET_KEY']
    app.json.ensure_ascii = False
    app.config['TEMPLATES_AUTO_RELOAD'] = True

    register_error_handlers(app)

    config.ensure_directories()
    app.teardown_appcontext(close_db)
    init_db()
    # Build a legacy FTS index through an app context so its connection is
    # released by the normal teardown path before the server accepts traffic.
    with app.app_context():
        ensure_article_search_index()
    load_modules(app)

    @app.context_processor
    def inject_global_admin_nav():
        return {
            "admin_nav": build_admin_nav(),
            "admin_nav_groups": build_admin_nav_groups(),
            "public_chat_enabled": is_public_chat_enabled,
            "public_site_login_required": is_public_site_login_required,
            "visitor_login_enabled": is_public_site_login_required,
            "current_identity": current_identity,
            "current_visitor": current_visitor,
            "csrf_token": csrf_token,
        }

    register_blueprints(app)

    @app.get('/healthz')
    def healthz():
        """Report process readiness without exposing dependency details."""
        try:
            healthy = _healthcheck_data_paths() and _healthcheck_database()
        except (OSError, sqlite3.Error, ValueError):
            app.logger.warning('Health check dependency validation failed', exc_info=True)
            healthy = False
        if not healthy:
            return jsonify({'status': 'unhealthy'}), 503
        return jsonify({'status': 'ok'})

    @app.before_request
    def require_visitor_for_public_site():
        endpoint = request.endpoint or ''
        path = request.path or ''
        if path in {'/favicon.ico', '/healthz'} or endpoint == 'static' or path.startswith('/static/'):
            return None
        if endpoint in {'public.login', 'public.logout', 'admin.login', 'admin.logout'}:
            return None
        if path.startswith('/api/auth/'):
            return None
        if path.startswith('/admin'):
            return None
        if not is_public_site_login_required():
            return None
        if current_visitor():
            return None
        if path.startswith('/api/'):
            return jsonify({'error': '请先登录'}), 401
        next_url = safe_next_url(request.full_path.rstrip('?'), url_for('public.index'))
        return redirect(url_for('public.login', next=next_url))

    @app.before_request
    def protect_state_changing_requests():
        """Reject unsafe requests that did not originate from this session."""
        if request.method in CSRF_SAFE_METHODS or not csrf_protection_enabled():
            return None
        if csrf_request_is_valid():
            return None
        return csrf_failure_response()

    return app


app = create_app()


if __name__ == '__main__':
    debug = str(os.environ.get('FLASK_DEBUG', '')).strip().lower() in {'1', 'true', 'yes', 'on'}
    app.run(
        host=os.environ.get('FLASK_HOST', '127.0.0.1'),
        port=int(os.environ.get('PORT', '8082')),
        debug=debug,
    )
