# 后端集成

**分析日期：** 2026-05-19

## 对前端暴露的接口

- 任务 API：创建、列表、读取、重命名、删除、发送消息、取消、事件轮询。
- 文件 API：上传任务资源。
- 产物 API：下载最新或 run-scoped artifact。
- SSE API：实时读取任务事件。
- 模型 API：返回可用模型。

这些接口由 `backend/app/api/` 提供，公共 schema 在 `backend/app/schemas.py`。

## 存储集成

- Postgres 通过 `psycopg` 访问。
- `MYAGENT_DATABASE_URL` 或 `DATABASE_URL` 提供连接字符串。
- `PostgresTaskStorage.initialize()` 在启动时创建或调整表结构。
- 本地文件保存在 `MYAGENT_TASK_ROOT`，默认是 `backend/storage/sessions/`。

## 模型 Provider

- DeepSeek：默认注册 provider，依赖 `DEEPSEEK_API_KEY`。
- OpenAI：支持显式 `openai:<model>` ID，依赖 `OPENAI_API_KEY`。
- Anthropic：支持显式 `anthropic:<model>` ID，依赖 `ANTHROPIC_API_KEY`。
- 模型创建入口在 `backend/app/models/provider.py`。
- 模型注册和可用性判断在 `backend/app/models/registry.py` 和 `backend/app/config.py`。

## 搜索

- SearXNG 通过 `MYAGENT_SEARXNG_URL` 配置。
- 工具实现位于 `backend/app/tools/searxng_search.py`。
- 搜索结果可写入 Postgres tool cache。

## 长期记忆

- Postgres 保存长期记忆的 canonical rows。
- DashScope-compatible embeddings 用于生成向量。
- Qdrant 用于语义搜索索引。
- 记忆服务位于 `backend/app/memory.py`。
- 管理入口位于 `backend/app/memory_admin.py`。

## 认证和 CORS

- 认证逻辑在 `backend/app/main.py`。
- loopback 可在无 token 时访问。
- 设置 `MYAGENT_ACCESS_TOKEN` 后，前端需要携带匹配 token。
- 支持 header、Bearer 和 SSE query token。
- CORS 由 `MYAGENT_CORS_ORIGINS` 控制。

## 未发现的后端集成

- 未发现 OAuth、cookie session 或多用户身份系统。
- 未发现 Redis、消息队列或 durable job queue。
- 未发现 Docker/Kubernetes 部署配置。
- 未发现外部日志、Sentry 或 OpenTelemetry。
