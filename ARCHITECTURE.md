# 水浇岭博客架构

水浇岭是一个按业务特性演进的 Flask 模块化单体。它保留单进程可部署、SQLite 和 Markdown 正文的低运维成本，同时避免把 HTTP、业务编排、数据库访问和外部调用混在同一层。

## 运行时分层

```text
app.py
  ├── routes/                  HTTP 边界：解析请求、鉴权、渲染或返回 JSON
  ├── features/                按业务特性组织的应用流程
  │   ├── articles/            正文、详情页读模型、SQLite 导航查询
  │   ├── chat/                模型调用与会话持久化编排
  │   └── home/                首页布局、文章和模块的页面编排
  ├── services/                已有领域能力；迁移期的兼容入口和细粒度实现
  ├── infrastructure/          SQLite 等运行时基础设施适配器
  ├── migrations/              部署期、带版本号的 SQLite schema/data 迁移
  ├── modules/                 受信任的本仓库扩展模块
  ├── templates/ static/       Jinja 视图与浏览器资源
  └── data/                    SQLite、文章正文、上传文件和缓存的运行时数据
```

`app.py` 只创建 Flask 应用、注册核心 Blueprint、加载模块、安装安全钩子和健康检查。它不执行建表、`ALTER TABLE`、历史数据回填或全文索引重建，因此每个 Gunicorn worker 都只承担请求服务。

新功能优先在 `features/<feature>/` 放置应用流程；路由必须调用特性应用服务，而不是直接执行 SQL。复杂特性可继续拆成：

```text
features/<feature>/
  application.py     # 用例和跨资源编排
  repository.py      # SQLite 查询与持久化边界
  content_store.py   # 文件正文等非数据库存储边界
```

已有 `services/` 不是新的聚合入口。它会在兼容期保留稳定导入路径，随后按文章、聊天、首页、社区等特性逐步下沉，避免一次性重写产生 URL、会话或数据回归。

## 文章双存储边界

SQLite 是文章元数据、标签、全文索引和活动事件的权威存储。Markdown 文件是不可变正文版本的权威存储。文章应用服务负责写入正文、提交 SQLite 指针、更新派生索引和失败补偿。

正文更新不会覆盖旧版本；SQLite 指向新 `content_key` 前，旧读者仍能读取完整正文。未引用版本由 `services/article_maintenance.py` 在离线维护窗口隔离和回收，在线请求不得清理正文文件。

文章详情页通过 `features/articles/application.py` 取得正文、字数和上一篇/下一篇读模型。导航 SQL 由 `features/articles/repository.py` 管理，时间相同的文章再以 id 排序，避免页面路由持有数据库细节。

## 数据库迁移和部署

`migrations/schema_migrations` 记录已提交版本。迁移同时覆盖新库建表、旧列升级、标签关系回填、活动事件回填和初始 FTS 构建。每个迁移使用 SQLite 写锁和事务，多个部署进程竞争时，后到进程会重新读取版本并跳过已经完成的迁移。

部署必须在启动 Web worker 前执行：

```bash
python -m migrations status
python -m migrations upgrade
```

Docker 发布由 `deploy.sh` 依次构建镜像、运行 `migrate` Compose 维护服务、再启动 `blog` 服务。不要把迁移调用放回 `create_app()`、请求处理器或健康检查。

## 首页和定时维护

首页模块由 `features/home/application.py` 组合文章、布局和模块 section。模块模板仍通过受控的 `services/home_modules.py` 渲染，以保留现有首页排序和可见性配置。

`get_daily_quote()` 只读取当天缓存、旧缓存或确定性的本地候选，不执行网络请求、写缓存或创建后台线程。定时任务应独立运行：

```bash
python -m maintenance refresh-daily-quote
```

可将该命令交给 cron、systemd timer 或平台调度器。刷新命令使用跨进程短租约，避免重复任务同时覆盖缓存。

## 受信任模块扩展 API

模块是同仓库、同部署信任边界内的 Python 代码，并不是可安全安装任意第三方代码的沙箱。每个 `modules/<name>/manifest.py` 必须显式声明兼容 API 版本和实际能力：

```python
from module_loader import HomeSectionDefinition

MODULE = {
    "id": "example",
    "name": "示例模块",
    "api_version": 1,
    "capabilities": ["home_sections"],
    "home_sections": [
        HomeSectionDefinition(
            id="example_section",
            name="示例首页块",
            template="home_sections/example.html",
            default_order=50,
        ),
    ],
    "blueprints": [],
    "admin_modules": [],
}
```

支持的能力是 `blueprints`、`home_sections` 与 `admin_modules`。加载器会在注册前校验模块 ID、API 版本、能力与实际内容一致性、回调可调用性、Blueprint 名称以及 URL 与 HTTP 方法冲突。模块注册表存放在 `app.extensions["blog_modules"]`，通过 `get_module_registry()` 访问；不存在全局 `module_loader.REGISTRY`。

首页 `section_order` 和 `section_visibility` 仍由运行时 `home_layout.json` 控制。新增首页区块应通过模块 manifest 注册，不应修改 `app.py` 或在 `templates/index.html` 中添加固定槽位。
