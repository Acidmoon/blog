"""Homepage section composition backed by the module registry."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

import config
from flask import render_template
from markupsafe import Markup

from module_loader import HOME_SECTION_PLACEMENTS, HomeSectionDefinition, get_module_registry


def section_registry() -> dict[str, HomeSectionDefinition]:
    """Return homepage sections for the current Flask application."""
    return get_module_registry().home_sections


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


def _normalize_requested_placements(
    placements: Iterable[str] | None,
) -> frozenset[str] | None:
    """Validate an optional placement filter supplied by a page renderer."""
    if placements is None:
        return None
    if isinstance(placements, str):
        placements = (placements,)

    normalized = frozenset(str(placement).strip().lower() for placement in placements)
    unsupported = normalized.difference(HOME_SECTION_PLACEMENTS)
    if unsupported:
        supported = ", ".join(sorted(HOME_SECTION_PLACEMENTS))
        invalid = ", ".join(sorted(unsupported))
        raise ValueError(f"unsupported home section placement(s): {invalid}; expected: {supported}")
    return normalized


def split_home_sections(sections: Iterable[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split registered sections into the existing main and sidebar containers."""
    main_sections: list[dict[str, Any]] = []
    sidebar_sections: list[dict[str, Any]] = []
    for section in sections:
        if section["placement"] == "sidebar":
            sidebar_sections.append(section)
        else:
            main_sections.append(section)
    return main_sections, sidebar_sections


def render_home_section(section: Mapping[str, Any]) -> Markup:
    """Render one registered section with all of its declared context.

    The template path comes from the trusted module manifest. Values produced by
    a module's context builder are still autoescaped by Jinja before the final
    trusted template output is marked safe for inclusion in ``index.html``.
    ``section``, ``section_id``, and ``section_name`` are reserved metadata
    keys supplied consistently to every section template.
    """
    section_context = section.get("context")
    if not isinstance(section_context, Mapping):
        raise TypeError("home section context must be a mapping")

    render_context = dict(section_context)
    render_context.update(
        {
            "section": section,
            "section_id": section["id"],
            "section_name": section["name"],
        }
    )
    return Markup(render_template(str(section["template"]), **render_context))


def build_home_sections(
    layout: dict[str, Any],
    *,
    articles: list[Any],
    page: int,
    total: int,
    current_tag: str,
    all_tags: list[str],
    placements: Iterable[str] | None = None,
    request_context: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Build ordered homepage sections from the module registry.

    ``placements`` lets fragment endpoints skip containers they never return,
    avoiding work in unrelated sidebar modules. Builders receive a copy of the
    shared page state plus a plain ``request_context`` mapping, while templates
    receive only the common page state and the values explicitly returned by
    their own builder.
    """
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
    builder_context = dict(base_context)
    builder_context["request_context"] = dict(request_context or {})
    requested_placements = _normalize_requested_placements(placements)

    sections: list[dict[str, Any]] = []
    registry = section_registry()
    for section_id in normalize_section_order(layout.get("section_order")):
        if not is_section_enabled(layout, section_id):
            continue
        definition = registry[section_id]
        if requested_placements is not None and definition.placement not in requested_placements:
            continue
        context = dict(base_context)
        if definition.build_context:
            custom_context = definition.build_context(layout, dict(builder_context))
            if not isinstance(custom_context, Mapping):
                raise TypeError(f"home section {definition.id!r} build_context must return a mapping")
            context.update(custom_context)
        sections.append({
            "id": definition.id,
            "name": definition.name,
            "template": definition.template,
            "placement": definition.placement,
            "context": context,
        })
    return sections
