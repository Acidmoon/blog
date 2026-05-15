"""Homepage section composition backed by the module registry."""

from __future__ import annotations

from typing import Any

import config
from module_loader import REGISTRY, HomeSectionDefinition


def section_registry() -> dict[str, HomeSectionDefinition]:
    """Return homepage sections contributed by loaded modules."""
    return REGISTRY.home_sections


def default_section_order() -> list[str]:
    return [
        section.id
        for section in sorted(section_registry().values(), key=lambda item: item.default_order)
    ]


def normalize_section_visibility(raw_visibility: Any) -> dict[str, bool]:
    """Return per-section visibility for every registered homepage section.

    Missing values default to True so newly installed modules appear on the
    homepage automatically until the admin explicitly hides them.
    """
    registry = section_registry()
    if not isinstance(raw_visibility, dict):
        raw_visibility = {}

    return {
        section_id: bool(raw_visibility.get(section_id, True))
        for section_id in registry
    }


def is_section_enabled(layout: dict[str, Any], section_id: str) -> bool:
    return normalize_section_visibility(layout.get("section_visibility")).get(section_id, True)


def normalize_section_order(raw_order: Any) -> list[str]:
    """Return a safe, deduplicated section order.

    Unknown ids are ignored. Missing registered sections are appended by default
    so layout config remains forward-compatible when modules are added.
    """
    registry = section_registry()
    if not isinstance(raw_order, list):
        raw_order = []

    normalized: list[str] = []
    for section_id in raw_order:
        if section_id in registry and section_id not in normalized:
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
    """Build ordered homepage sections for index.html."""
    total_pages = max(1, (total + config.ARTICLES_PER_PAGE - 1) // config.ARTICLES_PER_PAGE)
    base_context = {
        "articles": articles,
        "page": page,
        "total": total,
        "per_page": config.ARTICLES_PER_PAGE,
        "total_pages": total_pages,
        "current_tag": current_tag,
        "all_tags": all_tags,
    }

    sections: list[dict[str, Any]] = []
    registry = section_registry()
    for section_id in normalize_section_order(layout.get("section_order")):
        if not is_section_enabled(layout, section_id):
            continue
        definition = registry[section_id]
        context = dict(base_context)
        if definition.build_context:
            context.update(definition.build_context(layout, base_context))
        sections.append({
            "id": definition.id,
            "name": definition.name,
            "template": definition.template,
            "context": context,
        })
    return sections
