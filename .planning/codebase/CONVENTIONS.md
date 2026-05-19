# Coding Conventions

**Analysis Date:** 2026-05-19

## Naming Patterns

**Files:**
- Use `snake_case.py` for backend modules: `backend/app/task_titles.py`, `backend/app/conversation_context.py`, `backend/app/streaming/event_converter.py`.
- Use package directories for backend domains: `backend/app/api/`, `backend/app/runner/`, `backend/app/streaming/`, `backend/app/tools/`, `backend/app/security/`.
- Use `kebab-case.ts` for frontend non-component modules: `frontend/hooks/use-task-workspace.ts`, `frontend/lib/task-api.ts`, `frontend/app/task-state.ts`, `frontend/app/workspace-view.ts`.
- Use `PascalCase.tsx` for React component modules: `frontend/components/chat/ChatComposer.tsx`, `frontend/components/chat/TaskConversation.tsx`, `frontend/components/chat/TaskWorkspace.tsx`.
- Use `test_*.py` for backend tests and place them by scope under `backend/tests/unit/`, `backend/tests/integration/`, or `backend/tests/e2e/`.
- Use `test_*.test.ts` for frontend Node tests under `frontend/tests/` and `test_*.spec.mjs` for browser Playwright specs under `frontend/e2e-playwright/`.

**Functions:**
- Use `snake_case` for Python functions and helpers: `load_settings()` in `backend/app/config.py`, `_validate_runnable_model()` in `backend/app/api/tasks.py`, `extract_final_answer()` in `backend/app/streaming/v2_adapter.py`.
- Prefix private Python helpers with `_`: `_storage()` and `_settings()` in `backend/app/api/tasks.py`, `_terminal_event_payload()` in `backend/app/runner/core.py`.
- Use `camelCase` for frontend functions and helpers: `requestTaskJson()` in `frontend/lib/task-api.ts`, `normalizeTaskState()` in `frontend/app/task-state.ts`, `buildLiveLogItems()` in `frontend/app/workspace-view.ts`.
- Use `handle*` names for component and hook event handlers: `handleSubmit()` in `frontend/hooks/use-task-workspace.ts`, `handleComposerKeyDown()` in `frontend/components/chat/ChatComposer.tsx`.
- Use `use*` for React hooks: `useTaskWorkspace()` in `frontend/hooks/use-task-workspace.ts`.

**Variables:**
- Use `UPPER_SNAKE_CASE` for module constants: `MODEL_REGISTRY` in `backend/app/config.py`, `MAX_SSE_RETRIES` in `frontend/hooks/use-task-workspace.ts`, `DEFAULT_MODEL_ID` in `frontend/hooks/use-task-workspace.ts`.
- Use `snake_case` for backend API and storage fields matching public JSON contracts: `task_id`, `created_at`, `active_run_id` in `backend/app/schemas.py`.
- Use `camelCase` for frontend state fields after normalization: `createdAt`, `runId`, `activeTask`, `selectedModelRunnable` in `frontend/app/task-state.ts` and `frontend/hooks/use-task-workspace.ts`.
- Use explicit nullable defaults rather than sentinel strings for optional data: `str | None` in `backend/app/schemas.py`, `Record<string, unknown> | null` in `frontend/app/task-state.ts`.

**Types:**
- Use `PascalCase` for Python dataclasses, Pydantic models, protocols, and type aliases: `Settings` in `backend/app/config.py`, `TaskState` in `backend/app/schemas.py`, `RunnerStorage` in `backend/app/runner/core.py`.
- Use `@dataclass(frozen=True)` for immutable backend data carriers: `Settings` in `backend/app/config.py`, `ExecutionRequest` and `ExecutionResult` in `backend/app/execution/resources.py`.
- Use `Literal` type aliases for finite backend string contracts: `TaskStatus` in `backend/app/schemas.py`, `ArtifactType` and `UploadSourceFormat` in `backend/app/storage.py`.
- Use `PascalCase` TypeScript object and union types: `TaskState`, `ExecutionLog`, `LiveEventMetadata`, and `ConversationStreamItem` in `frontend/app/task-state.ts` and `frontend/app/workspace-view.ts`.

## Code Style

**Formatting:**
- Use Python 3.11 syntax with `from __future__ import annotations` at module top in backend source and tests: `backend/app/config.py`, `backend/app/runner/core.py`, `backend/tests/unit/runner/test_core.py`.
- Keep Python formatting compatible with Ruff line length `100` and target `py311`: `backend/pyproject.toml`.
- Use TypeScript `strict` mode and `noEmit` for frontend source: `frontend/tsconfig.json`.
- Use LF endings for Python, TypeScript, JavaScript, JSON, Markdown, YAML, and TOML; keep PowerShell as CRLF: `.gitattributes`.
- No Prettier or Biome config is present; rely on ESLint, TypeScript, Ruff, and local formatting style: `frontend/eslint.config.mjs`, `backend/pyproject.toml`.

**Linting:**
- Run Ruff across backend source and tests with selected rule families `E`, `F`, `I`, `UP`, `B`, and `SIM`: `backend/pyproject.toml`.
- Keep backend imports sorted by Ruff `I`; do not hand-roll inconsistent import grouping: `backend/pyproject.toml`.
- Run mypy with `check_untyped_defs = true`, `warn_unused_ignores = true`, and `ignore_missing_imports = true`: `backend/pyproject.toml`.
- Run frontend ESLint with Next core-web-vitals and TypeScript rules, and treat all warnings as failures with `--max-warnings=0`: `frontend/eslint.config.mjs`, `frontend/package.json`.
- Keep generated Next files out of lint and source review: `frontend/eslint.config.mjs`, `frontend/.gitignore`.

## Import Organization

**Order:**
1. Future annotations, standard library, third-party, then local application imports in Python: `backend/app/main.py`, `backend/app/runner/core.py`, `backend/tests/unit/api/test_tasks.py`.
2. External React and package imports before local imports in frontend components: `frontend/components/chat/TaskConversation.tsx`, `frontend/components/chat/ChatComposer.tsx`.
3. Type-only imports are marked with `type` in TypeScript: `frontend/components/chat/TaskConversation.tsx`, `frontend/components/chat/ChatComposer.tsx`.
4. Tests import built-in assertion/test modules before local app modules: `frontend/tests/state/test_task_state.test.ts`, `frontend/tests/workspace/test_task_workspace.test.ts`.

**Path Aliases:**
- Backend code uses absolute package imports from `app.*`: `backend/app/api/tasks.py`, `backend/app/runner/core.py`, `backend/app/tools/registry.py`.
- Backend tests import fake support from `tests.*`: `backend/tests/unit/api/test_tasks.py`, `backend/tests/unit/runner/test_core.py`.
- Frontend code uses relative imports; no TypeScript path alias is configured in `frontend/tsconfig.json`: `frontend/lib/task-api.ts`, `frontend/hooks/use-task-workspace.ts`.
- Do not introduce frontend alias imports without adding compiler, lint, and test support in `frontend/tsconfig.json`, `frontend/eslint.config.mjs`, and `frontend/package.json`.

## Error Handling

**Patterns:**
- Translate backend domain and validation errors to stable HTTP status codes at API boundaries: `backend/app/api/tasks.py`, `backend/app/api/files.py`, `backend/app/api/artifacts.py`.
- Use `HTTPException` in FastAPI routers, with user-facing detail strings, and suppress noisy exception chaining for expected 404/400 paths with `from None`: `backend/app/api/tasks.py`.
- Keep task-run failures in storage state through terminal events, not unhandled background exceptions: `backend/app/runner/core.py`.
- Treat best-effort enhancements as non-blocking after a run starts; log and continue for title generation, memory recall/write, and resource manifest context: `backend/app/api/tasks.py`, `backend/app/runner/core.py`.
- Return structured tool-call JSON errors for resource tools instead of raising into the runner: `backend/app/execution/resources.py`.
- Use custom exceptions for backend domain distinctions: `UploadConflictError` and `UploadLimitError` in `backend/app/storage.py`, `ModelProviderError` in `backend/app/models/provider.py`.
- On the frontend, wrap fetch failures and non-JSON responses in localized `Error` messages: `frontend/lib/task-api.ts`, `frontend/app/task-state.ts`.
- Normalize untrusted backend payloads through bounded readers before rendering or copying diagnostics: `frontend/app/task-state.ts`, `frontend/app/workspace-view.ts`.

## Logging

**Framework:** Python `logging`; frontend application code avoids `console`.

**Patterns:**
- Create module-level loggers with `logging.getLogger(__name__)`: `backend/app/main.py`, `backend/app/api/tasks.py`, `backend/app/runner/core.py`, `backend/app/streaming/v2_adapter.py`.
- Use `logger.warning(..., exc_info=True)` for recoverable degraded behavior that needs diagnostics: `backend/app/api/tasks.py`, `backend/app/runner/core.py`.
- Use `logger.exception()` only when re-raising unexpected runner failures: `backend/app/runner/core.py`.
- Use `logger.debug()` for ignored stream chunks or optional implementation details: `backend/app/streaming/v2_adapter.py`, `backend/app/agent/factory.py`.
- Keep browser-side user feedback in React state and rendered notices rather than console output: `frontend/hooks/use-task-workspace.ts`, `frontend/components/chat/TaskConversation.tsx`.

## Comments

**When to Comment:**
- Use module docstrings for backend modules with important boundaries: `backend/app/config.py`, `backend/app/runner/core.py`, `backend/app/execution/resources.py`, `backend/app/streaming/v2_adapter.py`.
- Add comments around security, streaming, lifecycle, or protocol edge cases where the code protects a contract: `backend/app/main.py`, `backend/app/runner/core.py`, `backend/app/streaming/v2_adapter.py`.
- Use inline comments sparingly in frontend pure projection code when distinguishing raw diagnostics from display projection: `frontend/app/workspace-view.ts`.
- Use targeted `# noqa` only when a framework boundary requires it, such as wrapping Starlette private request receive/body internals: `backend/app/main.py`.

**JSDoc/TSDoc:**
- JSDoc is not a dominant frontend pattern; exported TypeScript functions are documented mainly by names, types, and focused tests: `frontend/app/task-state.ts`, `frontend/app/workspace-view.ts`.
- Python docstrings are used on public functions and classes where behavior is non-trivial: `backend/app/models/provider.py`, `backend/app/runner/core.py`, `backend/app/streaming/v2_adapter.py`.

## Function Design

**Size:** Keep route handlers thin and move policy or normalization into helpers.
- FastAPI routers delegate to storage, model validation, runner scheduling, and helpers: `backend/app/api/tasks.py`, `backend/app/api/files.py`.
- Frontend rendering components delegate state and side effects to hooks and pure view helpers: `frontend/components/chat/TaskWorkspace.tsx`, `frontend/hooks/use-task-workspace.ts`, `frontend/app/workspace-view.ts`.

**Parameters:** Prefer explicit typed parameters and keyword-only options for boundary-sensitive calls.
- Backend runner and storage APIs use keyword-only arguments for model, run id, event payloads, and status transitions: `backend/app/runner/core.py`, `backend/app/storage.py`.
- Frontend helpers accept option objects for optional behavior: `buildMessageRequestPayload()` in `frontend/app/task-state.ts`, `fetchTask()` in `frontend/lib/task-api.ts`.

**Return Values:** Return structured records rather than loosely shaped dictionaries at module boundaries.
- Backend API and storage boundaries use Pydantic models: `backend/app/schemas.py`, `backend/app/api/tasks.py`.
- Backend resource tools return `ExecutionResult` and serialize to `{ok,data}` or `{ok,error}` JSON: `backend/app/execution/resources.py`.
- Frontend API functions return normalized `TaskState`, `TaskSummary`, `ExecutionLog`, and `ModelOption` types: `frontend/lib/task-api.ts`, `frontend/app/task-state.ts`.

## Module Design

**Exports:** Use explicit named exports.
- Backend packages expose concrete modules under `app.*`; keep endpoint routers in dedicated files under `backend/app/api/`.
- Frontend components and hooks use named exports: `TaskWorkspace` in `frontend/components/chat/TaskWorkspace.tsx`, `useTaskWorkspace` in `frontend/hooks/use-task-workspace.ts`.
- Keep pure frontend state and view projections separate from React effects: `frontend/app/task-state.ts`, `frontend/app/workspace-view.ts`, `frontend/hooks/use-task-workspace.ts`.
- Keep backend execution boundaries separated by domain: `backend/app/runner/core.py`, `backend/app/execution/resources.py`, `backend/app/streaming/v2_adapter.py`, `backend/app/storage.py`.

**Barrel Files:** Use package `__init__.py` files lightly.
- Backend `__init__.py` files mark packages and occasionally re-export stable execution helpers: `backend/app/execution/__init__.py`, `backend/app/runner/__init__.py`.
- Frontend has no barrel-export pattern; import directly from concrete modules such as `frontend/app/task-state.ts` and `frontend/components/chat/ChatComposer.tsx`.

---

*Convention analysis: 2026-05-19*
