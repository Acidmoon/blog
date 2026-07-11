"""Focused tests for application-local module registration."""

from __future__ import annotations

import pytest
from flask import Flask

import module_loader
from module_loader import (
    AdminModuleDefinition,
    HomeSectionDefinition,
    MODULE_REGISTRY_EXTENSION_KEY,
    ModuleDefinition,
    ModuleRegistry,
    get_module_registry,
    load_modules,
)
from services.admin_modules import admin_module_registry
from services.home_modules import section_registry


def _module_definition(module_id, *, section_id=None, admin_id=None):
    """Build a small module definition with optional section and admin identifiers."""
    home_sections = []
    if section_id:
        home_sections.append(
            HomeSectionDefinition(
                id=section_id,
                name=f"section:{section_id}",
                template=f"home_sections/{section_id}.html",
            )
        )

    admin_modules = []
    if admin_id:
        admin_modules.append(
            AdminModuleDefinition(
                id=admin_id,
                label=f"admin:{admin_id}",
                url=f"/admin/modules/{admin_id}",
            )
        )

    return ModuleDefinition(
        id=module_id,
        name=f"module:{module_id}",
        home_sections=home_sections,
        admin_modules=admin_modules,
    )


def test_load_modules_keeps_each_flask_application_registry_isolated():
    """Loading a second app must not replace the first app's registered modules."""
    first_app = Flask("first-module-registry-test")
    second_app = Flask("second-module-registry-test")

    first_registry = load_modules(first_app)
    second_registry = load_modules(second_app)

    assert first_registry is get_module_registry(first_app)
    assert second_registry is get_module_registry(second_app)
    assert first_registry is not second_registry

    first_registry.home_sections.pop("activity_heatmap")
    with first_app.app_context():
        assert "activity_heatmap" not in section_registry()
        assert admin_module_registry() is first_registry.admin_modules
    with second_app.app_context():
        assert "activity_heatmap" in section_registry()
        assert admin_module_registry() is second_registry.admin_modules

    with pytest.raises(RuntimeError, match="already initialized"):
        load_modules(first_app)


def test_module_registry_rejects_duplicate_module_section_and_admin_identifiers():
    """Conflicting manifests fail before a later registration can overwrite earlier data."""
    registry = ModuleRegistry()
    first = _module_definition("first", section_id="shared-section", admin_id="shared-admin")
    registry.register_module(first)

    with pytest.raises(ValueError, match="duplicate module id"):
        registry.register_module(_module_definition("first", section_id="other-section"))
    assert registry.modules["first"] is first

    with pytest.raises(ValueError, match="duplicate home section id"):
        registry.register_module(_module_definition("second", section_id="shared-section"))
    assert "second" not in registry.modules
    assert registry.home_sections["shared-section"].name == "section:shared-section"

    with pytest.raises(ValueError, match="duplicate admin module id"):
        registry.register_module(_module_definition("third", admin_id="shared-admin"))
    assert "third" not in registry.modules
    assert registry.admin_modules["shared-admin"].label == "admin:shared-admin"


def test_load_modules_rejects_duplicate_discovery_without_attaching_partial_registry(monkeypatch):
    """The loader validates all discovered manifests before mutating an application."""
    app = Flask("duplicate-module-discovery-test")
    duplicate_modules = [
        _module_definition("first", section_id="shared-section"),
        _module_definition("second", section_id="shared-section"),
    ]
    monkeypatch.setattr(module_loader, "discover_modules", lambda package_name: duplicate_modules)

    with pytest.raises(ValueError, match="duplicate home section id"):
        load_modules(app)

    assert MODULE_REGISTRY_EXTENSION_KEY not in app.extensions
