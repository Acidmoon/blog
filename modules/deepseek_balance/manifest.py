from module_loader import AdminModuleDefinition


MODULE = {
    "id": "deepseek_balance",
    "name": "DeepSeek Token 统计",
    "home_sections": [],
    "admin_modules": [
        AdminModuleDefinition(
            id="deepseek_balance",
            label="DeepSeek 余额",
            url="/admin/modules/deepseek_balance",
            description="配置 DeepSeek API Key 与 Token 用量显示",
            icon="💰",
            order=50,
            template="admin/deepseek_balance_settings.html",
        ),
    ],
}
