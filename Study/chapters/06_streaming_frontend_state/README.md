# 06 流式事件与前端状态

## 学习目标

你要理解实时进度是怎么来的：

1. DeepAgents/LangGraph 产生流式 chunk。
2. `v2_adapter.py` 统一不同版本的流格式。
3. `event_converter.py` 转成 `EventRecord`。
4. Storage 追加事件。
5. SSE endpoint 按游标推送事件。
6. 前端 `normalizeEventRecords`、`mergeExecutionLogs` 合并日志。
7. `workspace-view.ts` 投影成用户可读的进度卡片。

## 前置知识

- SSE：浏览器用 `EventSource` 接收服务器不断推送的 `data:` 消息。
- 增量合并：新事件到达时，前端不能把已有日志全丢掉。
- 展示投影：原始事件不直接等于 UI 文案，需要转换和折叠。

## 必读代码

- `backend/app/streaming/v2_adapter.py`
- `backend/app/streaming/event_converter.py`
- `backend/app/api/streaming.py`
- `frontend/app/task-state.ts`
- `frontend/app/workspace-view.ts`
- `frontend/hooks/use-task-workspace.ts`

## 本章主线

本章分清三层：

1. 后端 stream adapter 把 DeepAgents/LangGraph chunk 变成统一 event dict。
2. event converter 把 event dict 变成 `EventRecord` 并持久化。
3. 前端先按 id 合并，再在 `workspace-view.ts` 里按 `seq` 优先排序并投影成可见日志。

## 核心概念

### 原始流和 UI 日志不是同一个东西

原始流可能是 token、工具参数片段、节点更新。UI 日志要合并、翻译、折叠，变成“AI 正在思考”“调用工具”“任务已完成”等用户能理解的行。

### 排序优先看 seq

很多事件可能在同一秒产生。只按 `created_at` 排序会乱。后端给每个 task 的事件分配 `seq`，展示层应优先按 `seq`。

注意当前源码分工：

- `frontend/app/task-state.ts:mergeExecutionLogs` 只负责按 id 去重并追加。
- `frontend/app/workspace-view.ts:byLogOrder` 才负责展示排序，优先使用 `seq`。

### SSE 失败要补偿

前端 EventSource 出错后，会：

- 关闭连接。
- HTTP 拉一次 task summary 和 events。
- 指数退避重连。
- 达到最大次数后提示错误。

## 你可能卡住的问题

### 为什么 `assistant_thinking_delta` 不显示成 AI 回复？

它是供应商暴露的推理过程，只应该作为进度日志，不应该混进最终用户答案。

### 为什么 `final_answer` 事件还要触发状态刷新？

最终回答来自 authoritative graph state，前端收到后要刷新轻量任务状态，把消息、产物、状态同步到最新。

## 动手练习

运行：

```bash
node Study/chapters/06_streaming_frontend_state/mini_unit.mjs
```

尝试把 `mergeExecutionLogs` 里的排序改成只按 `createdAt`，再运行。你会看到失败，因为同秒事件会乱序。

准确地说，本练习模拟的是 `workspace-view.ts` 展示排序，不是 `task-state.ts` 的去重合并函数。练习也会读取源码确认这两个职责没有混在一起。

## 自测题

1. SSE endpoint 为什么在 runner 不运行后还要 drain 一次 remaining events？
2. `assistant_answer_delta` 和 `final_answer` 的区别是什么？
3. 前端为什么需要最大重试次数？
4. `mergeExecutionLogs` 和 `byLogOrder` 的职责有什么不同？

## 常见误区

- 误区：SSE 收到什么就直接显示什么。纠正：需要 normalization、合并、折叠、展示投影。
- 误区：`assistant_thinking_delta` 是答案的一部分。纠正：它是过程日志。
- 误区：前端合并函数已经完成排序。纠正：当前源码中展示排序在 `workspace-view.ts`。
