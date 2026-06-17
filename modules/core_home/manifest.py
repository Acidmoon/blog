from module_loader import AdminModuleDefinition
from services.home_layout_admin import handle_layout

MODULE = {
    "id": "core_home",
    "name": "核心首页模块",
    "admin_modules": [
        AdminModuleDefinition(
            id="daily_quote",
            label="设置",
            url="/admin/modules/daily_quote",
            description="管理首页 Hero 区域、每日一言与模块顺序",
            icon="📜",
            order=20,
            handler=handle_layout,
        ),
    ],
    "home_sections": [],
}
