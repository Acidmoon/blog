"""Homepage application workflows composed from layout and article services."""

from __future__ import annotations

from typing import Any, Mapping

from services.articles import list_all_tags, list_featured_articles, list_published_articles
from services.home_layout import load_home_layout, resolve_hero
from services.home_modules import build_home_sections, render_home_section, split_home_sections


def _home_data(page: int, current_tag: str) -> tuple[dict[str, Any], list[Any], int, list[str]]:
    """Load the common article and layout state used by both home responses."""
    articles, total = list_published_articles(page=page, tag=current_tag)
    layout = load_home_layout()
    return layout, articles, total, list_all_tags()


def build_public_home_context(
    *,
    page: int,
    current_tag: str,
    request_context: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Build the complete template context for the public homepage."""
    layout, articles, total, all_tags = _home_data(page, current_tag)
    all_home_sections = build_home_sections(
        layout,
        articles=articles,
        page=page,
        total=total,
        current_tag=current_tag,
        all_tags=all_tags,
        request_context=request_context,
    )
    home_sections, sidebar_sections = split_home_sections(all_home_sections)
    for section in home_sections:
        section["html"] = render_home_section(section)
    for section in sidebar_sections:
        if section["id"] != "activity_heatmap":
            section["html"] = render_home_section(section)
    return {
        "hero": resolve_hero(layout.get("hero"), current_tag),
        "body_class": "home-page",
        "featured_articles": list_featured_articles(layout.get("featured_articles"), limit=5),
        "home_sections": home_sections,
        "sidebar_sections": sidebar_sections,
    }


def build_main_home_sections_payload(
    *,
    page: int,
    current_tag: str,
    request_context: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Build the JSON-safe hero and rendered main-column section fragment."""
    layout, articles, total, all_tags = _home_data(page, current_tag)
    sections = build_home_sections(
        layout,
        articles=articles,
        page=page,
        total=total,
        current_tag=current_tag,
        all_tags=all_tags,
        placements=("main",),
        request_context=request_context,
    )
    return {
        "hero": resolve_hero(layout.get("hero"), current_tag),
        "html": "".join(render_home_section(section) for section in sections),
    }
