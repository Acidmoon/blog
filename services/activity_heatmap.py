from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date, datetime, timedelta

from models import get_db


def _parse_date(value: str | None) -> date | None:
    """Parse SQLite ISO datetime strings into a date."""
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return datetime.strptime(text[:10], "%Y-%m-%d").date()
        except ValueError:
            return None


def _activity_counts(start: date, end: date) -> dict[date, int]:
    """Count article create/update activity per day for published articles."""
    counts: dict[date, int] = defaultdict(int)
    conn = get_db()
    rows = conn.execute(
        """
        SELECT created_at, updated_at
        FROM articles
        WHERE published=1
          AND (date(created_at) BETWEEN ? AND ? OR date(updated_at) BETWEEN ? AND ?)
        """,
        (start.isoformat(), end.isoformat(), start.isoformat(), end.isoformat()),
    ).fetchall()
    conn.close()

    for row in rows:
        seen_for_article: set[date] = set()
        for field in ("created_at", "updated_at"):
            day = _parse_date(row[field])
            if day and start <= day <= end and day not in seen_for_article:
                counts[day] += 1
                seen_for_article.add(day)
    return dict(counts)


def build_month_activity_heatmap(today: date | None = None) -> dict:
    """Build a GitHub-contributions-style month grid for the homepage widget."""
    today = today or date.today()
    start = today.replace(day=1)
    last_day = calendar.monthrange(today.year, today.month)[1]
    end = today.replace(day=last_day)
    counts = _activity_counts(start, end)
    max_count = max(counts.values(), default=0)

    # Calendar grid starts on Monday and ends on Sunday so the squares align vertically.
    grid_start = start - timedelta(days=start.weekday())
    grid_end = end + timedelta(days=(6 - end.weekday()))

    weeks = []
    cursor = grid_start
    while cursor <= grid_end:
        week = []
        for _ in range(7):
            count = counts.get(cursor, 0)
            if count <= 0:
                level = 0
            elif max_count <= 1:
                level = 4
            else:
                # Map 1..max_count into 1..4, keeping any activity visible.
                level = max(1, min(4, int((count / max_count) * 4 + 0.999)))
            week.append(
                {
                    "date": cursor.isoformat(),
                    "day": cursor.day,
                    "count": count,
                    "level": level,
                    "in_month": cursor.month == today.month,
                    "is_today": cursor == today,
                    "label": f"{cursor.isoformat()}：{count} 次活动",
                }
            )
            cursor += timedelta(days=1)
        weeks.append(week)

    return {
        "title": f"{today.year}年{today.month}月活动",
        "subtitle": "文章发布 / 更新",
        "weeks": weeks,
        "total": sum(counts.values()),
        "max_count": max_count,
        "month": today.month,
        "year": today.year,
        "weekday_labels": ["一", "二", "三", "四", "五", "六", "日"],
    }
