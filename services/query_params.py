"""Strict parsing helpers for public pagination and calendar query values."""

from __future__ import annotations


class QueryParameterError(ValueError):
    """Raised when a user-supplied query value has no stable interpretation."""


def parse_positive_page(value: object, *, default: int = 1, maximum: int = 100_000) -> int:
    """Parse a one-based page number without allowing Python slice edge cases."""
    text = str(value or '').strip()
    if not text:
        return default
    try:
        page = int(text)
    except (TypeError, ValueError) as exc:
        raise QueryParameterError('页码必须是正整数') from exc
    if page < 1 or page > maximum:
        raise QueryParameterError(f'页码必须在 1 到 {maximum} 之间')
    return page


def parse_optional_year(value: object) -> int | None:
    """Parse an optional Gregorian year supported by Python's date type."""
    text = str(value or '').strip()
    if not text:
        return None
    try:
        year = int(text)
    except (TypeError, ValueError) as exc:
        raise QueryParameterError('年份必须是整数') from exc
    if not 1 <= year <= 9999:
        raise QueryParameterError('年份必须在 1 到 9999 之间')
    return year


def parse_optional_month(value: object) -> int | None:
    """Parse an optional one-based calendar month."""
    text = str(value or '').strip()
    if not text:
        return None
    try:
        month = int(text)
    except (TypeError, ValueError) as exc:
        raise QueryParameterError('月份必须是整数') from exc
    if not 1 <= month <= 12:
        raise QueryParameterError('月份必须在 1 到 12 之间')
    return month
