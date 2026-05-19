# 后端架构

**分析日期：** 2026-05-19

## 总览

`backend/` 是 MyAgent 的服务器端运行时。它用 FastAPI 暴露任务 API，用 Postgres 保存任务事实状态，用本地文件系统保存上传和产物，并用进程内 `TaskRunner` 调用 DeepAgents。

## 核心层次

- 应用壳：`backend/app/main.py` 创建 FastAPI app，加载 settings、storage、memory、runner，安装认证、CORS 和请求限制。
- API 路由：`backend/app/api/` 暴露 tasks、files、artifacts、streaming、models。
- 存储权威层：`backend/app/storage.py` 管理 Postgres 表、任务状态、事件游标、上传、产物、缓存、长期记忆和 agent store。
- 运行时编排：`backend/app/runner/core.py` 负责一次任务 run 的生命周期、取消、终态和事件持久化。
- Agent 构建：`backend/app/agent/factory.py` 包装 `deepagents.create_deep_agent()`，接入模型、工具、skills、subagents 和任务级文件系统。
- Streaming 转换：`backend/app/streaming/` 把 LangGraph/DeepAgents stream chunk 转换为稳定平台事件。
- 资源工具：`backend/app/execution/resources.py` 和 `backend/app/tools/registry.py` 提供上传资源读取和搜索工具。
- 模型、记忆、安全：`backend/app/models/`、`backend/app/memory.py`、`backend/app/security/scanner.py` 处理 provider、长期记忆和敏感内容过滤。

## 任务运行数据流

1. 前端调用 `POST /api/tasks` 或 `POST /api/tasks/{task_id}/messages`。
2. API 校验模型、任务状态和请求内容。
3. `storage.start_run()` 写入用户消息、run row 和 `running` 状态。
4. `runner.start_background()` 创建进程内异步运行。
5. runner 读取任务上下文、上传资源 manifest 和长期记忆。
6. runner 构建 DeepAgents graph 并消费 stream。
7. stream adapter 和 converter 生成 `EventRecord`。
8. storage 追加有序事件。
9. 成功时写入助手消息、`final_answer` 和 `task_completed`；失败/取消/超时时写入对应终态。

## SSE 数据流

1. 前端连接 `GET /api/tasks/{task_id}/stream`。
2. 后端从 storage 轮询有序事件。
3. 未知 cursor 会回放完整事件流。
4. runner 停止后，SSE drain 剩余事件并发送 `done`。

## 上传和产物流

- 上传通过 `POST /api/tasks/{task_id}/files`。
- storage 做文件数量、扩展名、重复名、大小、JSON 格式和路径安全检查。
- 上传文件保存在任务 workspace 中，并写入上传事件。
- Agent 工具通过任务级 resource adapter 检查或读取上传文件。
- 产物按 run 范围写入 `artifacts/runs/{run_id}/`，通过 artifact API 下载或打开。

## 关键边界

- Postgres 是状态和事件的权威来源。
- 本地 task root 是上传和产物 bytes 的权威来源。
- 进程内 `TaskRunner._active_runs` 只代表当前进程的活跃运行。
- 多 worker 不受支持，配置层会拒绝 worker 数大于 1。
- 文件系统工具必须限制在当前任务 workspace 内。
