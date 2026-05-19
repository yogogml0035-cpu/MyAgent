# External Integrations

**Analysis Date:** 2026-05-19

## APIs & External Services

**Model Providers:**
- DeepSeek - Default registered provider for chat, task titles, runner execution, and memory extraction.
  - SDK/Client: `langchain-deepseek` through `create_model()` in `backend/app/models/provider.py`.
  - Auth: `DEEPSEEK_API_KEY`; base URL from `DEEPSEEK_BASE_URL`.
  - Registry: `MODEL_REGISTRY` in `backend/app/config.py` exposes `deepseek:deepseek-chat` and `deepseek:deepseek-reasoner`.
- OpenAI - Optional provider for explicit `openai:<model>` IDs and subagent definitions.
  - SDK/Client: `langchain-openai` in `backend/app/models/provider.py`.
  - Auth: `OPENAI_API_KEY`.
- Anthropic - Optional provider for explicit `anthropic:<model>` IDs.
  - SDK/Client: `langchain-anthropic` in `backend/app/models/provider.py`.
  - Auth: `ANTHROPIC_API_KEY`.

**Search:**
- SearXNG - Local web search exposed as `searxng_search`.
  - Integration method: Direct JSON API calls to `/search` with `httpx` in `backend/app/tools/searxng_search.py`.
  - Auth: None detected.
  - URL config: `MYAGENT_SEARXNG_URL`, defaulting to local loopback.
  - Cache: Successful non-refresh results can be cached through `PostgresTaskStorage.cache_tool_result()`.

**Embeddings & Vector Memory:**
- DashScope-compatible embeddings - Embeds sanitized memory text.
  - Integration method: Direct `httpx.post` to `{MYAGENT_EMBEDDING_BASE_URL}/embeddings` in `backend/app/memory.py`.
  - Auth: `DASHSCOPE_API_KEY` bearer token.
  - Model config: `MYAGENT_EMBEDDING_MODEL` and `MYAGENT_EMBEDDING_DIMENSIONS`.
- Qdrant - Semantic memory index.
  - Integration method: Direct REST calls in `QdrantMemoryIndex` in `backend/app/memory.py`.
  - Auth: None detected in code.
  - Collection config: `MYAGENT_QDRANT_COLLECTION`.

## Data Storage

**Databases:**
- Postgres - Canonical storage for tasks, runs, messages, events, context summaries, tool caches, long-term memory rows, and LangGraph store items.
  - Connection: `MYAGENT_DATABASE_URL` or fallback `DATABASE_URL` in `backend/app/config.py`.
  - Client: `psycopg` with `dict_row` and JSONB values in `backend/app/storage.py`.
  - Migrations: `PostgresTaskStorage.initialize()` idempotently creates and alters tables at startup.

**File Storage:**
- Local task root - Uploads and artifacts are stored beneath `MYAGENT_TASK_ROOT`, defaulting to `backend/storage/sessions/`.
  - Uploads: `uploads/` per task; accepted extensions are `.md`, `.json`, `.txt`, `.docx`, `.xlsx`, and `.xlsm`.
  - Artifacts: `artifacts/runs/{run_id}/` per run plus compatibility top-level artifact copies for known names.
  - Path safety: Task IDs, run IDs, filenames, and artifact names are normalized in `backend/app/storage.py`.

**Caching:**
- Tool-result cache - Postgres `tool_result_cache` with TTL from `MYAGENT_FRESH_TOOL_CACHE_SECONDS`.
- No Redis, Memcached, or external cache service is used by the backend.

## Authentication & Identity

**Auth Provider:**
- Custom local token gate in `backend/app/main.py`.
  - Loopback clients are allowed when `MYAGENT_ACCESS_TOKEN` is unset.
  - When configured, credentials are accepted through `X-MyAgent-Token`, legacy `X-Agent-Chat-Token`, `Authorization: Bearer`, or SSE `token` query parameter.
  - CORS origins come from `MYAGENT_CORS_ORIGINS`.

**User Identity:**
- Long-term memory is scoped by `MYAGENT_DEFAULT_USER_ID`, defaulting to `local-user`.
- No OAuth, cookie session, or per-user account model is present in backend code.

## Monitoring & Observability

**Error Tracking:**
- No Sentry, OpenTelemetry, Datadog, or external error-tracking integration is detected.

**Logs:**
- Python `logging` is used in modules such as `backend/app/main.py`, `backend/app/runner/core.py`, `backend/app/memory.py`, and `backend/app/streaming/v2_adapter.py`.
- User-visible runtime diagnostics are persisted as ordered `events` rows and streamed through `backend/app/api/streaming.py`.

## CI/CD & Deployment

**Hosting:**
- Local/WSL deployment is documented in `backend/README.md`; backend listens on `127.0.0.1:8001` by default.
- No backend-specific Docker, Kubernetes, process manager, reverse proxy, or cloud hosting config is detected.

**CI Pipeline:**
- Root backend CI runs `uv lock --check`, `uv sync --locked --group dev`, `pip-audit`, pytest, Ruff, and mypy.

## Environment Configuration

**Development:**
- Required for real app startup: `MYAGENT_DATABASE_URL`, `MYAGENT_QDRANT_URL`, and `DASHSCOPE_API_KEY`.
- Required for runnable default models: `DEEPSEEK_API_KEY`.
- Local secrets belong only in `backend/.env` or backend process env.

**Production:**
- Non-loopback access should configure `MYAGENT_ACCESS_TOKEN` and restrictive `MYAGENT_CORS_ORIGINS`.
- Persistent deployments need durable Postgres and durable `MYAGENT_TASK_ROOT`.

## Webhooks & Callbacks

**Incoming:**
- No webhook-specific routes or signature verification handlers are detected.
- Public routes are task REST, file upload, artifact download, SSE stream, model list, and `/health`.

**Outgoing:**
- Model provider requests through LangChain provider packages.
- SearXNG HTTP search from `backend/app/tools/searxng_search.py`.
- DashScope-compatible embedding calls and Qdrant index calls from `backend/app/memory.py`.

---

*Integration audit: 2026-05-19*
*Update when adding/removing external services or auth/storage boundaries*
