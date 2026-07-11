"""Regression coverage for registry-driven homepage placement and rendering."""

from __future__ import annotations

import pytest
from jinja2 import ChoiceLoader, DictLoader

from features.home import application as home_application
from module_loader import HomeSectionDefinition, get_module_registry
from modules.activity_heatmap import manifest as activity_heatmap_manifest


def _override_home_layout(monkeypatch, layout):
    """Use one feature-level layout for both the full page and AJAX endpoint."""
    monkeypatch.setattr(home_application, "load_home_layout", lambda: layout)


def _install_test_templates(app, monkeypatch, templates):
    """Add module templates without writing into the repository template directory."""
    monkeypatch.setattr(
        app.jinja_env,
        "loader",
        ChoiceLoader([DictLoader(templates), app.jinja_env.loader]),
    )
    app.jinja_env.cache.clear()


def test_registered_custom_context_renders_on_full_page_and_home_api(app, client, monkeypatch):
    """A new module's arbitrary context must not need route or template whitelists."""
    def build_main_context(layout, base_context):
        return {
            "custom_text": f"main:{layout['marker']}:{base_context['current_tag']}",
            "request_mode": base_context["request_context"].get("mode", "missing"),
        }

    def build_sidebar_context(layout, base_context):
        return {
            "custom_text": f"sidebar:{layout['marker']}:{base_context['current_tag']}",
            "request_mode": base_context["request_context"].get("mode", "missing"),
        }

    main_section = HomeSectionDefinition(
        id="test_dynamic_main",
        name="动态主区",
        template="home_sections/test_dynamic_main.html",
        build_context=build_main_context,
    )
    sidebar_section = HomeSectionDefinition(
        id="test_dynamic_sidebar",
        name="动态侧栏",
        template="home_sections/test_dynamic_sidebar.html",
        build_context=build_sidebar_context,
        placement="sidebar",
    )
    monkeypatch.setattr(
        get_module_registry(app),
        "home_sections",
        {main_section.id: main_section, sidebar_section.id: sidebar_section},
    )
    _install_test_templates(
        app,
        monkeypatch,
        {
            "home_sections/test_dynamic_main.html": (
                '<section data-test-section="main">{{ custom_text }}|{{ request_mode }}|'
                "{{ section_id }}|{{ section_name }}</section>"
            ),
            "home_sections/test_dynamic_sidebar.html": (
                '<section data-test-section="sidebar">{{ custom_text }}|{{ request_mode }}|'
                "{{ section_id }}|{{ section_name }}</section>"
            ),
        },
    )
    _override_home_layout(
        monkeypatch,
        {
            "marker": "layout",
            "section_order": [main_section.id, sidebar_section.id],
            "section_visibility": {main_section.id: True, sidebar_section.id: True},
        },
    )

    full_page = client.get("/?tag=测试&mode=full")
    api_response = client.get("/api/home-sections?tag=测试&mode=api")

    assert full_page.status_code == 200
    full_html = full_page.get_data(as_text=True)
    assert "main:layout:测试|full|test_dynamic_main|动态主区" in full_html
    assert "sidebar:layout:测试|full|test_dynamic_sidebar|动态侧栏" in full_html
    assert '<section data-test-section="main">' in full_html
    assert '<section data-test-section="sidebar">' in full_html

    assert api_response.status_code == 200
    api_html = api_response.get_json()["html"]
    assert "main:layout:测试|api|test_dynamic_main|动态主区" in api_html
    assert "test_dynamic_sidebar" not in api_html
    app.jinja_env.cache.clear()


def test_home_api_skips_sidebar_builders_and_heatmap_builds_once_on_full_page(app, client, monkeypatch):
    """The full page builds its sidebar once, while the main-only API skips it."""
    registry = get_module_registry(app)
    heatmap_section = registry.home_sections["activity_heatmap"]
    monkeypatch.setattr(registry, "home_sections", {heatmap_section.id: heatmap_section})
    _override_home_layout(
        monkeypatch,
        {
            "section_order": [heatmap_section.id],
            "section_visibility": {heatmap_section.id: True},
        },
    )

    calls = []

    def build_fake_heatmap(year=None, month=None):
        calls.append((year, month))
        return {
            "year": year or 2026,
            "month": month or 7,
            "prev_year": 2026,
            "prev_month": 6,
            "next_year": 2026,
            "next_month": 8,
            "has_next": False,
            "month_display": "七月",
            "total_words": 0,
            "total": 0,
            "days_remaining": 0,
            "weekday_labels": [],
            "weeks": [],
        }

    monkeypatch.setattr(activity_heatmap_manifest, "build_month_activity_heatmap", build_fake_heatmap)

    full_page = client.get("/?heatmap_year=2024&heatmap_month=2")

    assert full_page.status_code == 200
    assert calls == [(2024, 2)]
    assert 'data-aw-year="2024"' in full_page.get_data(as_text=True)

    calls.clear()
    api_response = client.get("/api/home-sections")

    assert api_response.status_code == 200
    assert api_response.get_json()["html"] == ""
    assert calls == []


def test_home_section_definition_rejects_unknown_placement():
    """A typo in a module manifest must not silently disappear from the page."""
    with pytest.raises(ValueError, match="unsupported home section placement"):
        HomeSectionDefinition(
            id="invalid-placement",
            name="无效位置",
            template="home_sections/unused.html",
            placement="footer",
        )
