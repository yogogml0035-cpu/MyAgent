# Coding Conventions

**Analysis Date:** 2026-05-19

## Naming Patterns

**Files:**
- Use `snake_case.py` for source modules: `backend/app/conversation_context.py`, `backend/app/task_titles.py`.
- Use package directories for domains: `backend/app/api/`, `backend/app/runner/`, `backend/app/streaming/`.
- Use `test_*.py` for tests under `backend/tests/`.

**Functions:**
- Use `snake_case` for functions and helpers: `load_settings()`, `_validate_runnable_model()`, `extract_final_answer()`.
- Prefix private helpers with `_`, especially inside route and projection modules.
- Use explicit async functions for async FastAPI endpoints that schedule runner work, such as `create_task()` and `send_message()`.

**Variables:**
- Use `UPPER_SNAKE_CASE` for module constants: `MODEL_REGISTRY`, `UPLOAD_FORMATS`, `RUN_ARTIFACT_NAMES`.
- Use backend `snake_case` for public API fields: `task_id`, `created_at`, `active_run_id`.
- Use `None` for optional data rather than sentinel strings.

**Types:**
- Use `PascalCase` for dataclasses, Pydantic models, protocols, and type aliases: `Settings`, `TaskState`, `RunnerStorage`.
- Use `@dataclass(frozen=True)` for immutable carriers such as `Settings`, `ExecutionRequest`, and `ExecutionResult`.
- Use `Literal` for finite string contracts such as `TaskStatus` and upload/artifact type aliases.

## Code Style

**Formatting:**
- Put `from __future__ import annotations` near the top of backend modules.
- Keep formatting compatible with Ruff line length 100 and Python 3.11 target in `backend/pyproject.toml`.
- Prefer explicit type annotations at module boundaries.

**Linting:**
- Run `uv run ruff check .` from `backend/`.
- Ruff selected families are `E`, `F`, `I`, `UP`, `B`, and `SIM`; imports should stay Ruff-sortable.
- Run `uv run mypy app tests`; mypy checks untyped defs and warns on unused ignores.

## Import Organization

**Order:**
1. Future annotations.
2. Standard library.
3. Third-party packages.
4. Local `app.*` imports.
5. Test-only `tests.*` imports inside tests.

**Path Aliases:**
- Backend application imports use absolute package paths such as `from app.schemas import TaskState`.
- Tests import fakes and fixtures through `tests.*`, such as `from tests.fakes import InMemoryTaskStorage`.

## Error Handling

**Patterns:**
- Convert expected route errors to `HTTPException` with stable detail strings.
- Use `from None` when intentionally suppressing exception chains for expected 404/400 cases.
- Keep background runner failures in task state through terminal events, not only logs.
- Return structured tool-call JSON errors from resource tools rather than raising through the agent graph.
- Log degraded best-effort behavior, such as title generation or memory recall/write failure, and continue where safe.

**Error Types:**
- Domain exceptions include `UploadConflictError`, `UploadLimitError`, `ModelProviderError`, and `MemoryServiceError`.
- Use `ValueError` for invalid task IDs, artifact names, run IDs, filenames, and unsupported uploads inside storage/resource code.

## Logging

**Framework:**
- Python `logging` with module-level `logger = logging.getLogger(__name__)`.

**Patterns:**
- Use `logger.warning(..., exc_info=True)` for recoverable degraded behavior.
- Use `logger.exception()` around unexpected runner failures that are re-raised.
- Use `logger.debug()` for ignored stream chunks or internal setup details.
- User-visible runtime diagnostics should be persisted as `EventRecord` rows when they matter to the UI.

## Comments

**When to Comment:**
- Use module docstrings for important boundaries such as configuration, runner, resource tools, and streaming adapter.
- Add comments for security, lifecycle, streaming, or protocol edge cases.
- Avoid comments that restate obvious code.

**Docstrings:**
- Public classes and non-trivial public functions usually have short docstrings.
- Tests use descriptive test names rather than long comments.

## Function Design

**Size:**
- Keep route handlers thin; delegate lifecycle rules to storage, runner, model registry, and helpers.
- Split stream conversion and event display shaping into helpers rather than adding route logic.

**Parameters:**
- Prefer keyword-only parameters for boundary-sensitive calls: run IDs, model IDs, status transitions, artifact names.
- Use explicit protocols for collaborators in orchestration code, such as `RunnerStorage` and `RunnerMemoryService`.

**Return Values:**
- Return Pydantic models at API/storage boundaries.
- Return structured dataclasses or JSON payloads from resource execution helpers.
- Avoid loosely shaped dicts except where interacting with provider payloads or event metadata.

## Module Design

**Exports:**
- Prefer named functions/classes from concrete modules.
- Keep endpoint routers in dedicated files.
- Keep storage, runner, model provider, and stream adapter responsibilities separated even when they collaborate closely.

**Barrel Files:**
- `__init__.py` files are lightweight package markers.
- Import directly from concrete modules unless an `__init__.py` intentionally re-exports a stable helper.

---

*Convention analysis: 2026-05-19*
*Update when backend style, naming, or module-boundary conventions change*
