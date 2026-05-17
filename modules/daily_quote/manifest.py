from module_loader import HomeSectionDefinition
from services.home_layout import get_daily_quote


def build_daily_quote_context(layout, base_context):
    return {"daily_quote": get_daily_quote(layout.get("quotes", []))}


MODULE = {
    "id": "daily_quote",
    "name": "每日一言",
    "home_sections": [
        HomeSectionDefinition(
            id="daily_quote",
            name="每日一言",
            template="home_sections/daily_quote.html",
            default_order=10,
            build_context=build_daily_quote_context,
        ),
    ],
    "admin_modules": [],
}
