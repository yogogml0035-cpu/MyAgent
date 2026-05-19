# 代码结构

**分析日期：** 2026-05-19

## 顶层目录

```text
MyAgent/
├── AGENTS.md                         # 仓库级导航和执行边界
├── ARCHITECTURE.md                   # 根级系统架构说明
├── INTERFACES.md                     # 根级跨系统接口说明
├── DESIGN.md                         # 前端视觉设计依据
├── README.md                         # 项目使用说明
├── asset/                            # 长期知识包
├── backend/                          # FastAPI、DeepAgents、存储和后端测试
├── frontend/                         # Next.js 前端、Node 测试和 Playwright E2E
├── scripts/                          # 本地 WSL 开发脚本
├── Study/                            # 学习材料
├── Beginner Learning Docs/           # 初学者教学示例
├── .github/workflows/                # CI 工作流
└── .planning/codebase/               # 仓库级代码事实文档
```

## 子项目目录

### `backend/`

- `backend/app/`：后端应用包。
- `backend/app/api/`：任务、文件、产物、SSE、模型接口。
- `backend/app/runner/`：任务运行生命周期。
- `backend/app/agent/`：DeepAgents 构建和后端 store/filesystem。
- `backend/app/streaming/`：stream chunk 到平台事件的转换。
- `backend/app/execution/`：上传资源的读取和检查工具。
- `backend/app/tools/`：平台工具注册和 SearXNG 搜索。
- `backend/tests/`：pytest 单元、集成和后端 E2E。
- `backend/.planning/codebase/`：后端事实文档。

### `frontend/`

- `frontend/app/`：Next app router、全局 CSS、状态归一化和 view projection。
- `frontend/components/chat/`：聊天工作区展示组件。
- `frontend/hooks/`：React 副作用和任务工作流编排。
- `frontend/lib/`：浏览器 API adapter。
- `frontend/tests/`：Node 单元和源码边界测试。
- `frontend/e2e-playwright/`：浏览器 E2E specs 和本地截图证据。
- `frontend/.planning/codebase/`：前端事实文档。

## 重要入口

- 后端 ASGI：`backend/app/main.py`
- 后端任务 API：`backend/app/api/tasks.py`
- 后端 runner：`backend/app/runner/core.py`
- 前端页面：`frontend/app/page.tsx`
- 前端工作区：`frontend/components/chat/TaskWorkspace.tsx`
- 前端工作流 hook：`frontend/hooks/use-task-workspace.ts`
- 前端 API adapter：`frontend/lib/task-api.ts`
- 前端状态转换：`frontend/app/task-state.ts`

## 新代码放哪里

- 新后端接口：`backend/app/api/`，schema 放 `backend/app/schemas.py`。
- 新任务状态或存储契约：`backend/app/storage.py`，同步 `backend/tests/fakes.py`。
- 新 runner 或 stream 行为：`backend/app/runner/` 和 `backend/app/streaming/`。
- 新上传资源能力：`backend/app/execution/resources.py` 和 `backend/app/tools/registry.py`。
- 新前端 API 调用：`frontend/lib/task-api.ts`，状态转换放 `frontend/app/task-state.ts`。
- 新前端工作流：`frontend/hooks/use-task-workspace.ts`。
- 新前端展示：`frontend/components/chat/` 和 `frontend/app/globals.css`。
- 新浏览器验收：`frontend/e2e-playwright/test_*.spec.mjs`。

## 生成目录

- `backend/storage/sessions/`：本地任务上传和产物，不提交。
- `.next/`、`.next-dev/`、`.next-dev-e2e/`：前端构建或开发产物，不提交。
- `frontend/e2e-playwright/e2e-YYYYMMDDHHMMSS/`：E2E 截图证据，不提交。
- `.pytest_cache/`、`.ruff_cache/`、`.mypy_cache/`、`node_modules/`：工具缓存或依赖，不提交。
