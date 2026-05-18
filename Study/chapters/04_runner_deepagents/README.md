# 04 Runner 与 DeepAgents

## 学习目标

你要理解一次 Agent run 的内部步骤：

1. 创建 task workspace。
2. 注册平台工具。
3. 调用 `build_agent()` 包装 `create_deep_agent()`。
4. 注入会话上下文、长期记忆、资源 manifest。
5. 通过 `stream_agent()` 消费 DeepAgents/LangGraph 流。
6. 转换并持久化 EventRecord。
7. 写入终态和最终回答。

## 前置知识

- LangChain message：`HumanMessage`、`SystemMessage`、`AIMessage` 是模型输入输出的消息对象。
- 流式执行：Agent 不是一次返回全部结果，而是不断 yield chunk。
- 后台任务：`start_background()` 用 asyncio task 承载一次 run。

## 必读代码

- `backend/app/runner/core.py`
- `backend/app/agent/factory.py`
- `backend/app/streaming/v2_adapter.py`
- `backend/app/streaming/event_converter.py`
- `backend/app/tools/registry.py`
- `backend/app/tools/searxng_search.py`
- `backend/app/subagents/definitions.py`

## 本章主线

从 `TaskRunner.start_background()` 开始看：它先调用 `start()` 收集流式事件，再根据成功、超时、取消、异常写终态。`start()` 内部才是“构造 Agent 并消费流”的主流程。

## 核心概念

### Runner 是生命周期编排器

Runner 不是模型本身。它像一条生产线：

```text
准备工具/上下文 -> 构造 Agent -> 消费流式事件 -> 写事件 -> 提取最终回答 -> 写终态
```

### 平台工具由 registry 统一注册

`get_platform_tools(settings, task_id=..., storage=...)` 是平台工具入口。它做两类事：

- 有 `task_id` 时注册 task-scoped resource tools：`list_uploaded_resources`、`inspect_resource`、`read_resource_text`、`read_resource_table`。
- `settings.searxng_url` 非空时注册 `searxng_search`，默认调用本地 SearXNG：`http://127.0.0.1:8181/`。

注意：联网搜索现在按本地 SearXNG 引擎理解，不再按外部搜索 API Key 路径理解。工具调用失败时应返回可读错误字符串，不能让 Runner 因搜索服务不可用而崩溃。

### DeepAgents 是执行引擎

`build_agent()` 最终调用 `create_deep_agent()`。项目不要手动重复注入 DeepAgents 已经自动注入的中间件，例如 TodoList、Filesystem、Summarization 等。

`agent/factory.py` 还通过 `CompositeBackend` 把默认文件系统、`/scratch/` 状态后端和可选 `/memories/` store 组合起来。初学时不用记内部细节，只要知道：Agent 的文件读写被绑定到当前 task workspace。

### 中间 token 不等于最终回答

`assistant_answer_delta` 是流式中间片段。最终回答来自完成后的 graph state 中最后一个没有 tool call 的 AIMessage，并通过 `final_answer` 事件让前端刷新。

### 上下文进入 Agent 的顺序

Runner 组装 messages 时大致是：

```text
会话上下文 SystemMessage + 历史消息
-> 长期记忆 SystemMessage
-> 上传资源 manifest SystemMessage
-> 当前 HumanMessage
```

上传资源 manifest 只包含文件名、格式、大小、digest，不包含文件正文。

## 你可能卡住的问题

### 为什么 `start_background()` 要接收 run_id？

因为 run_id 由 storage 创建。Runner 必须用同一个 run_id 写事件、消息和产物，否则一次运行会被拆散。

### 为什么上下文和记忆失败不能让任务失败？

会话上下文、长期记忆是增强项。核心任务是执行当前用户消息。增强项失败时应降级，而不是把任务直接打失败。

### 为什么要有 timeout？

模型或工具可能挂住。Runner 用超时保护任务生命周期，避免永远 running。

## 动手练习

运行：

```bash
python3 Study/chapters/04_runner_deepagents/mini_unit.py
```

尝试把 `extract_final_answer` 改成返回最后一条 AI 消息，不过滤 `tool_calls`，再运行。你会看到失败。这个失败说明工具调用中间消息不能当最终回答。

练习还会读取 `runner/core.py`、`agent/factory.py`、`tools/registry.py`、`tools/searxng_search.py`、`v2_adapter.py`，确认当前项目确实通过这些源码路径实现 run 生命周期和本地搜索工具注册。

## 自测题

1. Runner 和 Agent factory 的职责有什么不同？
2. 为什么 `values_snapshot` 对最终回答很重要？
3. 工具调用事件为什么要转成平台自己的 `EventRecord`？
4. 上传资源 manifest 为什么不能包含文件正文？
5. `searxng_search` 和 resource tools 的注册条件有什么不同？

## 常见误区

- 误区：Runner 就是 Agent。纠正：Runner 编排生命周期，Agent 才执行模型和工具。
- 误区：看到 `assistant_answer_delta` 就能保存最终回答。纠正：它只是中间流；最终回答要等图状态完成。
- 误区：长期记忆召回失败就应该让任务失败。纠正：记忆是增强项，失败时降级执行当前任务。
