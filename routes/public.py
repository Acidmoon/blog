"""Public blueprint assembly.

The routes are split by product capability while keeping the Blueprint name
``public`` so existing URLs and ``url_for('public.*')`` endpoint names stay
stable.
"""

from datetime import datetime

from flask import Blueprint


bp = Blueprint('public', __name__)


@bp.context_processor
def inject_now():
    return {'now': datetime.now}


def _register_routes() -> None:
    from routes.home_api import register_routes as register_home_api_routes
    from routes.public_auth import register_routes as register_auth_routes
    from routes.public_chat import register_routes as register_chat_routes
    from routes.public_pages import register_routes as register_page_routes
    from routes.public_social import register_routes as register_social_routes

    register_auth_routes(bp)
    register_page_routes(bp)
    register_chat_routes(bp)
    register_home_api_routes(bp)
    register_social_routes(bp)


_register_routes()
