"""Regression coverage for deployment-time SQLite schema upgrades."""

from __future__ import annotations

import sqlite3

import config
from app import create_app
from migrations import current_version, migrate_database


def test_migrations_upgrade_legacy_schema_once_and_record_versions(tmp_path, monkeypatch):
    """A legacy installation upgrades before workers start and reruns as a no-op."""
    database_path = tmp_path / "legacy.db"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slug TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                tags TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                published INTEGER DEFAULT 1
            )
            """
        )

    monkeypatch.setattr(config, "DATABASE", str(database_path))
    first_run = migrate_database()

    with sqlite3.connect(database_path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(articles)")}
        versions = [row[0] for row in connection.execute("SELECT version FROM schema_migrations ORDER BY version")]

    assert {"word_count", "content_key", "cover_image", "cover_alt"} <= columns
    assert [migration.version for migration in first_run] == [1, 2, 3, 4, 5, 6]
    assert versions == [1, 2, 3, 4, 5, 6]
    assert current_version() == 6
    assert migrate_database() == []


def test_app_factory_does_not_create_or_migrate_a_database(tmp_path, monkeypatch):
    """Serving-process startup leaves schema changes to the deployment command."""
    database_path = tmp_path / "runtime" / "blog.db"
    monkeypatch.setattr(config, "DATA_DIR", database_path.parent)
    monkeypatch.setattr(config, "DATABASE", str(database_path))
    monkeypatch.setattr(config, "ARTICLES_DIR", str(database_path.parent / "articles"))
    monkeypatch.setattr(config, "UPLOAD_DIR", str(database_path.parent / "uploads"))
    monkeypatch.setattr(config, "CHAT_UPLOAD_DIR", str(database_path.parent / "chat_uploads"))
    monkeypatch.setattr(config, "HOME_LAYOUT_PATH", database_path.parent / "home_layout.json")
    monkeypatch.setattr(config, "QUOTE_CACHE_PATH", database_path.parent / "quote_cache.json")

    application = create_app({"TESTING": True})

    assert application is not None
    assert not database_path.exists()
