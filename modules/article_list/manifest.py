from module_loader import HomeSectionDefinition

MODULE = {
    "id": "article_list",
    "name": "文章列表",
    "api_version": 1,
    "capabilities": ["home_sections"],
    "home_sections": [
        HomeSectionDefinition(
            id="article_list",
            name="文章列表",
            template="home_sections/article_list.html",
            default_order=30,
        ),
    ],
    "admin_modules": [],
}
