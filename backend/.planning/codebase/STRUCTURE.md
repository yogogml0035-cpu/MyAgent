# Codebase Structure

**Analysis Date:** 2026-05-22

## Directory Layout

```text
backend/
|-- app/                    # FastAPI backend package
|   |-- api/                # REST and SSE routers
|   |-- agent/              # DeepAgents/LangGraph construction and middleware wiring
|   |-- contracts/          # Event, resource, and artifact dataclass contracts
|   |-- execution/          # Task-scoped resource execution tools
|   |-- models/             # Model registry, provider factory, DeepSeek thinking adapter
|   |-- runner/             # In-process task runner orchestration
|   |-- security/           # Secret scanning and redaction helpers
|   |-- session/            # Event-log projection helpers
|   |-- skills/             # Backend code for discovering project skill files
|   |-- streaming/          # LangGraph stream adapter, event conversion, SSE formatters
|   |-- subagents/          # Built-in DeepAgents subagent definitions
|   |-- tools/              # Platform tool registry and SearXNG tool
|   |-- main.py             # FastAPI composition root and ASGI app
|   |-- config.py           # Settings, env loading, model registry, worker guard
|   |-- storage.py          # PostgreSQL task/event store and local file workspace manager
|   |-- schemas.py          # Pydantic API DTOs
|   |-- memory.py           # Long-term memory service, Qdrant, DashScope embeddings
|   |-- agent_store.py      # LangGraph BaseStore adapter backed by storage
|   |-- conversation_context.py # Same-session context builder
|   |-- permissions.py      # Workspace/command permission policy
|   |-- reasoning_trace.py  # Reasoning trace payload helpers
|   `-- task_titles.py      # Automatic task title generation
|-- skills/                 # User-selectable project skills exposed to agents
|   |-- code_review/
|   `-- web_research/
|-- tests/                  # pytest suite, grouped by backend layer
|   |-- unit/
|   |-- integration/
|   |-- e2e/
|   |-- conftest.py
|   `-- fakes.py
|-- storage/                # Local runtime task workspaces; not source code
|-- tmp/                    # Local scratch/runtime temp files
|-- .planning/codebase/     # Backend-scoped GSD codebase maps
|-- .env.example            # Safe environment variable example
|-- .env                    # Local secrets/config; do not read or quote values
|-- pyproject.toml          # Python package/dependency/tooling config
|-- uv.lock                 # Locked uv dependency graph
`-- README.md               # Backend install/run/test/environment docs
```

## Directory Purposes

**`backend/app/`:**
- Purpose: Main backend Python package.
- Contains: FastAPI app, routers, services, persistence, model providers, tool integrations, stream adapters, and runtime helpers.
- Key files: `backend/app/main.py`, `backend/app/config.py`, `backend/app/storage.py`, `backend/app/runner/core.py`, `backend/app/schemas.py`.

**`backend/app/api/`:**
- Purpose: Define browser-facing REST and SSE routes.
- Contains: Router modules by surface area: tasks, files, artifacts, streaming, models, skills, dependencies.
- Key files: `backend/app/api/tasks.py`, `backend/app/api/files.py`, `backend/app/api/artifacts.py`, `backend/app/api/streaming.py`, `backend/app/api/models.py`, `backend/app/api/skills.py`.

**`backend/app/agent/`:**
- Purpose: Build DeepAgents/LangGraph compiled agents with platform defaults.
- Contains: `factory.py` for backend/skills/store/model/tool wiring and `middleware.py` for future middleware composition.
- Key files: `backend/app/agent/factory.py`, `backend/app/agent/middleware.py`.

**`backend/app/runner/`:**
- Purpose: Own in-process run orchestration.
- Contains: `TaskRunner`, runner protocols, background task management, run finalization, and terminal event payload helpers.
- Key files: `backend/app/runner/core.py`.

**`backend/app/streaming/`:**
- Purpose: Normalize LangGraph stream chunks into platform events and format SSE terminal messages.
- Contains: v2 stream adapter, event converter, and SSE formatter helpers.
- Key files: `backend/app/streaming/v2_adapter.py`, `backend/app/streaming/event_converter.py`, `backend/app/streaming/sse.py`.

**`backend/app/execution/`:**
- Purpose: Provide resource execution abstractions and LangChain tools for uploaded task files.
- Contains: provision/execute dataclasses, local resource adapter, resource tool factories, document/table readers.
- Key files: `backend/app/execution/resources.py`.

**`backend/app/tools/`:**
- Purpose: Register platform tools beyond DeepAgents built-ins.
- Contains: aggregate tool registry, SearXNG search tool, filesystem bridge utilities.
- Key files: `backend/app/tools/registry.py`, `backend/app/tools/searxng_search.py`, `backend/app/tools/filesystem_bridge.py`.

**`backend/app/models/`:**
- Purpose: Keep safe app model IDs separate from concrete provider model construction.
- Contains: DeepSeek-only registry checks, provider factory, and thinking-output adapter.
- Key files: `backend/app/models/registry.py`, `backend/app/models/provider.py`, `backend/app/models/deepseek_thinking.py`.

**`backend/app/contracts/`:**
- Purpose: Shared dataclass contracts for storage events, resources, artifacts, and payload serialization.
- Contains: `SessionEvent`, `NewSessionEvent`, `SessionSnapshot`, `ResourceRef`, `ArtifactRef`, payload builders.
- Key files: `backend/app/contracts/__init__.py`.

**`backend/app/session/`:**
- Purpose: Project event logs into task/session state snapshots.
- Contains: `TaskStateProjector`, projected state dataclasses, terminal event status mapping.
- Key files: `backend/app/session/projector.py`.

**`backend/app/security/`:**
- Purpose: Detect and redact sensitive text before it is written into context or memory.
- Contains: secret regexes, redaction, session output scanners, assertion helper.
- Key files: `backend/app/security/scanner.py`.

**`backend/app/skills/`:**
- Purpose: Backend code for discovering project skill files.
- Contains: `SKILL.md` frontmatter parser and browser-safe project skill projection.
- Key files: `backend/app/skills/loader.py`, `backend/app/skills/project.py`, `backend/app/skills/registry.py`.

**`backend/app/subagents/`:**
- Purpose: Define built-in DeepAgents subagents.
- Contains: Researcher, Coder, and File Analyst definitions plus lookup helpers.
- Key files: `backend/app/subagents/definitions.py`, `backend/app/subagents/registry.py`.

**`backend/skills/`:**
- Purpose: Project-scoped instruction skills available to users and mounted read-only for agents.
- Contains: One subdirectory per skill, each with a `SKILL.md` frontmatter file.
- Key files: `backend/skills/code_review/SKILL.md`, `backend/skills/web_research/SKILL.md`.

**`backend/tests/`:**
- Purpose: Backend pytest suite.
- Contains: unit tests by layer, integration tests for Postgres/memory/agent build, e2e streaming test, fake storage.
- Key files: `backend/tests/fakes.py`, `backend/tests/conftest.py`, `backend/tests/unit/api/test_tasks.py`, `backend/tests/unit/runner/test_core.py`, `backend/tests/integration/test_postgres_memory_storage.py`, `backend/tests/e2e/test_streaming_e2e.py`.

**`backend/storage/`:**
- Purpose: Local runtime task workspace root when `MYAGENT_TASK_ROOT` is not set.
- Contains: Session/task directories with uploads and artifacts at runtime.
- Key files: Not source code. Treat as runtime data.

**`backend/.planning/codebase/`:**
- Purpose: Backend-scoped codebase maps for GSD planning/execution agents.
- Contains: `ARCHITECTURE.md` and `STRUCTURE.md` for this focus.
- Key files: `backend/.planning/codebase/ARCHITECTURE.md`, `backend/.planning/codebase/STRUCTURE.md`.

## Key File Locations

**Entry Points:**
- `backend/app/main.py`: FastAPI app factory, ASGI `app`, middleware, router registration, lifespan startup.
- `backend/app/memory_admin.py`: CLI for Qdrant reset/rebuild operations.

**Configuration:**
- `backend/pyproject.toml`: Project metadata, dependencies, pytest config, Ruff config, mypy config, uv source pin.
- `backend/uv.lock`: Lockfile for uv-managed dependencies.
- `backend/.env.example`: Safe list of required/optional environment variables.
- `backend/app/config.py`: Runtime `Settings`, env loading, model registry, worker-count guard.

**API Routes:**
- `backend/app/api/tasks.py`: Task CRUD, message sends, run start/cancel, event history.
- `backend/app/api/files.py`: Upload endpoint.
- `backend/app/api/artifacts.py`: Artifact download endpoints.
- `backend/app/api/streaming.py`: SSE endpoint over persisted event records.
- `backend/app/api/models.py`: Model list endpoint.
- `backend/app/api/skills.py`: Project skill list endpoint.

**Core Logic:**
- `backend/app/runner/core.py`: Agent execution lifecycle and background run management.
- `backend/app/agent/factory.py`: DeepAgent construction and workspace/skills backend routing.
- `backend/app/storage.py`: Database schema creation, task state transitions, events, uploads, artifacts, memory rows, agent store rows.
- `backend/app/memory.py`: Memory recall, extraction, Qdrant index operations, DashScope embedding client.
- `backend/app/conversation_context.py`: Same-session context and tool-cache context builder.
- `backend/app/execution/resources.py`: Uploaded resource tool implementation.
- `backend/app/tools/registry.py`: Per-run platform tool list.
- `backend/app/tools/searxng_search.py`: SearXNG tool and result cache integration.

**Contracts and DTOs:**
- `backend/app/schemas.py`: Pydantic request/response models.
- `backend/app/contracts/__init__.py`: Dataclass contracts and stable resource/artifact IDs.
- `backend/app/session/projector.py`: Event-log projection contracts.

**Testing:**
- `backend/tests/fakes.py`: In-memory storage fake matching the storage public surface.
- `backend/tests/unit/api/`: API route behavior tests.
- `backend/tests/unit/runner/`: runner, context, concurrency, and memory orchestration tests.
- `backend/tests/unit/storage/`: storage and agent store tests.
- `backend/tests/unit/streaming/`: stream adapter and converter tests.
- `backend/tests/unit/tools/`: tool registry/resource/search tests.
- `backend/tests/integration/`: Postgres memory storage and agent build integration tests.
- `backend/tests/e2e/`: Streaming end-to-end test.

## Naming Conventions

**Files:**
- Use snake_case Python module names: `backend/app/conversation_context.py`, `backend/app/task_titles.py`, `backend/app/tools/searxng_search.py`.
- Use package `__init__.py` files for import boundaries: `backend/app/runner/__init__.py`, `backend/app/streaming/__init__.py`, `backend/app/session/__init__.py`.
- Use `test_*.py` for pytest modules, grouped under `backend/tests/unit/<layer>/`, `backend/tests/integration/`, or `backend/tests/e2e/`.
- Use `SKILL.md` exactly for project skill definitions under `backend/skills/<skill-name>/SKILL.md`.

**Directories:**
- Use domain/layer nouns under `backend/app/`: `api`, `runner`, `storage` as module file, `models`, `streaming`, `execution`, `skills`, `security`, `session`, `tools`.
- Use kebab-case for project skill directories: `backend/skills/code_review/` and `backend/skills/web_research/` are existing underscore names; keep new skill names aligned with their frontmatter `name`.
- Keep runtime data under `backend/storage/` or configured `MYAGENT_TASK_ROOT`, not inside `backend/app/`.

**Classes and Types:**
- Use PascalCase for dataclasses, Pydantic models, and service classes: `Settings`, `TaskRunner`, `PostgresTaskStorage`, `AgentMemoryService`, `EventRecord`.
- Use `Protocol` classes for injectable service/storage contracts: `RunnerStorage`, `RunnerMemoryService`, `ConversationStorage`, `LongTermMemoryStorage`.
- Use type aliases for constrained string unions in schema/contract modules: `TaskStatus`, `TaskMode`, `InputScope`, `EventLevel`.

**Functions and Variables:**
- Use snake_case for functions and methods: `create_app`, `load_settings`, `start_background`, `read_events`, `create_resource_tools`.
- Use private helper prefixes for route-local or module-local helpers: `_storage`, `_runner`, `_validate_runnable_model`, `_append_event_with_cursor`.
- Use uppercase module constants for registry/static configuration: `MODEL_REGISTRY`, `UPLOAD_FORMATS`, `RUN_ARTIFACT_NAMES`, `RESOURCE_TOOL_SYSTEM_PROMPT`.

## Where to Add New Code

**New REST Endpoint:**
- Primary code: add a router module under `backend/app/api/` or extend the closest existing router.
- Registration: include the router in `backend/app/main.py` near the existing `app.include_router(...)` calls.
- Schemas: add request/response DTOs to `backend/app/schemas.py` when the endpoint is browser-facing.
- Tests: add route tests under `backend/tests/unit/api/`.

**New Task Lifecycle Behavior:**
- Primary code: use `backend/app/api/tasks.py` for HTTP lifecycle validation and `backend/app/runner/core.py` for execution behavior.
- Persistence: add state transitions/events through `backend/app/storage.py` public methods.
- Tests: add runner tests under `backend/tests/unit/runner/` and API tests under `backend/tests/unit/api/`.

**New Persistent Task Data:**
- Primary code: update table creation and read/write methods in `backend/app/storage.py`.
- DTOs: update `backend/app/schemas.py` when data appears in API responses.
- Test fake: mirror the public storage behavior in `backend/tests/fakes.py`.
- Tests: add focused coverage under `backend/tests/unit/storage/`; use `backend/tests/integration/` when PostgreSQL semantics matter.

**New Agent Tool:**
- Primary code: implement the tool in `backend/app/tools/<name>.py` or `backend/app/execution/<domain>.py`.
- Registration: add it to `get_platform_tools(...)` in `backend/app/tools/registry.py`.
- Context/prompt: add a system prompt helper in the tool module when the agent needs usage instructions.
- Tests: add unit tests under `backend/tests/unit/tools/`.

**New Uploaded Resource Capability:**
- Primary code: extend `LocalResourceExecutionAdapter.execute(...)` and helpers in `backend/app/execution/resources.py`.
- Registration: expose a LangChain tool from `create_resource_tools(...)`.
- Storage hooks: use upload/resource helpers from `backend/app/storage.py` and resource contracts in `backend/app/contracts/__init__.py`.
- Tests: add cases under `backend/tests/unit/tools/test_resource_execution.py`.

**New Model Provider or Model ID:**
- Registry: add safe app-level metadata in `MODEL_REGISTRY` in `backend/app/config.py`.
- Availability: update checks in `backend/app/models/registry.py` if provider requirements differ.
- Construction: update `backend/app/models/provider.py` for concrete LangChain model creation.
- API shape: keep `backend/app/schemas.py` `ModelOption` browser-safe; do not expose provider secrets.
- Tests: add/extend `backend/tests/unit/models/`.

**New Project Skill:**
- Implementation: add `backend/skills/<skill-directory>/SKILL.md`.
- Frontmatter: include `name` and `description`; the loader only parses simple key/value YAML frontmatter.
- API exposure: no route change is needed when the skill lives under `backend/skills/`.
- Tests: update `backend/tests/unit/skills/test_builtin_skill_content.py` when built-in project skill content expectations change.

**New Long-Term Memory Feature:**
- Primary code: `backend/app/memory.py`.
- Canonical storage: add Postgres storage behavior to `backend/app/storage.py` before changing index-only behavior.
- Admin path: extend `backend/app/memory_admin.py` for operator commands.
- Tests: use `backend/tests/unit/runner/test_memory.py` for service behavior and `backend/tests/integration/test_postgres_memory_storage.py` for storage/index integration.

**New Streaming Event Type:**
- Adapter: emit normalized event dictionaries from `backend/app/streaming/v2_adapter.py`.
- Conversion: map the event in `backend/app/streaming/event_converter.py`.
- SSE: keep `backend/app/api/streaming.py` streaming full `EventRecord` JSON records.
- Tests: add cases under `backend/tests/unit/streaming/`.

**New Security or Permission Rule:**
- Secret scanning/redaction: update `backend/app/security/scanner.py`.
- Workspace/command permissions: update `backend/app/permissions.py`.
- Request access/auth/body limits: update middleware in `backend/app/main.py`.
- Tests: add cases under `backend/tests/unit/security/` and route tests under `backend/tests/unit/api/` when HTTP behavior changes.

**New Configuration:**
- Settings field: add to `Settings` and `load_settings()` in `backend/app/config.py`.
- Example env: update `backend/.env.example`; never read or quote `backend/.env`.
- Documentation: update `backend/README.md` if operators need to set it.
- Tests: add config-dependent unit tests near the affected module.

**New CLI/Operator Utility:**
- Implementation: add a module under `backend/app/` with `main(argv: list[str] | None = None) -> int`, following `backend/app/memory_admin.py`.
- Tests: add unit tests under `backend/tests/unit/` matching the target domain.

## Special Directories

**`backend/.venv/`:**
- Purpose: Local virtual environment.
- Generated: Yes
- Committed: No

**`backend/.mypy_cache/`, `backend/.pytest_cache/`, `backend/.ruff_cache/`:**
- Purpose: Tool caches for mypy, pytest, and Ruff.
- Generated: Yes
- Committed: No

**`backend/storage/`:**
- Purpose: Local runtime task workspaces when `MYAGENT_TASK_ROOT` uses its default.
- Generated: Yes
- Committed: No for runtime session contents.

**`backend/tmp/`:**
- Purpose: Local temporary scratch data.
- Generated: Yes
- Committed: No for runtime contents.

**`backend/.planning/codebase/`:**
- Purpose: Backend-scoped architecture/structure maps consumed by GSD planning and execution flows.
- Generated: Yes
- Committed: Project-dependent; these are the requested mapping artifacts.

**`backend/skills/`:**
- Purpose: Project skill source files mounted read-only for agents and listed through `/api/skills`.
- Generated: No
- Committed: Yes

**`backend/tests/`:**
- Purpose: Source-controlled pytest suite.
- Generated: No
- Committed: Yes

---

*Structure analysis: 2026-05-22*
