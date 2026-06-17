import os
from pathlib import Path
from datetime import timedelta

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / 'data'

SECRET_KEY = os.environ.get('BLOG_SECRET_KEY', 'change-this-to-a-random-secret-key')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD') or os.environ.get('BLOG_ADMIN_PASSWORD', 'admin123')
# 走统一登录/注册弹窗时，这个用户名 + ADMIN_PASSWORD 即可取得管理员权限
ADMIN_USERNAME = (os.environ.get('ADMIN_USERNAME') or 'Acidmoon').strip().lower()
ADMIN_SESSION_MAX_AGE_SECONDS = int(os.environ.get('ADMIN_SESSION_MAX_AGE_SECONDS', '43200'))

DATABASE = str(DATA_DIR / 'blog.db')
_default_articles_dir = DATA_DIR / 'articles' if (DATA_DIR / 'articles').exists() else BASE_DIR / 'articles'
ARTICLES_DIR = os.environ.get('ARTICLES_DIR') or os.environ.get('BLOG_ARTICLES_DIR') or str(_default_articles_dir)
UPLOAD_DIR = str(BASE_DIR / 'static' / 'images')
HOME_LAYOUT_PATH = BASE_DIR / 'home_layout.json'
QUOTE_CACHE_PATH = DATA_DIR / 'quote_cache.json'

SITE_TITLE = '水浇岭的博客'
SITE_SUBTITLE = '写点有意思的东西'
ARTICLES_PER_PAGE = 10
ASSET_VERSION = os.environ.get('ASSET_VERSION', '2026-06-17-architecture-refactor')
COOKIE_SECURE = str(os.environ.get('COOKIE_SECURE', '0')).strip().lower() in {'1', 'true', 'yes', 'on'}
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = os.environ.get('SESSION_COOKIE_SAMESITE', 'Lax')
SESSION_COOKIE_SECURE = COOKIE_SECURE
PERMANENT_SESSION_LIFETIME = timedelta(seconds=ADMIN_SESSION_MAX_AGE_SECONDS)
VISITOR_LAST_SEEN_WRITE_INTERVAL_SECONDS = int(os.environ.get('VISITOR_LAST_SEEN_WRITE_INTERVAL_SECONDS', '300'))
VISITOR_AUTH_MAX_ATTEMPTS = int(os.environ.get('VISITOR_AUTH_MAX_ATTEMPTS', '10'))
VISITOR_AUTH_WINDOW_SECONDS = int(os.environ.get('VISITOR_AUTH_WINDOW_SECONDS', '900'))

AI_POLISH_API_BASE = os.environ.get('AI_POLISH_API_BASE', 'https://www.waterhill.cyou/v1').rstrip('/')
AI_POLISH_API_KEY = os.environ.get('AI_POLISH_API_KEY', '')
AI_POLISH_MODEL = os.environ.get('AI_POLISH_MODEL', 'gpt-5.5')
AI_POLISH_TIMEOUT = float(os.environ.get('AI_POLISH_TIMEOUT', '60'))


def ensure_directories():
    Path(ARTICLES_DIR).mkdir(parents=True, exist_ok=True)
    Path(UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
