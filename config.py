import os
import shutil
import threading
from pathlib import Path
from datetime import timedelta

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / 'data'

INSECURE_SECRET_KEY = 'change-this-to-a-random-secret-key'
INSECURE_ADMIN_PASSWORD = 'admin123'
EXAMPLE_SECRET_KEY = 'replace-with-a-long-random-secret'
EXAMPLE_ADMIN_PASSWORD = 'replace-with-a-strong-admin-password'

SECRET_KEY = os.environ.get('BLOG_SECRET_KEY', INSECURE_SECRET_KEY)
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD') or os.environ.get('BLOG_ADMIN_PASSWORD', INSECURE_ADMIN_PASSWORD)
# 走统一登录/注册弹窗时，这个用户名 + ADMIN_PASSWORD 即可取得管理员权限
ADMIN_USERNAME = (os.environ.get('ADMIN_USERNAME') or 'Acidmoon').strip().lower()
ADMIN_SESSION_MAX_AGE_SECONDS = int(os.environ.get('ADMIN_SESSION_MAX_AGE_SECONDS', '43200'))

DATABASE = str(DATA_DIR / 'blog.db')
_default_articles_dir = DATA_DIR / 'articles' if (DATA_DIR / 'articles').exists() else BASE_DIR / 'articles'
ARTICLES_DIR = os.environ.get('ARTICLES_DIR') or os.environ.get('BLOG_ARTICLES_DIR') or str(_default_articles_dir)
UPLOAD_DIR = str(BASE_DIR / 'static' / 'images')
CHAT_UPLOAD_DIR = str(DATA_DIR / 'chat_uploads')
DEFAULT_HOME_LAYOUT_PATH = BASE_DIR / 'home_layout.json'
HOME_LAYOUT_PATH = Path(os.environ.get('HOME_LAYOUT_PATH') or DATA_DIR / 'home_layout.json')
QUOTE_CACHE_PATH = DATA_DIR / 'quote_cache.json'

SITE_TITLE = '水浇岭的博客'
SITE_SUBTITLE = '写点有意思的东西'
ARTICLES_PER_PAGE = 10
ASSET_VERSION = os.environ.get('ASSET_VERSION', '2026-07-11-request-security')
COOKIE_SECURE = str(os.environ.get('COOKIE_SECURE', '0')).strip().lower() in {'1', 'true', 'yes', 'on'}
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = os.environ.get('SESSION_COOKIE_SAMESITE', 'Lax')
SESSION_COOKIE_SECURE = COOKIE_SECURE
PERMANENT_SESSION_LIFETIME = timedelta(seconds=ADMIN_SESSION_MAX_AGE_SECONDS)
VISITOR_LAST_SEEN_WRITE_INTERVAL_SECONDS = int(os.environ.get('VISITOR_LAST_SEEN_WRITE_INTERVAL_SECONDS', '300'))
ADMIN_LOGIN_MAX_ATTEMPTS = int(os.environ.get('ADMIN_LOGIN_MAX_ATTEMPTS', '5'))
ADMIN_LOGIN_WINDOW_SECONDS = int(os.environ.get('ADMIN_LOGIN_WINDOW_SECONDS', '900'))
VISITOR_AUTH_MAX_ATTEMPTS = int(os.environ.get('VISITOR_AUTH_MAX_ATTEMPTS', '10'))
VISITOR_AUTH_WINDOW_SECONDS = int(os.environ.get('VISITOR_AUTH_WINDOW_SECONDS', '900'))
VISITOR_TOKEN_PURGE_INTERVAL_SECONDS = int(
    os.environ.get('VISITOR_TOKEN_PURGE_INTERVAL_SECONDS', '3600')
)
# Forwarded client addresses are ignored unless the immediate peer matches one
# of these explicit CIDRs, for example ``127.0.0.1/32,::1/128`` behind Nginx.
TRUSTED_PROXY_CIDRS = os.environ.get('TRUSTED_PROXY_CIDRS', '')
# ``None`` keeps public runtime strict while preserving the isolated legacy test
# suite; a focused test can explicitly set this to True.
CSRF_PROTECTION_ENABLED = None

AI_POLISH_API_BASE = os.environ.get('AI_POLISH_API_BASE', 'https://www.waterhill.cyou/v1').rstrip('/')
AI_POLISH_API_KEY = os.environ.get('AI_POLISH_API_KEY', '')
AI_POLISH_MODEL = os.environ.get('AI_POLISH_MODEL', 'gpt-5.5')
AI_POLISH_TIMEOUT = float(os.environ.get('AI_POLISH_TIMEOUT', '60'))
AI_CHAT_TIMEOUT = float(os.environ.get('AI_CHAT_TIMEOUT', '90'))


def _as_bool(value: str | None) -> bool:
    return str(value or '').strip().lower() in {'1', 'true', 'yes', 'on'}


def is_testing_environment() -> bool:
    """Return whether the process explicitly opted into test-only defaults."""
    return _as_bool(os.environ.get('BLOG_TESTING'))


def validate_security_config(testing: bool = False) -> None:
    """Reject known public credentials outside an explicitly isolated test run."""
    if testing or is_testing_environment():
        return
    if not os.environ.get('BLOG_SECRET_KEY') or _is_placeholder_secret(SECRET_KEY):
        raise RuntimeError('生产启动必须设置随机的 BLOG_SECRET_KEY')
    if (
        not (os.environ.get('ADMIN_PASSWORD') or os.environ.get('BLOG_ADMIN_PASSWORD'))
        or _is_placeholder_secret(ADMIN_PASSWORD)
    ):
        raise RuntimeError('生产启动必须设置非默认的 ADMIN_PASSWORD')


def _is_placeholder_secret(value: str | None) -> bool:
    """Recognize bundled defaults and obvious example values before public startup."""
    normalized = str(value or '').strip().lower()
    return (
        not normalized
        or normalized in {
            INSECURE_SECRET_KEY,
            INSECURE_ADMIN_PASSWORD,
            EXAMPLE_SECRET_KEY,
            EXAMPLE_ADMIN_PASSWORD,
        }
        or normalized.startswith(('replace-with-', 'change-this-', 'example-'))
    )


def _seed_home_layout() -> None:
    """Seed the runtime layout once without ever writing back to tracked source."""
    if HOME_LAYOUT_PATH.exists() or not DEFAULT_HOME_LAYOUT_PATH.exists():
        return
    HOME_LAYOUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(DEFAULT_HOME_LAYOUT_PATH, HOME_LAYOUT_PATH)


def ensure_directories():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    Path(ARTICLES_DIR).mkdir(parents=True, exist_ok=True)
    Path(UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
    Path(CHAT_UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
    _seed_home_layout()
