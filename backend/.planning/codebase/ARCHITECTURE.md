# Architecture

**Analysis Date:** 2026-05-19

## Pattern Overview

**Overall:** Local-first FastAPI service with in-process DeepAgents execution, Postgres state authority, append-only event streaming, and local task workspaces.

**Key Characteristics:**
- API routes expose task lifecycle, uploads, artifacts, SSE, and model availability.
- `PostgresTaskStorage` owns durable task state while upload/artifact bytes stay on local disk.
- `TaskRunner` owns active async runs in memory; this is why single-process runtime is mandatory.
- Streaming is a projection over persisted events; it is not the source of truth.
- DeepAgents receives task-scoped filesystem access through a virtual `FilesystemBackend`.

## Layers

**Application Shell:**
- Purpose: Build the FastAPI app and process-wide dependencies.
- Contains: `create_app()`, lifespan startup, auth/limit middleware, CORS, route registration, and `/health`.
- Location: `backend/app/main.py`
- Depends on: Settings, storage, memory, runner, routers.
- Used by: Uvicorn and backend API tests.

**API Routes:**
- Purpose: Public HTTP contract for frontend and tests.
- Contains: `backend/app/api/tasks.py`, `backend/app/api/files.py`, `backend/app/api/artifacts.py`, `backend/app/api/streaming.py`, and `backend/app/api/models.py`.
- Depends on: `request.app.state`, Pydantic schemas, storage, runner, model registry.
- Used by: `frontend/lib/task-api.ts` and Playwright specs.

**Storage Authority:**
- Purpose: Persist lifecycle state, event cursors, task messages, run metadata, caches, memory records, agent store items, uploads, and artifacts.
- Contains: `PostgresTaskStorage` in `backend/app/storage.py`.
- Depends on: Postgres, local filesystem, schemas, contract helpers.
- Used by: API routes, runner, memory, agent store, tools, and tests.

**Runtime Orchestration:**
- Purpose: Execute one task run from user message to terminal state.
- Contains: `TaskRunner` in `backend/app/runner/core.py`.
- Depends on: agent factory, platform tools, conversation context, memory recall/write, stream adapter, event converter, storage.
- Used by: `create_task`, `send_message`, `cancel_task`, and SSE status checks.

**Agent Construction:**
- Purpose: Wrap `deepagents.create_deep_agent()` with platform defaults.
- Contains: `build_agent()` and backend routing in `backend/app/agent/factory.py`.
- Depends on: model provider, tools, skills, optional subagents, task workspace, optional LangGraph store.
- Used by: `TaskRunner.start()`.

**Streaming Normalization:**
- Purpose: Convert LangGraph/DeepAgents stream chunks into stable platform records.
- Contains: `backend/app/streaming/v2_adapter.py`, `backend/app/streaming/event_converter.py`, and `backend/app/streaming/sse.py`.
- Depends on: LangChain message chunks and backend event schemas.
- Used by: runner event persistence and SSE response formatting.

**Resource Tool Boundary:**
- Purpose: Expose uploaded task resources to the agent without injecting full file contents into the prompt.
- Contains: `backend/app/execution/resources.py` and `backend/app/tools/registry.py`.
- Depends on: task-root filesystem, upload metadata helpers, `python-docx`, `openpyxl`, JSON/text readers.
- Used by: `TaskRunner.start()` through `get_platform_tools()`.

**Model, Memory, And Security Services:**
- Purpose: Resolve chat models, store semantic memory, and redact sensitive text.
- Contains: `backend/app/models/`, `backend/app/memory.py`, `backend/app/agent_store.py`, and `backend/app/security/scanner.py`.
- Depends on: provider env vars, DashScope-compatible embeddings, Qdrant, Postgres storage.
- Used by: `/api/models`, runner, memory admin, and tests.

## Data Flow

**Task Creation Without Message:**
1. Client calls `POST /api/tasks`.
2. `backend/app/api/tasks.py` resolves a registered model.
3. `PostgresTaskStorage.create_task()` creates a task row, local task dirs, and `task_created` event.
4. API returns `TaskState` with `idle` status.

**Task Run:**
1. Client calls `POST /api/tasks/{task_id}/messages` or creates a task with an initial message.
2. API validates model availability and calls `storage.start_run()` to write user message, run row, and `running` state.
3. API currently awaits auto-title generation through `backend/app/task_titles.py`.
4. `runner.start_background()` creates an async task with the authoritative `run_id`.
5. `TaskRunner.start()` builds task tools, conversation context, memory context, resource manifest, and DeepAgents graph.
6. `stream_agent()` yields normalized events; `convert_stream_event()` maps them to `EventRecord`.
7. Storage appends events with ordered seq values.
8. On success, runner extracts final answer, writes assistant message, appends `task_completed` and `final_answer`, and schedules memory write.
9. On failure, timeout, or cancellation, runner writes terminal state and terminal event.

**SSE Projection:**
1. Frontend opens `GET /api/tasks/{task_id}/stream`.
2. `backend/app/api/streaming.py` polls `storage.read_events()` every 0.5 seconds.
3. Unknown cursors replay the full ordered stream.
4. After the in-process runner stops, the endpoint drains remaining events and emits `done`.

**Upload And Artifact Flow:**
1. Uploads go through `POST /api/tasks/{task_id}/files`.
2. Storage validates file count, extension, duplicate names, JSON syntax, per-file bytes, and request bytes.
3. Saved uploads emit `file_uploaded` events with resource refs.
4. Agent tools list/inspect/read uploads through `LocalResourceExecutionAdapter`.
5. Run artifacts are written under `artifacts/runs/{run_id}` and served through artifact routes.

**State Management:**
- Postgres is authoritative for tasks, runs, messages, events, caches, store items, and memory rows.
- Local filesystem is authoritative for upload/artifact bytes.
- In-memory `TaskRunner._active_runs` is authoritative only for currently active process-local runs.

## Key Abstractions

**Settings:**
- Purpose: Immutable environment-backed runtime config.
- Example: `backend/app/config.py`.
- Pattern: Frozen dataclass loaded through `load_settings()`.

**TaskState/EventRecord/TaskRunRecord:**
- Purpose: Stable public API schema.
- Example: `backend/app/schemas.py`.
- Pattern: Pydantic models using backend `snake_case`.

**PostgresTaskStorage:**
- Purpose: Single storage authority and file workspace manager.
- Example: `backend/app/storage.py`.
- Pattern: Synchronous repository/service object guarded by an `RLock`.

**TaskRunner:**
- Purpose: Runtime orchestration and terminal state management.
- Example: `backend/app/runner/core.py`.
- Pattern: Async coordinator with process-local active task registry.

**CompositeBackend:**
- Purpose: DeepAgents backend routing for filesystem, scratch state, and optional memories.
- Example: `_make_backend()` in `backend/app/agent/factory.py`.
- Pattern: `FilesystemBackend` default plus `/scratch/` `StateBackend` and optional `/memories/` `StoreBackend`.

**AgentMemoryService:**
- Purpose: Recall, extract, persist, and index safe long-term memories.
- Example: `backend/app/memory.py`.
- Pattern: Service orchestrating embedding client, Qdrant index, model extraction, and storage.

## Entry Points

**ASGI App:**
- Location: `backend/app/main.py`
- Trigger: `uv run uvicorn app.main:app --reload --port 8001`
- Responsibilities: Construct dependencies, enforce middleware, register routes, run startup checks.

**Task API:**
- Location: `backend/app/api/tasks.py`
- Trigger: Browser REST calls.
- Responsibilities: task CRUD, run start, message send, cancel, events polling.

**Runner:**
- Location: `backend/app/runner/core.py`
- Trigger: `runner.start_background()`.
- Responsibilities: build agent, stream events, persist terminal state.

**Memory Admin:**
- Location: `backend/app/memory_admin.py`
- Trigger: Direct Python/admin use.
- Responsibilities: rebuild or inspect memory index from canonical Postgres rows.

## Error Handling

**Strategy:** Convert expected boundary errors to stable HTTP status codes and persist run failures as terminal task state.

**Patterns:**
- API routes raise `HTTPException` for 400/401/403/404/409/413 cases.
- Request validation is collapsed into a stable 422 message in `backend/app/main.py`.
- Runner catches timeout, cancellation, and generic failures separately in `backend/app/runner/core.py`.
- Resource tools return structured JSON errors instead of throwing into the agent loop.
- Memory recall/write failures are logged and treated as degraded behavior.

## Cross-Cutting Concerns

**Logging:**
- Python module loggers with `logging.getLogger(__name__)`.
- Runtime-visible diagnostics are `events` rows, not only process logs.

**Validation:**
- Pydantic for API schemas.
- Manual validation for model IDs, task paths, run IDs, artifact names, filenames, upload limits, and JSON upload syntax.

**Authentication:**
- Token/loopback gate in `backend/app/main.py`; no per-user sessions.

**Security:**
- Secret scanning/redaction in `backend/app/security/scanner.py`.
- Upload and artifact paths are constrained below task roots.

---

*Architecture analysis: 2026-05-19*
*Update when major runtime, storage, API, or streaming patterns change*
