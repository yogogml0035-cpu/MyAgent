# MyAgent Architecture

本文件是仓库级系统总览。子项目内部实现事实以
`backend/.planning/codebase/` 和 `frontend/.planning/codebase/` 为准；本文件只保留跨子系统边界、职责和推荐理解路径。

## 系统边界

MyAgent 是一个本地优先的 AI 智能体工作区，由 FastAPI 后端、Next.js 前端和长期知识包组成。

```text
Browser
  |
  | REST / SSE / artifact blob
  v
frontend/
  Next.js app router shell
  React chat workspace
  task-api transport adapter
  state and view normalization
  |
  | HTTP API contract
  v
backend/
  FastAPI API layer
  in-process DeepAgents/LangGraph runner
  PostgreSQL task/event/message store
  local upload and artifact files
  memory/search/model integrations
  |
  | provider and storage boundaries
  v
DeepSeek / DashScope embeddings / Qdrant / SearXNG / Postgres / local filesystem
```

## 子系统职责

### `backend/`

后端是任务生命周期和运行时状态的权威来源。它负责：

- 通过 `backend/app/main.py` 组装 FastAPI app、认证、CORS、运行时服务和路由。
- 通过 `backend/app/api/` 暴露任务、文件、产物、模型、技能和 SSE 端点。
- 通过 `backend/app/runner/core.py` 启动和取消进程内 agent run。
- 通过 `backend/app/storage.py` 持久化任务、运行、消息、事件、工具缓存、长期记忆元数据以及上传/产物文件。
- 通过 `backend/app/agent/`、`backend/app/tools/`、`backend/app/execution/` 连接 DeepAgents/LangGraph、项目技能、SearXNG 搜索和上传资源工具。
- 通过 `backend/app/memory.py`、DashScope embeddings、Qdrant 和 Postgres 提供长期记忆能力。

后端内部事实入口：

- `backend/.planning/codebase/ARCHITECTURE.md`
- `backend/.planning/codebase/INTEGRATIONS.md`
- `backend/.planning/codebase/STACK.md`
- `backend/.planning/codebase/TESTING.md`
- `backend/.planning/codebase/CONCERNS.md`

### `frontend/`

前端是浏览器工作区和后端 API 的客户端适配层。它负责：

- 通过 `frontend/app/layout.tsx` 和 `frontend/app/page.tsx` 提供 Next.js app router shell。
- 通过 `frontend/components/chat/` 渲染历史侧栏、会话流、日志、产物卡片和输入区。
- 通过 `frontend/hooks/use-task-workspace.ts` 管理浏览器侧任务状态、提交、取消、轮询/SSE 合并、产物打开和用户错误提示。
- 通过 `frontend/lib/task-api.ts` 集中封装 REST、SSE、multipart upload 和 artifact blob 请求。
- 通过 `frontend/app/task-state.ts` 和 `frontend/app/workspace-view.ts` 标准化后端 payload 并生成 JSX 友好的展示模型。
- 通过 `frontend/app/globals.css` 维护当前工作区视觉系统。

前端内部事实入口：

- `frontend/.planning/codebase/ARCHITECTURE.md`
- `frontend/.planning/codebase/INTEGRATIONS.md`
- `frontend/.planning/codebase/STACK.md`
- `frontend/.planning/codebase/TESTING.md`
- `frontend/.planning/codebase/CONCERNS.md`

### `asset/`

`asset/` 保存长期主题知识包。涉及招投标分析、平台运行边界、稳定业务规则、输入输出约束或回归风险时，应把长期知识同步到对应知识包，而不是只留在代码或一次性任务记录里。

## 推荐理解路径

通用上手：

1. `AGENTS.md`
2. `ARCHITECTURE.md`
3. `INTERFACES.md`
4. `backend/.planning/codebase/ARCHITECTURE.md`
5. `frontend/.planning/codebase/ARCHITECTURE.md`
6. 相关子项目的 `STRUCTURE.md`、`TESTING.md` 和 `CONCERNS.md`

后端任务从 HTTP 入口进入，落到 Postgres 状态、任务事件、上传/产物文件和进程内 runner。前端任务从 `TaskWorkspace` 进入，由 `use-task-workspace` 编排浏览器状态，并且只通过 `frontend/lib/task-api.ts` 与后端通信。

## 稳定目录职责

- `backend/app/api/`：HTTP/SSE 路由和请求边界。
- `backend/app/runner/`：agent run 生命周期和流事件落库。
- `backend/app/storage.py`：Postgres 状态和本地文件的权威存储边界。
- `backend/app/memory.py`：长期记忆、embedding 和 Qdrant 集成。
- `backend/skills/`：后端挂载给 agent 的项目技能。
- `frontend/app/`：Next shell、状态规范化、展示模型和全局样式。
- `frontend/components/chat/`：聊天工作区 UI 组件。
- `frontend/hooks/`：浏览器工作区控制器。
- `frontend/lib/`：浏览器到后端的传输适配。
- `frontend/tests/`：前端 Node 单元测试。
- `frontend/e2e-playwright/`：浏览器验收和本地截图证据。
- `asset/`：长期知识包。

## 系统维护建议

- 系统边界变化时先更新 `ARCHITECTURE.md` 和 `INTERFACES.md`，再同步 `AGENTS.md`。
- 子项目内部事实变化时刷新对应的 `.planning/codebase/`，不要把实现细节复制进根级文档。
- 行为变更需要同时考虑代码、测试、前后端接口、浏览器 E2E 证据和长期知识包。
- 当前后端 runner 是进程内单 worker 模型；启用多 worker 或横向扩展前，需要先引入外部任务队列、租约、心跳和跨进程事件发布。
