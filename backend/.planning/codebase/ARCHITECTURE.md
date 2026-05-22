<!-- refreshed: 2026-05-22 -->
# Architecture

**Analysis Date:** 2026-05-22

## System Overview

```text
+--------------------------------------------------------------------+
|                         FastAPI Application                         |
|                         `backend/app/main.py`                       |
+-------------------+-------------------+----------------------------+
| Task lifecycle    | Files/artifacts    | Models/skills/streaming    |
| `backend/app/api/`| `backend/app/api/` | `backend/app/api/`          |
+---------+---------+---------+---------+-------------+--------------+
          |                   |                       |
          v                   v                       v
+--------------------------------------------------------------------+
|                     Application Services                            |
| Runner: `backend/app/runner/core.py`                                |
| Context: `backend/app/conversation_context.py`                      |
| Memory: `backend/app/memory.py`                                     |
+-------------------+-------------------+----------------------------+
          |                   |                       |
          v                   v                       v
+--------------------------------------------------------------------+
|                  Agent, Tools, Streaming, Schemas                   |
| Agent factory: `backend/app/agent/factory.py`                       |
| Tool registry: `backend/app/tools/registry.py`                      |
| Resource tools: `backend/app/execution/resources.py`                |
| Stream adapters: `backend/app/streaming/`                           |
| DTOs/contracts: `backend/app/schemas.py`, `backend/app/contracts/`  |
+-------------------+-------------------+----------------------------+
          |                   |                       |
          v                   v                       v
+--------------------------------------------------------------------+
|                    Persistence and External Services                 |
| PostgreSQL task/event store: `backend/app/storage.py`               |
| Local task files: `backend/storage/sessions/<task_id>/`             |
| DeepSeek model API, SearXNG, DashScope embeddings, Qdrant memory    |
+--------------------------------------------------------------------+
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| App factory | Creates the FastAPI app, loads settings, wires storage/memory/runner, installs routers, auth, CORS, and body limits. | `backend/app/main.py` |
| Task API | Owns task CRUD, run creation, model validation, project-skill selection, cancellation, and event reads. | `backend/app/api/tasks.py` |
| File API | Accepts task uploads only when a task is not running and delegates validation/storage to the storage layer. | `backend/app/api/files.py` |
| Artifact API | Serves latest or run-scoped artifacts from storage-resolved paths. | `backend/app/api/artifacts.py` |
| Streaming API | Polls persisted task events and emits Server-Sent Events for browser clients. | `backend/app/api/streaming.py` |
| Model API | Returns browser-safe registered model options with availability flags. | `backend/app/api/models.py` |
| Skills API | Returns browser-safe project skill metadata from `backend/skills/*/SKILL.md`. | `backend/app/api/skills.py` |
| Task runner | Builds agents, injects context and memory, streams LangGraph events, appends events, and finalizes task status. | `backend/app/runner/core.py` |
| Agent factory | Builds DeepAgents/LangGraph agents with model, tools, workspace backend, read-only skills backend, scratch state, and optional store. | `backend/app/agent/factory.py` |
| Platform tools | Aggregates task resource tools and SearXNG search tools for each agent run. | `backend/app/tools/registry.py` |
| Resource execution | Exposes uploaded task resources through list/inspect/read text/read table LangChain tools. | `backend/app/execution/resources.py` |
| Storage | Persists lifecycle state, messages, events, runs, memory records, agent store items, tool cache, uploads, and artifacts. | `backend/app/storage.py` |
| Memory service | Uses DashScope embeddings and Qdrant for long-term memory recall/indexing, with canonical memory rows in Postgres. | `backend/app/memory.py` |
| Conversation context | Builds deterministic same-session context from Postgres messages, summaries, and fresh tool cache. | `backend/app/conversation_context.py` |
| Stream adapter | Normalizes LangGraph v2 streaming chunks into platform event dictionaries. | `backend/app/streaming/v2_adapter.py` |
| Event converter | Converts normalized stream events into persisted `EventRecord` values and live metadata payloads. | `backend/app/streaming/event_converter.py` |
| Schemas | Defines Pydantic request/response models and task/event DTO contracts. | `backend/app/schemas.py` |
| Contracts | Defines event/resource/artifact dataclasses and payload helpers used by storage and tools. | `backend/app/contracts/__init__.py` |

## Pattern Overview

**Overall:** Layered FastAPI backend with an in-process asynchronous agent runner, PostgreSQL-backed task/event state, local per-task file workspaces, and LangGraph/DeepAgents execution graphs.

**Key Characteristics:**
- HTTP routers in `backend/app/api/` stay thin: read dependencies from `request.app.state`, validate request state, and delegate to storage or runner services.
- `backend/app/main.py` is the composition root. Add new long-lived services there so tests can inject fakes through `create_app(...)`.
- The task lifecycle is persisted in Postgres tables and mirrored into `TaskState` Pydantic models; files remain under task-scoped local directories.
- Agent execution is process-local. `backend/app/config.py` rejects multi-worker deployments because active run tracking lives in `TaskRunner._active_runs`.
- Streaming clients consume stored events, not raw LangGraph streams. The runner converts raw stream chunks into `EventRecord` rows before the SSE endpoint polls them.
- Project skills are files under `backend/skills/<skill>/SKILL.md`; browser-facing skill APIs expose only names and descriptions.

## Layers

**HTTP/API Layer:**
- Purpose: Define REST and SSE endpoints, translate domain errors to HTTP status codes, and use Pydantic response models.
- Location: `backend/app/api/`
- Contains: `tasks.py`, `files.py`, `artifacts.py`, `streaming.py`, `models.py`, `skills.py`, `deps.py`
- Depends on: `backend/app/schemas.py`, `backend/app/storage.py`, `backend/app/models/registry.py`, `backend/app/skills/project.py`
- Used by: FastAPI app wiring in `backend/app/main.py`

**Composition and Runtime Layer:**
- Purpose: Load settings, construct shared services, attach app state, enforce request/security limits, initialize runtime dependencies.
- Location: `backend/app/main.py`
- Contains: `create_app`, lifespan startup, auth middleware, CORS setup, health endpoint.
- Depends on: `Settings`, `PostgresTaskStorage`, `AgentMemoryService`, `ConversationContextBuilder`, `PostgresAgentStore`, `TaskRunner`.
- Used by: `uvicorn app.main:app` and tests through `create_app(...)`.

**Runner/Orchestration Layer:**
- Purpose: Start/cancel background runs, build agents, assemble model input, stream execution events, finalize task state, and schedule memory writes.
- Location: `backend/app/runner/core.py`
- Contains: `TaskRunner`, runner storage/memory protocols, terminal event payload helpers.
- Depends on: `backend/app/agent/factory.py`, `backend/app/tools/registry.py`, `backend/app/conversation_context.py`, `backend/app/memory.py`, `backend/app/streaming/`.
- Used by: task endpoints in `backend/app/api/tasks.py`.

**Agent Construction Layer:**
- Purpose: Convert app settings into a DeepAgents/LangGraph graph with a model, platform tools, workspace backend, skills backend, scratch state, and optional LangGraph store.
- Location: `backend/app/agent/`
- Contains: `factory.py`, `middleware.py`
- Depends on: `deepagents`, `langgraph`, `backend/app/models/provider.py`, `backend/app/config.py`.
- Used by: `TaskRunner.start(...)`.

**Tool and Resource Layer:**
- Purpose: Provide LangChain tools outside DeepAgents built-ins, especially uploaded resource inspection and local SearXNG search.
- Location: `backend/app/tools/`, `backend/app/execution/`
- Contains: `get_platform_tools`, `create_resource_tools`, `LocalResourceExecutionAdapter`, `create_searxng_search_tool`.
- Depends on: task workspace paths from `Settings.workspace_root`, upload helpers from `backend/app/storage.py`, SearXNG URL from settings.
- Used by: `TaskRunner.start(...)` when building each agent run.

**Persistence Layer:**
- Purpose: Persist task state, runs, messages, event log, agent store, context summaries, tool cache, and long-term memory rows; manage upload/artifact files.
- Location: `backend/app/storage.py`
- Contains: `PostgresTaskStorage`, upload validation helpers, artifact resolvers, task/event serializers.
- Depends on: `psycopg`, local filesystem, Pydantic schemas, event/resource contracts.
- Used by: API routes, runner, memory service, resource tools, agent store adapter.

**Memory and Context Layer:**
- Purpose: Rehydrate same-session context and cross-session memories without exposing sensitive content back into model prompts.
- Location: `backend/app/conversation_context.py`, `backend/app/memory.py`, `backend/app/security/scanner.py`
- Contains: `ConversationContextBuilder`, `AgentMemoryService`, `DashScopeEmbeddingClient`, `QdrantMemoryIndex`, secret scanners/redactors.
- Depends on: storage protocols, DeepSeek model provider for memory extraction, DashScope embeddings, Qdrant.
- Used by: `TaskRunner.start(...)` before agent invocation and after successful completion.

**Streaming Layer:**
- Purpose: Normalize LangGraph stream chunks, convert them to persisted platform events, and expose stored event records as SSE.
- Location: `backend/app/streaming/`, `backend/app/api/streaming.py`
- Contains: `stream_agent`, `extract_final_answer`, `convert_stream_event`, SSE formatters and endpoint polling loop.
- Depends on: LangGraph `CompiledStateGraph`, `EventRecord`, storage event reads.
- Used by: `TaskRunner.start(...)` and browser clients calling `/api/tasks/{task_id}/stream`.

**Configuration and Model Layer:**
- Purpose: Load environment settings, expose safe model IDs, and create concrete LangChain chat model instances.
- Location: `backend/app/config.py`, `backend/app/models/`
- Contains: `Settings`, `MODEL_REGISTRY`, `load_settings`, `create_model`, registry availability checks, DeepSeek thinking wrapper.
- Depends on: environment variables loaded from `backend/.env` by code, `langchain-deepseek`, `langchain-openai` wrappers.
- Used by: app startup, task validation, runner, title generation, memory extraction.

## Data Flow

### Primary Task Run Path

1. Browser posts `TaskCreateRequest` to `POST /api/tasks` or `MessageRequest` to `POST /api/tasks/{task_id}/messages` (`backend/app/api/tasks.py:81`, `backend/app/api/tasks.py:154`).
2. The task router resolves the model, validates model availability, validates selected project skills, and calls `storage.create_task(...)` or `storage.start_run(...)` (`backend/app/api/tasks.py:86`, `backend/app/api/tasks.py:160`, `backend/app/api/tasks.py:168`).
3. `PostgresTaskStorage.start_run(...)` moves the task to `running`, creates a run row, and inserts the user message (`backend/app/storage.py:592`).
4. The router starts an in-process background task through `runner.start_background(...)` (`backend/app/api/tasks.py:102`, `backend/app/api/tasks.py:178`).
5. `TaskRunner.start(...)` creates the per-task workspace, gets platform tools, builds the DeepAgent, injects conversation context, recalls memory, adds resource manifest context, and appends the user message (`backend/app/runner/core.py:119`, `backend/app/runner/core.py:123`, `backend/app/runner/core.py:133`, `backend/app/runner/core.py:153`, `backend/app/runner/core.py:169`).
6. `stream_agent(...)` reads LangGraph v2 `messages`, `updates`, and `values` stream modes and yields normalized event dicts (`backend/app/streaming/v2_adapter.py:46`).
7. `convert_stream_event(...)` converts normalized stream events into `EventRecord` instances (`backend/app/streaming/event_converter.py:37`).
8. `TaskRunner.start_background(...)` appends each event through storage, extracts the final answer from the latest graph state, updates the task to `complete`, appends a `final_answer` event, and schedules memory persistence (`backend/app/runner/core.py:228`, `backend/app/runner/core.py:245`, `backend/app/runner/core.py:256`, `backend/app/runner/core.py:275`, `backend/app/runner/core.py:287`).

### Live Streaming Path

1. Browser opens `GET /api/tasks/{task_id}/stream` (`backend/app/api/streaming.py:77`).
2. The streaming route verifies the task exists through storage and returns `StreamingResponse` with `text/event-stream` (`backend/app/api/streaming.py:79`, `backend/app/api/streaming.py:84`).
3. `_event_stream(...)` polls `storage.read_events(...)` after the last emitted event ID and yields full `EventRecord` JSON payloads (`backend/app/api/streaming.py:44`, `backend/app/api/streaming.py:52`).
4. When `runner.is_running(task_id)` is false, the endpoint drains remaining events, yields `format_sse_done()`, and closes (`backend/app/api/streaming.py:56`, `backend/app/api/streaming.py:64`).

### Upload and Resource Tool Path

1. Browser uploads files with `POST /api/tasks/{task_id}/files` (`backend/app/api/files.py:21`).
2. The endpoint rejects missing tasks and running tasks, then passes upload limits from settings to `storage.save_uploads(...)` (`backend/app/api/files.py:25`, `backend/app/api/files.py:29`, `backend/app/api/files.py:33`).
3. `PostgresTaskStorage.save_uploads(...)` validates filename, type, duplicates, JSON validity, byte limits, and writes files under `<task_root>/<task_id>/uploads/` (`backend/app/storage.py:738`).
4. Storage emits `file_uploaded` events with stable upload resource refs (`backend/app/storage.py:786`, `backend/app/storage.py:793`).
5. On the next run, `TaskRunner` registers resource tools and injects a resource manifest message when uploads exist (`backend/app/runner/core.py:121`, `backend/app/runner/core.py:169`).
6. `LocalResourceExecutionAdapter` resolves resources inside the task workspace and executes `list_uploaded_resources`, `inspect_resource`, `read_resource_text`, or `read_resource_table` (`backend/app/execution/resources.py:114`, `backend/app/execution/resources.py:155`).

### Artifact Download Path

1. The frontend uses artifact URLs generated from `TaskState.artifacts` (`backend/app/storage.py:1781`).
2. Latest artifact downloads use `/api/tasks/{task_id}/artifacts/{artifact_name}` and run-scoped downloads use `/api/tasks/{task_id}/runs/{run_id}/artifacts/{artifact_name}` (`backend/app/api/artifacts.py:32`, `backend/app/api/artifacts.py:39`).
3. Storage normalizes artifact names, validates run IDs, checks run artifact membership, and resolves only paths inside the task artifact directories (`backend/app/storage.py:1484`, `backend/app/storage.py:1495`, `backend/app/storage.py:1825`).

### Model and Skill Discovery Path

1. `GET /api/models` calls `list_available_models(settings)` and returns only model registry metadata plus an availability flag (`backend/app/api/models.py:13`, `backend/app/models/registry.py:29`).
2. `GET /api/skills` scans `backend/skills/*/SKILL.md` and returns name/description pairs only (`backend/app/api/skills.py:13`, `backend/app/skills/project.py:15`).
3. Task messages can include selected skills. The task API validates names and prefixes the user message with `[$skill]` references before starting the run (`backend/app/api/tasks.py:162`, `backend/app/skills/project.py:35`).
4. The agent factory mounts configured skill directories as read-only DeepAgents filesystem routes under `/skills/` (`backend/app/agent/factory.py:51`, `backend/app/agent/factory.py:102`).

### Long-Term Memory Path

1. App startup constructs `AgentMemoryService` when external services are required (`backend/app/main.py:56`).
2. Startup probes Qdrant collection shape and DashScope embedding availability (`backend/app/memory.py:240`).
3. Before a run, the runner calls memory recall in a thread; memory recall skips sensitive input, embeds the query, searches Qdrant, filters by score, and emits context as a system message (`backend/app/runner/core.py:153`, `backend/app/memory.py:274`).
4. After a completed final answer, the runner schedules memory extraction and persistence without blocking task completion (`backend/app/runner/core.py:287`, `backend/app/runner/core.py:388`).
5. Memory extraction calls the configured DeepSeek model, stores canonical rows in Postgres, and upserts vector payloads into Qdrant (`backend/app/memory.py:328`, `backend/app/memory.py:408`).

**State Management:**
- Request-independent shared services live on `app.state` in `backend/app/main.py:87`.
- Active run tasks are held in process memory at `TaskRunner._active_runs` (`backend/app/runner/core.py:99`).
- Durable task lifecycle state is stored in Postgres tables created by `PostgresTaskStorage.initialize(...)` (`backend/app/storage.py:329`).
- File bytes for uploads and artifacts remain on local disk under `Settings.task_root` / `Settings.workspace_root` (`backend/app/config.py:80`, `backend/app/storage.py:316`).
- LangGraph store operations are backed by the Postgres `agent_store_items` table through `PostgresAgentStore` (`backend/app/agent_store.py:20`, `backend/app/storage.py:1149`).

## Key Abstractions

**`Settings`:**
- Purpose: Immutable runtime configuration loaded from `backend/.env` and process environment.
- Examples: `backend/app/config.py:12`, `backend/app/config.py:76`
- Pattern: Dataclass with typed fields, default values, and explicit environment parsers. Extend this for any new backend-wide config.

**Pydantic API Schemas:**
- Purpose: Define request and response shapes for tasks, messages, events, artifacts, runs, summaries, and model options.
- Examples: `backend/app/schemas.py`
- Pattern: Keep browser/API contracts in Pydantic models and use these models as route `response_model` values.

**`TaskRunner`:**
- Purpose: Orchestrates one agent run from model/tool construction through stream conversion and terminal state updates.
- Examples: `backend/app/runner/core.py:83`
- Pattern: Use injected storage and memory protocols, append platform events through storage, and never make routers stream raw agent chunks directly.

**`PostgresTaskStorage`:**
- Purpose: Owns all durable task state and local task-file path safety.
- Examples: `backend/app/storage.py:313`
- Pattern: Public methods lock around DB operations, validate task/run/artifact IDs, and return `TaskState` or records rather than raw database rows.

**`EventRecord`:**
- Purpose: Shared event DTO for persistent logs, SSE streams, and frontend live metadata.
- Examples: `backend/app/schemas.py:47`, `backend/app/streaming/event_converter.py:37`
- Pattern: Add new runtime event types by updating normalized streaming/event conversion and storing full payload metadata.

**Resource References:**
- Purpose: Stable `myagent://...` identities for uploaded resources and generated artifacts.
- Examples: `backend/app/contracts/__init__.py:51`, `backend/app/contracts/__init__.py:63`
- Pattern: Use `build_upload_resource_ref(...)` and `build_artifact_ref(...)`; do not invent ad hoc URL or ID formats.

**Project Skills:**
- Purpose: User-selectable instructions stored as local `SKILL.md` files and mounted read-only for agents.
- Examples: `backend/app/skills/project.py:10`, `backend/skills/code_review/SKILL.md`, `backend/skills/web_research/SKILL.md`
- Pattern: Add a directory under `backend/skills/<skill-name>/SKILL.md` with YAML frontmatter containing `name` and `description`.

**Agent Store:**
- Purpose: LangGraph `BaseStore` implementation backed by storage methods and the `agent_store_items` table.
- Examples: `backend/app/agent_store.py:20`, `backend/app/storage.py:1149`
- Pattern: Keep LangGraph store calls behind `PostgresAgentStore`; add storage methods first when store behavior expands.

## Entry Points

**Uvicorn ASGI App:**
- Location: `backend/app/main.py:245`
- Triggers: `uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8001`
- Responsibilities: Expose the app created by `create_app()` for local development and deployment.

**Testable App Factory:**
- Location: `backend/app/main.py:38`
- Triggers: tests and app import.
- Responsibilities: Allow injection of settings, storage, memory service, and title generator.

**Task REST API:**
- Location: `backend/app/api/tasks.py:81`
- Triggers: Browser task creation, message sends, cancellation, renames, deletes, and event history fetches.
- Responsibilities: Enforce task lifecycle rules and delegate execution to `TaskRunner`.

**SSE Stream API:**
- Location: `backend/app/api/streaming.py:77`
- Triggers: Browser live-log subscriptions.
- Responsibilities: Stream persisted task events until the runner stops.

**File Upload API:**
- Location: `backend/app/api/files.py:21`
- Triggers: Browser task file uploads.
- Responsibilities: Enforce not-running state and upload limits before storage writes.

**Artifact Download API:**
- Location: `backend/app/api/artifacts.py:32`
- Triggers: Browser artifact link clicks.
- Responsibilities: Serve storage-resolved task artifacts.

**Memory Admin CLI:**
- Location: `backend/app/memory_admin.py:34`
- Triggers: `python -m app.memory_admin reset-qdrant` or `rebuild-qdrant` from the backend environment.
- Responsibilities: Reset or rebuild the Qdrant memory index using configured storage and memory services.

## Architectural Constraints

- **Threading:** FastAPI runs on the event loop; blocking context/memory operations are sent to threads with `asyncio.to_thread(...)` in `backend/app/runner/core.py:135`, `backend/app/runner/core.py:357`, and `backend/app/runner/core.py:403`.
- **In-process runner:** `TaskRunner._active_runs` is process-local (`backend/app/runner/core.py:99`), and `enforce_single_process_runtime()` rejects multi-worker deployments (`backend/app/config.py:194`).
- **Database requirement:** Production app startup requires `MYAGENT_DATABASE_URL`; missing DB config is collected as a startup error in `backend/app/main.py:50`.
- **Memory requirement:** When production services are required, memory startup requires DashScope and Qdrant config through `AgentMemoryService` (`backend/app/main.py:56`, `backend/app/memory.py:220`).
- **Local access default:** API requests require either a configured access token or a loopback client (`backend/app/main.py:206`).
- **Filesystem boundaries:** Task directories, relative writes, artifact paths, run IDs, and resource workspaces are validated before filesystem access (`backend/app/storage.py:464`, `backend/app/storage.py:1353`, `backend/app/storage.py:1420`, `backend/app/execution/resources.py:231`).
- **Upload limits:** Multipart body size, upload count, per-file size, request size, and JSON body size come from `Settings` and are enforced in middleware and storage (`backend/app/main.py:116`, `backend/app/storage.py:738`).
- **Global state:** Safe module-level registries/constants exist for model IDs, upload formats, event type mapping, and subagent definitions in `backend/app/config.py`, `backend/app/storage.py`, `backend/app/streaming/event_converter.py`, and `backend/app/subagents/definitions.py`.
- **Circular imports:** No circular dependency chain is detected in the scanned backend files. Preserve the direction `api -> services/storage -> schemas/contracts`; do not import API modules from runner, storage, tools, models, or memory code.

## Anti-Patterns

### Router-Owned Business Logic

**What happens:** A route directly implements storage mutation, model calls, or agent execution instead of calling service/storage helpers.
**Why it's wrong:** It bypasses `create_app(...)` dependency injection and makes tests/fakes harder to use.
**Do this instead:** Keep routes thin like `backend/app/api/tasks.py:154` and delegate to `PostgresTaskStorage`, `TaskRunner`, or a new service wired in `backend/app/main.py`.

### Raw Filesystem Access Outside Storage/Resource Adapters

**What happens:** New code resolves task upload or artifact paths manually in an API route or tool.
**Why it's wrong:** It bypasses path traversal protections and artifact/run membership checks in `PostgresTaskStorage`.
**Do this instead:** Use `storage.save_uploads(...)`, `storage.resolve_artifact(...)`, `storage.resolve_run_artifact(...)`, or resource adapter helpers in `backend/app/execution/resources.py`.

### Streaming Raw LangGraph Chunks To Clients

**What happens:** New streaming endpoints emit raw LangGraph `astream(...)` chunks directly.
**Why it's wrong:** The frontend expects full `EventRecord` payloads with platform `live` metadata, and persisted event history is the authoritative replay source.
**Do this instead:** Normalize with `backend/app/streaming/v2_adapter.py`, convert with `backend/app/streaming/event_converter.py`, append through storage, and let `backend/app/api/streaming.py` stream stored records.

### Multi-Worker Deployment With Active Runs

**What happens:** Uvicorn/Gunicorn worker count is increased while runs remain tracked by in-process `asyncio.Task` objects.
**Why it's wrong:** Active run state splits across processes while API requests and SSE clients may hit different workers.
**Do this instead:** Keep a single backend worker unless the runner is moved to an external queue/worker system; `backend/app/config.py:194` enforces this for known worker-count env vars.

### Treating Uploaded Files As Chat Context

**What happens:** Prompts or features assume uploaded document contents are already included in the user message.
**Why it's wrong:** Uploads are task resources on disk and are only exposed through resource tools and manifests.
**Do this instead:** Use `list_uploaded_resources`, `inspect_resource`, `read_resource_text`, and `read_resource_table` from `backend/app/execution/resources.py`.

## Error Handling

**Strategy:** API routes convert expected domain exceptions to HTTP errors, runner terminal failures become task events/status updates, and optional context/memory steps fail soft unless startup requires the service.

**Patterns:**
- Translate missing/invalid task state into `HTTPException` in API routes (`backend/app/api/tasks.py:41`, `backend/app/api/files.py:25`, `backend/app/api/artifacts.py:23`).
- Reject bad client input with 400, conflicts with 409, oversize uploads/JSON with 413, and missing auth with 401/403 (`backend/app/main.py:108`, `backend/app/api/tasks.py:166`, `backend/app/api/files.py:40`).
- Convert request validation errors to a stable frontend-safe message (`backend/app/main.py:99`).
- Mark timeout, cancellation, and generic runner failures with persisted terminal events (`backend/app/runner/core.py:294`, `backend/app/runner/core.py:312`, `backend/app/runner/core.py:329`).
- Continue without optional memory/context pieces when recall, event payload generation, or resource manifest provisioning fails during a run (`backend/app/runner/core.py:352`, `backend/app/runner/core.py:367`, `backend/app/runner/core.py:380`).
- Return user-readable error strings from SearXNG tools instead of crashing the agent (`backend/app/tools/searxng_search.py:117`).

## Cross-Cutting Concerns

**Logging:** Uses Python `logging.getLogger(__name__)` in service modules such as `backend/app/main.py`, `backend/app/runner/core.py`, `backend/app/memory.py`, `backend/app/tools/searxng_search.py`, and `backend/app/skills/loader.py`.

**Validation:** Pydantic validates request/response shape in `backend/app/schemas.py`; storage validates filenames, run IDs, task paths, artifact paths, upload formats, JSON uploads, and request state in `backend/app/storage.py`.

**Authentication:** `backend/app/main.py` requires `MYAGENT_ACCESS_TOKEN` for non-local API access and accepts bearer token, `X-MyAgent-Token`, `X-Agent-Chat-Token`, or `token` query parameter when configured.

**Configuration:** `backend/app/config.py` loads `backend/.env` before environment reads, but documentation and code should reference `backend/.env.example` for variable names. Do not read or quote secret values from `backend/.env`.

**Secret Handling:** `backend/app/security/scanner.py` redacts provider key names, token fields, bearer tokens, and canary patterns before context/memory use.

**Testing Hooks:** `create_app(...)` accepts fake storage/memory/title-generator dependencies, and tests use `backend/tests/fakes.py` as the in-memory storage implementation.

---

*Architecture analysis: 2026-05-22*
