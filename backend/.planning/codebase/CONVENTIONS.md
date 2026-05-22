# Coding Conventions

**Analysis Date:** 2026-05-22

## Naming Patterns

**Files:**
- Use lowercase snake_case Python module names for application code: `backend/app/task_titles.py`, `backend/app/memory_admin.py`, `backend/app/reasoning_trace.py`.
- Group HTTP routers by API surface under `backend/app/api/`: `backend/app/api/tasks.py`, `backend/app/api/files.py`, `backend/app/api/artifacts.py`, `backend/app/api/streaming.py`.
- Group domain packages by responsibility under `backend/app/`: agent construction in `backend/app/agent/`, model providers in `backend/app/models/`, streaming conversion in `backend/app/streaming/`, security scanning in `backend/app/security/`, skill discovery in `backend/app/skills/`, resource tools in `backend/app/execution/`.
- Use `__init__.py` in package directories even when empty: `backend/app/api/__init__.py`, `backend/app/runner/__init__.py`, `backend/tests/unit/api/__init__.py`.
- Test files use `test_<subject>.py` and mirror the app package when practical: `backend/tests/unit/api/test_tasks.py` covers `backend/app/api/tasks.py`; `backend/tests/unit/streaming/test_event_converter.py` covers `backend/app/streaming/event_converter.py`.
- Built-in project skills live under `backend/skills/<skill-name>/SKILL.md`, for example `backend/skills/web_research/SKILL.md` and `backend/skills/code_review/SKILL.md`.

**Functions:**
- Use snake_case for public functions, private helpers, and pytest fixtures: `create_app()` in `backend/app/main.py`, `load_settings()` in `backend/app/config.py`, `safe_filename()` in `backend/app/storage.py`, `app_client()` in `backend/tests/unit/api/test_tasks.py`.
- Prefix module-private helper functions with `_`: `_storage()`, `_runner()`, `_get_existing_task()` in `backend/app/api/tasks.py`; `_run_searxng_search()` and `_search_params()` in `backend/app/tools/searxng_search.py`; `_sanitize_memory_segment()` in `backend/app/memory.py`.
- Use verb-first names for stateful operations and validators: `validate_run_id()` in `backend/app/storage.py`, `normalize_artifact_name()` in `backend/app/storage.py`, `authorize_task_request()` in `backend/app/main.py`.
- Async functions are used at I/O or event-loop boundaries: `create_task()` and `send_message()` in `backend/app/api/tasks.py`, `TaskRunner.start()` and `TaskRunner.cancel()` in `backend/app/runner/core.py`.

**Variables:**
- Use snake_case for locals and parameters: `task_id`, `run_id`, `memory_context`, `max_upload_file_bytes`.
- Use UPPER_SNAKE_CASE for module constants: `DEEPSEEK_V4_FLASH_MODEL_ID` in `backend/app/config.py`, `UPLOAD_CHUNK_SIZE` in `backend/app/storage.py`, `SEARCH_TOOL_NAME` in `backend/app/tools/searxng_search.py`, `SENSITIVE_REDACTION` in `backend/app/security/scanner.py`.
- Use descriptive collection names with typed literals where the value set is stable: `TaskStatus` in `backend/app/schemas.py`, `ArtifactType` in `backend/app/storage.py`, `EventLevel` in `backend/app/contracts/__init__.py`.

**Types:**
- Use Pydantic `BaseModel` classes for request and response DTOs in `backend/app/schemas.py`.
- Use frozen `@dataclass` classes for immutable internal records and configuration: `Settings` in `backend/app/config.py`, `RetrievedMemory` and `ExtractedMemory` in `backend/app/memory.py`, resource records in `backend/app/execution/resources.py`.
- Use `Protocol` for structural dependencies that are injected into services: `RunnerStorage` and `RunnerMemoryService` in `backend/app/runner/core.py`, `LongTermMemoryStorage` in `backend/app/memory.py`, `ConversationStorage` in `backend/app/conversation_context.py`.
- Use modern Python 3.11 union syntax and generic built-ins: `str | None`, `list[EventRecord]`, `dict[str, Any]`.
- Use `Literal` and `TypeAlias` for constrained string domains: `TaskMode`, `InputScope`, and `TaskStatus` in `backend/app/schemas.py`; `UploadSourceFormat` in `backend/app/storage.py`.

## Code Style

**Formatting:**
- Ruff is the formatting and linting authority through `backend/pyproject.toml`.
- Use Python 3.11 syntax; `backend/pyproject.toml` sets `requires-python = ">=3.11"` and Ruff `target-version = "py311"`.
- Keep line length at 100 characters where practical; `backend/pyproject.toml` sets `tool.ruff.line-length = 100`, while rule `E501` is ignored for occasional long literals.
- Add `from __future__ import annotations` at the top of Python modules; this appears across `backend/app/config.py`, `backend/app/main.py`, `backend/app/storage.py`, and tests.
- Prefer explicit UTF-8 file I/O for text: `read_text(encoding="utf-8")` and `write_text(..., encoding="utf-8")` in `backend/app/config.py`, `backend/app/storage.py`, `backend/app/skills/loader.py`, and tests.

**Linting:**
- Ruff lint rules selected in `backend/pyproject.toml`: `E`, `F`, `I`, `UP`, `B`, `SIM`.
- Ignored Ruff rules in `backend/pyproject.toml`: `B008`, `B904`, `E501`, `UP017`.
- Mypy is configured in `backend/pyproject.toml` with `check_untyped_defs = true`, `warn_unused_ignores = true`, and `ignore_missing_imports = true`.
- Use `# noqa` only for narrow, intentional exceptions, such as Starlette private request body hooks in `backend/app/main.py`.

## Import Organization

**Order:**
1. `from __future__ import annotations`
2. Standard library imports: `logging`, `pathlib.Path`, `typing`, `dataclasses`, `collections.abc`
3. Third-party imports: `fastapi`, `httpx`, `pydantic`, `langchain_core`, `psycopg`, `openpyxl`, `docx`
4. Local `app.*` imports
5. Test-only `tests.*` imports

**Path Aliases:**
- Runtime and tests import from the backend root using absolute package paths like `from app.config import Settings` and `from tests.fakes import InMemoryTaskStorage`.
- `backend/pyproject.toml` sets `pythonpath = ["."]` for pytest, so new tests should import `app.*` directly rather than using relative imports.
- Inside application modules, both package-relative imports and absolute `app.*` imports are present. Follow the local module style: `backend/app/main.py` uses relative imports such as `from .config import Settings`, while routers in `backend/app/api/tasks.py` use `from app.config import Settings`.

## Error Handling

**Patterns:**
- API routers translate storage and validation errors into explicit `HTTPException` responses. Use `404` for missing tasks or artifacts, `400` for invalid input, `409` for running-state conflicts, and `413` for upload/request limits, following `backend/app/api/tasks.py`, `backend/app/api/files.py`, and `backend/app/api/artifacts.py`.
- Suppress exception chaining with `from None` when internal details should not leak to API callers, as in `_get_existing_task()` in `backend/app/api/tasks.py`.
- Preserve exception causes with `from exc` when wrapping lower-level failures into domain errors, as in `backend/app/memory.py` and upload handling in `backend/app/storage.py`.
- Use custom exception classes for domain boundaries: `RequestBodyTooLarge` in `backend/app/main.py`, `ModelProviderError` in `backend/app/models/provider.py`, `MemoryServiceError` in `backend/app/memory.py`, `UploadConflictError` and `UploadLimitError` in `backend/app/storage.py`, `SecretScanViolation` in `backend/app/security/scanner.py`.
- Tool-facing functions return structured or readable error payloads instead of crashing the agent when failures are expected. Examples: SearXNG returns strings prefixed by `错误：` in `backend/app/tools/searxng_search.py`; resource tools return `{"ok": False, "error": {...}}` in `backend/app/execution/resources.py`.
- Recoverable background failures should log and continue when the user-facing task can proceed. Examples: title generation in `backend/app/api/tasks.py`, memory recall and resource manifest provisioning in `backend/app/runner/core.py`, memory extraction in `backend/app/memory.py`.
- Startup should fail fast when required production services are missing: `create_app()` collects missing `MYAGENT_DATABASE_URL`, DashScope, or Qdrant failures in `backend/app/main.py`.

## Logging

**Framework:** Python standard `logging`

**Patterns:**
- Define `logger = logging.getLogger(__name__)` at module scope for modules that log: `backend/app/main.py`, `backend/app/api/tasks.py`, `backend/app/runner/core.py`, `backend/app/memory.py`, `backend/app/skills/loader.py`, `backend/app/task_titles.py`.
- Use `logger.info()` for expected lifecycle events, such as interrupted running tasks in `backend/app/main.py` and skipped sensitive memory recall in `backend/app/memory.py`.
- Use `logger.warning(..., exc_info=True)` for recoverable failures where stack traces help diagnostics but execution continues, such as long-term memory recall in `backend/app/runner/core.py` and skill discovery read failures in `backend/app/skills/loader.py`.
- Use `logger.exception()` when re-raising unexpected runner failures, as in `TaskRunner.start()` in `backend/app/runner/core.py`.
- Do not log or emit secret values. Secret scanning and redaction live in `backend/app/security/scanner.py`; configuration documents secret variable names in `backend/.env.example` without requiring secret values.

## Comments

**When to Comment:**
- Use module docstrings for files with clear ownership or integration boundaries: `backend/app/tools/searxng_search.py`, `backend/app/tools/filesystem_bridge.py`, `backend/app/agent/factory.py`, `backend/app/api/tasks.py`.
- Use class/function docstrings for public helpers and services that define contracts: `Settings` in `backend/app/config.py`, `TaskRunner.start()` in `backend/app/runner/core.py`, `_ReadOnlyBackend` in `backend/app/agent/factory.py`.
- Add short inline comments only for non-obvious behavior or compatibility requirements, such as final-answer synthetic events in `backend/app/runner/core.py` and defensive future LangGraph operation handling in `backend/app/agent_store.py`.
- Do not add comments that restate a single obvious assignment or assertion.

**JSDoc/TSDoc:**
- Not applicable. This backend is Python-only.

## Function Design

**Size:** Keep API route functions small and delegate stateful behavior to storage, runner, model, memory, or execution modules. Larger orchestrators are acceptable in `backend/app/storage.py`, `backend/app/runner/core.py`, and `backend/app/execution/resources.py` when they protect a single domain boundary.

**Parameters:** Prefer explicit typed parameters and keyword-only options for optional behavior. Examples: `create_model(model_id, settings, *, temperature=0.0)` in `backend/app/models/provider.py`, `TaskRunner.start(..., *, model=None, run_id, on_event=None)` in `backend/app/runner/core.py`, and storage methods in `backend/app/storage.py`.

**Return Values:** Return typed DTOs or domain records at boundaries: FastAPI handlers return Pydantic models from `backend/app/schemas.py`; storage returns `TaskState`, `TaskSummary`, `EventRecord`, and dataclass records from `backend/app/storage.py`; resource execution returns `ExecutionResult` from `backend/app/execution/resources.py`.

## Module Design

**Exports:** Prefer direct named exports from focused modules. Avoid broad re-export layers except package markers. Examples: import `create_app` from `backend/app/main.py`, `TaskRunner` from `backend/app/runner/core.py`, `create_model` from `backend/app/models/provider.py`, and `discover_skills` from `backend/app/skills/loader.py`.

**Barrel Files:** `__init__.py` files mostly mark packages and are not used as broad barrel modules. Keep new code importable from its implementation module unless an existing package explicitly exposes a stable public surface.

**Skill-defined constraints:**
- Project skills are first-class runtime content. Keep built-in skills under `backend/skills/<skill-name>/SKILL.md` and discover them through `backend/app/skills/project.py` and `backend/app/skills/loader.py`.
- Skill files are mounted read-only into DeepAgents through `backend/app/agent/factory.py`; preserve the `_ReadOnlyBackend` pattern when changing skill access.
- `backend/skills/web_research/SKILL.md` assumes SearXNG-backed search via `backend/app/tools/searxng_search.py`.
- `backend/skills/code_review/SKILL.md` frames code-review behavior around quality, security, best practices, performance, and test coverage; keep backend review support aligned with `backend/app/security/scanner.py` and the test patterns in `backend/tests/unit/security/`.

---

*Convention analysis: 2026-05-22*
