from __future__ import annotations

import calendar
import re
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import config
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


def _month_boundary(year: int, month: int) -> tuple[date, date | None]:
    """Return the first day and an exclusive next-month boundary when representable."""
    start = date(year, month, 1)
    if year == 9999 and month == 12:
        # Python cannot represent 10000-01-01. A missing upper bound is safe here
        # because no valid SQLite ISO date can fall beyond the supported calendar.
        return start, None
    if month == 12:
        return start, date(year + 1, 1, 1)
    return start, date(year, month + 1, 1)


def _range_condition(column: str, start: date, end_exclusive: date | None) -> tuple[str, tuple[str, ...]]:
    """Build an index-friendly ISO range condition for one timestamp column."""
    if end_exclusive is None:
        return f"{column} >= ?", (start.isoformat(),)
    return f"{column} >= ? AND {column} < ?", (
        start.isoformat(),
        end_exclusive.isoformat(),
    )


def _count_words(text: str) -> int:
    """Count Chinese characters + English words in a markdown text.
    Chinese chars: CJK Unified Ideographs (U+4E00–U+9FFF) + extensions.
    English words: sequences of [a-zA-Z0-9]."""
    cjk = len(re.findall(r'[\u4e00-\u9fff\u3400-\u4dbf]', text))
    en_words = len(re.findall(r'[a-zA-Z0-9]+', text))
    return cjk + en_words


def _activity_counts(start: date, end: date, end_exclusive: date | None) -> dict[date, int]:
    """Count immutable, publicly visible article events per day."""
    counts: dict[date, int] = defaultdict(int)
    conn = get_db()
    occurred_condition, occurred_params = _range_condition('occurred_at', start, end_exclusive)
    rows = conn.execute(
        f"""
        SELECT occurred_at, COUNT(*) AS total
        FROM article_activity_events
        WHERE visible=1 AND ({occurred_condition})
        GROUP BY substr(occurred_at, 1, 10)
        """,
        occurred_params,
    ).fetchall()

    for row in rows:
        day = _parse_date(row['occurred_at'])
        if day and start <= day <= end:
            counts[day] += int(row['total'] or 0)
    return dict(counts)


def _word_counts(start: date, end: date, end_exclusive: date | None) -> dict[date, int]:
    """Aggregate net word changes recorded with immutable activity events."""
    words_per_day: dict[date, int] = defaultdict(int)
    conn = get_db()
    occurred_condition, occurred_params = _range_condition('occurred_at', start, end_exclusive)
    rows = conn.execute(
        f"""
        SELECT occurred_at, COALESCE(SUM(word_delta), 0) AS word_delta
        FROM article_activity_events
        WHERE visible=1 AND ({occurred_condition})
        GROUP BY substr(occurred_at, 1, 10)
        """,
        occurred_params,
    ).fetchall()

    for row in rows:
        word_delta = int(row["word_delta"] or 0)
        day = _parse_date(row["occurred_at"])
        if day and start <= day <= end:
            words_per_day[day] += word_delta
    return dict(words_per_day)


def build_month_activity_heatmap(year: int | None = None, month: int | None = None, today: date | None = None) -> dict:
    """Build a GitHub-contributions-style month grid for the homepage.

    If year/month are omitted, defaults to the current month.
    Returns prev/next month info for navigation.
    """
    today = today or date.today()
    if year is None:
        year = today.year
    if month is None:
        month = today.month
    if not isinstance(year, int) or not 1 <= year <= 9999:
        raise ValueError('年份必须在 1 到 9999 之间')
    if not isinstance(month, int) or not 1 <= month <= 12:
        raise ValueError('月份必须在 1 到 12 之间')

    start, end_exclusive = _month_boundary(year, month)
    last_day = calendar.monthrange(year, month)[1]
    end = date(year, month, last_day)

    # Navigation: prev / next month
    if month == 1:
        prev_year, prev_month = (year - 1, 12) if year > 1 else (None, None)
    else:
        prev_year, prev_month = year, month - 1
    if month == 12 and year == 9999:
        next_year, next_month = None, None
    elif month == 12:
        next_year, next_month = year + 1, 1
    else:
        next_year, next_month = year, month + 1

    # Don't navigate past the current month
    current_month = (today.year, today.month)
    has_prev = prev_year is not None
    has_next = next_year is not None and (next_year, next_month) <= current_month

    counts = _activity_counts(start, end, end_exclusive)
    max_count = max(counts.values(), default=0)
    words = _word_counts(start, end, end_exclusive)

    # Calendar grid starts on Monday and ends on Sunday so the squares align vertically.
    grid_start = start - timedelta(days=start.weekday())
    trailing_days = 6 - end.weekday()
    max_date = date.max
    grid_end = end if end > max_date - timedelta(days=trailing_days) else end + timedelta(days=trailing_days)

    weeks = []
    cursor = grid_start
    while cursor <= grid_end:
        week = []
        for _ in range(7):
            if cursor > grid_end:
                break
            count = counts.get(cursor, 0)
            if count <= 0:
                level = 0
            elif max_count <= 1:
                level = 4
            else:
                level = max(1, min(4, int((count / max_count) * 4 + 0.999)))
            word_count = words.get(cursor, 0)
            week.append(
                {
                    "date": cursor.isoformat(),
                    "day": cursor.day,
                    "count": count,
                    "level": level,
                    "in_month": cursor.month == month,
                    "is_today": cursor == today,
                    "label": f"{cursor.isoformat()}：{count} 次活动，{word_count} 字",
                    "words": word_count,
                }
            )
            if cursor == max_date:
                break
            cursor += timedelta(days=1)
        weeks.append(week)
        if cursor == max_date:
            break

    total_words = sum(words.values())
    today_words = words.get(today, 0)
    days_remaining = (date(today.year, 12, 31) - today).days

    # Month names for display
    month_names = ["一月", "二月", "三月", "四月", "五月", "六月",
                   "七月", "八月", "九月", "十月", "十一月", "十二月"]

    return {
        "title": f"{year}年{month}月活动",
        "subtitle": "文章活动记录",
        "weeks": weeks,
        "total": sum(counts.values()),
        "max_count": max_count,
        "month": month,
        "year": year,
        "month_display": month_names[month - 1],
        "weekday_labels": ["一", "二", "三", "四", "五", "六", "日"],
        "total_words": total_words,
        "today_words": today_words,
        "week_count": len(weeks),
        "days_remaining": days_remaining,
        # Navigation
        "prev_year": prev_year,
        "prev_month": prev_month,
        "has_prev": has_prev,
        "next_year": next_year,
        "next_month": next_month,
        "has_next": has_next,
    }
