from __future__ import annotations

import calendar
import re
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import config
from models import get_db
from services.articles import read_article_file


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


def _count_words(text: str) -> int:
    """Count Chinese characters + English words in a markdown text.
    Chinese chars: CJK Unified Ideographs (U+4E00–U+9FFF) + extensions.
    English words: sequences of [a-zA-Z0-9]."""
    cjk = len(re.findall(r'[\u4e00-\u9fff\u3400-\u4dbf]', text))
    en_words = len(re.findall(r'[a-zA-Z0-9]+', text))
    return cjk + en_words


def _activity_counts(start: date, end: date) -> dict[date, int]:
    """Count article create/update activity per day for published articles."""
    counts: dict[date, int] = defaultdict(int)
    conn = get_db()
    rows = conn.execute(
        """
        SELECT slug, created_at, updated_at
        FROM articles
        WHERE published=1
          AND (date(created_at) BETWEEN ? AND ? OR date(updated_at) BETWEEN ? AND ?)
        """,
        (start.isoformat(), end.isoformat(), start.isoformat(), end.isoformat()),
    ).fetchall()

    for row in rows:
        seen_for_article: set[date] = set()
        for field in ("created_at", "updated_at"):
            day = _parse_date(row[field])
            if day and start <= day <= end and day not in seen_for_article:
                counts[day] += 1
                seen_for_article.add(day)
    return dict(counts)


def _word_counts(start: date, end: date) -> dict[date, int]:
    """Count words in articles created or updated on each day in the range."""
    words_per_day: dict[date, int] = defaultdict(int)
    conn = get_db()
    rows = conn.execute(
        """
        SELECT slug, created_at, updated_at
        FROM articles
        WHERE published=1
          AND (date(created_at) BETWEEN ? AND ? OR date(updated_at) BETWEEN ? AND ?)
        """,
        (start.isoformat(), end.isoformat(), start.isoformat(), end.isoformat()),
    ).fetchall()

    for row in rows:
        slug = row["slug"]
        content = read_article_file(slug)
        if not content:
            continue
        wc = _count_words(content)
        # Attribute words to each day this article had activity on
        seen: set[date] = set()
        for field in ("created_at", "updated_at"):
            day = _parse_date(row[field])
            if day and start <= day <= end and day not in seen:
                words_per_day[day] += wc
                seen.add(day)
    return dict(words_per_day)


def build_month_activity_heatmap(today: date | None = None) -> dict:
    """Build a GitHub-contributions-style month grid for the homepage widget."""
    today = today or date.today()
    start = today.replace(day=1)
    last_day = calendar.monthrange(today.year, today.month)[1]
    end = today.replace(day=last_day)
    counts = _activity_counts(start, end)
    max_count = max(counts.values(), default=0)
    words = _word_counts(start, end)

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
                level = max(1, min(4, int((count / max_count) * 4 + 0.999)))
            word_count = words.get(cursor, 0)
            week.append(
                {
                    "date": cursor.isoformat(),
                    "day": cursor.day,
                    "count": count,
                    "level": level,
                    "in_month": cursor.month == today.month,
                    "is_today": cursor == today,
                    "label": f"{cursor.isoformat()}：{count} 次活动，{word_count} 字",
                    "words": word_count,
                }
            )
            cursor += timedelta(days=1)
        weeks.append(week)

    total_words = sum(words.values())
    today_words = words.get(today, 0)

    return {
        "title": f"{today.year}年{today.month}月活动",
        "subtitle": "文章发布 / 更新",
        "weeks": weeks,
        "total": sum(counts.values()),
        "max_count": max_count,
        "month": today.month,
        "year": today.year,
        "weekday_labels": ["一", "二", "三", "四", "五", "六", "日"],
        "total_words": total_words,
        "today_words": today_words,
    }
