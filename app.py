from flask import Flask

import config
from models import close_db, init_db
from module_loader import load_modules
from routes import register_blueprints
from services.admin_modules import build_admin_nav


def create_app():
    app = Flask(__name__)
    app.config.from_object(config)
    app.secret_key = config.SECRET_KEY
    app.json.ensure_ascii = False

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
        return {"admin_nav": build_admin_nav()}

    register_blueprints(app)

    return app


app = create_app()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8082, debug=True)
