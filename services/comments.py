"""Comments & likes for articles — visitor-authored, paginated."""

from __future__ import annotations

from datetime import datetime

from models import get_db

COMMENTS_PER_PAGE = 10
MAX_COMMENT_LENGTH = 2000


class CommentError(ValueError):
    pass


def _now_text() -> str:
    return datetime.now().isoformat(timespec='seconds')


def add_comment(article_id: int, user_id: int, content: str) -> dict:
    content = (content or '').strip()
    if not content:
        raise CommentError('评论内容不能为空')
    if len(content) > MAX_COMMENT_LENGTH:
        raise CommentError(f'评论太长了，最多 {MAX_COMMENT_LENGTH} 字')
    now = _now_text()
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO comments (article_id, user_id, content, created_at) VALUES (?, ?, ?, ?)",
        (article_id, user_id, content, now),
    )
    conn.commit()
    row = conn.execute(
        """
        SELECT c.id, c.article_id, c.user_id, c.content, c.created_at, u.username
        FROM comments c JOIN visitor_users u ON u.id = c.user_id
        WHERE c.id = ?
        """,
        (cur.lastrowid,),
    ).fetchone()
    return dict(row)


def get_comment(comment_id: int) -> dict | None:
    conn = get_db()
    row = conn.execute(
        "SELECT id, article_id, user_id, content, created_at FROM comments WHERE id = ?",
        (comment_id,),
    ).fetchone()
    return dict(row) if row else None


def delete_comment(comment_id: int) -> None:
    conn = get_db()
    conn.execute("DELETE FROM comments WHERE id = ?", (comment_id,))
    conn.commit()


def count_comments(article_id: int) -> int:
    conn = get_db()
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM comments WHERE article_id = ?",
        (article_id,),
    ).fetchone()
    return int(row['n'])


def list_comments(article_id: int, page: int = 1, per_page: int = COMMENTS_PER_PAGE) -> dict:
    page = max(1, int(page))
    total = count_comments(article_id)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, total_pages)
    offset = (page - 1) * per_page
    conn = get_db()
    rows = conn.execute(
        """
        SELECT c.id, c.user_id, c.content, c.created_at, u.username
        FROM comments c JOIN visitor_users u ON u.id = c.user_id
        WHERE c.article_id = ?
        ORDER BY c.created_at DESC, c.id DESC
        LIMIT ? OFFSET ?
        """,
        (article_id, per_page, offset),
    ).fetchall()
    return {
        'comments': [dict(r) for r in rows],
        'page': page,
        'per_page': per_page,
        'total': total,
        'total_pages': total_pages,
    }


def count_likes(article_id: int) -> int:
    conn = get_db()
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM article_likes WHERE article_id = ?",
        (article_id,),
    ).fetchone()
    return int(row['n'])


def has_liked(article_id: int, user_id: int | None, ip: str = '') -> bool:
    conn = get_db()
    if user_id is not None:
        row = conn.execute(
            "SELECT 1 FROM article_likes WHERE article_id = ? AND user_id = ?",
            (article_id, user_id),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT 1 FROM article_likes WHERE article_id = ? AND user_id IS NULL AND ip = ?",
            (article_id, ip),
        ).fetchone()
    return row is not None


def toggle_like(article_id: int, user_id: int | None, ip: str = '') -> dict:
    """Add a like if absent, remove it if present. Returns {liked, count}."""
    conn = get_db()
    liked_now = has_liked(article_id, user_id, ip)
    if liked_now:
        if user_id is not None:
            conn.execute(
                "DELETE FROM article_likes WHERE article_id = ? AND user_id = ?",
                (article_id, user_id),
            )
        else:
            conn.execute(
                "DELETE FROM article_likes WHERE article_id = ? AND user_id IS NULL AND ip = ?",
                (article_id, ip),
            )
        conn.commit()
        return {'liked': False, 'count': count_likes(article_id)}
    conn.execute(
        "INSERT INTO article_likes (article_id, user_id, ip, created_at) VALUES (?, ?, ?, ?)",
        (article_id, user_id, ip, _now_text()),
    )
    conn.commit()
    return {'liked': True, 'count': count_likes(article_id)}
