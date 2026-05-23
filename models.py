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
            word_count INTEGER DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_articles_created ON articles(created_at DESC);
        CREATE TABLE IF NOT EXISTS site_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS public_chat_ip_auth (
            ip TEXT PRIMARY KEY,
            expires_at REAL NOT NULL,
            updated_at TEXT NOT NULL
        );
    """)
    # Migration: add word_count column if missing (existing DB)
    try:
        conn.execute("ALTER TABLE articles ADD COLUMN word_count INTEGER DEFAULT 0")
    except Exception:
        pass  # column already exists
    conn.commit()
    conn.close()
