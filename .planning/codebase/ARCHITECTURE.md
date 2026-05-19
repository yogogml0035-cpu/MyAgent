<!-- refreshed: 2026-05-19 -->
# Architecture

**Analysis Date:** 2026-05-19

## System Overview

```text
+-------------------------------------------------------------+
|                    Browser / Next.js UI                     |
|  `frontend/app/page.tsx` -> `frontend/components/chat/`      |
|  `frontend/hooks/use-task-workspace.ts`                      |
+-----------------------------+-------------------------------+
                              |
                              | REST JSON, multipart upload, SSE
                              v
+-------------------------------------------------------------+
|                    FastAPI Application Shell                |
|  `backend/app/main.py`                                      |
|  auth, CORS, request size limits, route registration         |
+-------------------+----------------------+------------------+
                    |                      |
                    v                      v
+-------------------------------+  +---------------------------+
| Task API / File / Artifact    |  | SSE Stream API            |
| `backend/app/api/tasks.py`    |  | `backend/app/api/streaming.py` |
| `backend/app/api/files.py`    |  | polls append-only events  |
| `backend/app/api/artifacts.py`|  +---------------------------+
+-------------------+----------------------+
                    |
                    v
+-------------------------------------------------------------+
|                 Runtime Orchestration Layer                 |
| `backend/app/runner/core.py`                                |
| context -> memory -> resources -> DeepAgents graph stream   |
+-------------------+----------------------+------------------+
                    |                      |
                    v                      v
+-------------------------------+  +---------------------------+
| DeepAgents Agent Factory      |  | Storage Authority         |
| `backend/app/agent/factory.py`|  | `backend/app/storage.py`  |
| tools, skills, backend store  |  | Postgres state/events     |
+-------------------+-----------+  | local uploads/artifacts   |
                    |              +-------------+-------------+
                    v                            |
+------------------------------------------------v------------+
| External / Local Services and Files                         |
| Postgres, Qdrant, DashScope embeddings, model providers,    |
| local SearXNG, `backend/storage/sessions/<task_id>/`         |
+-------------------------------------------------------------+
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| FastAPI app factory | Load settings, create storage, memory service, context builder, agent store, and in-process runner; install middleware and routes. | `backend/app/main.py` |
| Request access and size boundary | Enforce loopback/token auth plus JSON and multipart request body limits before route handlers run. | `backend/app/main.py` |
| Task lifecycle API | Create/list/read/rename/delete tasks, start runs, send messages, cancel active runs, and expose event polling. | `backend/app/api/tasks.py` |
| Upload API | Accept multipart uploads only for existing non-running tasks and map storage exceptions to stable HTTP status codes. | `backend/app/api/files.py` |
| Artifact API | Serve latest or run-scoped artifacts through first-class `/api/tasks/.../artifacts/...` routes. | `backend/app/api/artifacts.py` |
| SSE API | Poll ordered persisted events until the active runner finishes, drain trailing events, and emit a terminal `done`. | `backend/app/api/streaming.py` |
| Storage authority | Own Postgres tables for tasks, runs, messages, events, summaries, tool cache, memory rows, and agent store items; own local upload/artifact bytes. | `backend/app/storage.py` |
| Runner | Build the agent, inject context/memory/resource manifest, stream DeepAgents events, persist converted records, update terminal task state, and manage cancellation. | `backend/app/runner/core.py` |
| Agent factory | Wrap `deepagents.create_deep_agent()` with model creation, task-scoped filesystem backend, state backend, optional store backend, tools, skills, and subagents. | `backend/app/agent/factory.py` |
| Middleware assembly | Build only additional DeepAgents middleware; default middleware belongs to `create_deep_agent()`. | `backend/app/agent/middleware.py` |
| Streaming adapter | Normalize LangGraph v2 stream chunks into platform event dicts and extract authoritative final answers from root graph state. | `backend/app/streaming/v2_adapter.py` |
| Event converter | Convert normalized stream events into persisted `EventRecord` payloads with display-safe `live` metadata. | `backend/app/streaming/event_converter.py` |
| Resource execution | Provide task-scoped upload inspection and read tools behind a local provision/execute adapter. | `backend/app/execution/resources.py` |
| Tool registry | Register resource tools and SearXNG search for a specific task. | `backend/app/tools/registry.py` |
| Model registry/provider | Validate provider-prefixed model IDs and instantiate LangChain chat models with configured provider keys. | `backend/app/models/registry.py`, `backend/app/models/provider.py` |
| Conversation context | Build deterministic same-task context from stored messages, summaries, and fresh tool cache. | `backend/app/conversation_context.py` |
| Long-term memory | Use Postgres as canonical memory storage and Qdrant plus DashScope embeddings as semantic index. | `backend/app/memory.py`, `backend/app/agent_store.py` |
| Frontend API adapter | Resolve backend origin, attach browser-safe access token, normalize JSON responses, create EventSource, fetch artifacts. | `frontend/lib/task-api.ts` |
| Frontend state mapper | Convert backend `snake_case` API records into camelCase UI state, normalize logs and artifacts, reject untrusted artifact URLs. | `frontend/app/task-state.ts` |
| Workspace state hook | Coordinate model availability, task creation, upload, message send, SSE retry, polling fallback, cancel, history, and artifacts. | `frontend/hooks/use-task-workspace.ts` |
| Workspace UI shell | Compose sidebar, conversation timeline, progress logs, artifact actions, upload preview, composer, and model picker. | `frontend/components/chat/TaskWorkspace.tsx` |
| Progress-log projection | Turn append-only backend events into user-facing run groups and expandable diagnostics. | `frontend/app/workspace-view.ts`, `frontend/components/chat/TaskConversation.tsx` |

## Pattern Overview

**Overall:** Local-first client/server task runtime with an append-only event log, in-process DeepAgents orchestration, Postgres state authority, and Next.js state projection.

**Key Characteristics:**
- Backend API state uses `snake_case`; frontend boundary code in `frontend/app/task-state.ts` converts it to camelCase.
- Postgres is authoritative for task lifecycle state, run rows, messages, and ordered events; local disk stores upload and artifact bytes under `backend/storage/sessions/<task_id>/`.
- The runner is in-process and single-worker; `backend/app/config.py` rejects multi-worker runtime variables.
- Streaming is not the source of truth; SSE is a projection over persisted `EventRecord` rows in `backend/app/storage.py`.
- Intermediate model chunks remain progress-log diagnostics; final user-visible assistant replies come from stored `ChatMessage` rows after `backend/app/streaming/v2_adapter.py` extracts the root graph final answer.
- Runtime skills use DeepAgents `SKILL.md` directories under `backend/skills/`; project-level `.codex/skills/` and `.agents/skills/` directories are not detected.

## Layers

**Backend Application Shell:**
- Purpose: Construct the FastAPI app and hold process-wide dependencies.
- Location: `backend/app/main.py`
- Contains: `create_app()`, lifespan startup checks, `app.state.settings`, `app.state.storage`, `app.state.runner`, `app.state.title_generator`, auth middleware, request-size middleware, CORS, `/health`.
- Depends on: `backend/app/config.py`, `backend/app/storage.py`, `backend/app/memory.py`, `backend/app/runner/core.py`, API routers under `backend/app/api/`.
- Used by: `uvicorn app.main:app`, tests under `backend/tests/unit/api/`, local scripts under `scripts/`.

**Backend API Routes:**
- Purpose: Public HTTP contract for the browser and tests.
- Location: `backend/app/api/`
- Contains: task lifecycle in `backend/app/api/tasks.py`, uploads in `backend/app/api/files.py`, artifacts in `backend/app/api/artifacts.py`, SSE in `backend/app/api/streaming.py`, models in `backend/app/api/models.py`.
- Depends on: `request.app.state` dependencies from `backend/app/main.py`, schemas in `backend/app/schemas.py`, storage/runner contracts.
- Used by: `frontend/lib/task-api.ts`, Playwright specs in `frontend/e2e-playwright/`, backend API tests in `backend/tests/unit/api/`.

**Storage Authority:**
- Purpose: Persist lifecycle state and append-only events; map stable artifacts/uploads to disk.
- Location: `backend/app/storage.py`
- Contains: `PostgresTaskStorage`, upload validation, artifact resolution, task summaries, event seq cursor generation, context summaries, tool-result cache, canonical long-term memory rows, LangGraph agent-store backing methods.
- Depends on: Postgres via `psycopg`, local task root from `Settings.task_root`, schemas in `backend/app/schemas.py`, resource/artifact helpers in `backend/app/contracts/__init__.py`.
- Used by: API routes, `TaskRunner`, `ConversationContextBuilder`, `AgentMemoryService`, `PostgresAgentStore`, tests and fakes.

**Runtime Orchestration:**
- Purpose: Execute a single task run from user message to terminal event.
- Location: `backend/app/runner/core.py`
- Contains: `TaskRunner.start()`, `TaskRunner.start_background()`, `TaskRunner.cancel()`, active-run tracking, memory recall/write scheduling, final-answer event emission.
- Depends on: `backend/app/agent/factory.py`, `backend/app/tools/registry.py`, `backend/app/execution/resources.py`, `backend/app/streaming/v2_adapter.py`, `backend/app/streaming/event_converter.py`, storage protocol.
- Used by: `backend/app/api/tasks.py`, `backend/app/api/files.py`, `backend/app/api/streaming.py`.

**Agent Construction:**
- Purpose: Build a DeepAgents graph from model, tools, runtime skills, filesystem backend, scratch state, and optional LangGraph store.
- Location: `backend/app/agent/`
- Contains: `build_agent()` and `build_agent_with_middleware()` in `backend/app/agent/factory.py`, extra middleware helpers in `backend/app/agent/middleware.py`.
- Depends on: `deepagents`, LangGraph, model provider in `backend/app/models/provider.py`, `Settings`.
- Used by: `TaskRunner.start()` in `backend/app/runner/core.py`.

**Streaming Normalization:**
- Purpose: Convert DeepAgents/LangGraph v2 stream chunks into durable platform records and frontend-friendly metadata.
- Location: `backend/app/streaming/`
- Contains: v2 adapter in `backend/app/streaming/v2_adapter.py`, converter in `backend/app/streaming/event_converter.py`, SSE formatting in `backend/app/streaming/sse.py`.
- Depends on: LangChain message classes and `EventRecord`.
- Used by: `TaskRunner.start()` and `backend/app/api/streaming.py`.

**Task Resource Tools:**
- Purpose: Expose uploaded documents to the agent without injecting uploaded bodies into prompt context.
- Location: `backend/app/execution/resources.py`, `backend/app/tools/registry.py`
- Contains: `LocalResourceExecutionAdapter`, `create_resource_tools()`, resource manifest building, document/table/text readers, SearXNG registration.
- Depends on: `backend/app/storage.py` helper functions, local filesystem, optional Word/Excel parsers.
- Used by: `TaskRunner.start()` through `get_platform_tools()`.

**Model And Memory Services:**
- Purpose: Resolve provider-backed chat models and long-term memory context.
- Location: `backend/app/models/`, `backend/app/memory.py`, `backend/app/agent_store.py`
- Contains: model registry, model availability flags, DashScope embedding client, Qdrant memory index, LangGraph `BaseStore` adapter.
- Depends on: environment-backed `Settings`, external model/embedding/vector services, storage.
- Used by: `/api/models`, task API validation, `build_agent()`, `TaskRunner`.

**Frontend API And State Boundary:**
- Purpose: Keep browser code isolated from backend wire formats and security-sensitive URL construction.
- Location: `frontend/lib/task-api.ts`, `frontend/app/task-state.ts`
- Contains: `requestTaskJson()`, REST helpers, SSE `EventSource` construction, artifact fetch, normalizers for tasks/logs/messages/artifacts/models.
- Depends on: `NEXT_PUBLIC_MYAGENT_API_BASE_URL`, `NEXT_PUBLIC_MYAGENT_TOKEN`, browser `fetch`/`EventSource`.
- Used by: `frontend/hooks/use-task-workspace.ts`.

**Frontend Workspace State:**
- Purpose: Coordinate user workflows and active task state.
- Location: `frontend/hooks/use-task-workspace.ts`
- Contains: selected model/file state, task summaries, active run state, SSE retry, polling recovery, upload/send/cancel/history/artifact handlers.
- Depends on: `frontend/lib/task-api.ts`, `frontend/app/task-state.ts`, `frontend/app/workspace-view.ts`, `frontend/app/model-ui.ts`, `frontend/app/file-upload.ts`.
- Used by: `frontend/components/chat/TaskWorkspace.tsx`.

**Frontend Presentation:**
- Purpose: Render the first-screen chat workspace and progress diagnostics.
- Location: `frontend/app/page.tsx`, `frontend/components/chat/`, `frontend/app/workspace-view.ts`, `frontend/app/globals.css`
- Contains: app-router page, sidebar, conversation, composer, progress-log rows, artifact actions, upload preview, model picker.
- Depends on: state hook return shape and design tokens in `frontend/app/globals.css`; visual work must read `DESIGN.md`.
- Used by: browser E2E specs in `frontend/e2e-playwright/` and frontend unit tests.

**Verification Layer:**
- Purpose: Guard contracts at unit, integration, and browser acceptance levels.
- Location: `backend/tests/`, `frontend/tests/`, `frontend/e2e-playwright/`
- Contains: backend unit/integration/e2e tests, frontend Node tests, Playwright specs and ignored screenshot evidence dirs.
- Depends on: repo scripts in `backend/pyproject.toml`, `frontend/package.json`, and local services for browser E2E.
- Used by: future behavior changes and CI.

## Data Flow

### Primary Request Path

1. The Next.js app router renders `TaskWorkspace` from `frontend/app/page.tsx:3` and `frontend/components/chat/TaskWorkspace.tsx:8`.
2. `useTaskWorkspace()` maintains task state, model options, files, logs, runs, and artifacts in `frontend/hooks/use-task-workspace.ts:164`.
3. On submit, `handleSubmit()` ensures a task exists, uploads selected files, posts the user message, refreshes state, and refreshes history in `frontend/hooks/use-task-workspace.ts:412`.
4. Browser API calls go through `frontend/lib/task-api.ts:27`, `frontend/lib/task-api.ts:76`, `frontend/lib/task-api.ts:135`, and `frontend/lib/task-api.ts:149`.
5. FastAPI routes are registered from `create_app()` in `backend/app/main.py:37` and `backend/app/main.py:91`.
6. `create_task()` validates the model, creates an idle task, starts a run when a message is present, and invokes `runner.start_background()` in `backend/app/api/tasks.py:81`.
7. `send_message()` validates that no run is active, calls `storage.start_run()`, sets best-effort auto title, and starts the background runner in `backend/app/api/tasks.py:146`.
8. `PostgresTaskStorage.start_run()` moves the task to `running`, creates a run row, and stores the user `ChatMessage` in `backend/app/storage.py:591`.
9. `TaskRunner.start_background()` creates an `asyncio.Task` and persists each converted stream event through `storage.append_event()` in `backend/app/runner/core.py:209`.
10. `TaskRunner.start()` builds task-scoped tools, builds a DeepAgents graph, adds context/memory/resource messages, streams the graph, converts events, and tracks root graph state in `backend/app/runner/core.py:102`.
11. `stream_agent()` normalizes LangGraph v2 stream chunks in `backend/app/streaming/v2_adapter.py:46`; `convert_stream_event()` creates `EventRecord` payloads in `backend/app/streaming/event_converter.py:36`.
12. On success, `extract_final_answer()` reads the root graph final AI message in `backend/app/streaming/v2_adapter.py:25`, and the runner stores the assistant `ChatMessage` before emitting `final_answer` in `backend/app/runner/core.py:243`.
13. `PostgresTaskStorage.update_task_if_status_and_append_event()` atomically applies terminal status and terminal event records in `backend/app/storage.py:709`.
14. The frontend receives a `final_answer` SSE event, calls `refreshTaskSummary()`, and displays the stored assistant message from the refreshed task state in `frontend/hooks/use-task-workspace.ts:334`.

### Streaming Recovery Path

1. The browser opens an `EventSource` using `createTaskEventSource()` in `frontend/lib/task-api.ts:162`; access token is passed as `?token=` because EventSource cannot set custom headers.
2. `stream_task()` returns `text/event-stream` from `backend/app/api/streaming.py:77`.
3. `_event_stream()` polls `storage.read_events(task_id, after_id=last_event_id)` every 0.5 seconds in `backend/app/api/streaming.py:44`.
4. `PostgresTaskStorage.read_events()` returns all events when no cursor is supplied, returns events with greater `seq` for known cursors, and replays the full ordered stream for unknown cursors in `backend/app/storage.py:975`.
5. The hook normalizes incoming events and merges unseen event IDs with `mergeExecutionLogs()` in `frontend/hooks/use-task-workspace.ts:334` and `frontend/app/task-state.ts:1305`.
6. If SSE errors, the hook closes the connection, refreshes summary/events over REST, and retries with exponential backoff up to `MAX_SSE_RETRIES` in `frontend/hooks/use-task-workspace.ts:66` and `frontend/hooks/use-task-workspace.ts:375`.

### Upload And Resource Tool Path

1. `ChatComposer` captures file selections from the hidden file input in `frontend/components/chat/ChatComposer.tsx:96`.
2. `handleFileSelection()` filters allowed upload extensions in `frontend/hooks/use-task-workspace.ts:486`.
3. `uploadTaskFiles()` sends multipart `files` to `/api/tasks/{id}/files` in `frontend/lib/task-api.ts:135`.
4. `upload_files()` rejects missing/running tasks and forwards upload limits from settings in `backend/app/api/files.py:21`.
5. `PostgresTaskStorage.save_uploads()` stages files, validates duplicates/limits/JSON, moves files into `uploads/`, and appends `file_uploaded` events with resource refs in `backend/app/storage.py:737`.
6. `get_platform_tools()` attaches resource tools for a specific `task_id` in `backend/app/tools/registry.py:12`.
7. `LocalResourceExecutionAdapter.provision()` resolves only `workspace_root / task_id / uploads`, and `create_resource_tools()` exposes list/inspect/read text/read table tools in `backend/app/execution/resources.py:114` and `backend/app/execution/resources.py:155`.

### Artifact Path

1. Completed runs may write run-scoped artifacts via `write_run_text()` or `write_run_json()` in `backend/app/storage.py:1365`.
2. Artifact HTTP routes serve latest or run-scoped files from `backend/app/api/artifacts.py:32` and `backend/app/api/artifacts.py:39`.
3. The frontend validates artifact URLs and rejects external origins, query/hash redirects, wrong task IDs, and wrong names in `frontend/app/task-state.ts:1188`.
4. `handleDownloadArtifact()` downloads blobs through `fetchArtifactBlob()` in `frontend/hooks/use-task-workspace.ts:628`.
5. `handleOpenArtifact()` opens HTML artifacts inside an `about:blank` popup with a sandboxed iframe generated by `buildSandboxedArtifactPreviewDocument()` in `frontend/hooks/use-task-workspace.ts:103` and `frontend/hooks/use-task-workspace.ts:657`.

**State Management:**
- Backend state is persisted in Postgres through `PostgresTaskStorage`; local in-process state is limited to active `asyncio.Task` handles in `TaskRunner._active_runs`.
- Frontend state is React hook state inside `useTaskWorkspace()` and is derived from normalized backend task/event records.
- Progress-log UI state is projected from append-only event records by `buildRunActivityGroups()` and `buildLiveLogItems()` in `frontend/app/workspace-view.ts`.

## Key Abstractions

**TaskState / TaskRunRecord / ChatMessage / EventRecord:**
- Purpose: Public task lifecycle schema and frontend normalization boundary.
- Examples: `backend/app/schemas.py`, `frontend/app/task-state.ts`
- Pattern: Backend Pydantic models with snake_case fields; frontend TypeScript types with camelCase fields and defensive normalizers.

**PostgresTaskStorage:**
- Purpose: Single authority for task lifecycle, run history, messages, append-only events, resource uploads, artifacts, cache, memory, and agent store.
- Examples: `backend/app/storage.py`, `backend/tests/unit/storage/test_storage.py`, `backend/tests/fakes.py`
- Pattern: Lock-protected repository object; event `seq` generated by incrementing `tasks.latest_event_seq` and inserting into `events` in the same transaction.

**TaskRunner:**
- Purpose: Runtime orchestrator for one active task run.
- Examples: `backend/app/runner/core.py`, `backend/tests/unit/runner/test_core.py`
- Pattern: In-process active-run registry plus background `asyncio.Task`; terminal state changes must go through storage compare-and-set methods.

**DeepAgents Graph:**
- Purpose: Model/tool/skill execution engine.
- Examples: `backend/app/agent/factory.py`, `backend/app/agent/middleware.py`, `backend/skills/web_research/SKILL.md`, `backend/skills/code_review/SKILL.md`
- Pattern: Build via `create_deep_agent()`; pass `skills=` and `subagents=` as DeepAgents arguments, not duplicated default middleware.

**Runtime Skills:**
- Purpose: Model-facing runtime instructions loaded from `SKILL.md` directories.
- Examples: `backend/skills/web_research/SKILL.md`, `backend/skills/code_review/SKILL.md`, `backend/app/skills/loader.py`
- Pattern: `SKILL.md` with YAML frontmatter `name` and `description`; discovered by `discover_skills()` from `settings.skills_dirs`.

**Resource Tools:**
- Purpose: Let the agent inspect/read uploaded files by explicit tool calls.
- Examples: `backend/app/execution/resources.py`, `backend/app/tools/registry.py`, `backend/tests/unit/tools/test_resource_execution.py`
- Pattern: Thin LangChain `@tool` functions returning JSON from `ExecutionResult`; no direct arbitrary filesystem reads.

**Stream Adapter And Event Converter:**
- Purpose: Preserve backend event order and normalize provider/tool/status streams for UI diagnostics.
- Examples: `backend/app/streaming/v2_adapter.py`, `backend/app/streaming/event_converter.py`, `frontend/app/workspace-view.ts`
- Pattern: Raw LangGraph chunks -> normalized event dict -> durable `EventRecord` -> frontend `ExecutionLog` -> progress rows.

**ConversationContextBuilder:**
- Purpose: Add deterministic same-task history context without depending on model memory.
- Examples: `backend/app/conversation_context.py`, `backend/tests/unit/runner/test_conversation_context.py`
- Pattern: Pull messages, summaries, and fresh tool cache from storage; redact sensitive content before prompt insertion.

**AgentMemoryService:**
- Purpose: Recall and write sanitized long-term memory around successful runs.
- Examples: `backend/app/memory.py`, `backend/app/agent_store.py`, `backend/tests/unit/runner/test_memory.py`
- Pattern: Postgres canonical rows plus Qdrant semantic index; recall/write failure must not change a successful run to failed.

**Frontend Workspace Projection:**
- Purpose: Convert backend state into a single usable first-screen workspace.
- Examples: `frontend/hooks/use-task-workspace.ts`, `frontend/app/workspace-view.ts`, `frontend/components/chat/TaskWorkspace.tsx`
- Pattern: Hook owns effects and handlers; pure functions in `frontend/app/` own data projection; components render props.

## Entry Points

**Backend ASGI App:**
- Location: `backend/app/main.py`
- Triggers: `uvicorn app.main:app` or tests importing `create_app()`.
- Responsibilities: Load settings, enforce single-process runtime, initialize storage/memory, register API routes and middleware.

**Task REST API:**
- Location: `backend/app/api/tasks.py`
- Triggers: Frontend calls from `frontend/lib/task-api.ts`.
- Responsibilities: Lifecycle transitions, run scheduling, model validation, cancellation, event polling.

**File Upload API:**
- Location: `backend/app/api/files.py`
- Triggers: Multipart upload from `frontend/lib/task-api.ts`.
- Responsibilities: Upload validation, task-state guard, stable HTTP error mapping.

**Artifact API:**
- Location: `backend/app/api/artifacts.py`
- Triggers: Browser download/open actions.
- Responsibilities: Latest and run-scoped artifact lookup and `FileResponse`.

**SSE API:**
- Location: `backend/app/api/streaming.py`
- Triggers: Browser `EventSource`.
- Responsibilities: Real-time projection over persisted events with terminal `done`.

**Memory Admin CLI:**
- Location: `backend/app/memory_admin.py`
- Triggers: Direct Python command invocation.
- Responsibilities: Reset or rebuild the configured Qdrant memory collection from Postgres memory rows.

**Frontend App Route:**
- Location: `frontend/app/page.tsx`
- Triggers: Next.js app-router request for `/`.
- Responsibilities: Mount the chat workspace as the first screen.

**Frontend Workspace Component:**
- Location: `frontend/components/chat/TaskWorkspace.tsx`
- Triggers: Rendered by `frontend/app/page.tsx`.
- Responsibilities: Compose history sidebar, conversation/progress timeline, and composer.

**Frontend State Hook:**
- Location: `frontend/hooks/use-task-workspace.ts`
- Triggers: React client component render/effects.
- Responsibilities: Fetch initial models/history, run user workflows, maintain SSE connection, recover with polling.

**Local Development Scripts:**
- Location: `scripts/start-dev-wsl.ps1`, `scripts/dev-terminal-runner.sh`, `scripts/stop-dev-ports.sh`
- Triggers: Developer commands.
- Responsibilities: Start/stop WSL backend/frontend dev services with polling watchers and default ports.

## Architectural Constraints

- **Threading:** FastAPI runs async request handlers, but task execution uses in-process `asyncio.Task` handles in `TaskRunner._active_runs` (`backend/app/runner/core.py`). Memory recall/write calls use `asyncio.to_thread()` to avoid blocking the event loop.
- **Single process:** `enforce_single_process_runtime()` rejects `WEB_CONCURRENCY`, `UVICORN_WORKERS`, or `GUNICORN_WORKERS` above 1 in `backend/app/config.py`.
- **Global state:** `backend/app/main.py` stores `settings`, `storage`, `runner`, and `title_generator` on `app.state`. `TaskRunner` stores active run tasks and memory write tasks in process-local sets.
- **Storage concurrency:** `PostgresTaskStorage` uses a re-entrant process lock plus Postgres transactions. Public state transitions should use compare-and-set methods such as `start_run()` and `update_task_if_status_and_append_event()`.
- **Event ordering:** Event order must use `EventRecord.seq`; `PostgresTaskStorage._append_event_with_cursor()` increments `tasks.latest_event_seq` and inserts the event in one transaction.
- **Filesystem scope:** Upload/resource/artifact code must stay inside `settings.workspace_root / task_id`; agent filesystem backend root is the task workspace passed from `TaskRunner.start()` to `build_agent()`.
- **Secrets:** `.env` and `.env.*` files are environment configuration only. `backend/.env` and `frontend/.env.local` are present but their contents must not be read or copied into docs/tests.
- **Frontend token boundary:** Provider keys remain backend-only. Browser config may only use public backend URL/token variables through `NEXT_PUBLIC_*`.
- **SSE auth:** EventSource token travels in the query string, and `authorize_task_request()` accepts query param `token` in `backend/app/main.py`.
- **Circular imports:** No required circular import chain is detected in the current architecture. Keep shared contracts in `backend/app/schemas.py` and `backend/app/contracts/__init__.py` instead of importing API/runner modules from storage or tools.
- **Project skills:** Repo-local project skill directories `.codex/skills/` and `.agents/skills/` are not detected. Runtime DeepAgents skills live under `backend/skills/`.
- **Browser acceptance:** Behavior changes touching frontend/user paths require live browser E2E specs and screenshot evidence under `frontend/e2e-playwright/e2e-YYYYMMDDHHMMSS/`.

## Anti-Patterns

### Duplicate DeepAgents Default Middleware

**What happens:** Adding `TodoListMiddleware`, `FilesystemMiddleware`, `SummarizationMiddleware`, or `PatchToolCallsMiddleware` manually in `backend/app/agent/middleware.py`.
**Why it's wrong:** `create_deep_agent()` already injects those defaults, so duplicate middleware causes assertion errors and unstable agent construction.
**Do this instead:** Add only platform-specific extras through `build_middleware()` in `backend/app/agent/middleware.py`, and pass runtime skills/subagents through `create_deep_agent(skills=..., subagents=...)` in `backend/app/agent/factory.py`.

### Bypassing Storage State Transitions

**What happens:** Directly changing task status, active run, messages, or events from API/runner code without using storage lifecycle methods.
**Why it's wrong:** The runner and API rely on compare-and-set semantics, active run IDs, and continuous event seq values.
**Do this instead:** Use `start_run()` before scheduling a run and `update_task_if_status_and_append_event()` for terminal changes in `backend/app/storage.py`.

### Treating Stream Deltas As Final Answer

**What happens:** Rendering `assistant_answer_delta` as an assistant reply card or using the last delta as the answer.
**Why it's wrong:** Deltas are intermediate process tokens; the last stream item may be a tool/status/subgraph event rather than a final answer.
**Do this instead:** Extract final answer with `extract_final_answer()` in `backend/app/streaming/v2_adapter.py`, store it as a `ChatMessage` in `backend/app/runner/core.py`, and keep deltas inside progress-log diagnostics in `frontend/app/workspace-view.ts`.

### Reading Arbitrary Host Files From Resource Tools

**What happens:** Letting a tool accept arbitrary local paths or global session paths.
**Why it's wrong:** It crosses task boundaries and can expose other sessions or host secrets.
**Do this instead:** Resolve resources only from `workspace_root / task_id / uploads` through `LocalResourceExecutionAdapter` in `backend/app/execution/resources.py`.

### Trusting Artifact URLs From Backend Payloads Blindly

**What happens:** Fetching arbitrary `artifact.url` values or top-level navigating to same-origin `blob:` URLs.
**Why it's wrong:** It can leak `X-MyAgent-Token` to an unexpected origin/path or grant generated HTML too much execution authority.
**Do this instead:** Build and validate artifact requests through `buildArtifactRequest()` in `frontend/app/task-state.ts` and preview HTML inside the sandboxed iframe shell in `frontend/hooks/use-task-workspace.ts`.

### Sorting Progress Logs Only By Timestamp

**What happens:** UI code orders live logs by wall-clock time only.
**Why it's wrong:** Multiple stream records can share the displayed second and appear out of model/tool/result order.
**Do this instead:** Use backend `EventRecord.seq` as primary order through `byLogOrder()` in `frontend/app/workspace-view.ts`.

## Error Handling

**Strategy:** Convert domain failures at the boundary closest to the caller while preserving durable task terminal events.

**Patterns:**
- API routes raise `HTTPException` with stable status codes for task missing/conflict/validation/upload conditions in `backend/app/api/tasks.py` and `backend/app/api/files.py`.
- Request validation errors are translated to a generic Chinese message in `backend/app/main.py`.
- SSE stream failures yield a JSON error payload and `done` marker in `backend/app/api/streaming.py`.
- Runner failures/timeouts/cancellations update task state through terminal events in `backend/app/runner/core.py`.
- Resource tool failures return `{ok:false,error:{code,message,retryable}}` JSON in `backend/app/execution/resources.py`.
- Frontend REST failures are normalized by `formatTaskApiFailure()` and `formatHttpErrorMessage()` in `frontend/lib/task-api.ts` and `frontend/app/task-state.ts`.

## Cross-Cutting Concerns

**Logging:** Backend modules use `logging.getLogger(__name__)`, especially `backend/app/main.py`, `backend/app/runner/core.py`, `backend/app/api/tasks.py`, `backend/app/api/streaming.py`, `backend/app/conversation_context.py`, and `backend/app/memory.py`.

**Validation:** Backend validates models via `backend/app/models/registry.py`, API bodies via Pydantic schemas in `backend/app/schemas.py`, uploads via `backend/app/storage.py`, request sizes/auth in `backend/app/main.py`, and artifact URL trust in `frontend/app/task-state.ts`.

**Authentication:** `backend/app/main.py` allows loopback callers by default; non-loopback access requires `MYAGENT_ACCESS_TOKEN`. Frontend sends `X-MyAgent-Token` for fetch calls and `?token=` for SSE from `frontend/lib/task-api.ts`.

**Configuration:** Backend configuration is centralized in `backend/app/config.py` and loaded from backend environment plus `backend/.env`; frontend public configuration is read in `frontend/lib/task-api.ts` and `frontend/next.config.mjs`.

**Knowledge And Planning:** Long-term repository guidance lives in `AGENTS.md`; domain/platform knowledge lives in `asset/deepagents_platform_knowledge_pack.md`, `asset/bid_analysis_workflow_knowledge_pack.md`, and `asset/tender_workflow_breakdown.md`; generated codebase maps live in `.planning/codebase/`.

---

*Architecture analysis: 2026-05-19*
