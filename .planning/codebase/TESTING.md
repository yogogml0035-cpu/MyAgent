# Testing Patterns

**Analysis Date:** 2026-05-19

## Test Framework

**Runner:**
- Backend: `pytest` with `pytest-asyncio`; configured in `backend/pyproject.toml` with `testpaths = ["tests"]`, `pythonpath = ["."]`, and `addopts = "-q --capture=tee-sys"`.
- Frontend unit/state tests: Node's built-in `node --test` runner with `tsx`, invoked by `frontend/package.json`.
- Browser E2E: Playwright via `@playwright/test`; reusable specs live under `frontend/e2e-playwright/`.
- Jest and Vitest are not detected; do not add Jest/Vitest-only patterns without adding config and scripts under `frontend/`.

**Assertion Library:**
- Backend: plain `assert`, `pytest.raises`, `pytest.mark.asyncio`, and FastAPI `TestClient`: `backend/tests/unit/api/test_tasks.py`, `backend/tests/unit/runner/test_core.py`.
- Frontend Node tests: `node:assert/strict` or `node:assert`: `frontend/tests/state/test_task_state.test.ts`, `frontend/tests/workspace/test_task_workspace.test.ts`.
- Browser E2E: Playwright `expect`: `frontend/e2e-playwright/test_runtime_contracts.spec.mjs`, `frontend/e2e-playwright/test_upload_preview_design.spec.mjs`.

**Run Commands:**
```bash
cd backend
uv run pytest              # Run backend tests from backend/pyproject.toml
uv run ruff check .        # Backend lint
uv run mypy app tests      # Backend type check
```

```bash
cd frontend
npm test                   # Run frontend node:test suites through tsx
npm run typecheck          # Run next typegen and tsc --noEmit
npm run lint               # ESLint with --max-warnings=0
npm run build              # Production Next build
```

```bash
cd frontend
npm run e2e:runtime-contracts
npx playwright test e2e-playwright/test_upload_preview_design.spec.mjs --reporter=line
```

```bash
git diff --check           # Required whitespace check for docs-only changes
```

## Test File Organization

**Location:**
- Backend unit tests are grouped by subsystem under `backend/tests/unit/agent/`, `backend/tests/unit/api/`, `backend/tests/unit/models/`, `backend/tests/unit/runner/`, `backend/tests/unit/security/`, `backend/tests/unit/session/`, `backend/tests/unit/skills/`, `backend/tests/unit/storage/`, `backend/tests/unit/streaming/`, and `backend/tests/unit/tools/`.
- Backend integration tests live under `backend/tests/integration/`, including Postgres and agent-build coverage in `backend/tests/integration/test_postgres_memory_storage.py` and `backend/tests/integration/test_agent_build.py`.
- Backend SSE E2E tests live under `backend/tests/e2e/test_streaming_e2e.py`.
- Frontend unit/state tests are grouped under `frontend/tests/state/`, `frontend/tests/workspace/`, `frontend/tests/upload/`, and `frontend/tests/model/`.
- Browser E2E specs live under `frontend/e2e-playwright/`; run-specific screenshots and downloads go under ignored `frontend/e2e-playwright/e2e-YYYYMMDDHHMMSS/` directories.

**Naming:**
- Python tests use `test_*.py`: `backend/tests/unit/api/test_tasks.py`, `backend/tests/unit/streaming/test_v2_adapter.py`.
- Frontend Node tests use `test_*.test.ts`: `frontend/tests/state/test_task_state.test.ts`, `frontend/tests/workspace/test_workspace_view.test.ts`.
- Playwright specs use `test_*.spec.mjs`: `frontend/e2e-playwright/test_runtime_contracts.spec.mjs`, `frontend/e2e-playwright/test_resource_upload_harness.spec.mjs`.

**Structure:**
```text
backend/tests/
├── conftest.py
├── fakes.py
├── unit/<subsystem>/test_*.py
├── integration/test_*.py
└── e2e/test_*.py

frontend/tests/
├── state/test_*.test.ts
├── workspace/test_*.test.ts
├── upload/test_*.test.ts
└── model/test_*.test.ts

frontend/e2e-playwright/
├── test_*.spec.mjs
└── e2e-YYYYMMDDHHMMSS/<scenario>/ screenshots and local evidence
```

## Test Structure

**Suite Organization:**
```python
# backend/tests/unit/api/test_tasks.py
@pytest.fixture
def app_client(tmp_path):
    settings = Settings(task_root=tmp_path / "tasks", workspace_root=tmp_path / "tasks")
    return TestClient(create_app(settings, storage=InMemoryTaskStorage(settings.task_root)))

class TestCreateTask:
    def test_create_task_returns_201(self, app_client):
        response = app_client.post("/api/tasks", json={"model": "deepseek:deepseek-chat"})
        assert response.status_code == 201
```

```typescript
// frontend/tests/state/test_task_state.test.ts
test("mergeExecutionLogs appends only new events by id", () => {
  const merged = mergeExecutionLogs(existing, incoming);
  assert.deepEqual(merged.map((log) => log.id), ["event-a", "event-b", "event-c"]);
});
```

```javascript
// frontend/e2e-playwright/test_upload_preview_design.spec.mjs
test("selected upload preview matches the warm-canvas design", async ({ page }) => {
  const evidenceDir = requirePath(process.env.MYAGENT_E2E_EVIDENCE_DIR, "MYAGENT_E2E_EVIDENCE_DIR");
  await page.goto("/");
  await page.screenshot({ fullPage: true, path: path.join(evidenceDir, "01-empty-composer.png") });
});
```

**Patterns:**
- Use class-based grouping for backend subsystem tests when it improves scanability: `backend/tests/unit/api/test_tasks.py`, `backend/tests/unit/storage/test_storage.py`.
- Use direct top-level `test()` calls for frontend pure functions: `frontend/tests/state/test_task_state.test.ts`, `frontend/tests/workspace/test_workspace_view.test.ts`.
- Use `describe()` and `it()` sparingly for grouped dynamic import/export smoke checks: `frontend/tests/workspace/test_task_workspace.test.ts`, `frontend/tests/workspace/test_task_api.test.ts`.
- Use browser-visible assertions and screenshots in Playwright specs: `frontend/e2e-playwright/test_runtime_contracts.spec.mjs`, `frontend/e2e-playwright/test_progress_log_disclosure.spec.mjs`.

## Mocking

**Framework:** `pytest.monkeypatch`, local fake classes, in-memory storage, Node source inspection, and Playwright request/page fixtures.

**Patterns:**
```python
# backend/tests/unit/runner/test_core.py
monkeypatch.setattr("app.runner.core.build_agent", lambda *args, **kwargs: object())
monkeypatch.setattr("app.runner.core.stream_agent", fake_stream_agent)
```

```python
# backend/tests/unit/api/test_tasks.py
runner = cast(Any, client.app).state.runner
original_start = runner.start_background
runner.start_background = mock_start_background
try:
    response = client.post(
        "/api/tasks",
        json={"message": "hello", "model": "deepseek:deepseek-chat"},
    )
finally:
    runner.start_background = original_start
```

```typescript
// frontend/tests/workspace/test_task_workspace.test.ts
const source = readFileSync(new URL("../../hooks/use-task-workspace.ts", import.meta.url), "utf-8");
assert.strictEqual(source.includes("buildSandboxedArtifactPreviewDocument"), true);
```

**What to Mock:**
- Mock external model calls, deepagents graph construction, streaming agents, HTTP calls, Qdrant, and workbook/doc parsing when the test targets orchestration contracts: `backend/tests/unit/agent/test_factory.py`, `backend/tests/unit/runner/test_core.py`, `backend/tests/unit/tools/test_resource_execution.py`.
- Use `InMemoryTaskStorage` for API and runner tests that need public storage behavior without Postgres: `backend/tests/fakes.py`, `backend/tests/unit/api/test_tasks.py`.
- Use Playwright `request` and direct Postgres seeding only in browser E2E specs that validate full runtime contracts: `frontend/e2e-playwright/test_runtime_contracts.spec.mjs`, `frontend/e2e-playwright/test_progress_log_disclosure.spec.mjs`.

**What NOT to Mock:**
- Do not weaken public task storage contracts in `backend/tests/fakes.py`; fake storage must mirror `PostgresTaskStorage` for state, events, uploads, runs, and artifacts.
- Do not replace browser E2E with source inspection or unit tests for behavior-changing frontend flows; encode user-visible results in Playwright specs under `frontend/e2e-playwright/`.
- Do not mock artifact URL security or upload validation at the frontend only; backend API tests and frontend normalization tests both cover the contract: `backend/tests/unit/api/test_artifacts.py`, `frontend/tests/state/test_task_state.test.ts`.

## Fixtures and Factories

**Test Data:**
```python
# backend/tests/conftest.py
@pytest.fixture
def test_settings(tmp_path):
    return Settings(task_root=tmp_path / "tasks", workspace_root=tmp_path / "tasks")
```

```python
# backend/tests/unit/tools/test_resource_execution.py
def _task_upload_dir(tmp_path, task_id: str):
    upload_dir = tmp_path / task_id / "uploads"
    upload_dir.mkdir(parents=True)
    return upload_dir
```

```javascript
// frontend/e2e-playwright/test_upload_preview_design.spec.mjs
function writeFixtureFiles(evidenceDir) {
  const fixtureDir = path.join(evidenceDir, "fixtures");
  fs.mkdirSync(fixtureDir, { recursive: true });
  return fixtureDir;
}
```

**Location:**
- Shared backend settings fixture: `backend/tests/conftest.py`.
- Shared backend in-memory storage fake: `backend/tests/fakes.py`.
- Backend local helper factories stay in the nearest test file: `_FakeStreamingAgent` in `backend/tests/unit/streaming/test_v2_adapter.py`, `_write_docx()` in `backend/tests/unit/tools/test_resource_execution.py`.
- Frontend Playwright fixture files are created under the scenario evidence directory: `frontend/e2e-playwright/test_upload_preview_design.spec.mjs`, `frontend/e2e-playwright/test_resource_upload_harness.spec.mjs`.

## Coverage

**Requirements:** No numeric coverage threshold is configured in `backend/pyproject.toml` or `frontend/package.json`.

**View Coverage:**
```bash
# No coverage command is configured. Add one only with matching CI support.
```

## Test Types

**Unit Tests:**
- Backend unit tests target contracts at API, runner, streaming, tool, storage, model, security, skills, and session boundaries: `backend/tests/unit/`.
- Frontend unit tests target normalization, projection, hook exports, upload filters, model UI, and architecture/source invariants: `frontend/tests/`.

**Integration Tests:**
- Backend integration tests validate agent factory wiring and Postgres/Qdrant memory storage contracts when dependencies are configured: `backend/tests/integration/test_agent_build.py`, `backend/tests/integration/test_postgres_memory_storage.py`.
- Repository CI runs script syntax, PowerShell help/dry-run, stop-port dry-run, and whitespace checks: `.github/workflows/repository-ci.yml`.

**E2E Tests:**
- Backend SSE E2E uses FastAPI `TestClient` and fake storage to verify SSE event format, done handling, and draining behavior: `backend/tests/e2e/test_streaming_e2e.py`.
- Frontend browser E2E uses Playwright against running services, environment-provided API URLs, and local evidence directories: `frontend/e2e-playwright/README.md`, `frontend/e2e-playwright/test_runtime_contracts.spec.mjs`.
- Behavior-changing frontend or full-stack work requires relevant Playwright coverage and screenshot evidence under `frontend/e2e-playwright/e2e-YYYYMMDDHHMMSS/`.

## Common Patterns

**Async Testing:**
```python
# backend/tests/unit/runner/test_core.py
@pytest.mark.asyncio
async def test_memory_recall_failure_is_ignored(test_settings, monkeypatch):
    runner = TaskRunner(test_settings, memory_service=FailingRecallMemoryService())
    _, state = await runner.start("task-1", "hello", run_id="run-1")
    assert state["messages"]
```

**Error Testing:**
```python
# backend/tests/unit/api/test_tasks.py
response = app_client.post("/api/tasks", json={"model": "fake:model"})
assert response.status_code == 400
assert response.json()["detail"] == "模型不在允许列表中"
```

```typescript
// frontend/tests/state/test_task_state.test.ts
assert.throws(
  () => buildArtifactRequest(artifact, "task-1", "http://localhost:8001", "secret-token"),
  /URL/,
);
```

**Browser Evidence:**
- Require `MYAGENT_E2E_EVIDENCE_DIR` in Playwright specs and fail fast when it is absent: `frontend/e2e-playwright/test_upload_preview_design.spec.mjs`, `frontend/e2e-playwright/test_runtime_contracts.spec.mjs`.
- Capture screenshots at key state changes, not only final states: `frontend/e2e-playwright/test_runtime_contracts.spec.mjs`, `frontend/e2e-playwright/test_resource_upload_harness.spec.mjs`.
- Keep timestamped evidence folders ignored by git and reference them in delivery notes: `frontend/e2e-playwright/README.md`, `.gitignore`.

---

*Testing analysis: 2026-05-19*
