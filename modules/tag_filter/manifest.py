from module_loader import HomeSectionDefinition

MODULE = {
    "id": "tag_filter",
    "name": "标签筛选",
    "api_version": 1,
    "capabilities": ["home_sections"],
    "home_sections": [
        HomeSectionDefinition(
            id="tag_filter",
            name="标签筛选",
            template="home_sections/tag_filter.html",
            default_order=20,
        ),
    ],
    "admin_modules": [],
}
