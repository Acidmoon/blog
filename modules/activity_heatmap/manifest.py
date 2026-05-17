from module_loader import HomeSectionDefinition
from services.activity_heatmap import build_month_activity_heatmap


def build_activity_heatmap_context(layout, base_context):
    return {"activity_heatmap": build_month_activity_heatmap()}


MODULE = {
    "id": "activity_heatmap",
    "name": "月度活动热力图",
    "home_sections": [
        HomeSectionDefinition(
            id="activity_heatmap",
            name="月度活动热力图",
            template="home_sections/activity_heatmap.html",
            default_order=5,
            build_context=build_activity_heatmap_context,
        ),
    ],
    "admin_modules": [],
}
