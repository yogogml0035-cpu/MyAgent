# 测试模式

**分析日期：** 2026-05-19

## 测试命令

后端：

```bash
cd backend
uv run pytest
uv run ruff check .
uv run mypy app tests
```

前端：

```bash
cd frontend
npm run typecheck
npm test
npm run lint
npm run build
```

浏览器 E2E：

```bash
cd frontend
npm run e2e:runtime-contracts
```

文档和空白：

```bash
git diff --check
```

## 后端测试结构

- `backend/tests/unit/`：按 agent、api、models、runner、security、session、skills、storage、streaming、tools 分组。
- `backend/tests/integration/`：Postgres、memory、agent build 等集成测试。
- `backend/tests/e2e/`：后端 SSE 端到端行为。
- `backend/tests/fakes.py`：内存版 storage fake，必须和生产 storage 契约保持一致。
- `backend/tests/conftest.py`：共享 pytest fixtures。

## 前端测试结构

- `frontend/tests/state/`：状态归一化和 artifact 安全。
- `frontend/tests/workspace/`：workspace projection、组件边界和源码不变量。
- `frontend/tests/upload/`：上传过滤和上传展示相关测试。
- `frontend/tests/model/`：模型展示 helper。
- `frontend/e2e-playwright/`：浏览器 E2E specs。
- `frontend/e2e-playwright/e2e-YYYYMMDDHHMMSS/`：本地截图证据，不提交。

## 什么时候跑什么

- 只改文档：至少跑 `git diff --check`。
- 改后端 API/storage/runner/streaming：跑后端相关单测，必要时跑集成测试。
- 改前端状态、URL、artifact 或展示投影：跑前端 Node 测试。
- 改 UI、交互、任务流、上传、SSE、产物打开或全栈行为：必须跑实际服务上的 Playwright E2E，并保存截图证据。
- 改视觉：截图要覆盖默认态、关键交互态和窄屏或受影响布局。

## 测试原则

- 行为变更不能只靠读代码确认。
- 单测不能替代浏览器 E2E。
- 接口自测不能替代用户可见路径验证。
- Playwright 失败先看 trace、screenshot、video 和日志；必要时再用浏览器现场诊断。
- 新增公开 storage 契约时，同步生产 storage、fake storage 和契约测试。
