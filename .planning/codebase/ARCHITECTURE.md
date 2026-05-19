# 架构地图

**分析日期：** 2026-05-19

## 系统概览

MyAgent 是一个本地优先的 DeepAgents 任务工作台。浏览器端用 Next.js 提供聊天式工作区；后端用 FastAPI 接收任务、上传文件、运行 agent、持久化事件；Postgres 保存任务事实状态，本地文件系统保存上传和产物。

```text
浏览器 / Next.js
  frontend/app/page.tsx
  frontend/components/chat/
  frontend/hooks/use-task-workspace.ts
        |
        | REST / multipart upload / SSE / artifact blob
        v
FastAPI 后端
  backend/app/main.py
  backend/app/api/
        |
        | task / run / message / event / file
        v
运行时和存储
  backend/app/runner/core.py
  backend/app/storage.py
  backend/app/agent/factory.py
        |
        v
外部与本地服务
  Postgres / Qdrant / embeddings / 模型 Provider / SearXNG / backend/storage/sessions/
```

## 主要层次

- 前端入口层：`frontend/app/page.tsx` 挂载工作区，`frontend/components/chat/` 负责展示。
- 前端编排层：`frontend/hooks/use-task-workspace.ts` 负责创建任务、上传、发送消息、SSE 重连、取消和产物操作。
- 前端接口层：`frontend/lib/task-api.ts` 封装 REST、SSE 和 artifact blob 请求。
- 前端状态层：`frontend/app/task-state.ts` 把后端 `snake_case` 数据转换成前端 `camelCase` 状态。
- 后端应用层：`backend/app/main.py` 创建 FastAPI app，安装认证、CORS、请求限制和路由。
- 后端 API 层：`backend/app/api/` 暴露任务、文件、产物、模型和 SSE 接口。
- 后端运行层：`backend/app/runner/core.py` 调用 DeepAgents、工具、上下文和记忆服务。
- 后端存储层：`backend/app/storage.py` 是 Postgres 状态和本地文件 workspace 的权威边界。

## 核心数据流

1. 用户在前端输入消息。
2. 前端通过 `frontend/lib/task-api.ts` 调用后端任务 API。
3. 后端创建任务、保存用户消息、写入事件，并启动 `TaskRunner`。
4. runner 构建 agent、任务级文件系统、工具、上下文和记忆。
5. DeepAgents/LangGraph 产生流式事件。
6. `backend/app/streaming/` 把原始 chunk 转换为平台事件。
7. storage 按顺序持久化事件和终态。
8. 前端通过 SSE 或事件轮询读取事件，刷新消息、日志和产物。

## 稳定边界

- Postgres 是任务、运行、消息、事件、缓存和长期记忆行的权威存储。
- 本地文件系统是上传和产物 bytes 的权威存储。
- SSE 只是持久化事件的投影，不是状态来源。
- 当前 runner 是进程内 active run registry，只支持单进程运行。
- 前端组件不直接理解后端原始字段，字段转换集中在 `frontend/app/task-state.ts`。

## 维护提示

- 改任务生命周期时，同时看 `backend/app/api/tasks.py`、`backend/app/runner/core.py`、`backend/app/storage.py` 和前端状态层。
- 改事件或日志时，同时更新后端 streaming tests、前端 state/view tests 和受影响的 Playwright 场景。
- 改前端视觉时先读 `DESIGN.md`，再改 `frontend/app/globals.css` 和相关组件。
- 改跨系统边界时同步根级 `ARCHITECTURE.md`、`INTERFACES.md` 和本目录事实文档。
