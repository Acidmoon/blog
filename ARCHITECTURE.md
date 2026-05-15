# 水浇岭博客代码结构

这是一个小型 Flask 单体博客。当前重构目标是先把结构规范化，保持现有功能和 URL 不变，为后续“自定义模块”预留入口。

## 目录职责

```text
/root/blog/
├── app.py                 # create_app / 初始化配置 / 注册 Blueprint
├── config.py              # 路径、站点配置、环境变量、目录初始化
├── models.py              # SQLite 连接与表初始化
├── routes/                # 页面和接口入口
│   ├── public.py          # 首页、文章详情、搜索、静态资源路由
│   └── admin.py           # 登录、文章 CRUD、上传、一言配置
├── services/              # 可复用业务逻辑
│   ├── articles.py        # 文章文件、Markdown、标签、文章列表
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

## 首页模块渲染约定

首页不再在 `templates/index.html` 里写死「一言 → 标签 → 文章 → 分页」的固定槽位，而是由 `services/home_modules.py` 统一注册可渲染 section：

```text
SECTION_REGISTRY
  daily_quote   -> templates/home_sections/daily_quote.html
  tag_filter    -> templates/home_sections/tag_filter.html
  article_list  -> templates/home_sections/article_list.html
  pagination    -> templates/home_sections/pagination.html
```

`home_layout.json` 的 `section_order` 控制首页模块从上到下的顺序；后台 `/admin/layout` 可编辑这个顺序。`index.html` 只负责遍历 `home_sections` 并 include 对应模板，这样新增模块时不需要再给首页硬塞一个固定位置。

## 后续自定义模块建议

后续如果要加“自定义模块”，建议新增：

```text
modules/
  example/
    manifest.py      # 模块元信息、后台入口、前台 section 声明
    routes.py        # 模块自己的 Blueprint
    service.py       # 模块业务逻辑
    templates/       # 模块模板
```

然后在 `app.py` 或专门的 `module_loader.py` 中统一发现和注册模块，并把前台入口汇总进 `home_modules.SECTION_REGISTRY`，避免每次加功能都修改核心路由或首页骨架。
