# 水浇岭博客设计与产品结构约定

## 产品分区

后台功能按四个产品区域组织：

- 内容：文章、草稿、发布、删除、公众号导出、编辑器 AI 润色。
- 首页：首页 Hero、每日一言、首页模块排序与显隐。
- 访问：访客登录、会话有效期。
- 系统：退出、后续系统级配置。

`services.admin_modules.build_admin_nav_groups()` 是后台信息架构的服务级来源；`build_admin_nav()` 只作为兼容旧模板的扁平视图。

## 视觉基础

- 继续使用 `static/css/style.css` 中的语义 token：背景、文本、强调色、边框、阴影和字体都从 token 取值。
- 新 CSS 放入对应组件文件，不直接扩张 `style.css`。
- 内容阅读页保持内容优先；后台页面保持安静、密集、可扫描。
- 新增页面优先复用 `.btn`、`.form-group`、`.flash-stack`、导航和卡片样式。

## 交互约定

- 表单必须有可见 label 或屏幕阅读器 label，错误信息靠近触发区域。
- 异步提交按钮必须在请求中禁用，并给出处理中、成功或失败反馈。
- 危险动作必须确认或提供清晰撤销路径；删除动作使用独立危险样式。
- 图标按钮必须有 `aria-label` 或可见文字；新增功能优先使用 SVG 图标，逐步减少功能性 emoji。
- 页面级脚本放在 `static/js/<feature>.js`，模板只输出 DOM、`data-*` 或 JSON 配置块。

## 前端模块边界

- `static/js/main.js`：全站轻量增强，如主题、导航、搜索、文章阅读增强。
- `static/js/auth-modal.js`：登录/注册弹窗和 `/api/auth/*` 契约。
- `static/js/article-social.js`：点赞、评论分页、评论提交和删除。
- `static/js/editor.js`：后台编辑器、标签输入、预览、上传和 AI 润色。

新增复杂页面时先创建独立脚本，不再把长脚本内联进 Jinja 模板。
