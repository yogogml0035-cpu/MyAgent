# Codebase Structure

**Analysis Date:** 2026-05-19

## Directory Layout

```text
backend/
├── app/                    # FastAPI app, runtime, storage, tools, memory, schemas
│   ├── api/                # REST/SSE route modules
│   ├── agent/              # DeepAgents factory and middleware helpers
│   ├── execution/          # Uploaded-resource tool implementation
│   ├── models/             # Model registry and provider creation
│   ├── runner/             # TaskRunner lifecycle orchestration
│   ├── security/           # Secret scanning and redaction
│   ├── streaming/          # LangGraph event adapter, event converter, SSE helpers
│   ├── subagents/          # Built-in subagent definitions and registry
│   ├── tools/              # Platform tool registry and SearXNG tool
│   ├── config.py           # Settings and model registry
│   ├── main.py             # FastAPI app factory and middleware
│   ├── schemas.py          # Public API schemas
│   └── storage.py          # Postgres state and local upload/artifact storage
├── skills/                 # Runtime DeepAgents skill directories
├── storage/                # Ignored local task workspaces
├── tests/                  # pytest unit, integration, and backend e2e tests
├── pyproject.toml          # Dependencies and tool config
├── uv.lock                 # Exact backend dependency lockfile
├── README.md               # Backend setup/run/test notes
└── .env.example            # Backend env var template
```

## Directory Purposes

**`backend/app/api/`:**
- Purpose: HTTP route boundaries.
- Key files: `tasks.py`, `files.py`, `artifacts.py`, `streaming.py`, `models.py`.
- Add new public endpoints here, keeping request/response schemas in `backend/app/schemas.py`.

**`backend/app/agent/`:**
- Purpose: DeepAgents creation and optional extra middleware assembly.
- Key files: `factory.py`, `middleware.py`.
- Use `build_agent()` as the production path unless the alternate middleware path has explicit tests.

**`backend/app/execution/`:**
- Purpose: Local Provision/Execute-style adapter for uploaded resources.
- Key file: `resources.py`.
- Add new uploaded-resource tools here, then expose them via `backend/app/tools/registry.py`.

**`backend/app/models/`:**
- Purpose: Validate provider-prefixed model IDs and instantiate LangChain chat models.
- Key files: `provider.py`, `registry.py`.

**`backend/app/runner/`:**
- Purpose: Task run lifecycle, cancellation, event persistence, final answer extraction, and memory write scheduling.
- Key file: `core.py`.

**`backend/app/security/`:**
- Purpose: Detect and redact secret-like content before memory or docs/logs reuse.
- Key file: `scanner.py`.

**`backend/app/streaming/`:**
- Purpose: Normalize DeepAgents/LangGraph stream chunks into platform events and format SSE.
- Key files: `v2_adapter.py`, `event_converter.py`, `sse.py`.

**`backend/app/tools/`:**
- Purpose: Register platform tools available to the agent.
- Key files: `registry.py`, `searxng_search.py`, `filesystem_bridge.py`.

**`backend/tests/`:**
- Purpose: Backend verification.
- Structure: `unit/`, `integration/`, `e2e/`, plus shared `conftest.py` and `fakes.py`.

## Key File Locations

**Entry Points:**
- `backend/app/main.py` - ASGI app factory and `app = create_app()`.
- `backend/app/api/tasks.py` - Task lifecycle REST API.
- `backend/app/runner/core.py` - Runtime execution entry.

**Configuration:**
- `backend/pyproject.toml` - Dependencies, pytest, Ruff, mypy, uv Git source.
- `backend/uv.lock` - Locked Python package versions.
- `backend/.env.example` - Backend env template.
- `backend/app/config.py` - Runtime settings and model registry.

**Core Logic:**
- `backend/app/storage.py` - Postgres tables, task state, events, uploads, artifacts, caches, memory rows, agent store.
- `backend/app/agent/factory.py` - DeepAgents graph creation.
- `backend/app/execution/resources.py` - Upload resource inspection/read tools.
- `backend/app/memory.py` - Long-term memory service and Qdrant/DashScope integration.
- `backend/app/streaming/v2_adapter.py` - Raw stream adapter.
- `backend/app/streaming/event_converter.py` - Platform event projection.

**Testing:**
- `backend/tests/unit/api/` - FastAPI route contracts.
- `backend/tests/unit/runner/` - runner, context, memory behavior.
- `backend/tests/unit/streaming/` - stream adapter, converter, SSE helpers.
- `backend/tests/unit/storage/` - storage and agent-store behavior.
- `backend/tests/integration/` - agent build and Postgres/memory integration.
- `backend/tests/e2e/test_streaming_e2e.py` - backend SSE end-to-end behavior with test storage.

**Documentation:**
- `backend/README.md` - Backend install/run/test/env notes.
- `backend/.planning/codebase/` - Backend codebase map.

## Naming Conventions

**Files:**
- `snake_case.py` for backend modules, such as `conversation_context.py` and `task_titles.py`.
- `test_*.py` for pytest files.
- `__init__.py` marks backend packages.

**Directories:**
- Domain package names are lowercase and usually singular/plural by domain: `api/`, `runner/`, `streaming/`, `tools/`, `skills/`.

**Special Patterns:**
- Route modules live in `backend/app/api/`.
- Test packages mirror subsystem boundaries under `backend/tests/unit/<subsystem>/`.
- Runtime skills use `skills/<skill_name>/SKILL.md`.

## Where to Add New Code

**New API endpoint:**
- Route: `backend/app/api/`.
- Schema: `backend/app/schemas.py`.
- Tests: `backend/tests/unit/api/test_*.py`.
- Frontend contract impact: update `frontend/lib/task-api.ts` and frontend map/docs when exposed to UI.

**New task state or storage contract:**
- Production storage: `backend/app/storage.py`.
- Fake storage parity: `backend/tests/fakes.py`.
- Tests: `backend/tests/unit/storage/` plus relevant API/runner tests.

**New runner or stream event behavior:**
- Runner: `backend/app/runner/core.py`.
- Adapter/converter: `backend/app/streaming/`.
- Tests: `backend/tests/unit/runner/`, `backend/tests/unit/streaming/`, and frontend state/projection tests if UI-visible.

**New uploaded-resource capability:**
- Implementation: `backend/app/execution/resources.py`.
- Registration: `backend/app/tools/registry.py`.
- Tests: `backend/tests/unit/tools/test_resource_execution.py`.

**New model provider:**
- Config: `backend/app/config.py`.
- Provider: `backend/app/models/provider.py`.
- Registry tests: `backend/tests/unit/models/`.

## Special Directories

**`backend/storage/sessions/`:**
- Purpose: Local task workspaces with uploads and artifacts.
- Source: Runtime-generated.
- Committed: No, except `.gitkeep` via ignore rules.

**`backend/.venv/`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, `__pycache__/`:**
- Purpose: Local generated tool/cache artifacts.
- Committed: No.

**`backend/skills/`:**
- Purpose: Runtime skill sources loaded by default `MYAGENT_SKILLS_DIRS=./skills`.
- Committed: Yes.

---

*Structure analysis: 2026-05-19*
*Update when backend directories, entry points, or placement rules change*
