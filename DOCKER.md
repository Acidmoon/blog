# Docker 运行约定

## 生产/日常运行

```bash
docker compose up -d --build
docker compose logs -f blog
docker compose restart blog
```

默认 `docker-compose.yml` 使用镜像内代码运行，只挂载运行时数据：

- `./data:/app/data`
- `./data/images:/app/static/images`
- `./home_layout.json:/app/home_layout.json`

这样容器重启后保留 SQLite、文章 Markdown、上传图片、聊天附件和首页布局，同时避免把本地源码目录完整覆盖进生产容器。

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

## 验证

```bash
docker compose --env-file .env.example config
docker build -t waterhill-blog:check .
```
