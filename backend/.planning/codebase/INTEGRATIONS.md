# 后端集成

**分析日期：** 2026-05-24

## 外部 API 与服务

### DeepSeek 模型

- 用途：任务运行、标题生成、长期记忆提取。
- SDK：`langchain-deepseek` 的 `ChatDeepSeek`，thinking 模式由 `backend/app/models/deepseek_thinking.py` 包装。
- 配置：`DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL`。
- 浏览器安全模型 ID：`deepseek-v4-flash`, `deepseek-v4-flash-thinking`。
- API 表面：`/api/models` 返回模型元数据和 availability，不暴露 provider secret。

### DashScope 兼容嵌入

- 用途：长期记忆 recall/index。
- 调用方式：`backend/app/memory.py` 用 `httpx.post` 调 `{MYAGENT_EMBEDDING_BASE_URL}/embeddings`。
- 配置：`DASHSCOPE_API_KEY`, `MYAGENT_EMBEDDING_BASE_URL`, `MYAGENT_EMBEDDING_MODEL`, `MYAGENT_EMBEDDING_DIMENSIONS`。

### SearXNG 搜索

- 用途：`searxng_search` LangChain 工具。
- 调用方式：`backend/app/tools/searxng_search.py` 用 `httpx.get` 调 `/search`。
- 默认 URL：`http://127.0.0.1:8181/`。
- 引擎边界：工具层暴露 `engine` 参数，只允许 `bing` 或 `baidu`，由 agent 每次调用时选择。
- 代理边界：工具层暴露 `trust_env` 参数，默认 `false`；遇到网络错误、502 或 timeout 时可设为 `true` 让 httpx 信任系统代理环境重试。
- 注册条件：`Settings.searxng_url` 存在时由 `backend/app/tools/registry.py` 注册。
- 运行预算：runner 可通过 registry 为单次 run 传入搜索调用上限；`[$web-research]` 默认使用 5 次总搜索预算，超过后工具返回可读错误并要求基于已有证据收束。
- 缓存：成功结果可以写入 Postgres tool cache，TTL 由 `MYAGENT_FRESH_TOOL_CACHE_SECONDS` 控制。

### DeepAgents / LangGraph 运行时

- 用途：本地 agent graph、虚拟 filesystem backend、state backend、store backend、project skills 和 subagents。
- 入口：`backend/app/agent/factory.py`, `backend/app/agent_store.py`。
- 虚拟挂载：`/scratch/`、`/memories/`、`/skills/` 或 `/skills/source-{n}/`。

## 数据存储

### PostgreSQL 存储

- 权威范围：tasks、runs、messages、events、agent_store_items、task_context_summaries、tool_result_cache、long_term_memories。
- 配置：`MYAGENT_DATABASE_URL`，fallback 为 `DATABASE_URL`。
- 客户端：`psycopg[binary]`。
- 表创建：`PostgresTaskStorage.initialize()`。
- 常见索引：events task seq、runs task、messages task、agent store namespace、tool cache task/tool、long-term memories user。
- 集成测试：`backend/tests/integration/test_postgres_memory_storage.py`，由 `MYAGENT_TEST_DATABASE_URL` 或 `MYAGENT_DATABASE_URL` 控制。

### Qdrant 向量库

- 用途：长期记忆向量索引。
- 配置：`MYAGENT_QDRANT_URL`, `MYAGENT_QDRANT_COLLECTION`, embedding dimensions。
- 调用方式：`backend/app/memory.py` 直接 HTTP 调 collection、upsert、search、reset。
- 管理入口：`backend/app/memory_admin.py reset-qdrant|rebuild-qdrant`。
- Postgres 是 canonical store，Qdrant 可重建。

### 本地文件系统

- 默认根：`MYAGENT_TASK_ROOT` 或 `backend/storage/sessions`。
- 上传：task 下的 `uploads/`。
- 产物：task 下的 `artifacts/runs/{run_id}/` 和 legacy latest mirror。
- 支持上传格式：Markdown、JSON、TXT、DOCX、XLSX、XLSM。
- 资源工具：`backend/app/execution/resources.py` 提供 list/inspect/read；当 run context、storage 和 runner 策略允许时才额外暴露 `create_word_document`。

### 缓存

- Postgres tool-result cache：主要服务 SearXNG 和未来工具缓存。
- in-process settings cache：`backend/app/api/deps.py` 用 `functools.lru_cache` 包装 `load_settings()`。

## 认证与身份

- 后端 `/api/` 使用自定义 token 或 loopback gate。
- 未设置 `MYAGENT_ACCESS_TOKEN` 时，只允许 loopback 或 testclient host。
- 设置 token 后，支持 `Authorization: Bearer ...`、`X-MyAgent-Token`、`X-Agent-Chat-Token` 和 query `token`。
- 比较使用 `hmac.compare_digest`。
- 长期记忆用户 scope 来自 `MYAGENT_DEFAULT_USER_ID`，默认 `local-user`。
- CORS 由 `MYAGENT_CORS_ORIGINS` 或 `AGENT_CHAT_CORS_ORIGINS` 控制，默认允许本地前端 `3001`。

## 监控与可观测性

- 未检测到 Sentry、OpenTelemetry 或托管错误追踪 SDK。
- Python 标准 `logging` 用于 main、runner、memory、agent factory、skills loader、task title 等模块。
- task-level observability 以结构化 Postgres events 保存，并通过 SSE 投影给前端。
- secret hygiene 由 `backend/app/security/scanner.py` 支撑。

## CI/CD 与部署

- 当前仓库未确认后端本地 CI workflow、Dockerfile、容器编排、Procfile 或云托管配置。
- 验证主要依赖本地命令：`uv lock --check`、`uv sync --no-dev`、`uv run pytest`、`uv run ruff check .`、`uv run mypy app tests`。
- 运行目标是本地同机服务 `127.0.0.1:8001`。

## 环境变量边界

- `backend/.env` 可能存在，但不能读取或引用真实值。
- `backend/.env.example` 是安全变量名来源。
- provider key、数据库 URL、Qdrant URL、embedding key 和客户资料只允许在后端运行环境或 ignored 本地 env 中出现。
- 前端可见配置只能通过浏览器安全的接口暴露，不得把 secret 放进 `/api/models`、`/api/skills` 或 `NEXT_PUBLIC_*`。

## Webhook 和回调

- 未检测到 incoming webhook endpoint。
- outgoing 调用只包括 DeepSeek、DashScope-compatible embeddings、Qdrant 和 SearXNG。
- 未检测到 outbound webhook delivery 机制。

---

*集成审计：2026-05-24*
