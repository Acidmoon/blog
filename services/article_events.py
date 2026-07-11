"""Immutable article activity events written inside article metadata transactions."""

from __future__ import annotations


EVENT_TYPES = {"created", "updated", "published"}


def record_article_activity(
    conn,
    article_id: int,
    event_type: str,
    occurred_at: str,
    *,
    word_delta: int = 0,
    visible: bool,
) -> None:
    """Append one event without committing the caller's article transaction."""
    if event_type not in EVENT_TYPES:
        raise ValueError("文章活动类型无效")
    conn.execute(
        """
        INSERT INTO article_activity_events (
            article_id, event_type, occurred_at, word_delta, visible
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (article_id, event_type, occurred_at, int(word_delta), int(bool(visible))),
    )
