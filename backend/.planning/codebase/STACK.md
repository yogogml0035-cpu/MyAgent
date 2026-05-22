# Technology Stack

**Analysis Date:** 2026-05-22

## Languages

**Primary:**
- Python >=3.11 - backend API, agent runner, model integrations, storage, and tests. The requirement is declared in `backend/pyproject.toml`; Ruff and mypy target Python 3.11 syntax. The local interpreter reports Python 3.12.10.

**Secondary:**
- Markdown - operator documentation and built-in skill definitions in `backend/README.md`, `backend/skills/web_research/SKILL.md`, and `backend/skills/code_review/SKILL.md`.
- TOML - package, dependency, lint, type-check, and test configuration in `backend/pyproject.toml`.

## Runtime

**Environment:**
- CPython >=3.11 - required by `backend/pyproject.toml`.
- ASGI server runtime through Uvicorn. Development and local deployment run `uv run uvicorn app.main:app --host 127.0.0.1 --port 8001` from `backend/README.md`.
- Single-process runtime is required. `backend/app/config.py` rejects `WEB_CONCURRENCY`, `UVICORN_WORKERS`, or `GUNICORN_WORKERS` values greater than 1 because the app uses an in-process task runner.

**Package Manager:**
- uv 0.11.7 - local package manager reported by `uv --version`.
- Lockfile: present at `backend/uv.lock`.
- Dependency source override: `backend/pyproject.toml` pins `langgraph-checkpoint` to the LangGraph GitHub repository subdirectory `libs/checkpoint` at a fixed revision.

## Frameworks

**Core:**
- FastAPI >=0.115,<1.0, resolved 0.136.1 - HTTP API application and route registration in `backend/app/main.py`, with routers in `backend/app/api/tasks.py`, `backend/app/api/files.py`, `backend/app/api/artifacts.py`, `backend/app/api/streaming.py`, `backend/app/api/models.py`, and `backend/app/api/skills.py`.
- Starlette, resolved 1.0.0 - response primitives and ASGI types used by FastAPI paths, including `StreamingResponse`, `FileResponse`, `Response`, and raw receive wrapping in `backend/app/main.py`.
- Uvicorn >=0.30,<1.0, resolved 0.46.0 - ASGI server used by commands in `backend/README.md`.
- Pydantic >=2,<3, resolved 2.13.3 - request and response schemas in `backend/app/schemas.py`.
- LangChain >=0.3,<2.0, resolved 1.2.17 - message and chat-model abstractions used in `backend/app/runner/core.py`, `backend/app/memory.py`, `backend/app/models/provider.py`, and `backend/app/models/deepseek_thinking.py`.
- LangGraph >=0.3,<2.0, resolved 1.1.10 - compiled agent graph and store interfaces used in `backend/app/agent/factory.py`, `backend/app/agent_store.py`, and `backend/app/streaming/v2_adapter.py`.
- DeepAgents >=0.5,<2.0, resolved 0.5.7 - agent construction, built-in backends, skills, and subagents in `backend/app/agent/factory.py`, `backend/app/agent/middleware.py`, and `backend/app/subagents/definitions.py`.

**Testing:**
- pytest >=8.0, resolved 9.0.3 - unit, integration, and e2e tests under `backend/tests/`.
- pytest-asyncio >=0.24, resolved 1.3.0 - async runner, streaming, and title-generation tests under `backend/tests/unit/runner/`, `backend/tests/unit/streaming/`, and `backend/tests/unit/models/`.
- FastAPI TestClient - API tests in `backend/tests/unit/api/` and streaming e2e tests in `backend/tests/e2e/test_streaming_e2e.py`.

**Build/Dev:**
- Ruff >=0.8, resolved 0.15.12 - linting configured in `backend/pyproject.toml` with line length 100 and rule groups `E`, `F`, `I`, `UP`, `B`, and `SIM`.
- mypy >=1.14, resolved 1.20.2 - type checking configured in `backend/pyproject.toml` with `check_untyped_defs = true`.
- uv - dependency synchronization, lock checking, and command runner. Use `uv sync`, `uv lock --check`, and `uv run ...` from `backend/README.md`.

## Key Dependencies

**Critical:**
- `fastapi` - owns the public HTTP API in `backend/app/main.py` and `backend/app/api/`.
- `uvicorn[standard]` - runs the ASGI app for development and local deployment.
- `python-multipart` - enables upload parsing for `UploadFile` endpoints in `backend/app/api/files.py`.
- `httpx` - calls SearXNG, DashScope embeddings, and Qdrant from `backend/app/tools/searxng_search.py` and `backend/app/memory.py`.
- `pydantic` - validates typed API contracts in `backend/app/schemas.py`.
- `langchain` and `langchain-core` - provide chat messages, tools, runnable config, and model interfaces across `backend/app/runner/core.py`, `backend/app/execution/resources.py`, and `backend/app/models/`.
- `langgraph` - provides compiled graph and persistent store interfaces in `backend/app/agent/factory.py` and `backend/app/agent_store.py`.
- `deepagents` - creates the task agent and mounts the virtual filesystem, state, memory store, and skills backends in `backend/app/agent/factory.py`.
- `langchain-deepseek` - creates DeepSeek chat models in `backend/app/models/provider.py`.

**Infrastructure:**
- `psycopg[binary]` >=3.2,<4.0, resolved 3.3.4 - PostgreSQL client used by `backend/app/storage.py` for tasks, runs, messages, events, agent store items, tool cache, and long-term memories.
- `langgraph-checkpoint`, resolved 4.1.0a4 from a Git source - available as a LangGraph checkpoint dependency; the app imports LangGraph store and graph interfaces rather than a separate checkpoint module directly.
- `python-docx` >=1.1,<2.0, resolved 1.2.0 - reads Word uploads in `backend/app/execution/resources.py`.
- `openpyxl` >=3.1,<4.0, resolved 3.1.5 - reads Excel uploads in `backend/app/execution/resources.py`.

## Configuration

**Environment:**
- Runtime configuration is centralized in `backend/app/config.py` via the immutable `Settings` dataclass.
- `backend/app/config.py` loads `backend/.env` at startup before reading process environment variables, without overwriting already-set process values.
- Use `backend/.env.example` as the non-secret reference for available settings. `backend/.env` exists and contains local environment configuration; do not read or quote it.
- Core model settings: `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL`, and `MYAGENT_DEFAULT_MODEL`.
- Storage and memory settings: `MYAGENT_DATABASE_URL`, `MYAGENT_QDRANT_URL`, `MYAGENT_QDRANT_COLLECTION`, `DASHSCOPE_API_KEY`, `MYAGENT_EMBEDDING_BASE_URL`, `MYAGENT_EMBEDDING_MODEL`, `MYAGENT_EMBEDDING_DIMENSIONS`, `MYAGENT_DEFAULT_USER_ID`, and `MYAGENT_MEMORY_MIN_SCORE`.
- Tool and task settings: `MYAGENT_SEARXNG_URL`, `MYAGENT_TASK_ROOT`, `MYAGENT_SKILLS_DIRS`, `MYAGENT_FRESH_TOOL_CACHE_SECONDS`, `MYAGENT_RECENT_MESSAGE_LIMIT`, `MYAGENT_MAX_CONCURRENT_SUBAGENTS`, and `MYAGENT_AGENT_TIMEOUT_SECONDS`.
- Access and browser settings: `MYAGENT_ACCESS_TOKEN`, `AGENT_CHAT_ACCESS_TOKEN`, `MYAGENT_CORS_ORIGINS`, and `AGENT_CHAT_CORS_ORIGINS`.
- Safety limit settings: `MYAGENT_MAX_UPLOAD_FILES`, `MYAGENT_MAX_UPLOAD_FILE_BYTES`, `MYAGENT_MAX_UPLOAD_REQUEST_BYTES`, and `MYAGENT_MAX_JSON_REQUEST_BYTES`.

**Build:**
- Package and project metadata: `backend/pyproject.toml`.
- Locked dependency graph: `backend/uv.lock`.
- Test config: `backend/pyproject.toml` under `[tool.pytest.ini_options]`.
- Lint config: `backend/pyproject.toml` under `[tool.ruff]` and `[tool.ruff.lint]`.
- Type-check config: `backend/pyproject.toml` under `[tool.mypy]`.

## Platform Requirements

**Development:**
- Install dependencies with `uv sync` from `backend/`.
- Run the server with `uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8001`.
- Run tests with `uv run pytest`.
- Configure environment by copying `backend/.env.example` to `backend/.env` and filling local secrets and service URLs.
- For realistic startup, provide `MYAGENT_DATABASE_URL`, `DASHSCOPE_API_KEY`, and `MYAGENT_QDRANT_URL`; `backend/app/main.py` treats PostgreSQL and memory services as required when dependency injection does not supply fakes.
- Browser callers must use an origin listed in `MYAGENT_CORS_ORIGINS`; defaults are `http://localhost:3001` and `http://127.0.0.1:3001`.

**Production:**
- Deployment target: local same-machine FastAPI service on `127.0.0.1:8001`, per `backend/README.md`.
- Run local deployment with `uv lock --check`, `uv sync --no-dev`, and `uv run uvicorn app.main:app --host 127.0.0.1 --port 8001`.
- Keep the deployment single-process. Do not configure multiple Uvicorn, Gunicorn, or web concurrency workers unless `backend/app/config.py` and `backend/app/runner/core.py` are changed to externalize active-run coordination.
- Required production services are PostgreSQL, Qdrant, DashScope-compatible embeddings, DeepSeek chat completion access, and optionally a local SearXNG instance.

---

*Stack analysis: 2026-05-22*
