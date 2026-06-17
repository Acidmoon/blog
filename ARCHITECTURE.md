# 水浇岭博客代码结构

这是一个小型 Flask 单体博客。当前重构目标是先把结构规范化，保持现有功能和 URL 不变，为后续“自定义模块”预留入口。

## 目录职责

```text
/root/blog/
├── app.py                 # create_app / 初始化配置 / 注册 Blueprint
├── config.py              # 路径、站点配置、环境变量、目录初始化
├── models.py              # SQLite 连接与表初始化
├── module_loader.py       # 自定义模块发现、manifest 解析、Blueprint/section 注册
├── modules/               # 可插拔模块目录，每个子目录可提供 manifest.py
├── routes/                # 页面和接口入口
│   ├── public.py          # public Blueprint 聚合入口，保持 endpoint 兼容
│   ├── public_pages.py    # 首页、文章详情、搜索、静态资源路由
│   ├── public_auth.py     # 访客登录、退出、弹窗认证 API
│   ├── public_social.py   # 文章评论、点赞 API
│   ├── home_api.py        # 首页 AJAX 片段 API
│   └── admin.py           # 后台页面入口，业务命令委托 services
├── services/              # 可复用业务逻辑
│   ├── articles.py        # 文章文件、Markdown、标签、文章列表
│   ├── media_uploads.py   # 后台媒体上传校验与保存
│   ├── search.py          # 搜索和高亮
│   ├── home_layout.py     # 首页一言配置、hitokoto、缓存
│   └── home_modules.py    # 首页模块注册、排序、渲染上下文
├── templates/             # Jinja 模板
├── static/                # CSS / JS / 图片
├── data/                  # SQLite、文章 Markdown、上传图片、缓存
└── docker-compose.yml
```

## 约定

1. 新页面或新接口优先放到 `routes/` 下的 Blueprint，不直接堆到 `app.py`。
2. 可复用逻辑放到 `services/`，路由层只负责取参数、调用服务、渲染模板或返回 JSON。
3. 数据库连接、表初始化只放在 `models.py`。
4. 路径、环境变量、站点标题等只放在 `config.py`。
5. 现有 URL 暂时保持不变：`/`、`/search`、`/article/<slug>`、`/admin/*`。

## 注册制模块约定

`app.py` 启动时会先调用 `module_loader.load_modules(app)`，自动扫描 `modules/*/manifest.py`。每个模块通过 `MODULE` 声明自己的元信息、Blueprint 和首页 section：

```python
from module_loader import HomeSectionDefinition

MODULE = {
    "id": "example",
    "name": "示例模块",
    "blueprints": [bp],
    "home_sections": [
        HomeSectionDefinition(
            id="example_section",
            name="示例首页块",
            template="home_sections/example.html",
            default_order=50,
            build_context=lambda layout, base_context: {"extra": "value"},
        )
    ],
}
```

模块目录建议：

```text
modules/
  example/
    __init__.py
    manifest.py      # 模块元信息、Blueprint、前台 section 声明
    routes.py        # 模块自己的 Blueprint，可选
    service.py       # 模块业务逻辑，可选
```

`module_loader.REGISTRY` 会保存已加载模块和首页 section。`services/home_modules.py` 从这个 registry 读取 section，负责排序、上下文构建和传给首页模板。

后台模块可以通过 `AdminModuleDefinition.handler` 声明自己的请求处理函数；核心后台路由不应再根据模块 ID 写特殊分支。

## 首页模块渲染约定

首页不再在 `templates/index.html` 里写死「一言 → 标签 → 文章 → 分页」的固定槽位。内置首页模块现在也是普通注册模块：`modules/core_home/manifest.py` 注册这些 section：

```text
daily_quote   -> templates/home_sections/daily_quote.html
tag_filter    -> templates/home_sections/tag_filter.html
article_list  -> templates/home_sections/article_list.html
pagination    -> templates/home_sections/pagination.html
```

`home_layout.json` 的 `section_order` 控制首页模块从上到下的顺序，`section_visibility` 控制每个模块是否显示；后台 `/admin/layout` 可编辑顺序并勾选启用/隐藏模块。`index.html` 只负责遍历 `home_sections` 并 include 对应模板，这样新增模块时不需要再给首页硬塞一个固定位置。

后续如果要加“自定义模块”，优先新增 `modules/<name>/manifest.py`，而不是修改 `app.py` 或 `templates/index.html`。
