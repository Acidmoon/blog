"""Home layout admin handler — extracted from routes/admin.py to keep the
route file focused on routing concerns rather than 100 lines of form parsing."""

from flask import flash, redirect, render_template, request, url_for

from services.articles import list_all_tags_admin
from services.home_layout import load_home_layout, save_home_layout
from services.home_modules import (
    normalize_section_order,
    normalize_section_visibility,
    section_order_from_text,
    section_order_to_text,
    section_registry,
)


def handle_layout():
    """GET renders the layout editor; POST saves hero / quotes / section config."""
    layout_config = load_home_layout()
    if request.method == 'POST':
        quotes_raw = request.form.get("quotes", "").strip()
        quotes = [q.strip() for q in quotes_raw.splitlines() if q.strip()]
        section_order_raw = request.form.get("section_order", "")
        registry = section_registry()

        hero_label = request.form.get("hero_label", "").strip()
        hero_title = request.form.get("hero_title", "").strip()
        hero_subtitle = request.form.get("hero_subtitle", "").strip()

        hero_tags = {}
        i = 0
        while True:
            name = request.form.get(f"hero_tag_{i}_name", "").strip()
            if not name:
                break
            label = request.form.get(f"hero_tag_{i}_label", "").strip()
            title = request.form.get(f"hero_tag_{i}_title", "").strip()
            subtitle = request.form.get(f"hero_tag_{i}_subtitle", "").strip()
            if label or title or subtitle:
                hero_tags[name] = {"label": label, "title": title, "subtitle": subtitle}
            i += 1

        layout_config["hero"] = {
            "_default": {
                "label": hero_label or "水浇岭",
                "title": hero_title or "水浇岭的博客",
                "subtitle": hero_subtitle or "写点有意思的东西",
            },
            "tags": hero_tags,
        }
        layout_config["quotes"] = quotes or ["书山有路勤为径，学海无涯苦作舟。"]
        layout_config["section_order"] = section_order_from_text(section_order_raw)
        layout_config["section_visibility"] = {
            section_id: request.form.get(f"section_enabled_{section_id}") == "on"
            for section_id in registry
        }
        save_home_layout(layout_config)
        flash('首页布局已更新', 'success')
        return redirect(url_for('admin.layout'))

    quotes_text = "\n".join(layout_config.get("quotes", []))
    section_order = normalize_section_order(layout_config.get("section_order"))
    section_order_text = section_order_to_text(section_order)
    registry = section_registry()
    section_visibility = normalize_section_visibility(layout_config.get("section_visibility"))
    hero = layout_config.get("hero", {})
    if not isinstance(hero, dict):
        hero = {}
    if "_default" in hero:
        hero_default = hero.get("_default", {})
        hero_label_val = hero_default.get("label", "水浇岭")
        hero_title_val = hero_default.get("title", "水浇岭的博客")
        hero_subtitle_val = hero_default.get("subtitle", "写点有意思的东西")
        hero_tags = hero.get("tags", {})
    else:
        hero_label_val = hero.get("label", "水浇岭")
        hero_title_val = hero.get("title", "水浇岭的博客")
        hero_subtitle_val = hero.get("subtitle", "写点有意思的东西")
        hero_tags = {}
    all_tags = list_all_tags_admin()
    hero_tags_entries = [
        {
            "tag": tag,
            "label": hero_tags.get(tag, {}).get("label", ""),
            "title": hero_tags.get(tag, {}).get("title", ""),
            "subtitle": hero_tags.get(tag, {}).get("subtitle", ""),
        }
        for tag in all_tags
    ]
    section_help = [
        {
            "id": section_id,
            "name": definition.name,
            "template": definition.template,
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
        hero_label=hero_label_val,
        hero_title=hero_title_val,
        hero_subtitle=hero_subtitle_val,
        hero_tags_entries=hero_tags_entries,
        quotes_text=quotes_text,
        section_order_text=section_order_text,
        section_help=section_help,
    )
