# MyAgent Backend

Local FastAPI backend for the v1 MyAgent workspace.

## Scope

- Stores every substantive task in a local task directory.
- Accepts Markdown and JSON uploads for the v1 document-analysis workflow.
- Generates an execution plan before acting.
- Runs category sub-agents concurrently with retry-on-failure behavior.
- Persists tool-style events, sub-agent reports, evidence records, final Markdown summary, and an interactive HTML report.
- Exposes only safe model IDs to the frontend. Provider secrets stay in backend `.env`.

## Install

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv --version
uv sync
```

如果需要把锁定依赖升级到当前约束允许的最新版本：

```bash
uv lock --upgrade
uv sync
```

## Run

开发模式：

```bash
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

本机部署：

```bash
uv lock --check
uv sync --no-dev
uv run uvicorn app.main:app --host 127.0.0.1 --port 8001
```

## Test

```bash
uv run pytest
```

## Environment

Copy `.env.example` to `.env` and configure:

- `DEEPSEEK_API_KEY`
- `DEEPSEEK_BASE_URL`
- `MYAGENT_SEARXNG_URL`
- `MYAGENT_CORS_ORIGINS`
- `MYAGENT_TASK_ROOT`

The default model registry exposes `deepseek-v4-flash` and `deepseek-v4-flash-thinking`.
The backend loads `backend/.env` on startup before reading process environment values.
Current documentation assumes local same-machine access over `localhost` or `127.0.0.1`.
Browser callers must use an origin listed in `MYAGENT_CORS_ORIGINS`, which defaults to
`http://localhost:3001,http://127.0.0.1:3001`. The frontend can use
`NEXT_PUBLIC_MYAGENT_API_BASE_URL=auto` to call the backend on the same hostname as the
opened page.
