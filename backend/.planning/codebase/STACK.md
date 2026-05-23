# 后端技术栈

**分析日期：** 2026-05-24

## 语言

- Python `>=3.11`：后端 API、agent runner、模型集成、storage 和测试。`backend/pyproject.toml` 声明版本要求，Ruff/mypy 目标是 Python 3.11 语法。
- Markdown：README、项目技能和文档事实层。
- TOML：`backend/pyproject.toml` 的依赖、lint、typecheck 和 test 配置。

## 运行时和包管理

- CPython `>=3.11`。
- ASGI 服务器：Uvicorn，本地默认 `uv run uvicorn app.main:app --host 127.0.0.1 --port 8001`。
- 包管理：uv，lockfile 为 `backend/uv.lock`。
- 单进程要求：`backend/app/config.py` 拒绝 `WEB_CONCURRENCY`、`UVICORN_WORKERS`、`GUNICORN_WORKERS` 大于 1。
- `backend/pyproject.toml` 固定了 `langgraph-checkpoint` 的 Git source revision。

## 核心框架

- FastAPI：HTTP API 和 route 注册，入口在 `backend/app/main.py`。
- Starlette：ASGI 类型、`StreamingResponse`、`FileResponse`、请求 body 包装等底层能力。
- Uvicorn：本地开发和部署服务器。
- Pydantic v2：请求/响应 schema，集中在 `backend/app/schemas.py`。
- LangChain：chat message、tool、runnable config 和模型接口。
- LangGraph：compiled graph、store interface 和 stream。
- DeepAgents：agent 构建、虚拟 filesystem、skills、subagents 和 middleware。

## 测试与开发工具

- pytest：后端 unit/integration/e2e 测试。
- pytest-asyncio：runner、streaming、title generation 等异步测试。
- FastAPI TestClient：API route 和 SSE e2e 测试。
- Ruff：lint，配置在 `backend/pyproject.toml`，line length 100，启用 `E`, `F`, `I`, `UP`, `B`, `SIM`。
- mypy：类型检查，`check_untyped_defs = true`。
- uv：依赖同步、lock 检查和命令运行。

## 关键依赖

- `fastapi`：公共 HTTP API。
- `uvicorn[standard]`：ASGI 服务。
- `python-multipart`：上传 endpoint 的 multipart parsing。
- `httpx`：SearXNG、DashScope-compatible embeddings、Qdrant HTTP 调用。
- `pydantic`：API 合同。
- `langchain`, `langchain-core`：messages、tools、chat model interfaces。
- `langgraph`：graph 和 store interface。
- `deepagents`：task agent、backend mounts、state、memory store、skills。
- `langchain-deepseek`：DeepSeek chat model。
- `psycopg[binary]`：Postgres task/event/memory/store 持久化。
- `python-docx`：读取 DOCX 上传资源。
- `openpyxl`：读取 XLSX/XLSM 上传资源。

## 配置

- 配置入口：`backend/app/config.py` 的 `Settings` dataclass 和 `load_settings()`。
- `.env` 行为：启动时读取 `backend/.env`，但文档和测试只能引用 `backend/.env.example` 的变量名。
- 模型：`DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL`, `MYAGENT_DEFAULT_MODEL`。
- 存储和记忆：`MYAGENT_DATABASE_URL`, `MYAGENT_QDRANT_URL`, `MYAGENT_QDRANT_COLLECTION`, `DASHSCOPE_API_KEY`, `MYAGENT_EMBEDDING_BASE_URL`, `MYAGENT_EMBEDDING_MODEL`, `MYAGENT_EMBEDDING_DIMENSIONS`, `MYAGENT_DEFAULT_USER_ID`, `MYAGENT_MEMORY_MIN_SCORE`。
- 工具和任务：`MYAGENT_SEARXNG_URL`, `MYAGENT_TASK_ROOT`, `MYAGENT_SKILLS_DIRS`, `MYAGENT_FRESH_TOOL_CACHE_SECONDS`, `MYAGENT_RECENT_MESSAGE_LIMIT`, `MYAGENT_MAX_CONCURRENT_SUBAGENTS`, `MYAGENT_AGENT_TIMEOUT_SECONDS`。
- 访问和浏览器：`MYAGENT_ACCESS_TOKEN`, `AGENT_CHAT_ACCESS_TOKEN`, `MYAGENT_CORS_ORIGINS`, `AGENT_CHAT_CORS_ORIGINS`。
- 限制：`MYAGENT_MAX_UPLOAD_FILES`, `MYAGENT_MAX_UPLOAD_FILE_BYTES`, `MYAGENT_MAX_UPLOAD_REQUEST_BYTES`, `MYAGENT_MAX_JSON_REQUEST_BYTES`。

## 开发要求

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
uv run pytest
uv run ruff check .
uv run mypy app tests
```

- 真实启动通常需要 Postgres、Qdrant、DashScope-compatible embeddings 和 DeepSeek key。
- 浏览器默认来自 `http://localhost:3001` 或 `http://127.0.0.1:3001`。
- provider secrets 只留在后端运行环境或 ignored env 文件，不能出现在前端、文档、测试夹具或截图中。

## 生产/本地部署事实

- 当前文档确认的是本地同机部署：后端 `127.0.0.1:8001`。
- 常用部署命令：`uv lock --check`, `uv sync --no-dev`, `uv run uvicorn app.main:app --host 127.0.0.1 --port 8001`。
- 当前仓库未确认 Dockerfile、容器编排、云部署或进程管理配置。
- 生产服务依赖 Postgres、Qdrant、DashScope-compatible embeddings、DeepSeek chat completion，可选本地 SearXNG。

---

*技术栈分析：2026-05-24*
