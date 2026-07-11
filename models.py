"""Compatibility exports for legacy callers of the SQLite connection helpers.

Schema ownership lives in :mod:`migrations`; feature code should gradually move
to repositories instead of importing this compatibility module directly.
"""

from infrastructure.sqlite import (
    SQLITE_BUSY_TIMEOUT_MS,
    close_db,
    get_db,
    open_database_connection,
)


# Keep the former helper name available while callers migrate to the explicit
# infrastructure adapter. It opens a standalone connection for CLI and tests.
_new_connection = open_database_connection


def init_db() -> None:
    """Run pending migrations for older scripts that still call ``init_db``.

    Web application startup deliberately does not call this helper. Deploy and
    maintenance workflows use ``python -m migrations upgrade`` before workers
    are started, keeping migration locks out of request-serving processes.
    """
    from migrations import migrate_database

    migrate_database()


__all__ = [
    "SQLITE_BUSY_TIMEOUT_MS",
    "_new_connection",
    "close_db",
    "get_db",
    "init_db",
    "open_database_connection",
]
