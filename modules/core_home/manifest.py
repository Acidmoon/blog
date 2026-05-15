from module_loader import AdminModuleDefinition, HomeSectionDefinition
from services.home_layout import get_daily_quote


def build_daily_quote_context(layout, base_context):
    return {"daily_quote": get_daily_quote(layout.get("quotes", []))}


MODULE = {
    "id": "core_home",
    "name": "核心首页模块",
    "admin_modules": [
        AdminModuleDefinition(
            id="daily_quote",
            label="一言",
            url="/admin/modules/daily_quote",
            description="管理每日一言与首页模块顺序",
            icon="📜",
            order=20,
        ),
    ],
    "home_sections": [
        HomeSectionDefinition(
            id="daily_quote",
            name="每日一言",
            template="home_sections/daily_quote.html",
            default_order=10,
            build_context=build_daily_quote_context,
        ),
        HomeSectionDefinition(
            id="tag_filter",
            name="标签筛选",
            template="home_sections/tag_filter.html",
            default_order=20,
        ),
        HomeSectionDefinition(
            id="article_list",
            name="文章列表",
            template="home_sections/article_list.html",
            default_order=30,
        ),
        HomeSectionDefinition(
            id="pagination",
            name="分页",
            template="home_sections/pagination.html",
            default_order=40,
        ),
    ],
}
