# MyAgent

MyAgent is a local-first AI agent workspace for Markdown-based tender and bid analysis. It uses a FastAPI backend to manage tasks, run analysis workers, persist evidence, and generate reports, plus a Next.js frontend for uploads, task messages, execution logs, and artifact viewing.

The current V1 workflow focuses on bid-collusion style document checks:

1. Start the backend and frontend locally.
2. Upload Markdown tender/bid documents.
3. Send a task such as `帮我检查是否有串标围标嫌疑`.
4. The backend creates a task plan, runs category sub-agents, stores evidence and logs, and writes report artifacts.
5. Open `report.html` from the frontend when the task completes.

## Repository Layout

```text
backend/                 FastAPI service, task runner, analysis pipeline, local storage
backend/app/             Runtime code
backend/tests/           Backend workflow and service tests
backend/storage/tasks/   Default local task/artifact storage
frontend/                Next.js app-router frontend
frontend/app/            UI and task-state mapping code
frontend/tests/          Frontend state/URL mapping tests
asset/                   Long-term knowledge-pack index for future agent work
```

## Prerequisites

- Python 3.11 or newer
- `uv` for backend dependency management
- Node.js and npm compatible with the checked-in Next.js version
- A DeepSeek API key for real model calls
- Optional Tavily API key for search-enabled analysis tools

## Installation

Install backend dependencies:

```bash
cd backend
uv sync --dev
```

Install frontend dependencies:

```bash
cd frontend
npm install
```

## Configuration

Create backend configuration from the example:

```bash
cd backend
cp .env.example .env
```

Backend-only values belong in `backend/.env`:

```env
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
TAVILY_API_KEY=
MYAGENT_ACCESS_TOKEN=
MYAGENT_TASK_ROOT=
MYAGENT_MAX_UPLOAD_FILES=10
MYAGENT_MAX_UPLOAD_FILE_BYTES=10485760
MYAGENT_MAX_UPLOAD_REQUEST_BYTES=105906176
MYAGENT_MAX_JSON_REQUEST_BYTES=65536
DEEPSEEK_TIMEOUT_SECONDS=15
```

Create frontend configuration from the example when defaults are not enough:

```bash
cd frontend
cp .env.example .env.local
```

Frontend public values:

```env
NEXT_PUBLIC_MYAGENT_API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_MYAGENT_TOKEN=
```

Keep provider credentials in the backend only. Anything prefixed with `NEXT_PUBLIC_` is browser-visible.

## Development Startup

Start the backend:

```bash
cd backend
uv run uvicorn app.main:app --reload --port 8000
```

Start the frontend in another terminal:

```bash
cd frontend
npm run dev
```

Open:

```text
http://localhost:3000
```

Health check:

```bash
curl http://localhost:8000/health
```

## Local Deployment Notes

The backend is designed for a single local process. Do not run it with multiple Uvicorn, Gunicorn, or platform workers unless the task runner and JSON storage are redesigned first. The application rejects worker counts greater than one through `WEB_CONCURRENCY`, `UVICORN_WORKERS`, or `GUNICORN_WORKERS`.

For a local production-style run:

```bash
cd frontend
npm run build
npm run start
```

Run the backend separately:

```bash
cd backend
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

If the task APIs are reachable from anything other than loopback, set `MYAGENT_ACCESS_TOKEN` on the backend and set the same value as `NEXT_PUBLIC_MYAGENT_TOKEN` for the frontend. Also set `MYAGENT_TASK_ROOT` to a persistent local directory if task artifacts must survive cleanups or redeploys.

This repository does not currently include Docker, process-manager, reverse-proxy, TLS, or multi-host deployment files. Add those explicitly before treating it as a production service.

## Usage Flow

1. Create or reuse a task from the frontend.
2. Upload Markdown files with `.md` names or `text/markdown` content type.
3. Send a user message describing the requested analysis.
4. Watch the execution log for planning, sub-agent assignment, tool calls, retries, and artifact creation.
5. Open generated artifacts, especially `report.html`, after completion.

The backend supports simple chat if no files are uploaded and the message does not look like a tender/document analysis request. Document-analysis requests require Markdown uploads.

## API Summary

- `GET /health` returns service health.
- `GET /api/models` lists safe model IDs exposed to the frontend.
- `POST /api/tasks` creates a task.
- `GET /api/tasks/{task_id}` reads task state, messages, logs, and artifacts.
- `GET /api/tasks/{task_id}/events` reads incremental event records.
- `POST /api/tasks/{task_id}/files` uploads Markdown files.
- `POST /api/tasks/{task_id}/messages` starts or resumes work for a task.
- `POST /api/tasks/{task_id}/cancel` requests cancellation.
- `GET /api/tasks/{task_id}/artifacts/{artifact_name}` downloads an artifact.

Task APIs are restricted to loopback clients by default. If `MYAGENT_ACCESS_TOKEN` is configured, requests must provide either `Authorization: Bearer <token>` or `X-MyAgent-Token`.

## Verification

Run backend tests and checks:

```bash
cd backend
uv run pytest
uv run ruff check .
uv run mypy app tests
```

Run frontend checks:

```bash
cd frontend
npm run typecheck
npm test
npm run lint
npm run build
```

For documentation-only changes:

```bash
git diff --check
```

## Runtime Boundaries

- Provider credentials are backend-only `.env` values.
- The frontend only sends safe model IDs such as `deepseek-reasoner`.
- Uploaded files, task plans, evidence, summaries, logs, and HTML reports are stored in local task directories.
- File access and command execution helpers are scoped to the task workspace by default.
- Upload and JSON request limits are controlled by backend environment variables.
- Legacy `AGENT_CHAT_*` and `NEXT_PUBLIC_AGENT_CHAT_*` names are still accepted for migrated local setups, but new configuration should use `MYAGENT_*`.

## Troubleshooting

- `401 Invalid or missing access token`: set matching `MYAGENT_ACCESS_TOKEN` and `NEXT_PUBLIC_MYAGENT_TOKEN`, then restart both services.
- `403 Task APIs are restricted to localhost`: access came from a non-loopback client without an access token.
- `409 Cannot upload files while the task is running`: stop or wait for the current task before uploading more files.
- `Upload Markdown files before starting a document-analysis task`: the task message requires document analysis but no Markdown files were uploaded.
- `At least two Markdown bidder documents are required for comparison`: upload at least two bidder Markdown files.
- Frontend cannot reach backend: confirm `NEXT_PUBLIC_MYAGENT_API_BASE_URL`, backend port `8000`, and browser CORS origin.
