"""Lightweight registration system for optional blog modules."""

from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass, field
from typing import Any, Callable

from flask import Flask


BuildContext = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class HomeSectionDefinition:
    """A renderable homepage section contributed by a module."""

    id: str
    name: str
    template: str
    default_order: int = 100
    build_context: BuildContext | None = None


@dataclass(frozen=True)
class AdminModuleDefinition:
    """An admin entry/page contributed by a module."""

    id: str
    label: str
    url: str
    description: str = ""
    icon: str = "🧩"
    order: int = 100
    template: str | None = None
    build_context: Callable[[], dict[str, Any]] | None = None
    handler: Callable[[], Any] | None = None


@dataclass
class ModuleDefinition:
    """Normalized module manifest."""

    id: str
    name: str
    enabled: bool = True
    blueprints: list[Any] = field(default_factory=list)
    home_sections: list[HomeSectionDefinition] = field(default_factory=list)
    admin_modules: list[AdminModuleDefinition] = field(default_factory=list)


@dataclass
class ModuleRegistry:
    """In-memory registry populated at app startup."""

    modules: dict[str, ModuleDefinition] = field(default_factory=dict)
    home_sections: dict[str, HomeSectionDefinition] = field(default_factory=dict)
    admin_modules: dict[str, AdminModuleDefinition] = field(default_factory=dict)

    def register_module(self, module: ModuleDefinition) -> None:
        if not module.enabled:
            return
        self.modules[module.id] = module
        for section in module.home_sections:
            self.home_sections[section.id] = section
        for admin_module in module.admin_modules:
            self.admin_modules[admin_module.id] = admin_module


REGISTRY = ModuleRegistry()


def _coerce_home_section(raw: Any) -> HomeSectionDefinition:
    if isinstance(raw, HomeSectionDefinition):
        return raw
    if not isinstance(raw, dict):
        raise TypeError(f"home section must be dict or HomeSectionDefinition, got {type(raw)!r}")
    return HomeSectionDefinition(
        id=str(raw["id"]),
        name=str(raw.get("name") or raw["id"]),
        template=str(raw["template"]),
        default_order=int(raw.get("default_order", 100) or 100),
        build_context=raw.get("build_context"),
    )


def _coerce_admin_module(raw: Any) -> AdminModuleDefinition:
    if isinstance(raw, AdminModuleDefinition):
        return raw
    if not isinstance(raw, dict):
        raise TypeError(f"admin module must be dict or AdminModuleDefinition, got {type(raw)!r}")
    module_id = str(raw["id"])
    return AdminModuleDefinition(
        id=module_id,
        label=str(raw.get("label") or raw.get("name") or module_id),
        url=str(raw.get("url") or f"/admin/modules/{module_id}"),
        description=str(raw.get("description") or ""),
        icon=str(raw.get("icon") or "🧩"),
        order=int(raw.get("order", 100) or 100),
        template=raw.get("template"),
        build_context=raw.get("build_context"),
        handler=raw.get("handler"),
    )


def _coerce_module(raw: Any, import_name: str) -> ModuleDefinition:
    if isinstance(raw, ModuleDefinition):
        return raw
    if not isinstance(raw, dict):
        raise TypeError(f"{import_name}.MODULE must be dict or ModuleDefinition, got {type(raw)!r}")
    module_id = str(raw.get("id") or import_name.rsplit(".", 2)[-2])
    return ModuleDefinition(
        id=module_id,
        name=str(raw.get("name") or module_id),
        enabled=bool(raw.get("enabled", True)),
        blueprints=list(raw.get("blueprints", [])),
        home_sections=[_coerce_home_section(item) for item in raw.get("home_sections", [])],
        admin_modules=[_coerce_admin_module(item) for item in raw.get("admin_modules", [])],
    )


def discover_modules(package_name: str = "modules") -> list[ModuleDefinition]:
    """Import modules/*/manifest.py and return enabled module definitions."""
    package = importlib.import_module(package_name)
    discovered: list[ModuleDefinition] = []
    for module_info in pkgutil.iter_modules(package.__path__, package.__name__ + "."):
        if not module_info.ispkg:
            continue
        manifest_name = f"{module_info.name}.manifest"
        try:
            manifest = importlib.import_module(manifest_name)
        except ModuleNotFoundError as exc:
            if exc.name == manifest_name:
                continue
            raise
        raw = getattr(manifest, "MODULE", None)
        if raw is None:
            continue
        module = _coerce_module(raw, manifest_name)
        if module.enabled:
            discovered.append(module)
    return discovered


def load_modules(app: Flask, package_name: str = "modules") -> ModuleRegistry:
    """Discover modules, register their blueprints, and populate REGISTRY."""
    REGISTRY.modules.clear()
    REGISTRY.home_sections.clear()
    REGISTRY.admin_modules.clear()

    for module in discover_modules(package_name):
        REGISTRY.register_module(module)
        for blueprint in module.blueprints:
            app.register_blueprint(blueprint)

    app.extensions["blog_modules"] = REGISTRY
    return REGISTRY
