import sqlite3

from flask import g

import config


def _new_connection():
    conn = sqlite3.connect(config.DATABASE)
    conn.row_factory = sqlite3.Row
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
            published INTEGER DEFAULT 1
        );
        CREATE INDEX IF NOT EXISTS idx_articles_created ON articles(created_at DESC);
    """)
    conn.commit()
    conn.close()
