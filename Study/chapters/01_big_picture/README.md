# 01 大图景：先看懂 MyAgent 在做什么

## 学习目标

学完本章，你要能用一张图解释 MyAgent：

```text
用户界面 -> 后端 API -> Storage 创建/更新任务 -> Runner 执行 Agent -> Storage 追加事件 -> 前端展示日志和产物
```

## 前置知识

你只需要知道三个普通概念：

- HTTP API：前端通过 URL 请求后端。
- 后台任务：API 可以先返回，真正耗时的 Agent 在后台跑。
- 事件流：长任务会不断产生过程记录，而不是等最后一次性返回。

## 必读代码

- `README.md`
- `backend/app/main.py`
- `backend/app/api/tasks.py`
- `backend/app/runner/core.py`
- `frontend/app/page.tsx`
- `frontend/components/chat/TaskWorkspace.tsx`
- `frontend/hooks/use-task-workspace.ts`

## 本章主线

本章先不深入每个模块内部，只追一个问题：用户点击发送以后，系统为什么不会直接“前端调用模型并显示结果”，而是拆成 Task、Run、Event、Artifact 这些对象？

## 通俗解释

把 MyAgent 想成一个“任务工厂”：

- 前端像接待窗口：收集消息和文件。
- API 像前台登记：校验信息、创建任务、分配运行编号。
- Storage 像档案室：所有状态、消息、事件都归档。
- Runner 像项目经理：拿到任务后组织 Agent、工具、上下文执行。
- DeepAgents 像真正干活的专家组：思考、调用工具、生成答案。
- SSE 像现场广播：把执行过程一条条播给前端。

## 结合项目分析

项目入口非常薄：

- `frontend/app/page.tsx` 只挂载 `TaskWorkspace`。
- `TaskWorkspace.tsx` 只组合侧边栏、会话区、输入区。
- 真正的用户动作编排在 `use-task-workspace.ts`。
- 后端 `main.py` 把 tasks、files、artifacts、streaming、models 路由注册到同一个 FastAPI app。

这种拆法让每层职责更清楚：组件负责展示，hook 负责编排，API 负责校验，Runner 负责执行，Storage 负责事实。

## 你可能卡住的问题

### 1. Task 和 Run 有什么区别？

一步一步想：

1. 一个聊天会话可以发很多轮消息。
2. 每一轮消息都可能触发一次 Agent 执行。
3. 会话容器叫 Task。
4. 每次执行叫 Run。
5. 所以一个 Task 可以有多个 Run。

### 2. 为什么不让前端直接调用模型？

因为模型密钥、上传文件、任务状态、长期记忆和工具调用都必须受后端控制。前端只负责表达用户意图，不接触 provider API key。

### 3. 为什么需要事件日志？

Agent 是流式执行的，过程中会思考、调用工具、返回中间状态。事件日志让前端能看到过程，也让刷新页面后可以恢复现场。

## 动手练习

运行：

```bash
python Study/chapters/01_big_picture/mini_unit.py
```

然后尝试把 `PIPELINE` 里 `runner.start_background` 放到 `storage.start_run` 前面，再运行。你应该看到断言失败。这个失败说明：必须先由 storage 创建 run_id 和 running 状态，Runner 才能接管同一轮运行。

这个练习还会读取当前源码，确认主入口和关键函数确实存在。

## 自测题

1. `frontend/app/page.tsx` 为什么只有一行主要逻辑？
2. `backend/app/main.py` 注册了哪些路由？
3. 一条用户消息为什么会同时影响 messages、runs、events？
4. 空 task 和带消息 task 的区别是什么？

## 常见误区

- 误区：Task 就是一次模型调用。纠正：Task 是会话容器，Run 才是一次执行。
- 误区：前端可以直接拼接流式 token 当最终答案。纠正：最终答案由后端从完成后的图状态提取。
- 误区：SSE 是唯一状态来源。纠正：SSE 是实时通道，Storage 才是权威事实来源。
