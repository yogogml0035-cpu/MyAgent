# External Integrations

**Analysis Date:** 2026-05-22

## APIs & External Services

**LLM Provider:**
- DeepSeek - chat model provider for task runs, title generation, and long-term memory extraction.
  - SDK/Client: `langchain-deepseek` via `ChatDeepSeek` in `backend/app/models/provider.py`; thinking mode subclasses it in `backend/app/models/deepseek_thinking.py`.
  - Auth: `DEEPSEEK_API_KEY`.
  - Base URL: `DEEPSEEK_BASE_URL`, defaulting to `https://api.deepseek.com` in `backend/app/config.py`.
  - Safe model IDs exposed to browsers: `deepseek-v4-flash` and `deepseek-v4-flash-thinking` from `MODEL_REGISTRY` in `backend/app/config.py`.
  - API surface: `/api/models` in `backend/app/api/models.py` returns browser-safe model metadata and availability without exposing provider secrets.

**Embedding Provider:**
- DashScope-compatible embeddings - embeds text for long-term memory recall and indexing.
  - SDK/Client: direct `httpx.post` to `{MYAGENT_EMBEDDING_BASE_URL}/embeddings` in `backend/app/memory.py`.
  - Auth: `DASHSCOPE_API_KEY` sent as a bearer token by `DashScopeEmbeddingClient`.
  - Base URL: `MYAGENT_EMBEDDING_BASE_URL`, defaulting to `https://dashscope.aliyuncs.com/compatible-mode/v1`.
  - Model: `MYAGENT_EMBEDDING_MODEL`, defaulting to `text-embedding-v3`.
  - Vector dimensions: `MYAGENT_EMBEDDING_DIMENSIONS`, defaulting to 1024.

**Search:**
- SearXNG - local web search engine exposed as the `searxng_search` LangChain tool.
  - SDK/Client: direct `httpx.get` to the `/search` endpoint in `backend/app/tools/searxng_search.py`.
  - Auth: none detected.
  - URL: `MYAGENT_SEARXNG_URL`, defaulting to `http://127.0.0.1:8181/`.
  - Tool registration: `backend/app/tools/registry.py` adds the tool when `Settings.searxng_url` is configured.
  - Cache: successful results can be cached in PostgreSQL tool cache rows through `storage.cache_tool_result` and `settings.fresh_tool_cache_seconds`.

**Agent Runtime:**
- DeepAgents and LangGraph - local agent graph creation, virtual filesystem backends, state backend, store backend, project skills, and subagents.
  - SDK/Client: `deepagents.create_deep_agent`, DeepAgents backend classes, and LangGraph store interfaces in `backend/app/agent/factory.py` and `backend/app/agent_store.py`.
  - Auth: not applicable.
  - Mounted routes: `/scratch/` state backend, `/memories/` store backend when a store is supplied, `/skills/` or `/skills/source-{n}/` read-only skill routes.

## Data Storage

**Databases:**
- PostgreSQL - primary durable task, run, message, event, store, cache, and memory metadata storage.
  - Connection: `MYAGENT_DATABASE_URL` with `DATABASE_URL` fallback in `backend/app/config.py`.
  - Client: `psycopg[binary]` in `backend/app/storage.py`.
  - Tables created by `PostgresTaskStorage.initialize()` in `backend/app/storage.py`: `tasks`, `runs`, `messages`, `events`, `agent_store_items`, `task_context_summaries`, `tool_result_cache`, and `long_term_memories`.
  - Indexes created in `backend/app/storage.py`: `idx_events_task_seq`, `idx_events_task_id`, `idx_runs_task`, `idx_messages_task`, `idx_agent_store_namespace`, `idx_tool_result_cache_task_tool`, and `idx_long_term_memories_user`.
  - Tests: PostgreSQL integration coverage in `backend/tests/integration/test_postgres_memory_storage.py` uses `MYAGENT_TEST_DATABASE_URL` or `MYAGENT_DATABASE_URL` when configured.

- Qdrant - vector index for long-term memory recall.
  - Connection: `MYAGENT_QDRANT_URL`.
  - Client: direct `httpx.get`, `httpx.put`, `httpx.post`, and `httpx.delete` calls in `backend/app/memory.py`.
  - Collection: `MYAGENT_QDRANT_COLLECTION`, defaulting to `myagent_memories`.
  - Vector schema: cosine distance with size from `MYAGENT_EMBEDDING_DIMENSIONS`.
  - Admin CLI: `backend/app/memory_admin.py` supports `reset-qdrant` and `rebuild-qdrant`.

**File Storage:**
- Local filesystem task storage - uploaded files and generated artifacts are stored under `Settings.task_root`.
  - Root: `MYAGENT_TASK_ROOT`, defaulting to `backend/storage/sessions` in `backend/app/config.py`.
  - Upload directory: each task uses an `uploads` child directory from `TASK_FILE_WORKSPACE_DIRS` in `backend/app/storage.py`.
  - Artifact directory: run artifacts are stored under task-local `artifacts/runs/{run_id}` paths in `backend/app/storage.py`.
  - API: uploads are handled by `backend/app/api/files.py`; downloads are served by `backend/app/api/artifacts.py`.
  - Supported upload formats: Markdown, JSON, TXT, DOCX, XLSX, and XLSM as enforced in `backend/app/storage.py`.
  - Resource tools: uploaded resources are listed, inspected, and read by `backend/app/execution/resources.py`.

**Caching:**
- PostgreSQL tool-result cache - `backend/app/storage.py` stores SearXNG and future tool results in `tool_result_cache`.
  - TTL: `MYAGENT_FRESH_TOOL_CACHE_SECONDS`, defaulting to 600 seconds.
  - Caller: `backend/app/tools/searxng_search.py` reads fresh cache entries unless the query asks for a refresh.
- In-process settings cache - `backend/app/api/deps.py` wraps `load_settings()` with `functools.lru_cache`.

## Authentication & Identity

**Auth Provider:**
- Custom token or local-client gate.
  - Implementation: `backend/app/main.py` middleware protects `/api/` routes.
  - Default behavior: when `MYAGENT_ACCESS_TOKEN` is unset, task APIs allow loopback clients and reject non-local clients.
  - Token behavior: when `MYAGENT_ACCESS_TOKEN` or `AGENT_CHAT_ACCESS_TOKEN` is set, callers must provide the value through `Authorization: Bearer <token>`, `X-MyAgent-Token`, `X-Agent-Chat-Token`, or the `token` query parameter.
  - Comparison: `hmac.compare_digest` in `backend/app/main.py`.
  - Identity for memory: `MYAGENT_DEFAULT_USER_ID`, defaulting to `local-user`, scopes long-term memory recall and indexing in `backend/app/memory.py`.

**CORS:**
- FastAPI CORSMiddleware in `backend/app/main.py`.
  - Origins: `MYAGENT_CORS_ORIGINS` with `AGENT_CHAT_CORS_ORIGINS` fallback; defaults are `http://localhost:3001` and `http://127.0.0.1:3001`.
  - Allowed methods: `GET`, `POST`, `PUT`, `PATCH`, `DELETE`, and `OPTIONS`.
  - Allowed headers: `Content-Type`, `Authorization`, `X-MyAgent-Token`, and `X-Agent-Chat-Token`.

## Monitoring & Observability

**Error Tracking:**
- None detected. No Sentry, OpenTelemetry collector, hosted error tracking SDK, or external monitoring service is configured in `backend/pyproject.toml` or `backend/app/`.

**Logs:**
- Python `logging` is used in `backend/app/main.py`, `backend/app/runner/core.py`, `backend/app/memory.py`, `backend/app/agent/factory.py`, `backend/app/skills/loader.py`, and `backend/app/task_titles.py`.
- Task-level observability is stored as structured PostgreSQL events in `events` through `backend/app/storage.py`.
- Streaming observability is delivered to clients as Server-Sent Events from `backend/app/api/streaming.py`.
- Secret hygiene uses scanner and redaction helpers in `backend/app/security/scanner.py` for memory and session outputs.

## CI/CD & Deployment

**Hosting:**
- Local same-machine deployment is documented in `backend/README.md`.
- Run command: `uv run uvicorn app.main:app --host 127.0.0.1 --port 8001`.
- No Dockerfile, container orchestration file, Procfile, cloud hosting configuration, or process manager configuration detected in `backend/`.

**CI Pipeline:**
- None detected in the backend project. No backend-local GitHub Actions, GitLab CI, Azure Pipelines, or equivalent CI configuration is present under `backend/`.
- Validation commands are local: `uv lock --check`, `uv sync --no-dev`, and `uv run pytest` from `backend/README.md`.

## Environment Configuration

**Required env vars:**
- `DEEPSEEK_API_KEY` - required before registered models are runnable in `backend/app/models/provider.py`.
- `DEEPSEEK_BASE_URL` - optional override for the DeepSeek-compatible endpoint; defaults to `https://api.deepseek.com`.
- `MYAGENT_DATABASE_URL` - required for normal app startup when no test storage is injected in `backend/app/main.py`.
- `MYAGENT_QDRANT_URL` - required by `AgentMemoryService` in `backend/app/memory.py`.
- `DASHSCOPE_API_KEY` - required by `AgentMemoryService` and `DashScopeEmbeddingClient` in `backend/app/memory.py`.
- `MYAGENT_EMBEDDING_BASE_URL` - optional embedding endpoint override.
- `MYAGENT_EMBEDDING_MODEL` - optional embedding model override.
- `MYAGENT_EMBEDDING_DIMENSIONS` - optional embedding dimension override; must match Qdrant collection vector size.
- `MYAGENT_QDRANT_COLLECTION` - optional Qdrant collection name.
- `MYAGENT_DEFAULT_USER_ID` - optional memory identity scope.
- `MYAGENT_SEARXNG_URL` - optional local SearXNG endpoint.
- `MYAGENT_CORS_ORIGINS` - required when browser origin differs from the defaults.
- `MYAGENT_ACCESS_TOKEN` - required for non-loopback access to `/api/` routes.
- `MYAGENT_TASK_ROOT` - optional filesystem storage root override.
- `MYAGENT_SKILLS_DIRS` - optional comma-separated skill source override for agent-mounted skill files.
- `MYAGENT_MAX_UPLOAD_FILES`, `MYAGENT_MAX_UPLOAD_FILE_BYTES`, `MYAGENT_MAX_UPLOAD_REQUEST_BYTES`, and `MYAGENT_MAX_JSON_REQUEST_BYTES` - optional request safety limits.
- `MYAGENT_AGENT_TIMEOUT_SECONDS`, `MYAGENT_MAX_CONCURRENT_SUBAGENTS`, `MYAGENT_RECENT_MESSAGE_LIMIT`, `MYAGENT_FRESH_TOOL_CACHE_SECONDS`, and `MYAGENT_MEMORY_MIN_SCORE` - optional runtime behavior limits.

**Secrets location:**
- `backend/.env` file present - contains local environment configuration and must not be read or quoted.
- `backend/.env.example` is the safe source for variable names and non-secret placeholders.
- Provider secrets stay backend-only; `backend/README.md` states safe model IDs are exposed to the frontend while provider secrets remain in backend `.env`.

## Webhooks & Callbacks

**Incoming:**
- None detected. No webhook-specific endpoints are implemented in `backend/app/api/`.
- Public API endpoints are task lifecycle, uploads, artifacts, streaming, model registry, skills, and health:
  - `/health` in `backend/app/main.py`
  - `/api/tasks` and task subroutes in `backend/app/api/tasks.py`
  - `/api/tasks/{task_id}/files` in `backend/app/api/files.py`
  - `/api/tasks/{task_id}/artifacts/{artifact_name}` and `/api/tasks/{task_id}/runs/{run_id}/artifacts/{artifact_name}` in `backend/app/api/artifacts.py`
  - `/api/tasks/{task_id}/stream` in `backend/app/api/streaming.py`
  - `/api/models` in `backend/app/api/models.py`
  - `/api/skills` in `backend/app/api/skills.py`

**Outgoing:**
- DeepSeek chat completion calls are made through LangChain DeepSeek clients in `backend/app/models/provider.py`.
- DashScope-compatible embedding calls are made by `backend/app/memory.py`.
- Qdrant collection, upsert, search, reset, and rebuild calls are made by `backend/app/memory.py` and `backend/app/memory_admin.py`.
- SearXNG search calls are made by `backend/app/tools/searxng_search.py`.
- No outbound webhook callback delivery mechanism is detected.

---

*Integration audit: 2026-05-22*
