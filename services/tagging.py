"""Canonical tag parsing shared by article writes, migrations, and filters."""

from __future__ import annotations


MAX_TAGS_PER_ARTICLE = 20
MAX_TAG_LENGTH = 48


def _clean_tag_values(value: object):
    """Yield non-empty legacy tag values with whitespace normalized."""
    for raw_tag in str(value or '').split(','):
        tag = ' '.join(raw_tag.strip().split())
        if tag:
            yield tag


def normalize_tags(value: object) -> list[str]:
    """Return unique, bounded display tags while preserving their first spelling."""
    tags: list[str] = []
    seen: set[str] = set()
    for tag in _clean_tag_values(value):
        if len(tag) > MAX_TAG_LENGTH:
            raise ValueError(f'单个标签不能超过 {MAX_TAG_LENGTH} 个字符')
        normalized = tag.casefold()
        if normalized in seen:
            continue
        seen.add(normalized)
        tags.append(tag)
        if len(tags) > MAX_TAGS_PER_ARTICLE:
            raise ValueError(f'每篇文章最多设置 {MAX_TAGS_PER_ARTICLE} 个标签')
    return tags


def normalize_legacy_tags(value: object) -> list[str]:
    """Recover valid tags from historical rows without rejecting the article.

    Values are evaluated left to right. Blank and oversized values are skipped,
    case-insensitive duplicates retain their first spelling, and only the first
    ``MAX_TAGS_PER_ARTICLE`` valid tags are kept. New article writes continue to
    use ``normalize_tags`` and reject invalid input instead.
    """
    tags: list[str] = []
    seen: set[str] = set()
    for tag in _clean_tag_values(value):
        if len(tag) > MAX_TAG_LENGTH:
            continue
        normalized = tag.casefold()
        if normalized in seen:
            continue
        seen.add(normalized)
        tags.append(tag)
        if len(tags) == MAX_TAGS_PER_ARTICLE:
            break
    return tags


def normalize_tag_filter(value: object) -> str:
    """Accept one exact tag filter and reject comma-separated pseudo-filters."""
    raw_tag = str(value or '').strip()
    if not raw_tag or ',' in raw_tag:
        return ''
    tags = normalize_tags(raw_tag)
    return tags[0] if len(tags) == 1 else ''


def serialize_tags(tags: list[str]) -> str:
    """Keep the legacy comma-separated article field as a compatibility projection."""
    return ','.join(tags)
