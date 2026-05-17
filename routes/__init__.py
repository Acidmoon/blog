from .admin import bp as admin_bp
from .admin_ai import ai_bp as admin_ai_bp
from .public import bp as public_bp


def register_blueprints(app):
    app.register_blueprint(public_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(admin_ai_bp)
