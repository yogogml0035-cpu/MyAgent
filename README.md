# MyAgent

Local personal AI agent workspace with a FastAPI backend and a Next.js frontend.

## V1 Flow

1. Start the backend.
2. Start the frontend.
3. Upload Markdown tender/bid documents.
4. Send a natural-language task such as `帮我检查是否有串标围标嫌疑`.
5. The backend creates a task plan, runs concurrent category sub-agents, persists evidence and logs, and writes an interactive HTML report.

The backend is a local-first service. Task APIs are limited to loopback clients unless
`MYAGENT_ACCESS_TOKEN` is configured; set `NEXT_PUBLIC_MYAGENT_TOKEN` in the frontend
when using that token locally.

## Backend

```bash
cd backend
uv run uvicorn app.main:app --reload --port 8000
```

## Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`.

## Verification

```bash
cd backend && uv run pytest
cd backend && uv run ruff check . && uv run mypy app tests
cd frontend && npm run typecheck && npm test && npm run lint && npm run build
```

## Architecture Notes

- Provider credentials are backend-only `.env` values.
- `backend/.env` is loaded by the FastAPI process on startup.
- The frontend only sends safe model IDs such as `deepseek-reasoner`.
- Complex tasks are stored under backend task directories.
- V1 complex document analysis supports Markdown uploads only.
- File access and command execution helpers are scoped to the task workspace by default.
