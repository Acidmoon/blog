import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

SECRET_KEY = os.environ.get('BLOG_SECRET_KEY', 'change-this-to-a-random-secret-key')
ADMIN_PASSWORD = os.environ.get('BLOG_ADMIN_PASSWORD', 'admin123')

DATABASE = os.path.join(BASE_DIR, 'data', 'blog.db')
ARTICLES_DIR = os.path.join(BASE_DIR, 'articles')
UPLOAD_DIR = os.path.join(BASE_DIR, 'static', 'images')
SITE_TITLE = '水浇岭的博客'
SITE_SUBTITLE = '写点有意思的东西'
ARTICLES_PER_PAGE = 10
