"""Small, dependency-free SQLite migration runner.

Migrations run before web workers are started, never from Flask application
startup.  Each version is recorded in the database and is applied under a
short SQLite writer lock, allowing concurrent deploy processes to safely
observe a migration completed by another process.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sqlite3

import config
from infrastructure.sqlite import open_database_connection
from services.article_index import sync_article_search
from services.tagging import normalize_legacy_tags


MigrationAction = Callable[[sqlite3.Connection], None]


@dataclass(frozen=True)
class Migration:
    """One ordered, irreversible schema or data upgrade."""

    version: int
    name: str
    upgrade: MigrationAction


def _execute_statements(connection: sqlite3.Connection, statements: tuple[str, ...]) -> None:
    """Execute DDL one statement at a time inside the caller's transaction."""
    for statement in statements:
        connection.execute(statement)


def _table_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    """Read a trusted table's existing columns for legacy-schema adoption."""
    return {str(row["name"]) for row in connection.execute(f"PRAGMA table_info({table_name})")}


def _add_column_if_missing(
    connection: sqlite3.Connection,
    table_name: str,
    column_name: str,
    definition: str,
) -> None:
    """Make a migration safe for installations created before version tracking."""
    if column_name not in _table_columns(connection, table_name):
        connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


def _migration_001_initial_schema(connection: sqlite3.Connection) -> None:
    """Create the original application tables on a new installation."""
    _execute_statements(
        connection,
        (
            """
            CREATE TABLE IF NOT EXISTS articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slug TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                tags TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                published INTEGER DEFAULT 1
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_articles_created ON articles(created_at DESC)",
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS article_search USING fts5(
                article_id UNINDEXED,
                title,
                tags,
                content,
                tokenize='unicode61 remove_diacritics 2'
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS site_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS public_chat_ip_auth (
                ip TEXT PRIMARY KEY,
                expires_at REAL NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS visitor_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_ip TEXT DEFAULT '',
                last_seen_at TEXT DEFAULT ''
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS visitor_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                token_hash TEXT UNIQUE NOT NULL,
                expires_at REAL NOT NULL,
                created_at TEXT NOT NULL,
                last_seen_at TEXT DEFAULT '',
                last_ip TEXT DEFAULT '',
                FOREIGN KEY (user_id) REFERENCES visitor_users(id) ON DELETE CASCADE
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_visitor_tokens_user ON visitor_tokens(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_visitor_tokens_expires ON visitor_tokens(expires_at)",
            """
            CREATE TABLE IF NOT EXISTS chat_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL DEFAULT '新的对话',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES visitor_users(id) ON DELETE CASCADE
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_updated ON chat_sessions(user_id, updated_at DESC)",
            """
            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                content TEXT NOT NULL,
                rendered_html TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_chat_messages_session_created ON chat_messages(session_id, created_at, id)",
            """
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
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_chat_files_session ON chat_files(session_id)",
            """
            CREATE TABLE IF NOT EXISTS comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                article_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES visitor_users(id) ON DELETE CASCADE
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_comments_article_created ON comments(article_id, created_at DESC, id DESC)",
            """
            CREATE TABLE IF NOT EXISTS article_likes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                article_id INTEGER NOT NULL,
                user_id INTEGER,
                ip TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES visitor_users(id) ON DELETE CASCADE
            )
            """,
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_article_likes_user ON article_likes(article_id, user_id) WHERE user_id IS NOT NULL",
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_article_likes_ip ON article_likes(article_id, ip) WHERE user_id IS NULL",
        ),
    )


def _migration_002_article_metadata(connection: sqlite3.Connection) -> None:
    """Add immutable body pointers and presentation metadata to articles."""
    _add_column_if_missing(connection, "articles", "word_count", "INTEGER DEFAULT 0")
    _add_column_if_missing(connection, "articles", "content_key", "TEXT NOT NULL DEFAULT ''")
    _add_column_if_missing(connection, "articles", "cover_image", "TEXT DEFAULT ''")
    _add_column_if_missing(connection, "articles", "cover_alt", "TEXT DEFAULT ''")
    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_articles_content_key "
        "ON articles(content_key) WHERE content_key <> ''"
    )


def _migration_003_article_tags(connection: sqlite3.Connection) -> None:
    """Create normalized tag relations and build them once from legacy metadata."""
    _execute_statements(
        connection,
        (
            """
            CREATE TABLE IF NOT EXISTS article_tags (
                article_id INTEGER NOT NULL,
                tag TEXT NOT NULL COLLATE NOCASE,
                PRIMARY KEY (article_id, tag),
                FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE CASCADE
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_article_tags_tag_article ON article_tags(tag, article_id)",
        ),
    )
    rows = connection.execute("SELECT id, tags FROM articles").fetchall()
    connection.execute("DELETE FROM article_tags")
    for row in rows:
        tags = normalize_legacy_tags(row["tags"])
        if tags:
            connection.executemany(
                "INSERT INTO article_tags (article_id, tag) VALUES (?, ?)",
                [(row["id"], tag) for tag in tags],
            )


def _migration_004_article_activity_events(connection: sqlite3.Connection) -> None:
    """Create immutable history from each legacy article's observable snapshots."""
    _execute_statements(
        connection,
        (
            """
            CREATE TABLE IF NOT EXISTS article_activity_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                article_id INTEGER NOT NULL,
                event_type TEXT NOT NULL CHECK (event_type IN ('created', 'updated', 'published')),
                occurred_at TEXT NOT NULL,
                word_delta INTEGER NOT NULL DEFAULT 0,
                visible INTEGER NOT NULL DEFAULT 0 CHECK (visible IN (0, 1))
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_article_activity_visible_at ON article_activity_events(visible, occurred_at, id)",
        ),
    )
    rows = connection.execute(
        "SELECT id, created_at, updated_at, published, word_count FROM articles"
    ).fetchall()
    for row in rows:
        has_event = connection.execute(
            "SELECT 1 FROM article_activity_events WHERE article_id=? LIMIT 1",
            (row["id"],),
        ).fetchone()
        if has_event is not None:
            continue
        visible = int(bool(row["published"]))
        connection.execute(
            """
            INSERT INTO article_activity_events (
                article_id, event_type, occurred_at, word_delta, visible
            ) VALUES (?, 'created', ?, ?, ?)
            """,
            (row["id"], row["created_at"], int(row["word_count"] or 0), visible),
        )
        if row["updated_at"] != row["created_at"]:
            connection.execute(
                """
                INSERT INTO article_activity_events (
                    article_id, event_type, occurred_at, word_delta, visible
                ) VALUES (?, 'updated', ?, 0, ?)
                """,
                (row["id"], row["updated_at"], visible),
            )


def _migration_005_visitor_admin_identity(connection: sqlite3.Connection) -> None:
    """Add the explicit administrator marker used by visitor authentication."""
    _add_column_if_missing(connection, "visitor_users", "is_admin", "INTEGER NOT NULL DEFAULT 0")
    connection.execute(
        "UPDATE visitor_users SET is_admin=1 WHERE username=?",
        (config.ADMIN_USERNAME,),
    )


def _article_body_path(slug: str, content_key: str) -> Path:
    """Locate a committed article body using the same legacy/new storage split."""
    filename = f"{content_key}.md" if content_key else f"{slug}.md"
    return Path(config.ARTICLES_DIR) / filename


def _migration_006_article_search_index(connection: sqlite3.Connection) -> None:
    """Build FTS data once after all article-body storage migrations are complete."""
    connection.execute("DELETE FROM article_search")
    rows = connection.execute(
        "SELECT id, slug, content_key, title, tags FROM articles"
    ).fetchall()
    for row in rows:
        try:
            content = _article_body_path(row["slug"], row["content_key"]).read_text(encoding="utf-8")
        except OSError:
            # Metadata remains searchable when a legacy body is unavailable.
            content = ""
        sync_article_search(connection, row["id"], row["title"], row["tags"], content)


MIGRATIONS: tuple[Migration, ...] = (
    Migration(1, "initial_schema", _migration_001_initial_schema),
    Migration(2, "article_metadata", _migration_002_article_metadata),
    Migration(3, "article_tags", _migration_003_article_tags),
    Migration(4, "article_activity_events", _migration_004_article_activity_events),
    Migration(5, "visitor_admin_identity", _migration_005_visitor_admin_identity),
    Migration(6, "article_search_index", _migration_006_article_search_index),
)


def _ensure_migration_table(connection: sqlite3.Connection) -> None:
    """Create the minimal ledger before checking any application schema."""
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL
        )
        """
    )
    connection.commit()


def _applied_versions(connection: sqlite3.Connection) -> set[int]:
    """Return migration versions committed by any deployment process."""
    return {
        int(row["version"])
        for row in connection.execute("SELECT version FROM schema_migrations")
    }


def current_version() -> int:
    """Return the recorded schema version without modifying the database."""
    database_path = Path(config.DATABASE)
    if not database_path.is_file():
        return 0
    database_uri = f"{database_path.resolve().as_uri()}?mode=ro"
    connection = sqlite3.connect(database_uri, uri=True)
    connection.row_factory = sqlite3.Row
    try:
        if "schema_migrations" not in {
            row["name"]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }:
            return 0
        return max(_applied_versions(connection), default=0)
    finally:
        connection.close()


def migrate_database() -> list[Migration]:
    """Apply each pending migration exactly once and return those applied now."""
    config.ensure_directories()
    connection = open_database_connection()
    applied_now: list[Migration] = []
    try:
        _ensure_migration_table(connection)
        for migration in MIGRATIONS:
            if migration.version in _applied_versions(connection):
                continue
            connection.execute("BEGIN IMMEDIATE")
            try:
                if migration.version not in _applied_versions(connection):
                    migration.upgrade(connection)
                    connection.execute(
                        "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
                        (
                            migration.version,
                            migration.name,
                            datetime.now(timezone.utc).isoformat(),
                        ),
                    )
                    applied_now.append(migration)
                connection.commit()
            except Exception:
                connection.rollback()
                raise
    finally:
        connection.close()
    return applied_now
