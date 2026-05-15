from .admin import bp as admin_bp
from .public import bp as public_bp


def register_blueprints(app):
    app.register_blueprint(public_bp)
    app.register_blueprint(admin_bp)
