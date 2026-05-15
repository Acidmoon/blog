import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / 'data'

SECRET_KEY = os.environ.get('BLOG_SECRET_KEY', 'change-this-to-a-random-secret-key')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD') or os.environ.get('BLOG_ADMIN_PASSWORD', 'admin123')

DATABASE = str(DATA_DIR / 'blog.db')
ARTICLES_DIR = str(BASE_DIR / 'articles')
UPLOAD_DIR = str(BASE_DIR / 'static' / 'images')
HOME_LAYOUT_PATH = BASE_DIR / 'home_layout.json'
QUOTE_CACHE_PATH = DATA_DIR / 'quote_cache.json'

SITE_TITLE = '水浇岭的博客'
SITE_SUBTITLE = '写点有意思的东西'
ARTICLES_PER_PAGE = 10
ASSET_VERSION = os.environ.get('ASSET_VERSION', '2026-05-15')

AI_POLISH_API_BASE = os.environ.get('AI_POLISH_API_BASE', 'https://www.waterhill.cyou/v1').rstrip('/')
AI_POLISH_API_KEY = os.environ.get('AI_POLISH_API_KEY', '')
AI_POLISH_MODEL = os.environ.get('AI_POLISH_MODEL', 'gpt-5.5')
AI_POLISH_TIMEOUT = float(os.environ.get('AI_POLISH_TIMEOUT', '60'))


def ensure_directories():
    Path(ARTICLES_DIR).mkdir(parents=True, exist_ok=True)
    Path(UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
