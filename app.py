from flask import Flask

import config
from models import init_db
from module_loader import load_modules
from routes import register_blueprints
from services.admin_modules import build_admin_nav


def create_app():
    app = Flask(__name__)
    app.config.from_object(config)
    app.secret_key = config.SECRET_KEY

    config.ensure_directories()
    init_db()
    load_modules(app)

    @app.context_processor
    def inject_global_admin_nav():
        return {"admin_nav": build_admin_nav()}

    register_blueprints(app)

    return app


app = create_app()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8082, debug=True)
