# 02 标准答案

## 自测题答案

1. 最小长度避免空消息触发无意义运行；最大长度保护后端、模型上下文和日志存储，避免单个请求过大。
2. Runner 一旦启动，任务就进入 running。提前校验模型可用性可以避免留下没有实际执行者接管的异常运行。
3. `include_events=false` 用于轻量刷新任务状态，不拉取完整事件日志，适合 SSE 已经合并日志后只补状态、产物、消息等摘要信息。
4. `TaskCreateRequest` 支持创建草稿 task，所以 message 可以为空；`MessageRequest` 表示“给已有 task 触发一次运行”，空消息没有业务意义，所以要求至少 1 个字符。

## 练习观察点

`task_id -> id` 是前端核心映射。真实代码里这个归一化在 `frontend/app/task-state.ts`，API 调用封装在 `frontend/lib/task-api.ts`。
