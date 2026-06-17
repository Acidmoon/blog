"""Admin navigation and module page helpers."""

from __future__ import annotations

from typing import Any

from module_loader import REGISTRY, AdminModuleDefinition


def admin_module_registry() -> dict[str, AdminModuleDefinition]:
    """Return admin modules contributed by loaded modules."""
    return REGISTRY.admin_modules


def admin_module_list() -> list[AdminModuleDefinition]:
    return sorted(admin_module_registry().values(), key=lambda item: (item.order, item.id))


def _nav_item(url: str, label: str) -> dict[str, str]:
    return {"url": url, "label": label}


def build_admin_nav_groups() -> list[dict[str, Any]]:
    """Return the admin navigation grouped by product area."""
    return [
        {
            "id": "content",
            "label": "内容",
            "items": [_nav_item("/admin", "文章")],
        },
        {
            "id": "home",
            "label": "首页",
            "items": [_nav_item(item.url, item.label) for item in admin_module_list()],
        },
        {
            "id": "ai",
            "label": "AI",
            "items": [_nav_item("/admin/chat-settings", "AI 对话")],
        },
        {
            "id": "access",
            "label": "访问",
            "items": [_nav_item("/admin/access-settings", "访问设置")],
        },
        {
            "id": "system",
            "label": "系统",
            "items": [_nav_item("/admin/logout", "退出")],
        },
    ]


def build_admin_nav() -> list[dict[str, str]]:
    """Build the flat top navigation shown after login."""
    nav: list[dict[str, str]] = []
    for group in build_admin_nav_groups():
        nav.extend(group["items"])
    return nav


def get_admin_module(module_id: str) -> AdminModuleDefinition | None:
    return admin_module_registry().get(module_id)


def build_admin_module_context(module: AdminModuleDefinition) -> dict[str, Any]:
    context = {"module": module}
    if module.build_context:
        context.update(module.build_context())
    return context
