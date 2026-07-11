"""SQLite reads owned by the article feature rather than HTTP route handlers."""

from __future__ import annotations

from typing import Any

from infrastructure.sqlite import get_db


def find_published_neighbors(article_id: int, created_at: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Return stable previous/next published articles around one article.

    The primary creation-time ordering preserves the existing public behavior.
    Article id makes the result deterministic for articles created in the same
    timestamp, which the former route-level query did not distinguish.
    """
    connection = get_db()
    previous_row = connection.execute(
        """
        SELECT slug, title
        FROM articles
        WHERE published=1
          AND (created_at < ? OR (created_at = ? AND id < ?))
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (created_at, created_at, article_id),
    ).fetchone()
    next_row = connection.execute(
        """
        SELECT slug, title
        FROM articles
        WHERE published=1
          AND (created_at > ? OR (created_at = ? AND id > ?))
        ORDER BY created_at ASC, id ASC
        LIMIT 1
        """,
        (created_at, created_at, article_id),
    ).fetchone()
    return (
        dict(previous_row) if previous_row else None,
        dict(next_row) if next_row else None,
    )
