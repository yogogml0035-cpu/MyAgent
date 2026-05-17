# 02 后端 API 与 Schema

## 学习目标

你要理解后端公开契约：

- 请求体用 Pydantic 模型约束。
- 响应体用 `TaskState`、`TaskSummary`、`EventRecord` 等结构描述。
- API 层负责校验模型、任务状态、运行中冲突和错误码。

## 前置知识

- Pydantic 模型：用类描述请求和响应的字段。
- HTTP 状态码：400/404/409/413/422 分别代表不同类型的失败。
- 前后端字段风格：Python 常用 `snake_case`，TypeScript 常用 `camelCase`。

## 必读代码

- `backend/app/schemas.py`
- `backend/app/api/tasks.py`
- `backend/app/api/files.py`
- `backend/app/api/models.py`
- `backend/tests/unit/api/test_tasks.py`

## 本章主线

从 `schemas.py` 出发，先看“后端承诺返回什么”，再看 `api/tasks.py` 如何在启动 Runner 前保护这些承诺。

## 核心概念

### Schema 是前后端合同

后端字段使用 `snake_case`，例如 `task_id`、`active_run_id`、`created_at`。前端状态层会转换为 `camelCase`，例如 `id`、`activeRunId`、`createdAt`。

不要在前端到处猜字段，应该通过 `frontend/app/task-state.ts` 统一归一化。

关键 schema 对照：

| 后端模型 | 作用 |
| --- | --- |
| `TaskCreateRequest` | 创建空 task，或创建时直接带第一条消息 |
| `MessageRequest` | 给已有 task 发送消息 |
| `TaskState` | 任务详情页和前端状态的主要来源 |
| `TaskSummary` | 历史会话列表 |
| `EventRecord` | 进度日志和 SSE 的基本单元 |
| `ModelOption` | 模型选择器和可用性提示 |

### API 层做什么？

以 `send_message` 为例：

1. 解析请求体 `MessageRequest`。
2. 解析并校验模型。
3. 确认 task 存在。
4. 如果 runner 正在运行，返回 409。
5. 调用 `storage.start_run()`。
6. 自动生成标题，失败也不能阻塞 Runner。
7. 调用 `runner.start_background()`。
8. 返回最新 `TaskState`。

### 常见错误码

- 400：模型不允许、模型服务未配置、上传类型不支持。
- 404：任务或产物不存在。
- 409：任务运行中，不能重复发送、删除或上传。
- 413：上传文件或请求体超过限制。
- 422：请求体格式不符合 schema。

## 你可能卡住的问题

### 为什么 `create_task` 和 `send_message` 是 `async def`？

因为它们内部要在异步上下文里调度后台任务。把它改成同步函数会破坏运行时调度边界。

### 为什么无消息创建 task 不要求 provider key？

空 task 只是草稿，尚未启动模型运行。真正发送消息或创建带消息的 task 时，才必须确认模型 provider key 已配置。

## 动手练习

运行：

```bash
python3 Study/chapters/02_backend_api_schemas/mini_unit.py
```

尝试把 `BACKEND_TO_FRONTEND_FIELD["task_id"]` 改成 `"taskId"`，再运行。你会看到失败，因为本项目前端把后端 `task_id` 统一映射成 `id`。

练习会同时读取 `schemas.py`、`api/tasks.py` 和 `task-state.ts`，确认字段、状态、模型校验函数在源码中存在。

## 自测题

1. `MessageRequest` 的 `message` 为什么有最小长度和最大长度？
2. API 层为什么要在启动 Runner 前校验模型可用性？
3. `include_events=false` 有什么用？
4. 为什么 `TaskCreateRequest.message` 可以是空，而 `MessageRequest.message` 不可以是空？

## 常见误区

- 误区：前端可以直接使用后端原始字段。纠正：统一经过 `normalizeTaskState()`，避免每个组件重复兼容。
- 误区：模型 ID 只要传给 provider 能用就行。纠正：必须先在 `MODEL_REGISTRY` 注册，再检查 provider key。
- 误区：409 是服务器坏了。纠正：这里很多 409 是业务冲突，例如任务正在运行。
