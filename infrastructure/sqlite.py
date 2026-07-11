"""SQLite connection lifecycle shared by HTTP requests and maintenance commands."""

from __future__ import annotations

import sqlite3

from flask import g

import config


# Keep the DB-API timeout and SQLite pragma aligned so concurrent writes wait
# for the same bounded period before surfacing a recoverable lock error.
SQLITE_BUSY_TIMEOUT_MS = 5_000


def open_database_connection(database: str | None = None) -> sqlite3.Connection:
    """Open one configured SQLite connection without depending on Flask state."""
    connection = sqlite3.connect(
        database or config.DATABASE,
        timeout=SQLITE_BUSY_TIMEOUT_MS / 1_000,
    )
    connection.row_factory = sqlite3.Row
    connection.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA journal_mode=WAL")
    return connection


def get_db() -> sqlite3.Connection:
    """Return a context-cached connection, or a standalone one for CLI work."""
    try:
        g.get("_blog_db")
    except RuntimeError:
        return open_database_connection()

    connection = g.get("_blog_db")
    if connection is not None:
        try:
            connection.execute("SELECT 1")
        except sqlite3.ProgrammingError:
            connection = None
    if connection is None:
        connection = open_database_connection()
        g._blog_db = connection
    return connection


def close_db(exception: BaseException | None = None) -> None:
    """Close the request-scoped connection when Flask tears down its context."""
    connection = g.pop("_blog_db", None)
    if connection is not None:
        connection.close()
