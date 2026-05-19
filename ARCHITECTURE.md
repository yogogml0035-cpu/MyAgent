# MyAgent Architecture

本文件是 MyAgent 的系统级架构地图。它承接跨子项目的稳定边界和理解路径；后端、前端内部实现事实以 `backend/.planning/codebase/` 和 `frontend/.planning/codebase/` 为准。

## 系统边界

MyAgent 是一个本地优先的浏览器任务工作台：浏览器端 Next.js 应用负责用户工作区和状态投影，FastAPI 后端负责任务生命周期、DeepAgents 运行时、持久化事件、上传资源、产物和模型服务边界。

```text
Browser / Next.js workspace
  frontend/app/page.tsx
  frontend/components/chat/
  frontend/hooks/use-task-workspace.ts
        |
        | REST JSON, multipart upload, artifact blob, SSE
        v
FastAPI backend
  backend/app/main.py
  backend/app/api/
        |
        | task state, events, uploads, artifacts
        v
Runtime and storage
  backend/app/runner/core.py
  backend/app/storage.py
  backend/app/agent/factory.py
        |
        | model calls, search, embeddings, vector index, local files
        v
External/local services
  Postgres, Qdrant, DashScope-compatible embeddings,
  model providers, SearXNG, backend/storage/sessions/
```

## 子系统职责

### `backend/`

后端拥有所有服务器端权威状态和运行时边界：

- FastAPI app、认证、CORS、请求体限制和路由注册。
- 任务创建、消息发送、取消、历史、事件轮询和 SSE。
- Postgres 任务、运行、消息、事件、工具缓存、长期记忆和 LangGraph store。
- 本地上传与产物文件管理，默认路径为 `backend/storage/sessions/`。
- DeepAgents agent 构建、任务级文件系统、运行时 skills、subagents、工具注册和 streaming 转换。
- 模型 Provider、DashScope-compatible embeddings、Qdrant 长期记忆和 SearXNG 搜索。

后端事实入口：

- `backend/.planning/codebase/ARCHITECTURE.md`
- `backend/.planning/codebase/STRUCTURE.md`
- `backend/.planning/codebase/INTEGRATIONS.md`
- `backend/.planning/codebase/CONCERNS.md`
- `backend/.planning/codebase/TESTING.md`

### `frontend/`

前端拥有所有浏览器端状态投影和交互体验：

- Next.js app router 页面入口和聊天工作区。
- REST/SSE/blob API adapter、后端字段归一化、artifact URL 信任检查。
- React hook 编排：模型加载、任务历史、创建任务、上传、发送消息、SSE 重连、轮询恢复、取消、重命名、删除、产物打开或下载。
- 纯 view projection：日志分组、运行进度、会话排序、诊断 JSON、展示标签。
- 全局 CSS、响应式布局、设计 token、Playwright 浏览器验收和截图证据。

前端事实入口：

- `frontend/.planning/codebase/ARCHITECTURE.md`
- `frontend/.planning/codebase/STRUCTURE.md`
- `frontend/.planning/codebase/INTEGRATIONS.md`
- `frontend/.planning/codebase/CONCERNS.md`
- `frontend/.planning/codebase/TESTING.md`

### `asset/`

`asset/` 是长期主题知识层，不是一次性日志层。它保存跨多次需求都会复用的业务规则、输入输出、运行边界、验证入口和回归风险。

当前主要知识包：

- `asset/deepagents_platform_knowledge_pack.md`
- `asset/bid_analysis_workflow_knowledge_pack.md`
- `asset/tender_workflow_breakdown.md`

### `scripts/`

`scripts/` 提供本地 WSL 开发服务入口和端口清理入口。默认后端端口是 `8001`，默认前端端口是 `3001`。涉及服务启动、端口清理、watcher 或本地开发方式变化时，同步根文档和 README。

## 主要数据流

### 任务创建和运行

1. 前端在 `frontend/app/page.tsx` 挂载 `TaskWorkspace`。
2. `frontend/hooks/use-task-workspace.ts` 通过 `frontend/lib/task-api.ts` 调用后端。
3. 后端 `backend/app/api/tasks.py` 验证模型和任务状态。
4. `backend/app/storage.py` 创建或更新任务、运行、消息和事件。
5. `backend/app/runner/core.py` 启动进程内异步任务，构建 agent、工具、上下文、长期记忆和资源 manifest。
6. DeepAgents/LangGraph stream 由 `backend/app/streaming/` 归一化为平台事件并持久化。
7. 终态由后端写入 Postgres，前端刷新任务状态并展示消息、日志和产物。

### SSE 和恢复

SSE 只是持久化事件的浏览器投影。后端从 storage 读取有序事件，前端按事件 ID 合并去重。未知或漂移的游标应触发完整有序事件恢复，而不是静默丢弃旧事件。

### 上传和产物

上传由前端 multipart 请求进入后端文件接口，后端做权威扩展名、大小、JSON 格式和路径安全校验。产物由后端按 task/run 范围提供，前端必须通过 `frontend/app/task-state.ts` 的 URL 信任检查后再携带 token 获取。

### 长期记忆

Postgres 是长期记忆的 canonical store；Qdrant 是语义检索索引；DashScope-compatible embeddings 负责向量生成。上传原文、完整产物正文、工具原始日志、密钥和客户敏感内容不能进入长期记忆。

## 稳定目录职责

- `backend/app/api/`：HTTP 路由边界。
- `backend/app/storage.py`：Postgres 状态和本地文件 workspace 权威层。
- `backend/app/runner/`：任务运行生命周期、取消、终态、事件持久化。
- `backend/app/agent/`：DeepAgents 构建和后端 store/filesystem 边界。
- `backend/app/streaming/`：stream chunk 到平台事件的转换。
- `backend/app/execution/` 和 `backend/app/tools/`：上传资源工具和平台工具注册。
- `backend/tests/`：后端单元、集成和后端 E2E 验证。
- `frontend/app/`：app router、全局样式、纯状态归一化和 view projection。
- `frontend/components/chat/`：聊天工作区展示组件。
- `frontend/hooks/`：浏览器工作流副作用。
- `frontend/lib/`：REST/SSE/blob API adapter。
- `frontend/tests/`：前端 Node/source 测试。
- `frontend/e2e-playwright/`：浏览器验收 specs 和本地截图证据。

## 系统维护建议

- 后端行为变化优先从 API、storage、runner、streaming 的公共契约回推测试。
- 前端行为变化优先从 `task-state.ts`、`use-task-workspace.ts`、`workspace-view.ts` 和用户可见页面回推测试。
- 前后端事件、产物 URL、字段名或认证边界变更必须同步更新 `INTERFACES.md`。
- 视觉变化必须先读 `DESIGN.md`，再改 `frontend/app/globals.css` 和相关组件。
- 当前运行模式是单进程 runner；多 worker、多主机、远程文件存储或多用户会话都不是已有能力，不能当成已经支持。
