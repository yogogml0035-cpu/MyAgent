# 集成关系

**分析日期：** 2026-05-19

## 前后端接口

- 前端通过 `frontend/lib/task-api.ts` 调用后端。
- 后端路由集中在 `backend/app/api/`。
- REST 用于模型、任务、文件、消息、取消、事件轮询和产物 blob。
- SSE 用于实时任务事件流。
- 后端字段是 `snake_case`，前端状态是 `camelCase`，转换集中在 `frontend/app/task-state.ts`。

## 认证边界

- 后端默认允许 loopback。
- 非本机访问应设置 `MYAGENT_ACCESS_TOKEN`。
- 前端用 `NEXT_PUBLIC_MYAGENT_TOKEN` 或旧变量携带浏览器可见 token。
- 普通 fetch 请求通过 header 传 token。
- SSE 因为 EventSource 不能设置自定义 header，所以通过 `?token=` 传 token。
- provider key、数据库 URL、Qdrant URL 和 embedding key 不能放进 `NEXT_PUBLIC_*`。

## 模型和工具

- DeepSeek 是默认注册模型 provider。
- OpenAI 和 Anthropic provider 支持存在，但是否可用取决于配置和模型 ID。
- SearXNG 作为本地搜索工具，由后端工具注册后暴露给 agent。
- DeepAgents skills 存放在 `backend/skills/`，由后端配置加载。

## 存储和文件

- Postgres 是任务、运行、消息、事件、缓存、长期记忆和 store item 的权威存储。
- 本地文件系统保存上传和产物，默认根目录为 `backend/storage/sessions/`。
- 上传由后端做最终校验；前端上传过滤只提供用户体验。
- artifact URL 必须经过前端信任检查后才能附带 token 请求。

## 长期记忆

- Postgres 保存长期记忆的 canonical row。
- Qdrant 保存语义检索索引。
- DashScope-compatible embeddings 负责向量生成。
- 记忆写入前要做敏感内容过滤；上传原文、完整产物、流式 token、工具原始日志和密钥不应进入记忆。

## CI 和开发脚本

- `.github/workflows/backend-ci.yml`：后端 lock、安装、审计、pytest、Ruff、mypy。
- `.github/workflows/frontend-ci.yml`：npm ci、typecheck、Node tests、lint、build。
- `.github/workflows/repository-ci.yml`：脚本和空白检查。
- `scripts/start-dev-wsl.ps1`：Windows 侧启动入口。
- `scripts/dev-terminal-runner.sh`：WSL 终端内启动后端/前端。
- `scripts/stop-dev-ports.sh`：清理默认或指定端口。

## 未发现的集成

- 未发现 OAuth、SSO、cookie session 或多用户账号系统。
- 未发现 Docker、Kubernetes、Vercel、Netlify 或云部署配置。
- 未发现 Redis、Memcached 或外部日志监控平台。
- 未发现 webhook 或外部回调路由。
