# Testing Patterns

**Analysis Date:** 2026-05-19

## Test Framework

**Runner:**
- pytest 9.0.3 with pytest-asyncio 1.3.0.
- Config: `backend/pyproject.toml` with `testpaths = ["tests"]`, `pythonpath = ["."]`, and `addopts = "-q --capture=tee-sys"`.

**Assertion Library:**
- Plain `assert`, `pytest.raises`, `pytest.mark.asyncio`, and FastAPI `TestClient`.

**Run Commands:**
```bash
cd backend
uv run pytest
uv run ruff check .
uv run mypy app tests
```

## Test File Organization

**Location:**
- Unit tests: `backend/tests/unit/<subsystem>/test_*.py`.
- Integration tests: `backend/tests/integration/test_*.py`.
- Backend E2E tests: `backend/tests/e2e/test_*.py`.
- Shared fixtures: `backend/tests/conftest.py`.
- Shared in-memory storage fake: `backend/tests/fakes.py`.

**Naming:**
- Python test files use `test_*.py`.
- Test classes use descriptive subsystem names, such as `TestCreateTask` or `TestTaskRunnerMemory`.
- Test functions describe expected behavior, such as `test_read_events_after_unknown_id_recovers_with_full_event_stream`.

**Structure:**
```text
backend/tests/
├── conftest.py
├── fakes.py
├── unit/
│   ├── agent/test_*.py
│   ├── api/test_*.py
│   ├── models/test_*.py
│   ├── runner/test_*.py
│   ├── security/test_*.py
│   ├── session/test_*.py
│   ├── skills/test_*.py
│   ├── storage/test_*.py
│   ├── streaming/test_*.py
│   └── tools/test_*.py
├── integration/test_*.py
└── e2e/test_*.py
```

## Test Structure

**Suite Organization:**
```python
@pytest.fixture
def app_client(tmp_path):
    settings = Settings(task_root=tmp_path / "tasks", workspace_root=tmp_path / "tasks")
    app = create_app(settings, storage=InMemoryTaskStorage(settings.task_root))
    return TestClient(app)

class TestCreateTask:
    def test_create_task_returns_201(self, app_client):
        response = app_client.post("/api/tasks", json={"model": "deepseek:deepseek-chat"})
        assert response.status_code == 201
```

**Patterns:**
- Use class grouping for API, runner, storage, and model contract tests.
- Use `pytest.mark.asyncio` for async runner and stream tests.
- Patch expensive or external boundaries with `monkeypatch`.
- Validate exact response status and detail strings for public API errors.

## Mocking

**Framework:**
- `pytest.monkeypatch`, local fake classes, `InMemoryTaskStorage`, and FastAPI `TestClient`.

**Patterns:**
```python
monkeypatch.setattr("app.runner.core.build_agent", lambda *args, **kwargs: object())
monkeypatch.setattr("app.runner.core.stream_agent", fake_stream_agent)
```

```python
runner = cast(Any, client.app).state.runner
original_start = runner.start_background
runner.start_background = mock_start_background
try:
    response = client.post("/api/tasks", json={"message": "hello"})
finally:
    runner.start_background = original_start
```

**What to Mock:**
- Model provider calls, DeepAgents graph construction, stream agents, Qdrant, DashScope embeddings, SearXNG HTTP, file parser edge cases, and background runner scheduling when a test targets API contracts.

**What NOT to Mock:**
- Public storage contract shape when the test is specifically about API, runner, events, uploads, artifacts, or summaries.
- Fake storage parity; `backend/tests/fakes.py` must remain aligned with `PostgresTaskStorage`.

## Fixtures and Factories

**Test Data:**
- `test_settings` in `backend/tests/conftest.py` creates temporary task/workspace roots with no real API keys.
- `InMemoryTaskStorage` in `backend/tests/fakes.py` mirrors task state, runs, events, uploads, artifacts, context summaries, agent store, cache, and memory rows.
- Local helpers are kept near test files, such as fake streaming agents in runner/streaming tests and document builders in resource tests.

**Location:**
- Shared broad fixtures belong in `backend/tests/conftest.py`.
- Cross-subsystem fake storage belongs in `backend/tests/fakes.py`.
- Specialized factories stay in the nearest `test_*.py`.

## Coverage

**Requirements:**
- No numeric coverage threshold is configured.
- Risk-driven coverage is expected for changed API, runner, storage, streaming, model, security, resource, or memory behavior.

**View Coverage:**
```bash
# No coverage command is configured in backend/pyproject.toml.
```

## Test Types

**Unit Tests:**
- API contracts under `backend/tests/unit/api/`.
- Runner and memory orchestration under `backend/tests/unit/runner/`.
- Streaming adapter and converter under `backend/tests/unit/streaming/`.
- Tool/resource behavior under `backend/tests/unit/tools/`.
- Storage and fake parity risks under `backend/tests/unit/storage/`.
- Security scanner under `backend/tests/unit/security/`.

**Integration Tests:**
- Agent factory wiring in `backend/tests/integration/test_agent_build.py`.
- Postgres and memory storage integration in `backend/tests/integration/test_postgres_memory_storage.py`, gated by external env/services.

**E2E Tests:**
- Backend SSE behavior in `backend/tests/e2e/test_streaming_e2e.py`.
- Browser/full-stack E2E lives in the frontend subproject and must be run for UI-visible or behavior-changing full-stack work.

## Common Patterns

**Async Testing:**
```python
@pytest.mark.asyncio
async def test_memory_recall_failure_is_ignored(test_settings, monkeypatch):
    runner = TaskRunner(test_settings, memory_service=FailingRecallMemoryService())
    _, state = await runner.start("task-1", "hello", run_id="run-1")
    assert state["messages"]
```

**Error Testing:**
```python
response = app_client.post("/api/tasks", json={"model": "fake:model"})
assert response.status_code == 400
assert response.json()["detail"] == "模型不在允许列表中"
```

**Storage Event Testing:**
- Assert ordered event IDs/seq values and cursor recovery through `read_events(after_id=...)`.
- Test both task state and emitted event payload when changing lifecycle behavior.

---

*Testing analysis: 2026-05-19*
*Update when backend test structure, commands, or mocking contracts change*
