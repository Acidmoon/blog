"""Admin navigation and module page helpers."""

from __future__ import annotations

from typing import Any

from module_loader import REGISTRY, AdminModuleDefinition


def admin_module_registry() -> dict[str, AdminModuleDefinition]:
    """Return admin modules contributed by loaded modules."""
    return REGISTRY.admin_modules


def admin_module_list() -> list[AdminModuleDefinition]:
    return sorted(admin_module_registry().values(), key=lambda item: (item.order, item.id))


def build_admin_nav() -> list[dict[str, str]]:
    """Build the top navigation shown after login."""
    nav = [{"url": "/admin", "label": "文章"}]
    nav.extend({"url": item.url, "label": item.label} for item in admin_module_list())
    nav.append({"url": "/admin/chat-settings", "label": "AI 对话"})
    nav.append({"url": "/admin/access-settings", "label": "访问设置"})
    nav.append({"url": "/admin/logout", "label": "退出"})
    return nav


def get_admin_module(module_id: str) -> AdminModuleDefinition | None:
    return admin_module_registry().get(module_id)


def build_admin_module_context(module: AdminModuleDefinition) -> dict[str, Any]:
    context = {"module": module}
    if module.build_context:
        context.update(module.build_context())
    return context
