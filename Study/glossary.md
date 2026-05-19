# 术语表

## Task

一次会话或任务的长期容器。一个 Task 有标题、状态、消息、事件、上传文件、产物和多次 Run。

相关代码：

- `backend/app/schemas.py` 的 `TaskState`
- `backend/app/api/tasks.py`
- `frontend/app/task-state.ts`

## Run

一次模型执行。一个 Task 可以多次发送消息，因此可以有多个 Run。Run 有自己的 `run_id`，用于把消息、事件、产物关联起来。

相关代码：

- `backend/app/storage.py` 的 `start_run`
- `backend/app/schemas.py` 的 `TaskRunRecord`

## Event

追加式事件日志。模型流式输出、工具调用、任务完成、失败、取消都会变成 Event。前端的进度日志主要来自这些 Event。

关键点：`seq` 是后端同一 task 内的顺序事实，比显示时间更适合作为展示排序依据。当前前端的展示投影层 `workspace-view.ts` 会按 `seq` 优先排序；`task-state.ts` 里的 `mergeExecutionLogs` 只负责按 id 去重和追加。

相关代码：

- `backend/app/storage.py` 的 `append_event`、`read_events`
- `backend/app/streaming/event_converter.py`
- `frontend/app/task-state.ts`
- `frontend/app/workspace-view.ts`

## Runner

负责把一次用户消息变成一次 Agent 执行。它会构造工具、载入上下文、调用 DeepAgents、收集流式事件、写终态。

相关代码：

- `backend/app/runner/core.py`

## Storage

结构化事实来源。生产里是 Postgres，测试里常用 `InMemoryTaskStorage`。它负责 Task、Run、Message、Event、Artifact、Upload 等状态。

相关代码：

- `backend/app/storage.py`
- `backend/tests/fakes.py`

## Resource

上传文件在当前任务内的资源表示。它不是自动进入上下文的文本，而是需要工具按需读取。

相关代码：

- `backend/app/api/files.py`
- `backend/app/execution/resources.py`

## Web Search Tool

联网搜索工具。当前平台工具名是 `searxng_search`，由 `backend/app/tools/registry.py` 注册，具体实现是 `backend/app/tools/searxng_search.py`。它调用后端配置的本地 SearXNG JSON 搜索接口，默认地址为 `http://127.0.0.1:8181/`。

关键点：搜索工具不是模型 provider，不需要 provider API key；如果本地 SearXNG 不可用，工具应返回错误字符串，让 Agent 可以降级说明，而不是让 Runner 崩溃。

相关代码：

- `backend/app/tools/registry.py`
- `backend/app/tools/searxng_search.py`
- `backend/app/config.py` 的 `searxng_url`

## Artifact

Agent 运行后生成的结果文件，例如 `report.html`、`final-summary.md`。前端通过受控 API 下载或预览。

相关代码：

- `backend/app/api/artifacts.py`
- `frontend/lib/task-api.ts`
- `frontend/hooks/use-task-workspace.ts`

## Skill

DeepAgents 的技能说明文件，通常是 `SKILL.md`，用于告诉 Agent 某类任务应该按什么流程做。

相关代码：

- `backend/app/skills/loader.py`
- `backend/skills/*/SKILL.md`

## Model Registry

后端允许使用的模型清单。模型 ID 是后端公开给前端的安全标识，例如当前项目里的 `deepseek-v4-flash`、`deepseek-v4-flash-thinking`。API 会先校验模型是否在 registry 中，再根据 provider key 判断是否 available。

相关代码：

- `backend/app/config.py` 的 `MODEL_REGISTRY`
- `backend/app/models/registry.py`
- `backend/app/models/provider.py`
- `backend/app/api/models.py`

## SubAgent

DeepAgents 的子智能体定义，比如 researcher、coder、file-analyst。它是一种任务分工描述，不等于系统进程。

相关代码：

- `backend/app/subagents/definitions.py`

## SSE

Server-Sent Events。浏览器用 `EventSource` 接收后端实时事件。由于 EventSource 不能自定义 header，token 通过 query param 传递。

相关代码：

- `backend/app/api/streaming.py`
- `frontend/lib/task-api.ts`
- `frontend/hooks/use-task-workspace.ts`

## Conversation Context

同一个 Task 内的短期上下文。Runner 每次运行前会从历史消息、会话摘要、短期工具缓存中确定性组装上下文。

相关代码：

- `backend/app/conversation_context.py`
- `backend/app/runner/core.py`

## Long-Term Memory

跨任务的长期记忆，只保存脱敏后的稳定偏好、用户事实、项目规则和工作流摘要。它不是上传文件原文仓库。

相关代码：

- `backend/app/memory.py`
- `backend/app/security/scanner.py`

## 最容易混淆的四组词

### Task vs Run

- `Task` 是整个会话容器。
- `Run` 是这个会话里某一次真正的执行。

### Event vs SSE

- `Event` 是后端持久化下来的事实记录。
- `SSE` 是把这些事实实时推给浏览器的一条通道。

### Resource vs Artifact

- `Resource` 是用户上传后，Agent 可以按需读取的输入资源。
- `Artifact` 是 Agent 跑完后生成给用户看的输出结果。

### 会话上下文 vs 长期记忆

- 会话上下文来自同一个 task 的近期消息和短期状态。
- 长期记忆跨 task 检索，只保留稳定、脱敏、未来反复有用的摘要。

如果你读某一章时突然分不清一个词在说“输入”“输出”“事实”还是“通道”，先回这页复位，再继续往下读，会轻松很多。
