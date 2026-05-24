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
        CREATE TABLE IF NOT EXISTS visitor_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
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
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL DEFAULT '新的对话',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES visitor_users(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_updated ON chat_sessions(user_id, updated_at DESC);
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
            content TEXT NOT NULL,
            rendered_html TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_chat_messages_session_created ON chat_messages(session_id, created_at, id);
        CREATE TABLE IF NOT EXISTS chat_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            original_name TEXT NOT NULL,
            stored_path TEXT NOT NULL,
            mime_type TEXT DEFAULT '',
            size_bytes INTEGER NOT NULL DEFAULT 0,
            extracted_text TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_chat_files_session ON chat_files(session_id);
    """)
    # Migration: add word_count column if missing (existing DB)
    try:
        conn.execute("ALTER TABLE articles ADD COLUMN word_count INTEGER DEFAULT 0")
    except Exception:
        pass  # column already exists
    conn.commit()
    conn.close()
