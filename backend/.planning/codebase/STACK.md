# Technology Stack

**Analysis Date:** 2026-05-19

## Languages

**Primary:**
- Python >=3.11 - FastAPI API, DeepAgents runtime, storage, streaming, memory, tool, and test code under `backend/app/` and `backend/tests/`.

**Secondary:**
- TOML - Dependency, pytest, Ruff, mypy, and uv source configuration in `backend/pyproject.toml`.
- Markdown - Runtime skill definitions in `backend/skills/code_review/SKILL.md` and `backend/skills/web_research/SKILL.md`.

## Runtime

**Environment:**
- Python target is 3.11 from root `.python-version` and `backend/pyproject.toml`.
- ASGI app is `app.main:app` from `backend/app/main.py`.
- Local development runs Uvicorn on port 8001.
- Runtime is intentionally single-process; `backend/app/config.py` rejects `WEB_CONCURRENCY`, `UVICORN_WORKERS`, or `GUNICORN_WORKERS` values greater than 1.

**Package Manager:**
- `uv` manages backend dependencies from `backend/pyproject.toml`.
- Lockfile: `backend/uv.lock` is present.

## Frameworks

**Core:**
- FastAPI 0.136.1 - HTTP API, middleware, route registration, CORS, request limits, and `/health` in `backend/app/main.py`.
- Uvicorn 0.46.0 - ASGI local server used by `backend/README.md` and root development scripts.
- Pydantic 2.13.3 - Request and response models in `backend/app/schemas.py`.
- DeepAgents 0.5.7 - Agent graph construction and task-scoped filesystem backend in `backend/app/agent/factory.py`.
- LangChain 1.2.17 - Chat model and message/tool abstractions in `backend/app/models/provider.py`, `backend/app/runner/core.py`, and `backend/app/execution/resources.py`.
- LangGraph 1.1.10 - Streaming graph and store interfaces in `backend/app/streaming/v2_adapter.py` and `backend/app/agent_store.py`.

**Testing:**
- pytest 9.0.3 - Backend test runner configured in `backend/pyproject.toml`.
- pytest-asyncio 1.3.0 - Async runner and streaming tests in `backend/tests/unit/runner/` and `backend/tests/unit/streaming/`.
- FastAPI `TestClient` - API contract tests in `backend/tests/unit/api/`.

**Build/Dev:**
- Ruff 0.15.12 - Linting for `backend/app/` and `backend/tests/`.
- mypy 1.20.2 - Static type checking with `check_untyped_defs = true`.
- pip-audit - Dependency audit is run by root backend CI workflow.

## Key Dependencies

**Critical:**
- `deepagents` - Creates the core agent graph in `backend/app/agent/factory.py`.
- `langchain-deepseek` - Default provider support for registered DeepSeek models.
- `langchain-openai` and `langchain-anthropic` - Optional provider support for explicit model IDs.
- `psycopg[binary]` 3.3.4 - Postgres task, run, message, event, memory, cache, and store persistence in `backend/app/storage.py`.
- `httpx` 0.28.1 - SearXNG, Qdrant, and DashScope-compatible embedding HTTP calls.
- `python-multipart` 0.0.28 - Multipart upload parsing for `backend/app/api/files.py`.
- `python-docx` 1.2.0 and `openpyxl` 3.1.5 - Uploaded Word and Excel resource inspection in `backend/app/execution/resources.py`.

**Infrastructure:**
- Postgres - Authoritative lifecycle storage via `backend/app/storage.py`.
- Local filesystem - Upload and artifact bytes under `backend/storage/sessions/` by default.
- Qdrant REST API - Semantic long-term memory index through `backend/app/memory.py`.
- DashScope-compatible embeddings endpoint - Vector generation through direct `httpx.post` calls in `backend/app/memory.py`.
- SearXNG JSON API - Local web search tool in `backend/app/tools/searxng_search.py`.

## Configuration

**Environment:**
- Backend config is loaded by `load_settings()` in `backend/app/config.py`; it reads `backend/.env` before process env without overwriting existing env vars.
- Secret-bearing env vars include `DEEPSEEK_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `DASHSCOPE_API_KEY`, `MYAGENT_DATABASE_URL`, `MYAGENT_QDRANT_URL`, and optional `MYAGENT_ACCESS_TOKEN`.
- Runtime tuning env vars include `MYAGENT_TASK_ROOT`, `MYAGENT_SEARXNG_URL`, `MYAGENT_QDRANT_COLLECTION`, `MYAGENT_EMBEDDING_*`, `MYAGENT_DEFAULT_MODEL`, `MYAGENT_SKILLS_DIRS`, `MYAGENT_AGENT_TIMEOUT_SECONDS`, and upload/body limit vars.
- `backend/.env` is ignored by `backend/.gitignore`; only `backend/.env.example` should be committed.

**Build:**
- `backend/pyproject.toml` holds dependency constraints, test config, Ruff, mypy, and the Git source pin for `langgraph-checkpoint`.
- `backend/uv.lock` holds exact resolved package versions.

## Platform Requirements

**Development:**
- Install with `cd backend && uv sync`.
- Run with `cd backend && uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8001`.
- Provide Postgres, Qdrant, DashScope, and model-provider configuration for full runtime startup.
- Tests can inject `InMemoryTaskStorage` from `backend/tests/fakes.py` and temporary `Settings` from `backend/tests/conftest.py` to avoid real services.

**Production:**
- Current deployment shape is local/single-host Uvicorn plus durable Postgres and task-root filesystem.
- Multi-worker or multi-host deployment is not supported until active-run ownership moves out of the in-process `TaskRunner`.
- No Dockerfile, process manager, reverse proxy, or TLS config is present under `backend/`.

---

*Stack analysis: 2026-05-19*
*Update after major dependency, runtime, or deployment changes*
