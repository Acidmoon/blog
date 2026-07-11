from module_loader import HomeSectionDefinition

MODULE = {
    "id": "pagination",
    "name": "分页",
    "api_version": 1,
    "capabilities": ["home_sections"],
    "home_sections": [
        HomeSectionDefinition(
            id="pagination",
            name="分页",
            template="home_sections/pagination.html",
            default_order=40,
        ),
    ],
    "admin_modules": [],
}
