# Codebase Structure

**Analysis Date:** 2026-05-19

## Directory Layout

```text
MyAgent/
|-- AGENTS.md                         # Repository-level collaboration and validation rules
|-- DESIGN.md                         # Frontend visual system reference
|-- README.md                         # Root setup, architecture, and local development guide
|-- asset/                            # Long-term project knowledge packs
|-- backend/                          # FastAPI backend, DeepAgents runtime, storage, tests
|   |-- app/                          # Backend application package
|   |   |-- api/                      # FastAPI route modules
|   |   |-- agent/                    # DeepAgents factory and extra middleware assembly
|   |   |-- contracts/                # Event/resource/artifact dataclasses and payload helpers
|   |   |-- execution/                # Resource execution adapter and upload tools
|   |   |-- models/                   # Model registry and provider creation
|   |   |-- runner/                   # In-process task runner
|   |   |-- security/                 # Secret scanning/redaction helpers
|   |   |-- session/                  # Session-event projection helpers
|   |   |-- skills/                   # Runtime skill discovery
|   |   |-- streaming/                # LangGraph stream adapters and SSE helpers
|   |   |-- subagents/                # Built-in DeepAgents subagent definitions
|   |   |-- tools/                    # Tool registry and SearXNG/filesystem bridges
|   |   |-- main.py                   # FastAPI app factory and ASGI `app`
|   |   |-- storage.py                # Postgres task storage plus local file workspace
|   |   `-- schemas.py                # Public Pydantic API schemas
|   |-- skills/                       # Runtime DeepAgents SKILL.md directories
|   |-- storage/sessions/             # Ignored local uploads/artifacts by task_id
|   |-- tests/                        # Backend pytest suite
|   |-- pyproject.toml                # Backend package, tools, and pytest config
|   `-- uv.lock                       # Backend uv lockfile
|-- frontend/                         # Next.js app-router frontend and tests
|   |-- app/                          # Route entry, global CSS, pure state/view helpers
|   |-- components/chat/              # Chat workspace components
|   |-- hooks/                        # Client workflow hooks
|   |-- lib/                          # Browser API adapter
|   |-- tests/                        # Node test suite grouped by state/workspace/upload/model
|   |-- e2e-playwright/               # Playwright specs plus ignored screenshot evidence dirs
|   |-- next.config.mjs               # Next config and distDir override
|   |-- package.json                  # Frontend scripts and dependencies
|   `-- tsconfig.json                 # Strict TypeScript config
|-- scripts/                          # Local WSL development helper scripts
|-- Study/                            # Learning/study notes and mini-units
|-- .github/workflows/                # Backend, frontend, and repository CI workflows
|-- .planning/codebase/               # Generated codebase maps for GSD planning/execution
`-- audits/                           # Ignored audit run artifacts
```

## Directory Purposes

**`backend/`:**
- Purpose: Own all server-side runtime, persistence, agent execution, and backend verification.
- Contains: `backend/app/`, `backend/skills/`, `backend/tests/`, `backend/pyproject.toml`, `backend/uv.lock`, `backend/storage/`.
- Key files: `backend/app/main.py`, `backend/app/storage.py`, `backend/app/runner/core.py`, `backend/app/schemas.py`.

**`backend/app/api/`:**
- Purpose: Keep HTTP route modules separated by public API concern.
- Contains: `tasks.py`, `files.py`, `artifacts.py`, `streaming.py`, `models.py`, `deps.py`.
- Key files: `backend/app/api/tasks.py` for lifecycle, `backend/app/api/files.py` for uploads, `backend/app/api/streaming.py` for SSE.

**`backend/app/runner/`:**
- Purpose: Keep the in-process task orchestration implementation isolated from API handlers.
- Contains: `backend/app/runner/core.py`.
- Key files: `backend/app/runner/core.py`.

**`backend/app/agent/`:**
- Purpose: Centralize DeepAgents construction and extra middleware rules.
- Contains: `backend/app/agent/factory.py`, `backend/app/agent/middleware.py`.
- Key files: `backend/app/agent/factory.py`.

**`backend/app/streaming/`:**
- Purpose: Normalize DeepAgents/LangGraph stream output and format SSE payloads.
- Contains: `backend/app/streaming/v2_adapter.py`, `backend/app/streaming/event_converter.py`, `backend/app/streaming/sse.py`.
- Key files: `backend/app/streaming/v2_adapter.py`, `backend/app/streaming/event_converter.py`.

**`backend/app/execution/`:**
- Purpose: Provide the task-scoped resource provision/execute boundary for uploaded files.
- Contains: `backend/app/execution/resources.py`.
- Key files: `backend/app/execution/resources.py`.

**`backend/app/tools/`:**
- Purpose: Register platform tools beyond DeepAgents built-ins.
- Contains: `backend/app/tools/registry.py`, `backend/app/tools/searxng_search.py`, `backend/app/tools/filesystem_bridge.py`.
- Key files: `backend/app/tools/registry.py`.

**`backend/app/models/`:**
- Purpose: Validate and instantiate provider-prefixed chat models.
- Contains: `backend/app/models/registry.py`, `backend/app/models/provider.py`.
- Key files: `backend/app/models/registry.py`, `backend/app/models/provider.py`.

**`backend/app/skills/` and `backend/skills/`:**
- Purpose: `backend/app/skills/` discovers skill metadata; `backend/skills/` stores runtime DeepAgents skill directories.
- Contains: `backend/app/skills/loader.py`, `backend/app/skills/registry.py`, `backend/skills/web_research/SKILL.md`, `backend/skills/code_review/SKILL.md`.
- Key files: `backend/app/skills/loader.py`, `backend/skills/web_research/SKILL.md`, `backend/skills/code_review/SKILL.md`.

**`backend/app/subagents/`:**
- Purpose: Define and retrieve built-in DeepAgents subagents.
- Contains: `backend/app/subagents/definitions.py`, `backend/app/subagents/registry.py`.
- Key files: `backend/app/subagents/definitions.py`.

**`backend/app/security/`:**
- Purpose: Scan and redact sensitive text before context/memory use.
- Contains: `backend/app/security/scanner.py`.
- Key files: `backend/app/security/scanner.py`.

**`backend/app/session/`:**
- Purpose: Project append-only session events into run/session state.
- Contains: `backend/app/session/projector.py`.
- Key files: `backend/app/session/projector.py`.

**`backend/tests/`:**
- Purpose: Verify backend API, runner, storage, streaming, tools, models, security, skills, and integration contracts.
- Contains: `backend/tests/unit/`, `backend/tests/integration/`, `backend/tests/e2e/`, `backend/tests/fakes.py`, `backend/tests/conftest.py`.
- Key files: `backend/tests/fakes.py`, `backend/tests/unit/api/test_tasks.py`, `backend/tests/unit/runner/test_core.py`, `backend/tests/unit/storage/test_storage.py`.

**`backend/storage/sessions/`:**
- Purpose: Default local task workspace for uploads and artifacts.
- Contains: ignored generated task directories named by `task_id`, usually with `uploads/` and lazily-created `artifacts/`.
- Key files: `backend/storage/sessions/.gitkeep`.

**`frontend/`:**
- Purpose: Own browser UI, frontend state boundary, tests, and E2E specs.
- Contains: `frontend/app/`, `frontend/components/`, `frontend/hooks/`, `frontend/lib/`, `frontend/tests/`, `frontend/e2e-playwright/`.
- Key files: `frontend/app/page.tsx`, `frontend/hooks/use-task-workspace.ts`, `frontend/lib/task-api.ts`, `frontend/app/task-state.ts`.

**`frontend/app/`:**
- Purpose: Keep app-router route entry, global CSS, and pure state/view projection helpers.
- Contains: `frontend/app/page.tsx`, `frontend/app/layout.tsx`, `frontend/app/globals.css`, `frontend/app/task-state.ts`, `frontend/app/workspace-view.ts`, `frontend/app/file-upload.ts`, `frontend/app/model-ui.ts`.
- Key files: `frontend/app/page.tsx`, `frontend/app/task-state.ts`, `frontend/app/workspace-view.ts`.

**`frontend/components/chat/`:**
- Purpose: Render the chat workspace UI from hook state and callbacks.
- Contains: `TaskWorkspace.tsx`, `TaskConversation.tsx`, `ChatComposer.tsx`, `ChatSidebar.tsx`, `RobotAvatar.tsx`, `TypewriterText.tsx`.
- Key files: `frontend/components/chat/TaskWorkspace.tsx`, `frontend/components/chat/TaskConversation.tsx`, `frontend/components/chat/ChatComposer.tsx`.

**`frontend/hooks/`:**
- Purpose: Own client workflow state and side effects.
- Contains: `frontend/hooks/use-task-workspace.ts`.
- Key files: `frontend/hooks/use-task-workspace.ts`.

**`frontend/lib/`:**
- Purpose: Isolate browser calls to backend REST/SSE/artifact endpoints.
- Contains: `frontend/lib/task-api.ts`.
- Key files: `frontend/lib/task-api.ts`.

**`frontend/tests/`:**
- Purpose: Unit-test frontend pure helpers and component source contracts with Node's test runner.
- Contains: `frontend/tests/state/`, `frontend/tests/workspace/`, `frontend/tests/upload/`, `frontend/tests/model/`.
- Key files: `frontend/tests/state/test_task_state.test.ts`, `frontend/tests/workspace/test_task_workspace.test.ts`, `frontend/tests/upload/test_file_upload.test.ts`.

**`frontend/e2e-playwright/`:**
- Purpose: Store committed Playwright specs and ignored browser acceptance screenshot evidence dirs.
- Contains: `test_*.spec.mjs`, `README.md`, ignored `e2e-YYYYMMDDHHMMSS/` evidence directories.
- Key files: `frontend/e2e-playwright/test_runtime_contracts.spec.mjs`, `frontend/e2e-playwright/test_resource_upload_harness.spec.mjs`, `frontend/e2e-playwright/README.md`.

**`asset/`:**
- Purpose: Store long-term project knowledge packs for future agents.
- Contains: `asset/deepagents_platform_knowledge_pack.md`, `asset/bid_analysis_workflow_knowledge_pack.md`, `asset/tender_workflow_breakdown.md`.
- Key files: `asset/deepagents_platform_knowledge_pack.md`.

**`scripts/`:**
- Purpose: Provide local WSL developer service startup and port cleanup.
- Contains: `scripts/start-dev-wsl.ps1`, `scripts/dev-terminal-runner.sh`, `scripts/stop-dev-ports.sh`.
- Key files: `scripts/start-dev-wsl.ps1`.

**`.github/workflows/`:**
- Purpose: Define CI entrypoints for backend, frontend, and repository-level checks.
- Contains: `.github/workflows/backend-ci.yml`, `.github/workflows/frontend-ci.yml`, `.github/workflows/repository-ci.yml`.
- Key files: `.github/workflows/frontend-ci.yml`.

**`.planning/codebase/`:**
- Purpose: Store generated architecture/structure/quality/concern maps consumed by GSD commands.
- Contains: `ARCHITECTURE.md`, `STRUCTURE.md`.
- Key files: `.planning/codebase/ARCHITECTURE.md`, `.planning/codebase/STRUCTURE.md`.

## Key File Locations

**Entry Points:**
- `backend/app/main.py`: FastAPI `create_app()` and ASGI `app`.
- `frontend/app/page.tsx`: App-router page that mounts the workspace.
- `frontend/components/chat/TaskWorkspace.tsx`: Client component that wires hook state into chat UI components.
- `scripts/start-dev-wsl.ps1`: Windows PowerShell entry for local WSL dev terminals.
- `backend/app/memory_admin.py`: CLI entry for memory index reset/rebuild operations.

**Configuration:**
- `backend/app/config.py`: Backend settings, model registry, env loading, single-worker enforcement.
- `backend/pyproject.toml`: Python dependencies, pytest path, ruff, mypy, uv source pin.
- `frontend/package.json`: Next/npm scripts, frontend dependencies, lint/test/typecheck commands.
- `frontend/next.config.mjs`: Next `distDir` override and polling watcher config.
- `frontend/tsconfig.json`: Strict TypeScript config and generated Next type includes.
- `.gitignore`, `backend/.gitignore`, `frontend/.gitignore`: Generated file and secret exclusions.
- `.gitattributes`: Repository line-ending policy.
- `backend/.env` and `frontend/.env.local`: Present environment config files; never read contents.

**Core Logic:**
- `backend/app/api/tasks.py`: Task CRUD, message send, cancel, event polling.
- `backend/app/api/files.py`: Upload endpoint.
- `backend/app/api/artifacts.py`: Artifact download endpoints.
- `backend/app/api/streaming.py`: SSE event stream.
- `backend/app/storage.py`: Postgres task storage and local file workspace.
- `backend/app/runner/core.py`: Agent run orchestration.
- `backend/app/agent/factory.py`: DeepAgents graph creation.
- `backend/app/streaming/v2_adapter.py`: LangGraph stream normalization and final answer extraction.
- `backend/app/streaming/event_converter.py`: EventRecord creation and `live` metadata.
- `backend/app/execution/resources.py`: Task resource tools.
- `backend/app/conversation_context.py`: Deterministic same-session context.
- `backend/app/memory.py`: Long-term memory service.
- `frontend/app/task-state.ts`: Backend-to-frontend state mapping, log normalization, artifact URL trust.
- `frontend/app/workspace-view.ts`: Progress-log and conversation projection.
- `frontend/hooks/use-task-workspace.ts`: Browser workflow orchestration.
- `frontend/lib/task-api.ts`: REST/SSE/artifact fetch adapter.

**Testing:**
- `backend/tests/unit/api/`: FastAPI route unit tests.
- `backend/tests/unit/runner/`: Runner and context/memory tests.
- `backend/tests/unit/storage/`: Storage contract tests.
- `backend/tests/unit/streaming/`: Stream adapter/converter/SSE tests.
- `backend/tests/unit/tools/`: Resource and search tool tests.
- `backend/tests/integration/`: Backend integration tests.
- `backend/tests/e2e/test_streaming_e2e.py`: Backend streaming E2E test.
- `frontend/tests/state/`: Frontend state mapper tests.
- `frontend/tests/workspace/`: Workspace hook/projection/API tests.
- `frontend/tests/upload/`: Upload and upload-preview tests.
- `frontend/tests/model/`: Model UI tests.
- `frontend/e2e-playwright/test_*.spec.mjs`: Browser-side Playwright acceptance specs.

**Documentation And Knowledge:**
- `AGENTS.md`: Repository-level rules and validation requirements.
- `DESIGN.md`: Required visual reference for frontend UI changes.
- `README.md`, `backend/README.md`, `frontend/README.md`: User-facing setup and operation docs.
- `asset/deepagents_platform_knowledge_pack.md`: Primary platform knowledge pack.
- `asset/bid_analysis_workflow_knowledge_pack.md`: Bid-analysis workflow knowledge.
- `asset/tender_workflow_breakdown.md`: Tender workflow breakdown.
- `Study/`: Learning notes and mini-units.

## Naming Conventions

**Files:**
- Python source modules use lowercase snake_case: `backend/app/task_titles.py`, `backend/app/conversation_context.py`.
- Python package directories use lowercase names: `backend/app/runner/`, `backend/app/streaming/`, `backend/app/security/`.
- Backend tests must use `test_*.py`: `backend/tests/unit/api/test_tasks.py`.
- Frontend component files use PascalCase: `frontend/components/chat/TaskConversation.tsx`.
- Frontend pure helper files use kebab-case or domain names: `frontend/app/task-state.ts`, `frontend/app/workspace-view.ts`, `frontend/lib/task-api.ts`.
- Frontend Node tests must use `test_*.test.ts`: `frontend/tests/workspace/test_task_workspace.test.ts`.
- Playwright specs use `test_*.spec.mjs`: `frontend/e2e-playwright/test_runtime_contracts.spec.mjs`.
- Runtime skill directories use snake_case, and each skill contains `SKILL.md`: `backend/skills/web_research/SKILL.md`.

**Directories:**
- Backend unit-test subdirectories mirror functional areas: `backend/tests/unit/api/`, `backend/tests/unit/runner/`, `backend/tests/unit/storage/`, `backend/tests/unit/tools/`.
- Frontend tests are grouped by product boundary: `frontend/tests/state/`, `frontend/tests/workspace/`, `frontend/tests/upload/`, `frontend/tests/model/`.
- Browser evidence dirs follow timestamp naming and are ignored: `frontend/e2e-playwright/e2e-YYYYMMDDHHMMSS/`.
- Local task workspaces are named by generated task IDs under `backend/storage/sessions/<task_id>/`.

**Functions And Types:**
- Python functions and methods use snake_case: `create_task()`, `start_run()`, `read_events()`.
- Python classes use PascalCase: `TaskRunner`, `PostgresTaskStorage`, `AgentMemoryService`.
- TypeScript functions and variables use camelCase: `normalizeTaskState()`, `buildLiveLogItems()`, `handleSubmit`.
- TypeScript types use PascalCase: `TaskState`, `ExecutionLog`, `ModelDisplayOption`.
- React components use PascalCase exported functions: `TaskWorkspace`, `ChatComposer`, `TaskConversation`.

**Wire Format:**
- Backend API fields are snake_case, for example `task_id`, `created_at`, `active_run_id`, `upload_count`.
- Frontend state fields are camelCase, for example `id`, `createdAt`, `activeRunId`, `uploadCount`.
- Model IDs use provider-prefixed format such as `deepseek:deepseek-chat`.

## Where to Add New Code

**New Backend API Endpoint:**
- Primary code: add a route module or extend an existing module under `backend/app/api/`.
- Route registration: include new routers in `backend/app/main.py`.
- Request/response schemas: add Pydantic models to `backend/app/schemas.py`.
- Tests: add `backend/tests/unit/api/test_*.py`; use `backend/tests/conftest.py` and `backend/tests/fakes.py` patterns.

**New Task Lifecycle Or Storage Contract:**
- Primary code: `backend/app/storage.py` and `backend/app/schemas.py`.
- Runner integration: `backend/app/runner/core.py` when lifecycle affects active runs.
- Frontend mapping: `frontend/app/task-state.ts` and `frontend/lib/task-api.ts` if public API shape changes.
- Tests: `backend/tests/unit/storage/test_storage.py`, `backend/tests/fakes.py`, `backend/tests/unit/api/test_tasks.py`, `frontend/tests/state/test_task_state.test.ts`.

**New Runner Or Agent Behavior:**
- Primary code: `backend/app/runner/core.py`.
- Agent construction: `backend/app/agent/factory.py`, `backend/app/agent/middleware.py`.
- Stream behavior: `backend/app/streaming/v2_adapter.py`, `backend/app/streaming/event_converter.py`.
- Tests: `backend/tests/unit/runner/`, `backend/tests/unit/agent/`, `backend/tests/unit/streaming/`.

**New Runtime Tool:**
- Primary code: `backend/app/tools/` for tool-specific code or `backend/app/execution/resources.py` for resource tools.
- Registration: `backend/app/tools/registry.py`.
- Tests: `backend/tests/unit/tools/test_*.py`.

**New Upload Resource Format:**
- Primary code: upload validation and format helpers in `backend/app/storage.py`; read/inspect implementation in `backend/app/execution/resources.py`.
- Frontend selection: `frontend/app/file-upload.ts` and `frontend/components/chat/ChatComposer.tsx`.
- Tests: `backend/tests/unit/tools/test_resource_execution.py`, `backend/tests/unit/storage/test_storage.py`, `frontend/tests/upload/test_file_upload.test.ts`, relevant Playwright spec under `frontend/e2e-playwright/`.

**New Model Provider Or Model Option:**
- Primary code: `backend/app/config.py`, `backend/app/models/provider.py`, `backend/app/models/registry.py`.
- Frontend display: `frontend/app/model-ui.ts`, `frontend/hooks/use-task-workspace.ts` if picker filtering changes.
- Tests: `backend/tests/unit/models/`, `backend/tests/unit/api/test_models.py`, `frontend/tests/model/test_model_ui.test.ts`.

**New Frontend Workflow State:**
- Primary code: `frontend/hooks/use-task-workspace.ts`.
- Backend adapter: `frontend/lib/task-api.ts`.
- State mapping: `frontend/app/task-state.ts`.
- Tests: `frontend/tests/workspace/test_task_workspace.test.ts`, `frontend/tests/workspace/test_task_api.test.ts`, `frontend/tests/state/test_task_state.test.ts`.

**New Frontend UI Component Or Visual Change:**
- Read first: `DESIGN.md`.
- Primary code: `frontend/components/chat/` for components and `frontend/app/globals.css` for styling.
- Pure view helpers: `frontend/app/workspace-view.ts`.
- Tests: `frontend/tests/workspace/` or `frontend/tests/upload/`; add/update Playwright spec in `frontend/e2e-playwright/` and screenshot evidence under `frontend/e2e-playwright/e2e-YYYYMMDDHHMMSS/`.

**New Progress-Log Projection:**
- Primary code: `frontend/app/workspace-view.ts`.
- UI rendering: `frontend/components/chat/TaskConversation.tsx`.
- Backend event shape: `backend/app/streaming/event_converter.py`.
- Tests: `frontend/tests/workspace/test_workspace_view.test.ts`, `frontend/e2e-playwright/test_progress_log_disclosure.spec.mjs`.

**New Runtime Skill:**
- Primary code: `backend/skills/<skill_name>/SKILL.md`.
- Discovery changes: `backend/app/skills/loader.py`, `backend/app/skills/registry.py`.
- Agent use: pass through `Settings.skills_dirs` and `TaskRunner.start()` in `backend/app/runner/core.py`.
- Tests: `backend/tests/unit/skills/test_loader.py`, `backend/tests/unit/skills/test_builtin_skill_content.py`.

**New Long-Term Memory Behavior:**
- Primary code: `backend/app/memory.py`, `backend/app/agent_store.py`, `backend/app/storage.py`.
- Runner integration: `backend/app/runner/core.py`.
- Tests: `backend/tests/unit/runner/test_memory.py`, `backend/tests/unit/storage/test_agent_store.py`, `backend/tests/integration/test_postgres_memory_storage.py`.

**New Browser E2E Scenario:**
- Spec: `frontend/e2e-playwright/test_<scenario>.spec.mjs`.
- Evidence: ignored local directory `frontend/e2e-playwright/e2e-YYYYMMDDHHMMSS/<scenario>/`.
- Support docs: keep `frontend/e2e-playwright/README.md` current.

**New Knowledge Pack:**
- Prefer existing package: `asset/deepagents_platform_knowledge_pack.md` for platform/runtime boundaries.
- Theme-specific package: update `asset/bid_analysis_workflow_knowledge_pack.md` or `asset/tender_workflow_breakdown.md` when the topic fits.
- Only create a new `asset/*.md` when a stable independent theme cannot fit an existing pack.

## Special Directories

**`backend/storage/sessions/`:**
- Purpose: Local task file workspace for uploads and generated artifacts.
- Generated: Yes.
- Committed: No, except `backend/storage/sessions/.gitkeep`.

**`frontend/e2e-playwright/e2e-YYYYMMDDHHMMSS/`:**
- Purpose: Local browser acceptance screenshots, traces, fixtures, and evidence grouped by timestamp/scenario.
- Generated: Yes.
- Committed: No.

**`frontend/e2e-playwright/`:**
- Purpose: Committed Playwright spec directory and local evidence root.
- Generated: Mixed; specs and `README.md` are source, `e2e-*`, `test-results/`, and reports are generated.
- Committed: Specs and `README.md` are committed; generated evidence is ignored.

**`backend/skills/`:**
- Purpose: Runtime DeepAgents skill sources loaded by settings.
- Generated: No.
- Committed: Yes.

**`.planning/codebase/`:**
- Purpose: Generated architecture, structure, stack, integrations, conventions, testing, and concerns docs for GSD workflows.
- Generated: Yes.
- Committed: Yes when updated by mapping tasks.

**`asset/`:**
- Purpose: Long-term project knowledge packs and stable workflow boundaries.
- Generated: No.
- Committed: Yes.

**`audits/`:**
- Purpose: Local audit run artifacts and logs.
- Generated: Yes.
- Committed: No.

**`.playwright-mcp/`:**
- Purpose: Local Chrome/Playwright MCP exploration logs and screenshots.
- Generated: Yes.
- Committed: No.

**`frontend/.next`, `frontend/.next-dev`, `frontend/.next-dev-e2e`:**
- Purpose: Next.js production, dev, and E2E dev build outputs.
- Generated: Yes.
- Committed: No.

**`frontend/node_modules/` and `backend/.venv/`:**
- Purpose: Dependency installs for frontend npm and backend uv/Python environments.
- Generated: Yes.
- Committed: No.

**`backend/.env` and `frontend/.env.local`:**
- Purpose: Local environment configuration.
- Generated: Developer/local.
- Committed: No; contents must never be read or quoted.

**`.codex/skills/` and `.agents/skills/`:**
- Purpose: Optional project-specific Codex/agent skills.
- Generated: Not applicable.
- Committed: Not detected in this repo. A root `.codex` empty file exists, but no project skill directory is present.

---

*Structure analysis: 2026-05-19*
