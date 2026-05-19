# Technology Stack

**Analysis Date:** 2026-05-19

## Languages

**Primary:**
- Python >=3.11 - FastAPI backend, agent runtime, storage, streaming, and tests in `backend/app/`, `backend/tests/`, `backend/pyproject.toml`, and `.python-version`.
- TypeScript/TSX - Next.js app router UI, React components, state mapping, API client, and frontend tests in `frontend/app/`, `frontend/components/`, `frontend/hooks/`, `frontend/lib/`, `frontend/tests/`, and `frontend/tsconfig.json`.

**Secondary:**
- JavaScript ES modules - Playwright E2E specs and browser harnesses in `frontend/e2e-playwright/*.mjs`.
- Bash - WSL service runner and port cleanup scripts in `scripts/dev-terminal-runner.sh` and `scripts/stop-dev-ports.sh`.
- PowerShell 5.1+ - Windows-to-WSL development launcher in `scripts/start-dev-wsl.ps1`.
- Markdown - Long-lived agent knowledge, skills, and codebase maps in `AGENTS.md`, `asset/deepagents_platform_knowledge_pack.md`, `backend/skills/*/SKILL.md`, and `.planning/codebase/`.

## Runtime

**Environment:**
- Backend runs on Python >=3.11 with project marker `3.11` in `.python-version`; CI uses `actions/setup-python` with `.python-version` in `.github/workflows/backend-ci.yml`.
- Frontend targets Node.js 20 from `.nvmrc` and `.github/workflows/frontend-ci.yml`; `frontend/package.json` scripts run Next.js on port 3001.
- Backend development runs Uvicorn on port 8001 through `scripts/dev-terminal-runner.sh` or direct commands in `README.md`.
- Frontend development uses Next.js dev server on port 3001 and isolates dev output through `NEXT_DIST_DIR=.next-dev` in `frontend/package.json` and `frontend/next.config.mjs`.

**Package Manager:**
- Backend: `uv` with lockfile `backend/uv.lock`; dependency constraints live in `backend/pyproject.toml`.
- Frontend: `npm` with lockfile `frontend/package-lock.json`; dependency constraints live in `frontend/package.json`.
- CI installs backend dependencies with `uv sync --locked --group dev` in `.github/workflows/backend-ci.yml`.
- CI installs frontend dependencies with `npm ci` in `.github/workflows/frontend-ci.yml`.
- No root-level package manager manifest is detected; backend and frontend are managed independently from `backend/` and `frontend/`.

## Frameworks

**Core:**
- FastAPI 0.136.1 - HTTP API, middleware, CORS, request limits, and health endpoint in `backend/app/main.py` and `backend/uv.lock`.
- Uvicorn 0.46.0 - ASGI development and local deployment server from `backend/pyproject.toml`, `backend/uv.lock`, `README.md`, and `scripts/dev-terminal-runner.sh`.
- Next.js 15.5.18 - App router frontend with root page mounted by `frontend/app/page.tsx`, configured by `frontend/next.config.mjs`, and locked in `frontend/package-lock.json`.
- React 19.2.5 and React DOM 19.2.5 - Frontend workspace components in `frontend/components/chat/` and locked in `frontend/package-lock.json`.
- DeepAgents 0.5.7 - Agent factory, filesystem backend, skills middleware, and optional subagent middleware in `backend/app/agent/factory.py`, `backend/app/agent/middleware.py`, and `backend/uv.lock`.
- LangChain 1.2.17 and LangGraph 1.1.10 - Chat model initialization, tools, graph streaming, and stores in `backend/app/models/provider.py`, `backend/app/streaming/v2_adapter.py`, `backend/app/agent_store.py`, and `backend/uv.lock`.
- Pydantic 2.13.3 - API request/response schemas in `backend/app/schemas.py` and `backend/uv.lock`.

**Testing:**
- pytest 9.0.3 - Backend unit, integration, and E2E tests under `backend/tests/`, configured in `backend/pyproject.toml` and locked in `backend/uv.lock`.
- pytest-asyncio 1.3.0 - Backend async test support in `backend/pyproject.toml` and `backend/uv.lock`.
- Node built-in `node:test` - Frontend unit tests invoked by `frontend/package.json` and located under `frontend/tests/`.
- Playwright 1.60.0 - Browser E2E specs under `frontend/e2e-playwright/` and locked in `frontend/package-lock.json`.

**Build/Dev:**
- TypeScript 5.9.3 - Strict frontend type checking through `frontend/tsconfig.json`, `frontend/package.json`, and `frontend/package-lock.json`.
- ESLint 9.39.4 with `eslint-config-next` 15.5.15 - Frontend linting via `frontend/eslint.config.mjs`, `frontend/package.json`, and `frontend/package-lock.json`.
- Ruff 0.15.12 - Backend linting configured in `backend/pyproject.toml` and locked in `backend/uv.lock`.
- mypy 1.20.2 - Backend type checking configured in `backend/pyproject.toml` and locked in `backend/uv.lock`.
- pip-audit - Python dependency audit runs in `.github/workflows/backend-ci.yml` through `uv run --with pip-audit pip-audit --strict`.
- Windows Terminal plus WSL scripts - Local service orchestration is implemented in `scripts/start-dev-wsl.ps1`, `scripts/dev-terminal-runner.sh`, and `scripts/stop-dev-ports.sh`.

## Key Dependencies

**Critical:**
- `deepagents` 0.5.7 - Builds the core agent graph and task-scoped filesystem backend in `backend/app/agent/factory.py` and `backend/uv.lock`.
- `langchain` 1.2.17 - Initializes provider chat models and defines tool/message types in `backend/app/models/provider.py`, `backend/app/execution/resources.py`, and `backend/uv.lock`.
- `langgraph` 1.1.10 - Provides compiled graph streaming and `BaseStore` integration in `backend/app/streaming/v2_adapter.py`, `backend/app/agent_store.py`, and `backend/uv.lock`.
- `langchain-deepseek` 1.0.1 - Supports the default DeepSeek provider selected by `MODEL_REGISTRY` in `backend/app/config.py` and locked in `backend/uv.lock`.
- `langchain-openai` 1.2.1 - Supports OpenAI provider IDs in `backend/app/models/provider.py` and optional subagent definitions in `backend/app/subagents/definitions.py`.
- `langchain-anthropic` 1.4.3 - Supports Anthropic provider IDs in `backend/app/models/provider.py`.
- `psycopg[binary]` 3.3.4 - Postgres-backed task, run, message, event, store, cache, and memory tables in `backend/app/storage.py` and `backend/uv.lock`.
- `httpx` 0.28.1 - Outbound HTTP client for SearXNG, Qdrant, and DashScope-compatible embeddings in `backend/app/tools/searxng_search.py`, `backend/app/memory.py`, and `backend/uv.lock`.
- `python-multipart` 0.0.28 - FastAPI multipart upload support for `POST /api/tasks/{task_id}/files` in `backend/app/api/files.py`.
- `python-docx` 1.2.0 and `openpyxl` 3.1.5 - Uploaded Word and Excel resource inspection in `backend/app/execution/resources.py`.
- `next` 15.5.18, `react` 19.2.5, and `react-dom` 19.2.5 - Frontend app and chat workspace in `frontend/app/page.tsx`, `frontend/components/chat/`, and `frontend/package-lock.json`.

**Infrastructure:**
- Postgres - Canonical storage for tasks, runs, messages, events, LangGraph store items, tool-result cache, summaries, and long-term memory rows in `backend/app/storage.py`.
- Qdrant REST API - Semantic long-term memory index accessed directly with `httpx` in `backend/app/memory.py`; no `qdrant-client` package is present in `backend/pyproject.toml`.
- DashScope-compatible embeddings endpoint - Embedding client posts to `/embeddings` in `backend/app/memory.py`.
- SearXNG JSON API - Local web search tool calls `/search?format=json` in `backend/app/tools/searxng_search.py`.
- Local filesystem - Upload and artifact bytes are stored under `backend/storage/sessions/` by default, configured by `MYAGENT_TASK_ROOT` in `backend/app/config.py`, and protected by path checks in `backend/app/storage.py`.
- Browser EventSource - Frontend SSE subscription is created in `frontend/lib/task-api.ts` and consumed by `frontend/hooks/use-task-workspace.ts`.
- React Markdown stack - Assistant and artifact text rendering uses `react-markdown` 10.1.0 and `remark-gfm` 4.0.1 in `frontend/components/chat/TaskConversation.tsx` and `frontend/components/chat/TypewriterText.tsx`.
- DeepAgents skill files - Runtime skills are stored as `backend/skills/code_review/SKILL.md` and `backend/skills/web_research/SKILL.md`, discovered by `backend/app/skills/loader.py`, and routed through `MYAGENT_SKILLS_DIRS` in `backend/app/config.py`.

## Configuration

**Environment:**
- Backend configuration is loaded from process environment plus `backend/.env` by `load_settings()` in `backend/app/config.py`; do not read or commit `backend/.env`.
- Backend secret-bearing env vars include `DEEPSEEK_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `DASHSCOPE_API_KEY`, `MYAGENT_DATABASE_URL`, `MYAGENT_QDRANT_URL`, and optional `MYAGENT_ACCESS_TOKEN`, all referenced in `backend/app/config.py`.
- Backend runtime tuning env vars include `MYAGENT_TASK_ROOT`, `MYAGENT_SEARXNG_URL`, `MYAGENT_QDRANT_COLLECTION`, `MYAGENT_EMBEDDING_BASE_URL`, `MYAGENT_EMBEDDING_MODEL`, `MYAGENT_EMBEDDING_DIMENSIONS`, `MYAGENT_DEFAULT_MODEL`, `MYAGENT_SKILLS_DIRS`, `MYAGENT_MAX_CONCURRENT_SUBAGENTS`, `MYAGENT_AGENT_TIMEOUT_SECONDS`, `MYAGENT_FRESH_TOOL_CACHE_SECONDS`, `MYAGENT_RECENT_MESSAGE_LIMIT`, `MYAGENT_MEMORY_MIN_SCORE`, `MYAGENT_CORS_ORIGINS`, and upload/body limit vars in `backend/app/config.py`.
- Frontend public env vars are limited to browser-safe values: `NEXT_PUBLIC_MYAGENT_API_BASE_URL`, legacy `NEXT_PUBLIC_API_BASE_URL`, `NEXT_PUBLIC_MYAGENT_TOKEN`, and legacy `NEXT_PUBLIC_AGENT_CHAT_TOKEN` in `frontend/lib/task-api.ts`.
- `.env` files are ignored by `.gitignore`, `backend/.gitignore`, and `frontend/.gitignore`; `.env.example` files exist at `backend/.env.example` and `frontend/.env.example` but are not needed to understand runtime values.
- Single-process runtime is enforced by `WEB_CONCURRENCY`, `UVICORN_WORKERS`, and `GUNICORN_WORKERS` checks in `backend/app/config.py`.

**Build:**
- Backend project config lives in `backend/pyproject.toml` for dependency constraints, pytest, Ruff, and mypy.
- Backend lockfile is `backend/uv.lock`; CI checks it with `uv lock --check` in `.github/workflows/backend-ci.yml`.
- Frontend dependency and script config lives in `frontend/package.json`; exact package resolution is locked in `frontend/package-lock.json`.
- Frontend TypeScript config lives in `frontend/tsconfig.json`.
- Frontend Next.js config lives in `frontend/next.config.mjs` with `distDir` controlled by `NEXT_DIST_DIR`.
- Frontend ESLint config lives in `frontend/eslint.config.mjs` and ignores `.next/`, `.next-dev/`, `.next-dev-e2e/`, `node_modules/`, and generated Next types.
- CI pipeline definitions live in `.github/workflows/backend-ci.yml`, `.github/workflows/frontend-ci.yml`, and `.github/workflows/repository-ci.yml`.

## Platform Requirements

**Development:**
- Install backend dependencies from `backend/` with `uv sync` as documented in `README.md`.
- Install frontend dependencies from `frontend/` with `npm ci` as documented in `README.md`.
- Run Postgres and provide `MYAGENT_DATABASE_URL`; startup creates tables in `backend/app/storage.py` and refuses missing database config in `backend/app/main.py`.
- Run Qdrant and provide `MYAGENT_QDRANT_URL`; startup checks or creates the configured collection in `backend/app/memory.py`.
- Provide `DASHSCOPE_API_KEY` for embedding startup probes in `backend/app/memory.py`.
- Provide `DEEPSEEK_API_KEY` for the registered default models in `backend/app/config.py` and `backend/app/models/registry.py`.
- Run SearXNG at `MYAGENT_SEARXNG_URL` or use the default local URL from `backend/app/config.py` and `backend/app/tools/searxng_search.py`.
- Use the WSL launcher in `scripts/start-dev-wsl.ps1` or run `uv run uvicorn app.main:app --reload --port 8001` and `npm run dev` from `README.md`.

**Production:**
- Deployment target is local/single-host: FastAPI/Uvicorn on `127.0.0.1:8001` and Next.js on `127.0.0.1:3001`, as documented in `README.md`.
- Backend must remain single-process because `TaskRunner` is in-process while task state is in Postgres; this is enforced in `backend/app/config.py` and documented in `AGENTS.md`.
- No Dockerfile, docker-compose, reverse proxy, TLS, process manager, Vercel config, or Netlify config is detected; deployment hardening is outside the current repo in `README.md`.
- Persistent production data requires Postgres plus a durable `MYAGENT_TASK_ROOT` for local upload and artifact files in `backend/app/config.py` and `backend/app/storage.py`.
- Non-loopback access requires `MYAGENT_ACCESS_TOKEN`, matching frontend `NEXT_PUBLIC_MYAGENT_TOKEN`, and controlled `MYAGENT_CORS_ORIGINS` per `backend/app/main.py`, `frontend/lib/task-api.ts`, and `README.md`.

---

*Stack analysis: 2026-05-19*
