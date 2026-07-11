"""Admin handler for homepage layout settings."""

from flask import flash, redirect, render_template, request, url_for

from services.articles import list_admin_articles
from services.home_layout import load_home_layout, save_home_layout
from services.home_modules import (
    normalize_section_order,
    normalize_section_visibility,
    section_registry,
)


FEATURED_SLOT_COUNT = 5


def _featured_articles_from_form() -> list[str]:
    slugs = []
    for index in range(FEATURED_SLOT_COUNT):
        slug = request.form.get(f"featured_article_{index}", "").strip()
        if slug and slug not in slugs:
            slugs.append(slug)
    return slugs


def _featured_slots(layout_config: dict) -> list[str]:
    configured = layout_config.get("featured_articles")
    if not isinstance(configured, list):
        configured = []
    return [str(configured[index]) if index < len(configured) else "" for index in range(FEATURED_SLOT_COUNT)]


def handle_layout():
    """GET renders the homepage editor; POST saves focused homepage settings."""
    layout_config = load_home_layout()
    registry = section_registry()

    if request.method == 'POST':
        quotes_raw = request.form.get("quotes", "").strip()
        quotes = [q.strip() for q in quotes_raw.splitlines() if q.strip()]

        layout_config["featured_articles"] = _featured_articles_from_form()
        hero = layout_config.setdefault("hero", {"_default": {}, "tags": {}})
        if not isinstance(hero, dict):
            hero = {"_default": {}, "tags": {}}
            layout_config["hero"] = hero
        default_hero = hero.setdefault("_default", {})
        if not isinstance(default_hero, dict):
            default_hero = {}
            hero["_default"] = default_hero
        for field in ("label", "title", "subtitle"):
            default_hero[field] = request.form.get(f"hero_{field}", "").strip()
        layout_config["quotes"] = quotes or ["书山有路勤为径，学海无涯苦作舟。"]
        layout_config["section_order"] = normalize_section_order(layout_config.get("section_order"))
        layout_config["section_visibility"] = {
            section_id: request.form.get(f"section_enabled_{section_id}") == "on"
            for section_id in registry
        }
        save_home_layout(layout_config)
        flash('首页设置已保存', 'success')
        return redirect(url_for('admin.layout'))

    quotes_text = "\n".join(layout_config.get("quotes", []))
    section_order = normalize_section_order(layout_config.get("section_order"))
    section_visibility = normalize_section_visibility(layout_config.get("section_visibility"))
    article_options = list_admin_articles()
    section_help = [
        {
            "id": section_id,
            "name": definition.name,
            "enabled": section_visibility.get(section_id, True),
            "in_order": section_id in section_order,
        }
        for section_id, definition in sorted(
            registry.items(),
            key=lambda item: (item[1].default_order, item[0]),
        )
    ]
    return render_template(
        'admin/layout.html',
        hero_default=(layout_config.get("hero", {}).get("_default", {}) if isinstance(layout_config.get("hero"), dict) else {}),
        article_options=article_options,
        featured_slots=_featured_slots(layout_config),
        quotes_text=quotes_text,
        section_help=section_help,
    )
