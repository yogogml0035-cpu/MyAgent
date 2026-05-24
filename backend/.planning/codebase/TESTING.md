# 后端测试模式

**分析日期：** 2026-05-24

## 测试框架

- Runner：pytest。
- 异步支持：pytest-asyncio。
- API 测试：FastAPI `TestClient`。
- 断言：原生 `assert`、`pytest.raises`、`pytest.mark.parametrize`、`pytest.mark.asyncio`。
- Mock：pytest `monkeypatch` 与标准库 `unittest.mock.patch` / `MagicMock`。

## 常用命令

```bash
cd backend
uv run pytest
uv run pytest -q
uv run pytest tests/unit
uv run pytest tests/integration
uv run pytest tests/e2e
uv run ruff check .
uv run mypy app tests
```

## 测试组织

```text
backend/tests/
|-- conftest.py                 # 共享 pytest fixtures
|-- fakes.py                    # 内存 storage fake 和 fake records
|-- unit/
|   |-- api/                    # FastAPI route 行为
|   |-- runner/                 # TaskRunner、context、memory、并发
|   |-- storage/                # storage 不变量和文件写入
|   |-- streaming/              # event conversion、SSE formatting
|   |-- security/               # auth、permission、secret scan
|   |-- tools/                  # SearXNG 和 resource tools
|   |-- skills/                 # 内置技能发现和内容
|   |-- models/                 # provider 和 registry
|   |-- agent/                  # DeepAgents factory wiring
|   `-- session/                # session projection
|-- integration/
|   |-- test_agent_build.py
|   `-- test_postgres_memory_storage.py
`-- e2e/
    `-- test_streaming_e2e.py
```

## 命名和结构

- 测试文件：`test_<subject>.py`。
- 测试类：`Test<Subject>`，不继承 `unittest.TestCase`。
- 测试函数：`test_<behavior>`，描述可观察行为。
- 单模块 fake/helper 使用 `_` 前缀。
- API 测试常见模式：构造 `Settings(task_root=tmp_path / "tasks")`，注入 `InMemoryTaskStorage`，用 `TestClient(create_app(...))` 请求并断言 response status/body。

## Fixture 和数据

- 所有文件系统状态使用 `tmp_path`，不要写入 `backend/storage/`。
- 测试直接注入 `Settings`，不要依赖 `backend/.env`。
- route、runner 和 storage-adjacent unit test 优先使用 `backend/tests/fakes.py` 的 `InMemoryTaskStorage`。
- 需要 Postgres、Qdrant、DashScope 的测试必须 env-gated skip。
- 文件 fixture helper 放在使用它们的测试附近。

## Mock 规则

应该 mock：

- 网络 client：`httpx.get`, `httpx.post`、Qdrant/DashScope boundary。
- 模型创建和 DeepAgents 构建。
- `stream_agent`、`build_agent` 等 runner 边界。
- API 测试中不希望真正执行 agent 的 background start。

不应该 mock：

- FastAPI routing；route 行为用 `TestClient`。
- `InMemoryTaskStorage` 的内部细节。
- 单元测试中不要调用真实 DeepSeek、DashScope、Qdrant、SearXNG 或 Postgres。
- 不读取 `backend/.env`。

## 测试类型

### 单元测试

- 覆盖 service、router、storage helper、event conversion、security scanner、tools、model registry。
- pure logic 直接调用函数/类。
- route logic 用 TestClient + InMemoryTaskStorage。
- runner 用 fake event stream 和 monkeypatch agent/model。

### 集成测试

- 覆盖需要基础设施语义的 wiring。
- 用 `pytest.mark.skipif` 按 env var 跳过未配置服务。
- 能 fake 的昂贵外部部分应 fake，例如 embedding。

### 端到端测试

- 当前后端 E2E 使用 FastAPI TestClient 验证 API/SSE 端到端行为，不启动独立 Uvicorn。
- 重点覆盖流事件 shape、终态 drain-before-done 和 completion ordering。

## 常见模式

- async 测试使用 `pytest.mark.asyncio`。
- 新异常断言优先 `pytest.raises(..., match=...)`。
- API failure 断言 status 和 body detail，中文错误文案是合同时需要精确断言。
- 安全测试只使用 fake placeholder secrets 或 canary，不使用真实 env 值。
- 外部服务测试用 skip guard，`.env.example` 占位值视为未配置。

## 覆盖与验证实践

- 没有强制 coverage threshold。
- 新行为应围绕 API response、event payload、storage invariant、安全检查和集成边界补测试。
- 文档-only 变更至少运行 `git diff --check`。
- 涉及后端行为的变更通常运行 `uv run pytest`、`uv run ruff check .`、`uv run mypy app tests`。

---

*测试分析：2026-05-24*
