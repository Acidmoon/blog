import sqlite3

from flask import g

import config
from services.tagging import normalize_legacy_tags


# SQLite's default busy wait is short enough to expose normal overlapping web
# writes as transient "database is locked" errors. Keep the DB-API timeout and
# the SQLite pragma aligned so every connection has the same retry window.
SQLITE_BUSY_TIMEOUT_MS = 5_000


def _new_connection():
    conn = sqlite3.connect(
        config.DATABASE,
        timeout=SQLITE_BUSY_TIMEOUT_MS / 1_000,
    )
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
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


def _backfill_article_tags(conn) -> None:
    """Rebuild article tag rows from the legacy comma-separated projection.

    The legacy field is authoritative during migration. Rebuilding instead of
    inserting missing rows removes stale relations left by prior partial runs.
    """
    rows = conn.execute('SELECT id, tags FROM articles').fetchall()
    conn.execute('DELETE FROM article_tags')
    for row in rows:
        tags = normalize_legacy_tags(row['tags'])
        if tags:
            conn.executemany(
                'INSERT INTO article_tags (article_id, tag) VALUES (?, ?)',
                [(row['id'], tag) for tag in tags],
            )


def _article_tag_relations_are_current(conn) -> bool:
    """Compare the legacy projection and relation table without taking a writer lock."""
    expected: set[tuple[int, str]] = set()
    for row in conn.execute('SELECT id, tags FROM articles'):
        expected.update((row['id'], tag) for tag in normalize_legacy_tags(row['tags']))
    actual = {
        (row['article_id'], row['tag'])
        for row in conn.execute('SELECT article_id, tag FROM article_tags')
    }
    return actual == expected


def _backfill_article_activity_events(conn) -> None:
    """Create conservative historical events for installations without event logs.

    Existing databases only retain the current create/update snapshots. The
    backfill records those observable points once, while all future mutations
    write precise immutable events from the article transaction itself.
    """
    rows = conn.execute(
        """
        SELECT id, created_at, updated_at, published, word_count
        FROM articles
        """
    ).fetchall()
    for row in rows:
        has_event = conn.execute(
            "SELECT 1 FROM article_activity_events WHERE article_id=? LIMIT 1",
            (row['id'],),
        ).fetchone()
        if has_event is not None:
            continue
        visible = int(bool(row['published']))
        conn.execute(
            """
            INSERT INTO article_activity_events (
                article_id, event_type, occurred_at, word_delta, visible
            ) VALUES (?, 'created', ?, ?, ?)
            """,
            (row['id'], row['created_at'], int(row['word_count'] or 0), visible),
        )
        if row['updated_at'] != row['created_at']:
            conn.execute(
                """
                INSERT INTO article_activity_events (
                    article_id, event_type, occurred_at, word_delta, visible
                ) VALUES (?, 'updated', ?, 0, ?)
                """,
                (row['id'], row['updated_at'], visible),
            )


def _article_activity_events_are_current(conn) -> bool:
    """Return whether every extant article has at least one activity record."""
    row = conn.execute(
        """
        SELECT 1
        FROM articles
        LEFT JOIN article_activity_events events ON events.article_id = articles.id
        GROUP BY articles.id
        HAVING COUNT(events.id) = 0
        LIMIT 1
        """
    ).fetchone()
    return row is None


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
            content_key TEXT NOT NULL DEFAULT '',
            cover_image TEXT DEFAULT '',
            cover_alt TEXT DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_articles_created ON articles(created_at DESC);
        CREATE VIRTUAL TABLE IF NOT EXISTS article_search USING fts5(
            article_id UNINDEXED,
            title,
            tags,
            content,
            tokenize='unicode61 remove_diacritics 2'
        );
        CREATE TABLE IF NOT EXISTS article_activity_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            article_id INTEGER NOT NULL,
            event_type TEXT NOT NULL CHECK (event_type IN ('created', 'updated', 'published')),
            occurred_at TEXT NOT NULL,
            word_delta INTEGER NOT NULL DEFAULT 0,
            visible INTEGER NOT NULL DEFAULT 0 CHECK (visible IN (0, 1))
        );
        CREATE INDEX IF NOT EXISTS idx_article_activity_visible_at
            ON article_activity_events(visible, occurred_at, id);
        CREATE TABLE IF NOT EXISTS article_tags (
            article_id INTEGER NOT NULL,
            tag TEXT NOT NULL COLLATE NOCASE,
            PRIMARY KEY (article_id, tag),
            FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_article_tags_tag_article ON article_tags(tag, article_id);
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
    # Upgrade legacy article databases without hiding unrelated migration failures.
    try:
        conn.execute("ALTER TABLE articles ADD COLUMN word_count INTEGER DEFAULT 0")
    except sqlite3.OperationalError as exc:
        if 'duplicate column name' not in str(exc).lower():
            raise
    try:
        conn.execute("ALTER TABLE articles ADD COLUMN content_key TEXT NOT NULL DEFAULT ''")
    except sqlite3.OperationalError as exc:
        if 'duplicate column name' not in str(exc).lower():
            raise
    for column_name, definition in (
        ('cover_image', "TEXT DEFAULT ''"),
        ('cover_alt', "TEXT DEFAULT ''"),
    ):
        try:
            conn.execute(f"ALTER TABLE articles ADD COLUMN {column_name} {definition}")
        except sqlite3.OperationalError as exc:
            if 'duplicate column name' not in str(exc).lower():
                raise
    try:
        conn.execute("ALTER TABLE visitor_users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0")
    except sqlite3.OperationalError as exc:
        if 'duplicate column name' not in str(exc).lower():
            raise
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_articles_content_key "
        "ON articles(content_key) WHERE content_key <> ''"
    )
    conn.execute(
        "UPDATE visitor_users SET is_admin=1 WHERE username=?",
        (config.ADMIN_USERNAME,),
    )
    try:
        # Worker starts normally do only read checks. If legacy data or a prior
        # interrupted migration left drift behind, take a short writer lock and
        # recheck before applying an all-or-nothing repair.
        needs_tag_rebuild = not _article_tag_relations_are_current(conn)
        needs_event_backfill = not _article_activity_events_are_current(conn)
        if needs_tag_rebuild or needs_event_backfill:
            if not conn.in_transaction:
                conn.execute('BEGIN IMMEDIATE')
            if not _article_tag_relations_are_current(conn):
                _backfill_article_tags(conn)
            if not _article_activity_events_are_current(conn):
                _backfill_article_activity_events(conn)
            conn.commit()
    except Exception:
        if conn.in_transaction:
            conn.rollback()
        raise
    finally:
        conn.close()
