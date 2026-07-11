from module_loader import HomeSectionDefinition
from services.activity_heatmap import build_month_activity_heatmap


def _optional_query_int(request_context, name):
    """Read an optional integer query value without making the module Flask-specific."""
    value = request_context.get(name)
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def build_activity_heatmap_context(layout, base_context):
    request_context = base_context.get("request_context", {})
    if not isinstance(request_context, dict):
        request_context = {}
    return {
        "activity_heatmap": build_month_activity_heatmap(
            year=_optional_query_int(request_context, "heatmap_year"),
            month=_optional_query_int(request_context, "heatmap_month"),
        )
    }


MODULE = {
    "id": "activity_heatmap",
    "name": "月度活动热力图",
    "api_version": 1,
    "capabilities": ["home_sections"],
    "home_sections": [
        HomeSectionDefinition(
            id="activity_heatmap",
            name="月度活动热力图",
            template="home_sections/activity_heatmap.html",
            default_order=5,
            build_context=build_activity_heatmap_context,
            placement="sidebar",
        ),
    ],
    "admin_modules": [],
}
