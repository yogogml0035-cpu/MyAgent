# 后端技术栈

**分析日期：** 2026-05-19

## 语言和运行时

- Python 3.11+。
- 本地 ASGI 服务使用 Uvicorn。
- 依赖由 `uv` 管理，配置在 `backend/pyproject.toml`，锁文件为 `backend/uv.lock`。
- 后端默认监听 `127.0.0.1:8001`。
- 单进程运行是当前架构要求。

## 框架和核心库

- FastAPI：HTTP API、middleware、CORS、请求限制和健康检查。
- Pydantic：请求和响应模型。
- DeepAgents：核心 agent graph、任务级 filesystem backend、skills 和 subagents。
- LangChain：模型、message、tool 抽象。
- LangGraph：streaming graph 和 store 接口。
- psycopg：Postgres 访问。
- httpx：SearXNG、Qdrant、embedding HTTP 调用。
- python-multipart：multipart 上传。
- python-docx / openpyxl：Word、Excel 上传资源读取。

## 测试和质量

- pytest：后端测试 runner。
- pytest-asyncio：异步测试。
- FastAPI TestClient：API 测试。
- Ruff：lint。
- mypy：类型检查。
- pip-audit：依赖安全审计。

## 外部服务

- Postgres：任务、运行、消息、事件、缓存、记忆和 store item。
- Qdrant：长期记忆向量索引。
- DashScope-compatible embeddings：长期记忆向量生成。
- DeepSeek：默认模型 provider。
- OpenAI / Anthropic：可选模型 provider。
- SearXNG：本地搜索工具。

## 配置

- `backend/app/config.py` 读取后端配置。
- `backend/.env` 是本地私密文件，不应提交。
- `DEEPSEEK_API_KEY`、`OPENAI_API_KEY`、`ANTHROPIC_API_KEY`、`DASHSCOPE_API_KEY`、`MYAGENT_DATABASE_URL`、`MYAGENT_QDRANT_URL` 等属于后端秘密配置。
- `MYAGENT_TASK_ROOT` 可改变上传和产物根目录。
- `MYAGENT_ACCESS_TOKEN` 用于非 loopback 访问。
- `WEB_CONCURRENCY`、`UVICORN_WORKERS`、`GUNICORN_WORKERS` 不能大于 1。

## 开发入口

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

## 验证入口

```bash
cd backend
uv run pytest
uv run ruff check .
uv run mypy app tests
```
