# 03 Storage 与事件日志

## 学习目标

你要理解 Storage 为什么是系统的“事实来源”：

- Task 状态不以浏览器本地状态为准。
- Run、Message、Event、Artifact 都要能从 Storage 恢复。
- 事件日志是追加式的，`seq` 表示同一个 Task 内的自然顺序。

## 前置知识

- 事务：多个数据库操作要么一起成功，要么一起失败。
- 游标：客户端说“我已经看到某个事件了，请给我后面的”。
- Fake：测试中模拟生产对象的替身，但公开行为必须和生产一致。

## 必读代码

- `backend/app/storage.py`
- `backend/tests/fakes.py`
- `backend/tests/unit/storage/test_storage.py`
- `backend/tests/unit/api/test_tasks.py`

## 本章主线

先看 `start_run()` 如何把 task 变成 running 并创建 run，再看 `append_event()` 和 `read_events()` 如何让长任务可恢复。

## 核心概念

### 生产 Storage 与测试 Fake 必须同步

生产用 `PostgresTaskStorage`，测试常用 `InMemoryTaskStorage`。Fake 不是随便写的替身，它必须保留生产公开契约，例如：

- `start_run()` 成功后任务变为 `running`。
- `append_event()` 递增 `seq`。
- `read_events(after_id=未知)` 应返回完整有序事件流，而不是空列表。
- 删除任务要同时清理结构化状态和文件工作区。

### 事件游标是提示，不是权威边界

前端可能断线、刷新、本地状态丢失，带来的 `after_id` 可能已经不存在。此时后端返回完整事件流，前端再按事件 ID 去重，比直接返回空列表更安全。

### 文件工作区不是状态数据库

`backend/storage/sessions/<task_id>/` 保存上传和产物文件。任务状态、消息、事件的权威来源是 Postgres。

### Storage 与 Runner 的隐式耦合

Runner 假设 storage 提供这些能力：

- `start_run()` 已经生成 run_id。
- `append_event()` 能把每个流式事件落库。
- `update_task_if_status_and_append_event()` 能用“预期状态”保护终态写入。
- `read_events()` 能按 `seq` 有序返回事件。

如果 storage 的实现变了，Runner、API、SSE 和测试 fake 都要一起检查。

## 结合项目分析

把这章和真实代码对上，最值得抓的是三个函数：

```text
storage.start_run()
-> 把 task 状态改成 running
-> 写入这次用户消息
-> 创建 run_id 和 active_run_id

storage.append_event()
-> 给 event 分配递增 seq
-> 持久化过程日志

storage.read_events(after_id)
-> 找到游标就返回后续事件
-> 找不到游标就 fail open 返回完整事件流
```

这一章读懂之后，下一章 `Runner` 就不会再像“黑盒子”。

因为你已经知道：Runner 不是随便往外吐字符串，它依赖 storage 提供 run_id、事件顺序和终态保护。

## 你可能卡住的问题

### 为什么不每次读文件目录来判断任务状态？

因为目录只能说明“文件存在”，不能说明 run 状态、消息顺序、事件顺序、取消状态、错误原因。结构化状态必须在数据库中。

### 为什么 seq 要在事务里生成？

为了保证并发追加事件时顺序连续、不会重复、不会回退。前端进度日志依赖这个顺序。

## 动手练习

运行：

```bash
python Study/chapters/03_storage_event_log/mini_unit.py
```

尝试把 `read_events` 里未知 `after_id` 的返回值改成 `[]`，再运行。你会看到失败。这个失败模拟了浏览器恢复时丢事件的风险。

练习还会读取生产 `storage.py` 和测试 `fakes.py`，确认二者的未知游标语义一致。

## 自测题

1. 为什么 fake storage 不能为了测试方便弱化公开契约？
2. `append_event` 为什么比“覆盖当前状态文本”更适合流式 Agent？
3. 删除 task 时为什么也要清理文件工作区？
4. 为什么终态更新要带 expected statuses？

## 常见误区

- 误区：Postgres 和文件目录都存状态，哪个方便用哪个。纠正：Postgres 是结构化事实来源，文件目录只存上传和产物字节。
- 误区：`after_id` 找不到说明没有新事件。纠正：找不到可能是旧标签页或本地状态漂移，应 fail open 返回完整事件流。
- 误区：fake storage 越简单越好。纠正：fake 可以少依赖外部服务，但不能改变公开契约。
