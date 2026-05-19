# 后端测试

**分析日期：** 2026-05-19

## 命令

```bash
cd backend
uv run pytest
uv run ruff check .
uv run mypy app tests
```

## 测试框架

- pytest：主要测试框架。
- pytest-asyncio：异步 runner 和 streaming 测试。
- FastAPI TestClient：API contract 测试。
- `pytest.monkeypatch`：替换模型、agent、stream、外部服务和后台调度。

## 目录结构

```text
backend/tests/
├── conftest.py
├── fakes.py
├── unit/
│   ├── agent/
│   ├── api/
│   ├── models/
│   ├── runner/
│   ├── security/
│   ├── session/
│   ├── skills/
│   ├── storage/
│   ├── streaming/
│   └── tools/
├── integration/
└── e2e/
```

## 测试重点

- API：状态码、detail、任务状态、事件和错误边界。
- runner：run_id 传递、stream 事件、终态、取消、记忆召回和写入。
- storage：任务、运行、事件 cursor、上传、产物、cache、memory、agent store。
- streaming：LangGraph v2 chunk 转换、final answer 提取、SSE 格式。
- tools：上传资源读取、Word/Excel/JSON/TXT 处理、结构化错误。
- models：模型 ID、provider 创建、可运行性。
- security：敏感内容扫描和脱敏。

## Fake Storage

- `backend/tests/fakes.py` 是后端测试中的内存版 storage。
- 它必须尽量模拟 `PostgresTaskStorage` 的公开契约。
- 新增 storage 方法、状态转换、事件格式、上传或产物行为时，必须同步 fake 和生产实现。

## 何时补测试

- 改 API：补或改 `backend/tests/unit/api/`。
- 改 runner：补或改 `backend/tests/unit/runner/`。
- 改 stream：补或改 `backend/tests/unit/streaming/`。
- 改 storage：补或改 `backend/tests/unit/storage/`，必要时补 integration。
- 改工具：补或改 `backend/tests/unit/tools/`。
- UI 可见行为变更还需要前端 Playwright E2E。
