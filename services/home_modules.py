"""Lightweight homepage module/section composition.

This keeps homepage blocks out of a fixed template order. Each block declares an
id, template, default order and the context it needs. The persisted layout config
can reorder or hide blocks without changing routes/public.py or index.html.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import config
from services.home_layout import get_daily_quote


@dataclass(frozen=True)
class HomeSectionDefinition:
    id: str
    name: str
    template: str
    default_order: int


SECTION_REGISTRY: dict[str, HomeSectionDefinition] = {
    "daily_quote": HomeSectionDefinition(
        id="daily_quote",
        name="每日一言",
        template="home_sections/daily_quote.html",
        default_order=10,
    ),
    "tag_filter": HomeSectionDefinition(
        id="tag_filter",
        name="标签筛选",
        template="home_sections/tag_filter.html",
        default_order=20,
    ),
    "article_list": HomeSectionDefinition(
        id="article_list",
        name="文章列表",
        template="home_sections/article_list.html",
        default_order=30,
    ),
    "pagination": HomeSectionDefinition(
        id="pagination",
        name="分页",
        template="home_sections/pagination.html",
        default_order=40,
    ),
}


def default_section_order() -> list[str]:
    return [
        section.id
        for section in sorted(SECTION_REGISTRY.values(), key=lambda item: item.default_order)
    ]


def normalize_section_order(raw_order: Any) -> list[str]:
    """Return a safe, deduplicated section order.

    Unknown ids are ignored. Missing known sections are appended by default so a
    partial config remains forward-compatible when new modules are added.
    """
    if not isinstance(raw_order, list):
        raw_order = []

    normalized: list[str] = []
    for section_id in raw_order:
        if section_id in SECTION_REGISTRY and section_id not in normalized:
            normalized.append(section_id)

    for section_id in default_section_order():
        if section_id not in normalized:
            normalized.append(section_id)

    return normalized


def section_order_to_text(order: list[str]) -> str:
    return "\n".join(order)


def section_order_from_text(text: str) -> list[str]:
    return normalize_section_order([
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ])


def build_home_sections(
    layout: dict[str, Any],
    *,
    articles: list[Any],
    page: int,
    total: int,
    current_tag: str,
    all_tags: list[str],
) -> list[dict[str, Any]]:
    """Build ordered homepage sections for index.html.

    The index template only iterates these sections. Adding a future custom
    module means registering a new section definition and template rather than
    hard-coding another slot into index.html.
    """
    total_pages = max(1, (total + config.ARTICLES_PER_PAGE - 1) // config.ARTICLES_PER_PAGE)
    common_context = {
        "articles": articles,
        "page": page,
        "total": total,
        "per_page": config.ARTICLES_PER_PAGE,
        "total_pages": total_pages,
        "current_tag": current_tag,
        "all_tags": all_tags,
        "daily_quote": get_daily_quote(layout.get("quotes", [])),
    }

    sections: list[dict[str, Any]] = []
    for section_id in normalize_section_order(layout.get("section_order")):
        definition = SECTION_REGISTRY[section_id]
        sections.append({
            "id": definition.id,
            "name": definition.name,
            "template": definition.template,
            "context": common_context,
        })
    return sections
