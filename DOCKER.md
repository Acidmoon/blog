# Docker 运行约定

## 生产/日常运行

```bash
docker compose build blog
docker compose run --rm --no-deps migrate
docker compose up -d --no-build blog
docker compose logs -f blog
docker compose restart blog
```

`migrate` 是显式的部署期维护服务，会在启动 Web worker 前执行 `python -m migrations upgrade`。不要跳过该步骤，也不要依赖应用启动自动建表或修复历史数据。

默认 `docker-compose.yml` 使用镜像内代码运行，只挂载运行时数据：

- `./data:/app/data`
- `./data/images:/app/static/images`

首页布局的运行时文件是 `./data/home_layout.json`，由 `./data:/app/data` 挂载提供。根目录的 `home_layout.json` 仅作为镜像内的默认模板，不再作为可写运行时挂载。

这样容器重启后保留 SQLite、文章 Markdown、上传图片和首页布局，同时避免把本地源码目录完整覆盖进生产容器。

默认端口映射为 `127.0.0.1:${BLOG_PORT:-8082}:8082`，只允许本机反向代理或本机运维检查访问。需要直接暴露端口时，必须在 `.env` 明确设置 `BLOG_BIND_ADDRESS=0.0.0.0`（或指定的内网地址），不要通过删除端口配置来绕过此边界。

容器健康检查请求只读的 `GET /healthz`。该端点验证 SQLite 与运行时数据目录、文章目录、图片目录、聊天附件目录和首页布局文件均可读；正常仅返回 `{"status":"ok"}`，异常仅返回 `{"status":"unhealthy"}`，不泄露路径或数据库错误详情。

## 首页布局首次迁移

已有部署在升级此挂载方式前，应先暂停管理员对首页布局的保存操作，并把现有布局复制到运行时目录。不要移动、删除或覆盖根目录的 `home_layout.json`，它仍是新环境初始化时使用的默认模板。

```bash
cd /root/blog
mkdir -p data
if [ ! -e data/home_layout.json ]; then
  cp -p home_layout.json data/home_layout.json
fi
python -m json.tool data/home_layout.json >/dev/null
```

只有在目标文件不存在时才复制，避免覆盖已经存在的运行时布局。校验通过后，先执行数据库迁移，再只重建目标服务，不要执行 `docker compose down`：

```bash
cd /root/blog
docker compose build blog
docker compose run --rm --no-deps migrate
docker compose up -d --no-build blog
docker compose exec -T blog python -c "from pathlib import Path; print(Path('/app/data/home_layout.json').is_file())"
```

最后一条命令应输出 `True`。全新部署无需手动复制，应用会从根目录默认模板初始化 `data/home_layout.json`。

## 开发热更新

需要边改代码边看效果时使用 override：

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
```

开发模式会挂载整个项目目录并开启 Gunicorn `--reload`。不要把 dev override 当生产启动方式。

## 环境变量

`.env` 不进 Git。首次部署可以从样例生成：

```bash
cp .env.example .env
```

至少应设置：

- `BLOG_SECRET_KEY`
- `ADMIN_PASSWORD`
- 需要 AI 润色时设置对应 `AI_POLISH_*_API_KEY`

样例中的密钥和密码只是占位符；应用会拒绝带占位符或默认凭据的非测试启动。

`TRUSTED_PROXY_CIDRS` 默认为空，因此应用会忽略客户端可伪造的 `X-Forwarded-For`。只有反向代理直连应用时，才填写该反向代理的实际来源 CIDR，例如本机 Nginx 可填 `127.0.0.1/32,::1/128`；不要填写公网客户端网段。

`ASSET_VERSION` 的默认值与应用配置保持一致。发布了静态资源变更时，可显式改为新的非敏感版本标识，让浏览器获取新资源。

## 部署回滚

建议通过 `deploy.sh` 发布目标服务：

```bash
cd /root/blog
REMOTE=origin BRANCH=master SERVICE=blog ./deploy.sh
```

脚本会在更新前记录当前 Git revision 和目标容器镜像。新容器未通过 Docker 健康检查时，脚本会将工作树和镜像标签恢复到先前状态，并且只强制重建目标服务；不会执行 `docker compose down`、清理卷或触及运行时 `data/`。

## 派生数据维护

全文搜索索引是可重建的派生数据。需要人工校验或修复时，在容器内运行：

```bash
docker compose exec -T blog python -m services.search --rebuild
```

正文版本隔离工具会移动未引用的历史版本，不会直接删除。它只能在没有文章写入的维护窗口执行：

```bash
docker compose exec -T blog python -m services.article_maintenance --retention-days 30
docker compose exec -T blog python -m services.article_maintenance --retention-days 30 --apply --offline
```

先检查 dry-run 输出和恢复批次清单，再决定是否保留或清理隔离目录；运行中的 Web 请求不得执行 `--apply`。

每日一言刷新是独立维护任务，不在首页请求中创建后台线程。可由 cron 或其他调度器每天调用：

```bash
docker compose run --rm --no-deps blog python -m maintenance refresh-daily-quote
```

## 验证

```bash
docker compose --env-file .env.example config
docker build -t waterhill-blog:check .
```
