# MyAgent Backend

Local FastAPI backend for the v1 MyAgent workspace.

## Scope

- Stores every substantive task in a local task directory.
- Accepts Markdown and JSON uploads for the v1 document-analysis workflow.
- Generates an execution plan before acting.
- Runs category sub-agents concurrently with retry-on-failure behavior.
- Persists tool-style events, sub-agent reports, evidence records, final Markdown summary, and an interactive HTML report.
- Exposes only safe model IDs to the frontend. Provider secrets stay in backend `.env`.

## Run

```bash
uv run uvicorn app.main:app --reload --port 8001
```

## Test

```bash
uv run pytest
```

## Environment

Copy `.env.example` to `.env` and configure:

- `DEEPSEEK_API_KEY`
- `DEEPSEEK_BASE_URL`
- `TAVILY_API_KEY`
- `MYAGENT_ACCESS_TOKEN`
- `MYAGENT_CORS_ORIGINS`
- `MYAGENT_TASK_ROOT`

The default model registry exposes `deepseek:deepseek-chat`.
The backend loads `backend/.env` on startup before reading process environment values.
Task APIs accept local loopback clients by default. If `MYAGENT_ACCESS_TOKEN` is set,
all task APIs require either `Authorization: Bearer <token>` or `X-MyAgent-Token`.
Browser callers must use an origin listed in `MYAGENT_CORS_ORIGINS`, which defaults to
`http://localhost:3001,http://127.0.0.1:3001`. Add LAN frontend origins such as
`http://<LAN_IP>:3001` when running the frontend by IP. The frontend can use
`NEXT_PUBLIC_MYAGENT_API_BASE_URL=auto` to call the backend on the same hostname as the
opened page.
The legacy `AGENT_CHAT_*` environment names and `X-Agent-Chat-Token` header are still
accepted for migrated local setups.
