# Testing Patterns

**Analysis Date:** 2026-05-22

## Test Framework

**Runner:**
- Pytest `>=8.0.0`
- Async support: `pytest-asyncio>=0.24.0`
- Config: `backend/pyproject.toml`

**Assertion Library:**
- Native `assert` statements with pytest helpers such as `pytest.raises`, `pytest.mark.parametrize`, `pytest.mark.asyncio`, and `pytest.mark.skipif`.
- FastAPI API tests use `fastapi.testclient.TestClient`.
- Mocking uses pytest `monkeypatch` and standard-library `unittest.mock.patch` / `MagicMock`.

**Run Commands:**
```bash
uv run pytest              # Run all tests with backend/pyproject.toml addopts
uv run pytest -q           # Run all tests quietly
uv run pytest tests/unit   # Run unit tests only
uv run pytest tests/integration   # Run integration tests; env-gated tests skip when services are absent
uv run pytest tests/e2e    # Run end-to-end API/SSE tests
uv run ruff check .        # Lint backend Python files
uv run mypy .              # Type-check backend Python files
```

## Test File Organization

**Location:**
- Tests live under `backend/tests/`.
- Unit tests live under `backend/tests/unit/` and are grouped by app area: `backend/tests/unit/api/`, `backend/tests/unit/runner/`, `backend/tests/unit/storage/`, `backend/tests/unit/streaming/`, `backend/tests/unit/security/`, `backend/tests/unit/tools/`, `backend/tests/unit/skills/`, `backend/tests/unit/models/`, `backend/tests/unit/agent/`, `backend/tests/unit/session/`.
- Integration tests live under `backend/tests/integration/`.
- E2E tests live under `backend/tests/e2e/`.
- Shared fixtures live in `backend/tests/conftest.py`.
- Shared fake infrastructure lives in `backend/tests/fakes.py`.

**Naming:**
- Test modules use `test_<subject>.py`: `backend/tests/unit/api/test_tasks.py`, `backend/tests/unit/runner/test_core.py`, `backend/tests/unit/security/test_auth.py`.
- Test classes use `Test<Subject>` names without inheriting from `unittest.TestCase`: `TestCreateTask`, `TestTaskRunnerStreamState`, `TestScanTextForSecrets`.
- Test functions use `test_<behavior>` names that describe expected behavior: `test_create_task_without_message_is_idle`, `test_memory_recall_failure_is_ignored`, `test_read_events_after_unknown_id_recovers_with_full_event_stream`.
- Helper fakes use leading underscores when scoped to one test module: `_FakeEmbedding` in `backend/tests/integration/test_postgres_memory_storage.py`, `_FakeStreamingAgent` in `backend/tests/unit/runner/test_core.py`.

**Structure:**
```text
backend/tests/
├── conftest.py                      # shared pytest fixtures
├── fakes.py                         # in-memory storage and fake records
├── unit/
│   ├── api/                         # FastAPI route behavior
│   ├── runner/                      # TaskRunner and context/memory orchestration
│   ├── storage/                     # storage invariants and file writes
│   ├── streaming/                   # event conversion and SSE formatting
│   ├── security/                    # auth, permissions, secret scanning
│   ├── tools/                       # SearXNG and resource tools
│   ├── skills/                      # built-in skill discovery/content
│   ├── models/                      # provider and registry behavior
│   ├── agent/                       # DeepAgents factory wiring
│   └── session/                     # session projection
├── integration/
│   ├── test_agent_build.py
│   └── test_postgres_memory_storage.py
└── e2e/
    └── test_streaming_e2e.py
```

## Test Structure

**Suite Organization:**
```python
@pytest.fixture
def app_client(tmp_path):
    settings = Settings(
        task_root=tmp_path / "tasks",
        workspace_root=tmp_path / "tasks",
        deepseek_api_key="sk-test",
    )
    app = create_app(settings, storage=InMemoryTaskStorage(settings.task_root))
    return TestClient(app)


class TestCreateTask:
    def test_create_task_returns_201(self, app_client):
        response = app_client.post("/api/tasks", json={"model": "deepseek-v4-flash"})

        assert response.status_code == 201
        assert response.json()["status"] == "idle"
```

Use this pattern for new API tests near `backend/tests/unit/api/test_tasks.py`: create a local `Settings`, inject `InMemoryTaskStorage`, exercise the route through `TestClient`, and assert the response status plus response body.

**Patterns:**
- Use `tmp_path` for all filesystem state. Do not write to `backend/storage/` in tests.
- Inject `Settings` directly instead of relying on `backend/.env`.
- Use `InMemoryTaskStorage` from `backend/tests/fakes.py` for route, runner, and storage-adjacent unit tests that do not need Postgres.
- Use class groupings for large behavior areas in long test modules: `backend/tests/unit/api/test_tasks.py`, `backend/tests/unit/runner/test_core.py`, `backend/tests/unit/storage/test_storage.py`.
- Use direct API assertions for route behavior and direct object assertions for service behavior.
- Prefer deterministic fake model/tool responses over real provider calls.

## Mocking

**Framework:** pytest `monkeypatch` and `unittest.mock`

**Patterns:**
```python
def test_searxng_search_returns_error_string_when_request_fails(monkeypatch):
    def fake_get(*args, **kwargs):
        raise RuntimeError("connection refused")

    monkeypatch.setattr("app.tools.searxng_search.httpx.get", fake_get)

    result = _run_searxng_search(
        "http://127.0.0.1:8181/",
        "python",
        max_results=5,
        topic="general",
        language="auto",
        timeout_seconds=1.0,
    )

    assert result == "错误：SearXNG 搜索失败 - connection refused"
```

```python
@patch("app.agent.factory._create_model", return_value=_mock_model())
@patch("app.agent.factory.create_deep_agent")
def test_returns_compiled_graph(self, mock_create, mock_model_fn, test_settings):
    fake_graph = MagicMock(spec=CompiledStateGraph)
    mock_create.return_value = fake_graph

    result = build_agent(test_settings)

    assert result is fake_graph
    mock_create.assert_called_once()
```

**What to Mock:**
- Mock network clients (`httpx.get`, `httpx.post`, Qdrant/DashScope boundaries) when testing formatting, error mapping, or service orchestration. See `backend/tests/unit/tools/test_searxng_search.py` and `backend/tests/unit/runner/test_memory.py`.
- Mock model creation and DeepAgents construction in unit tests. See `backend/tests/unit/agent/test_factory.py` and `backend/tests/integration/test_agent_build.py`.
- Mock `stream_agent` and `build_agent` when testing `TaskRunner` event behavior. See `backend/tests/unit/runner/test_core.py`.
- Mock runner background starts in API tests when the endpoint should start a task but not execute an agent. See `backend/tests/unit/api/test_tasks.py`.
- Mock storage methods only to assert a boundary is not crossed, such as upload size rejection before `save_uploads()` in `backend/tests/unit/api/test_main.py`.

**What NOT to Mock:**
- Do not mock FastAPI routing when testing route behavior; use `TestClient(create_app(...))`.
- Do not mock `InMemoryTaskStorage` internals for normal route tests; use it as the fake persistence implementation.
- Do not call real DeepSeek, DashScope, Qdrant, SearXNG, or Postgres in unit tests.
- Do not read `backend/.env` in tests. Use direct `Settings(...)`, `monkeypatch.setenv()`, or env-gated integration tests.

## Fixtures and Factories

**Test Data:**
```python
@pytest.fixture
def test_settings(tmp_path):
    return Settings(
        task_root=tmp_path / "tasks",
        workspace_root=tmp_path / "tasks",
    )
```

```python
@pytest.fixture
def create_idle_task(app_client):
    def _create(model="deepseek-v4-flash"):
        response = app_client.post("/api/tasks", json={"model": model})
        assert response.status_code == 201
        return response.json()

    return _create
```

**Location:**
- Global fixture: `backend/tests/conftest.py` provides `test_settings`.
- API-local fixtures: `backend/tests/unit/api/test_tasks.py` defines `app_client` and `create_idle_task`.
- E2E-local fixtures: `backend/tests/e2e/test_streaming_e2e.py` defines `app_client` and `_collect_sse()`.
- Fake persistence: `backend/tests/fakes.py` implements `InMemoryTaskStorage` and related in-memory records.
- File fixture helpers should stay near the tests that use them, such as `_write_docx()` and `_write_xlsx()` in `backend/tests/unit/tools/test_resource_execution.py`.

## Coverage

**Requirements:** No enforced coverage threshold detected in `backend/pyproject.toml`.

**View Coverage:**
```bash
uv run pytest              # Standard suite; no coverage plugin configured
```

Coverage practice is behavior-driven rather than percentage-gated. Add tests around observable API responses, event payloads, storage invariants, security checks, and integration boundaries affected by the change.

## Test Types

**Unit Tests:**
- Scope: isolated behavior in services, routers, storage helpers, event conversion, security scanning, tools, and model registry.
- Location: `backend/tests/unit/`.
- Use direct function/class calls for pure logic, as in `backend/tests/unit/streaming/test_event_converter.py` and `backend/tests/unit/security/test_scanner.py`.
- Use `TestClient` plus `InMemoryTaskStorage` for route logic, as in `backend/tests/unit/api/test_tasks.py`, `backend/tests/unit/api/test_main.py`, `backend/tests/unit/security/test_auth.py`.
- Use fake event streams and monkeypatched agent/model functions for runner behavior, as in `backend/tests/unit/runner/test_core.py`.

**Integration Tests:**
- Scope: wiring that spans infrastructure or external-service adapters.
- Location: `backend/tests/integration/`.
- Use env-gated `pytest.mark.skipif` for tests that need Postgres, Qdrant, or DashScope. `backend/tests/integration/test_postgres_memory_storage.py` reads `MYAGENT_TEST_DATABASE_URL` or `MYAGENT_DATABASE_URL` and skips placeholder values.
- Keep integration tests deterministic by replacing expensive or external subparts with fakes where possible, such as `_FakeEmbedding` in `backend/tests/integration/test_postgres_memory_storage.py`.

**E2E Tests:**
- Framework: FastAPI `TestClient`.
- Location: `backend/tests/e2e/`.
- Current E2E coverage focuses on SSE streaming records and completion ordering in `backend/tests/e2e/test_streaming_e2e.py`.
- E2E tests still use in-memory storage and direct app construction; they validate end-to-end API behavior without launching a separate Uvicorn process.

## Common Patterns

**Async Testing:**
```python
@pytest.mark.asyncio
async def test_start_scopes_streamed_events_to_current_run(test_settings, monkeypatch):
    async def fake_stream_agent(agent, messages, config):
        yield {"type": "message_chunk", "data": {"content": "partial answer"}}

    monkeypatch.setattr("app.runner.core.build_agent", lambda *args, **kwargs: object())
    monkeypatch.setattr("app.runner.core.stream_agent", fake_stream_agent)

    runner = TaskRunner(test_settings)
    records, latest_state = await runner.start("task-1", "hello", run_id="run-1")

    assert {record.run_id for record in records} == {"run-1"}
```

Use `pytest.mark.asyncio` for coroutine tests in `backend/tests/unit/runner/`, `backend/tests/unit/streaming/`, and model-title generation tests. For isolated async helper checks that are not pytest-asyncio tests, `asyncio.run()` is used in `backend/tests/unit/api/test_main.py`.

**Error Testing:**
```python
with pytest.raises(ModelProviderError, match="DEEPSEEK_API_KEY"):
    create_model(DEEPSEEK_V4_FLASH_MODEL_ID, test_settings)
```

```python
try:
    storage.task_dir("..")
except ValueError:
    pass
else:
    raise AssertionError("Expected ValueError for path traversal")
```

Prefer `pytest.raises(..., match=...)` for new exception assertions. Existing tests also use explicit `try`/`except` plus `AssertionError`; follow the surrounding style when editing a local block.

**API Response Testing:**
```python
response = client.post("/api/tasks", json={"message": "hello"})

assert response.status_code == 400
assert response.json()["detail"] == "模型服务未配置，请先在后端配置对应 API Key"
```

Assert both HTTP status and response details for API failures. Include exact Chinese response text when it is part of the API contract, as in `backend/tests/unit/api/test_tasks.py` and `backend/tests/unit/security/test_auth.py`.

**Security Testing:**
```python
results = scan_text_for_secrets("Bearer not_a_real_token_999", source="test.txt")

assert any(f.pattern == "bearer-token" for f in results)
```

Security tests intentionally use fake placeholder secrets and `# ggignore` comments in `backend/tests/unit/security/test_scanner.py`. Keep new samples fake and never use values from `backend/.env`.

**External-Service Integration Guards:**
```python
@pytest.mark.skipif(not _database_url(), reason="Postgres integration env is not configured")
def test_postgres_event_seq_survives_storage_reinstantiation(tmp_path):
    ...
```

Use skip guards for tests that need local services or credentials. Treat placeholder env values from `backend/.env.example` as not configured.

---

*Testing analysis: 2026-05-22*
