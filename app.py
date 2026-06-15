from flask import Flask, jsonify, redirect, request, url_for

import config
from models import close_db, init_db
from module_loader import load_modules
from routes import register_blueprints
from services.admin_modules import build_admin_nav
from services.ai_chat import is_public_chat_enabled
from services.access_settings import is_visitor_login_enabled
from services.visitor_auth import current_visitor


def create_app():
    app = Flask(__name__)
    app.config.from_object(config)
    app.secret_key = config.SECRET_KEY
    app.json.ensure_ascii = False
    app.config['TEMPLATES_AUTO_RELOAD'] = True

    # Ensure all errors return JSON, not HTML
    @app.errorhandler(400)
    @app.errorhandler(500)
    @app.errorhandler(502)
    def json_error(exc):
        from flask import jsonify
        return jsonify({'error': str(exc)}), exc.code if hasattr(exc, 'code') else 500

    config.ensure_directories()
    init_db()
    load_modules(app)

    # Per-request DB connection lifecycle
    app.teardown_appcontext(close_db)

    @app.context_processor
    def inject_global_admin_nav():
        return {
            "admin_nav": build_admin_nav(),
            "public_chat_enabled": is_public_chat_enabled,
            "visitor_login_enabled": is_visitor_login_enabled,
            "current_visitor": current_visitor,
        }

    register_blueprints(app)

    @app.before_request
    def require_visitor_for_public_site():
        if not is_visitor_login_enabled():
            return None
        endpoint = request.endpoint or ''
        path = request.path or ''
        if path == '/favicon.ico' or endpoint == 'static' or path.startswith('/static/'):
            return None
        if endpoint in {'public.login', 'public.logout', 'admin.login', 'admin.logout'}:
            return None
        if path.startswith('/api/auth/'):
            return None
        if path.startswith('/admin'):
            return None
        if current_visitor():
            return None
        if path.startswith('/api/'):
            return jsonify({'error': '请先登录'}), 401
        return redirect(url_for('public.login', next=request.full_path.rstrip('?')))

    return app


app = create_app()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8082, debug=True)
