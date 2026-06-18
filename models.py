import sqlite3

from flask import g

import config


def _new_connection():
    conn = sqlite3.connect(config.DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def get_db():
    """Return a per-request cached connection when inside a Flask request context,
    otherwise a new standalone connection (for scripts / CLI / cron)."""
    try:
        if g:
            pass  # inside request context
    except RuntimeError:
        return _new_connection()
    db = g.get('_blog_db')
    if db is not None:
        # Detect closed connections (e.g. from older code that still calls .close())
        try:
            db.execute("SELECT 1")
        except sqlite3.ProgrammingError:
            db = None
    if db is None:
        db = _new_connection()
        g._blog_db = db
    return db


def close_db(exception=None):
    db = g.pop('_blog_db', None)
    if db is not None:
        db.close()


def init_db():
    conn = _new_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            tags TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            published INTEGER DEFAULT 1,
            word_count INTEGER DEFAULT 0,
            cover_image TEXT DEFAULT '',
            cover_alt TEXT DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_articles_created ON articles(created_at DESC);
        CREATE TABLE IF NOT EXISTS site_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS visitor_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            is_admin INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            last_ip TEXT DEFAULT '',
            last_seen_at TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS visitor_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token_hash TEXT UNIQUE NOT NULL,
            expires_at REAL NOT NULL,
            created_at TEXT NOT NULL,
            last_seen_at TEXT DEFAULT '',
            last_ip TEXT DEFAULT '',
            FOREIGN KEY (user_id) REFERENCES visitor_users(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_visitor_tokens_user ON visitor_tokens(user_id);
        CREATE INDEX IF NOT EXISTS idx_visitor_tokens_expires ON visitor_tokens(expires_at);
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            article_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES visitor_users(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_comments_article_created ON comments(article_id, created_at DESC, id DESC);
        CREATE TABLE IF NOT EXISTS article_likes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            article_id INTEGER NOT NULL,
            user_id INTEGER,
            ip TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES visitor_users(id) ON DELETE CASCADE
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_article_likes_user ON article_likes(article_id, user_id) WHERE user_id IS NOT NULL;
        CREATE UNIQUE INDEX IF NOT EXISTS idx_article_likes_ip ON article_likes(article_id, ip) WHERE user_id IS NULL;
    """)
    # Migration: add word_count column if missing (existing DB)
    try:
        conn.execute("ALTER TABLE articles ADD COLUMN word_count INTEGER DEFAULT 0")
    except Exception:
        pass  # column already exists
    try:
        conn.execute("ALTER TABLE visitor_users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0")
    except Exception:
        pass  # column already exists
    conn.execute(
        "UPDATE visitor_users SET is_admin=1 WHERE username=?",
        (config.ADMIN_USERNAME,),
    )
    conn.commit()
    conn.close()
