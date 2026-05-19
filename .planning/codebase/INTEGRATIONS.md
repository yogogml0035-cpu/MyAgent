# External Integrations

**Analysis Date:** 2026-05-19

## APIs & External Services

**Model Providers:**
- DeepSeek - Default and only frontend-exposed model provider in `MODEL_REGISTRY`; used for chat completions, task titles, main agent runs, and memory extraction through `backend/app/config.py`, `backend/app/models/provider.py`, `backend/app/models/registry.py`, `backend/app/task_titles.py`, `backend/app/runner/core.py`, and `backend/app/memory.py`.
  - SDK/Client: `langchain-deepseek` via LangChain `init_chat_model` in `backend/app/models/provider.py`; dependency is declared in `backend/pyproject.toml` and locked in `backend/uv.lock`.
  - Auth: `DEEPSEEK_API_KEY` in `backend/app/config.py`.
  - Base URL: `DEEPSEEK_BASE_URL` in `backend/app/config.py`.
- OpenAI - Provider support exists for explicit `openai:<model>` IDs and built-in subagent definitions, but `MODEL_REGISTRY` currently exposes only DeepSeek entries to the frontend in `backend/app/config.py`.
  - SDK/Client: `langchain-openai` via LangChain `init_chat_model` in `backend/app/models/provider.py`; dependency is declared in `backend/pyproject.toml` and locked in `backend/uv.lock`.
  - Auth: `OPENAI_API_KEY` in `backend/app/config.py`.
  - Usage path: Provider map in `backend/app/models/provider.py`; optional researcher subagent model in `backend/app/subagents/definitions.py`.
- Anthropic - Provider support exists for explicit `anthropic:<model>` IDs, but no Anthropic model is registered in `MODEL_REGISTRY` in `backend/app/config.py`.
  - SDK/Client: `langchain-anthropic` via LangChain `init_chat_model` in `backend/app/models/provider.py`; dependency is declared in `backend/pyproject.toml` and locked in `backend/uv.lock`.
  - Auth: `ANTHROPIC_API_KEY` in `backend/app/config.py`.

**Search:**
- SearXNG - Local web search engine exposed to the agent as `searxng_search`; calls the JSON `/search` endpoint and optionally caches successful results in Postgres through `backend/app/tools/searxng_search.py`, `backend/app/tools/registry.py`, and `backend/app/storage.py`.
  - SDK/Client: `httpx` in `backend/app/tools/searxng_search.py`.
  - Auth: None detected in `backend/app/tools/searxng_search.py`.
  - URL config: `MYAGENT_SEARXNG_URL` in `backend/app/config.py`, defaulting to a local loopback SearXNG URL.

**Embeddings & Vector Memory:**
- DashScope-compatible embeddings - Used to embed sanitized long-term memory text for startup probes, recall, and index upserts in `backend/app/memory.py`.
  - SDK/Client: Direct `httpx.post` to `{MYAGENT_EMBEDDING_BASE_URL}/embeddings` in `backend/app/memory.py`.
  - Auth: `DASHSCOPE_API_KEY` bearer token in `backend/app/memory.py` and `backend/app/config.py`.
  - Model config: `MYAGENT_EMBEDDING_MODEL` and `MYAGENT_EMBEDDING_DIMENSIONS` in `backend/app/config.py`.
- Qdrant - Semantic long-term memory index with collection creation, validation, reset, upsert, and search via REST in `backend/app/memory.py`.
  - SDK/Client: Direct `httpx.get`, `httpx.put`, `httpx.post`, and `httpx.delete` in `backend/app/memory.py`.
  - Auth: None detected in `backend/app/memory.py`; URL is `MYAGENT_QDRANT_URL` in `backend/app/config.py`.
  - Collection config: `MYAGENT_QDRANT_COLLECTION` in `backend/app/config.py`.

**Frontend to Backend:**
- MyAgent REST API - Browser frontend calls FastAPI endpoints for models, tasks, events, files, messages, cancellation, and artifact blobs through `frontend/lib/task-api.ts` and routes in `backend/app/api/`.
  - SDK/Client: Browser `fetch` in `frontend/lib/task-api.ts`.
  - Auth: `X-MyAgent-Token` header from `NEXT_PUBLIC_MYAGENT_TOKEN` or legacy `NEXT_PUBLIC_AGENT_CHAT_TOKEN` in `frontend/lib/task-api.ts`.
  - Base URL: `NEXT_PUBLIC_MYAGENT_API_BASE_URL` or legacy `NEXT_PUBLIC_API_BASE_URL` in `frontend/lib/task-api.ts`.
- MyAgent SSE stream - Browser frontend subscribes to task events through `EventSource` in `frontend/lib/task-api.ts`; backend emits `text/event-stream` from `backend/app/api/streaming.py`.
  - SDK/Client: Browser `EventSource` in `frontend/lib/task-api.ts` and `frontend/hooks/use-task-workspace.ts`.
  - Auth: `token` query parameter from `NEXT_PUBLIC_MYAGENT_TOKEN` because EventSource cannot send custom headers, handled by `backend/app/main.py`.

**Development & Browser Automation:**
- Playwright - Browser E2E specs use local frontend and backend URLs plus evidence directories through env vars in `frontend/e2e-playwright/*.mjs` and docs in `frontend/e2e-playwright/README.md`.
  - SDK/Client: `@playwright/test` in `frontend/e2e-playwright/*.mjs`, locked in `frontend/package-lock.json`.
  - Auth: `MYAGENT_E2E_ACCESS_TOKEN` for E2E requests in `frontend/e2e-playwright/*.mjs`.

## Data Storage

**Databases:**
- Postgres - Canonical store for tasks, runs, messages, events, LangGraph store items, context summaries, search cache rows, and long-term memory rows in `backend/app/storage.py`.
  - Connection: `MYAGENT_DATABASE_URL` or fallback `DATABASE_URL` in `backend/app/config.py`.
  - Client: `psycopg` with `dict_row` and `Jsonb` in `backend/app/storage.py`.
  - Schema management: `PostgresTaskStorage.initialize()` creates and migrates tables idempotently in `backend/app/storage.py`.
- Qdrant - Semantic memory index for long-term memories in `backend/app/memory.py`.
  - Connection: `MYAGENT_QDRANT_URL` in `backend/app/config.py`.
  - Client: Direct REST calls through `httpx` in `backend/app/memory.py`.
  - Canonical source: Postgres `long_term_memories` remains canonical in `backend/app/storage.py`; Qdrant is rebuilt by `backend/app/memory_admin.py`.

**File Storage:**
- Local filesystem only - Uploads and artifacts are stored beneath `MYAGENT_TASK_ROOT`, defaulting to `backend/storage/sessions/`, by `backend/app/storage.py`.
- Task uploads - Supported source formats are Markdown, JSON, TXT, DOCX, XLSX, and XLSM in `backend/app/storage.py`; upload API lives in `backend/app/api/files.py`.
- Run artifacts - Run-scoped artifacts live under `artifacts/runs/{run_id}` inside each task directory in `backend/app/storage.py`; artifact download routes live in `backend/app/api/artifacts.py`.
- DeepAgents filesystem backend - Agent file tools are scoped to the task workspace through `CompositeBackend` and `FilesystemBackend` in `backend/app/agent/factory.py`.

**Caching:**
- Postgres search cache - SearXNG tool results are cached in `tool_result_cache` with TTL from `MYAGENT_FRESH_TOOL_CACHE_SECONDS` through `backend/app/storage.py` and `backend/app/tools/searxng_search.py`.
- No Redis, Memcached, or external cache service is detected in `backend/pyproject.toml`, `frontend/package.json`, or source imports under `backend/app/` and `frontend/`.

## Authentication & Identity

**Auth Provider:**
- Custom local token gate - No OAuth, SSO, session cookie, or third-party identity provider is detected in `backend/app/main.py`, `backend/pyproject.toml`, or `frontend/package.json`.
  - Implementation: Loopback clients are allowed without a token; non-loopback or token-configured deployments require `MYAGENT_ACCESS_TOKEN` in `backend/app/config.py` and `backend/app/main.py`.
  - Accepted backend credentials: `X-MyAgent-Token`, legacy `X-Agent-Chat-Token`, `Authorization: Bearer`, or SSE query `token` in `backend/app/main.py`.
  - Frontend credential source: `NEXT_PUBLIC_MYAGENT_TOKEN` or legacy `NEXT_PUBLIC_AGENT_CHAT_TOKEN` in `frontend/lib/task-api.ts`.
  - CORS control: `MYAGENT_CORS_ORIGINS` in `backend/app/config.py` and `CORSMiddleware` in `backend/app/main.py`.

## Monitoring & Observability

**Error Tracking:**
- None detected - No Sentry, OpenTelemetry, Datadog, Rollbar, or similar package appears in `backend/pyproject.toml`, `frontend/package.json`, or source imports under `backend/app/` and `frontend/`.

**Logs:**
- Backend uses Python `logging` in `backend/app/main.py`, `backend/app/runner/core.py`, `backend/app/memory.py`, `backend/app/tools/searxng_search.py`, and `backend/app/streaming/v2_adapter.py`.
- User-visible runtime logs are persisted as `events` rows by `backend/app/storage.py`, streamed through SSE in `backend/app/api/streaming.py`, and normalized in `frontend/app/workspace-view.ts`.
- Frontend E2E evidence screenshots and traces are stored locally under ignored `frontend/e2e-playwright/e2e-*/` directories per `.gitignore` and `frontend/e2e-playwright/README.md`.

## CI/CD & Deployment

**Hosting:**
- Local/WSL deployment only - `README.md` documents Uvicorn on `127.0.0.1:8001` and Next.js on `127.0.0.1:3001`.
- No Dockerfile, docker-compose, Kubernetes manifests, process manager config, reverse proxy config, TLS config, Vercel config, or Netlify config is detected by repository file scan.
- Windows-to-WSL development startup is scripted by `scripts/start-dev-wsl.ps1` and `scripts/dev-terminal-runner.sh`.

**CI Pipeline:**
- GitHub Actions backend CI - `uv lock --check`, `uv sync --locked --group dev`, `pip-audit`, `pytest`, Ruff, and mypy in `.github/workflows/backend-ci.yml`.
- GitHub Actions frontend CI - `npm ci`, Next typegen plus TypeScript, Node tests, ESLint with zero warnings, and Next build in `.github/workflows/frontend-ci.yml`.
- GitHub Actions repository CI - shell validation, PowerShell validation, and whitespace checks in `.github/workflows/repository-ci.yml`.

## Environment Configuration

**Required env vars:**
- `MYAGENT_DATABASE_URL` - Required for production app startup when real storage is used; loaded in `backend/app/config.py` and validated in `backend/app/main.py`.
- `MYAGENT_QDRANT_URL` - Required for memory startup when real services are used; loaded in `backend/app/config.py` and validated in `backend/app/memory.py`.
- `DASHSCOPE_API_KEY` - Required for embedding startup probe and memory embedding calls in `backend/app/config.py` and `backend/app/memory.py`.
- `DEEPSEEK_API_KEY` - Required for registered DeepSeek models to be runnable through `backend/app/models/registry.py` and `backend/app/models/provider.py`.
- `MYAGENT_ACCESS_TOKEN` - Required for non-loopback access and recommended when binding outside localhost; enforced in `backend/app/main.py`.
- `NEXT_PUBLIC_MYAGENT_API_BASE_URL` - Browser backend base URL read by `frontend/lib/task-api.ts`; `auto` behavior is implemented by `frontend/app/task-state.ts`.
- `NEXT_PUBLIC_MYAGENT_TOKEN` - Browser-visible token paired with `MYAGENT_ACCESS_TOKEN` for protected local/LAN deployments in `frontend/lib/task-api.ts`.

**Optional env vars:**
- `DEEPSEEK_BASE_URL` - DeepSeek-compatible API base URL in `backend/app/config.py`.
- `OPENAI_API_KEY` - Enables explicit OpenAI provider IDs in `backend/app/models/provider.py`.
- `ANTHROPIC_API_KEY` - Enables explicit Anthropic provider IDs in `backend/app/models/provider.py`.
- `MYAGENT_SEARXNG_URL` - Overrides the local SearXNG endpoint used by `backend/app/tools/searxng_search.py`.
- `MYAGENT_QDRANT_COLLECTION` - Sets the Qdrant memory collection in `backend/app/config.py` and `backend/app/memory.py`.
- `MYAGENT_EMBEDDING_BASE_URL`, `MYAGENT_EMBEDDING_MODEL`, and `MYAGENT_EMBEDDING_DIMENSIONS` - Configure embedding requests in `backend/app/config.py` and `backend/app/memory.py`.
- `MYAGENT_TASK_ROOT` - Moves local upload and artifact storage from `backend/storage/sessions/` in `backend/app/config.py`.
- `MYAGENT_SKILLS_DIRS` - Controls DeepAgents skill sources loaded by `backend/app/config.py`, `backend/app/skills/loader.py`, and `backend/app/agent/factory.py`.
- `MYAGENT_CORS_ORIGINS` - Controls allowed browser origins in `backend/app/main.py`.
- `MYAGENT_MAX_UPLOAD_FILES`, `MYAGENT_MAX_UPLOAD_FILE_BYTES`, `MYAGENT_MAX_UPLOAD_REQUEST_BYTES`, and `MYAGENT_MAX_JSON_REQUEST_BYTES` - Control upload/body limits in `backend/app/config.py`, `backend/app/main.py`, and `backend/app/api/files.py`.
- `MYAGENT_AGENT_TIMEOUT_SECONDS`, `MYAGENT_FRESH_TOOL_CACHE_SECONDS`, `MYAGENT_RECENT_MESSAGE_LIMIT`, `MYAGENT_MEMORY_MIN_SCORE`, and `MYAGENT_DEFAULT_USER_ID` - Tune runner, cache, context, and memory behavior in `backend/app/config.py`.
- `WEB_CONCURRENCY`, `UVICORN_WORKERS`, and `GUNICORN_WORKERS` - Must not exceed 1; enforced by `backend/app/config.py`.
- `MYAGENT_E2E_*` vars - Browser E2E configuration consumed by `frontend/e2e-playwright/*.mjs` and documented in `frontend/e2e-playwright/README.md`.

**Secrets location:**
- Backend secrets belong in `backend/.env` or backend process environment and are loaded by `backend/app/config.py`; `backend/.env` exists locally and is ignored by `.gitignore` and `backend/.gitignore`.
- Frontend `.env.local` exists locally and is ignored by `frontend/.gitignore`; only browser-safe `NEXT_PUBLIC_*` values belong there per `frontend/lib/task-api.ts` and `README.md`.
- Example env files exist at `backend/.env.example` and `frontend/.env.example`; do not copy secret values into committed docs.

## Webhooks & Callbacks

**Incoming:**
- None detected - FastAPI exposes REST and SSE endpoints only through routers in `backend/app/api/tasks.py`, `backend/app/api/files.py`, `backend/app/api/artifacts.py`, `backend/app/api/streaming.py`, and `backend/app/api/models.py`.
- No webhook-specific route names, signature verification handlers, or external callback endpoints are detected under `backend/app/`.

**Outgoing:**
- Model provider requests are initiated by LangChain `init_chat_model` clients from `backend/app/models/provider.py`.
- DashScope-compatible embedding requests are sent with `httpx.post` in `backend/app/memory.py`.
- Qdrant collection, upsert, search, reset, and validation requests are sent with `httpx` in `backend/app/memory.py`.
- SearXNG search requests are sent with `httpx.get` in `backend/app/tools/searxng_search.py`.
- Browser-to-backend REST, blob, and SSE requests are sent from `frontend/lib/task-api.ts`.

---

*Integration audit: 2026-05-19*
