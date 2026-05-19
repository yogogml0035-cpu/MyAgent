# 00 最小可运行示例：先看懂一条最短主链路

## 学习目标

学完这一章，你应该能用最简单的话复述：

```text
用户输入一句话
-> 后端接住
-> 系统创建这次 run
-> Runner 调 Agent
-> 系统写回最终答案
-> 前端再把最新状态显示出来
```

## 前置知识

你只需要知道三件事：

- 函数可以调用另一个函数
- 字典可以用来存数据
- 列表可以用来按顺序保存消息和事件

如果你现在还不熟类、异步、数据库，也没关系。这一章故意不依赖那些知识。

## 必读代码

- `Study/chapters/00_minimal_runnable_example/mini_unit.py`
- `frontend/hooks/use-task-workspace.ts`
- `backend/app/api/tasks.py`
- `backend/app/runner/core.py`

## 本章主线

真实项目里，用户点一次发送，会经过前端 hook、后端 API、Storage、Runner、Agent、事件日志、前端状态归一化这些层。

第一次学时，最容易迷路的地方不是“不会写代码”，而是“层太多，看不出主骨架”。

所以这章只做一件事：把整个项目压成一个最短、能跑、能追调用顺序的版本。

## 先跑起来

运行：

```bash
python3 Study/chapters/00_minimal_runnable_example/mini_unit.py
```

你会看到：

1. 每个函数按顺序打印出来。
2. 最后打印出“页面最后拿到的数据”。
3. 脚本还会顺手检查真实项目源码里是不是确实存在对应入口。

## 这份最小代码故意删掉了什么

这份代码不是生产版，所以我主动删掉了下面这些东西：

- 真正的 HTTP 请求
- 真正的数据库
- 真正的异步后台任务
- SSE 流式返回
- 文件上传和产物
- 模型配置和 API Key
- 参数校验和复杂错误处理
- 权限、安全、日志、监控

删掉这些东西之后，留下来的才是你现在最该看懂的“核心骨架”。

## 代码每一段在做什么

### 1. `database = {"tasks": {}}`

这是一个假的内存数据库。

它的作用只有一个：让你能很直观地看到数据放在哪里、谁改了它。

你可以把它理解成：

- `tasks` 里面放所有会话
- 每个会话里再放消息、run、事件

真实项目里，这些数据会放进 Postgres 和文件系统，而不是放在一个 Python 变量里。

### 2. `frontend_send_message(user_text)`

这是“前端拿到用户输入”的最小入口。

它先做一件很朴素的事：

- 如果 `task-1` 这个会话还不存在，就先创建一个空会话

然后它把 `user_text` 交给 `api_send_message()`。

这里最重要的理解是：

- 前端只是发起流程
- 前端自己不直接生成答案

### 3. `api_send_message(task_id, user_text)`

这是“后端 API 接住消息”的最小版。

它做了四件核心事：

1. 找到这次消息属于哪个 task
2. 创建一个新的 `run_id`
3. 把用户消息写进 `messages`
4. 把 task 状态改成 `running`

做完之后，它把控制权交给 `runner_start()`。

这里你一定要先记住一句话：

- `task` 是会话容器
- `run` 是会话里的某一次执行

### 4. `runner_start(task_id, run_id, user_text)`

这是“Runner 开始接手执行”的最小版。

它先写一条事件，表示“Runner 已经开始工作了”，然后调用 `fake_agent(user_text)`。

拿到答案后，它再写一条 `final_answer` 事件，最后把结果交给 `storage_finish_run()`。

这里最值得学的是：

- Runner 的核心职责不是“自己思考”
- Runner 的核心职责是“组织这次执行流程”

### 5. `fake_agent(user_text)`

这是一个假的 Agent。

它没有联网、没有模型、没有工具，只是把用户输入拼成一段返回文本。

我故意这么做，是因为你当前要学的是：

- 参数怎么一层层传下去
- 返回值怎么一层层传回来

如果一上来就接真实 LLM，你会先被 SDK、流式输出、API Key 分散注意力。

### 6. `storage_finish_run(task_id, run_id, answer)`

这是“Storage 把最终结果写回去”的最小版。

它做了四件事：

1. 把 task 状态改成 `complete`
2. 追加一条 assistant 消息
3. 把当前 run 状态改成 `complete`
4. 追加一条 `task_completed` 事件

然后它再调用 `frontend_render()`。

这一段特别重要，因为它体现了真实系统里的一个原则：

- 先写权威状态
- 再让前端展示

### 7. `frontend_render(task_id)`

这是“前端重新读取状态并展示”的最小版。

它没有真的去渲染 React 组件，只是把页面最终需要的数据打包返回：

- `task_id`
- `status`
- `messages`
- `events`

你可以把这个返回值理解成：

“页面已经拿到了足够渲染聊天区的数据。”

### 8. `assert_project_links()`

这段不是业务逻辑，它是“和真实项目对齐”的小检查。

它会去读真实源码，确认下面这些入口确实存在：

- 前端有 `handleSubmit`
- 前端会调 `postTaskMessage`
- 后端会先 `storage.start_run()`
- 后端会调 `runner.start_background()`
- Runner 里确实有 `start_background()`

也就是说，这个最小例子虽然很短，但不是凭空编的，它和真实项目的主骨架是对得上的。

## 数据是怎么流动的

把它想成一条传送带：

1. 用户输入的 `user_text` 先进入 `frontend_send_message(user_text)`。
2. 前端把它传给 `api_send_message(task_id, user_text)`。
3. API 把这条消息写进 `task["messages"]`。
4. API 创建 `run_id`，再把 `user_text` 交给 `runner_start(task_id, run_id, user_text)`。
5. Runner 再把 `user_text` 交给 `fake_agent(user_text)`。
6. `fake_agent()` 产出 `answer`。
7. `answer` 被交给 `storage_finish_run(task_id, run_id, answer)`。
8. Storage 把 `answer` 写回 `messages` 和 `events`。
9. `frontend_render()` 再把最终状态交给页面。

如果你只记一句话，就记这个：

“用户输入一路往下传，最终答案一路往上写回。”

## 函数是怎么互相调用的

调用顺序就是这一条：

```text
frontend_send_message
-> api_send_message
-> runner_start
-> fake_agent
-> storage_finish_run
-> frontend_render
```

初学者最稳的读法不是横着看全部函数，而是这样追：

1. 先看 `__main__`
2. 它先调用了谁
3. 那个函数最后 return 给了谁
4. 再往下一层继续追

你把这条调用链追完，整章就通了。

## 你可能会追问的问题

### 1. 为什么要分 `task` 和 `run`？

因为“一个聊天会话”和“会话里的某一次执行”不是同一个东西。

你可以用一句很容易复述的话记住：

- `task` 像聊天窗口
- `run` 像你点了一次发送之后发生的那次处理

所以一个 task 可以有很多个 run。

### 2. 为什么要先写 Storage，再前端显示？

因为前端不应该展示“我猜现在大概完成了”，而应该展示“系统已经确认保存好的状态”。

你可以直接背这句话：

“先把事实写下来，再把事实显示出来。”

### 3. 为什么前端不直接调模型？

因为真实项目里模型密钥、工具权限、上传文件、长期记忆、任务状态都该由后端控制。

前端更像提交请求的人，后端更像组织执行的人。

### 4. 为什么这个例子没有 SSE？

因为 SSE 解决的是“边执行边推送过程”。

但你现在先要看懂的是更基础的骨架：

- 谁接住请求
- 谁创建 run
- 谁调 agent
- 谁写回结果

骨架先懂，再学 SSE，脑子会更清楚。

### 5. 为什么这里把 `task_id` 写死成 `task-1`？

因为这章的目标不是模拟完整多会话系统，而是让你最短路径看懂一次调用。

如果一上来就加随机 id、多任务切换、历史恢复，你会更难追数据流。

### 6. 为什么这里用全局 `database`，看起来很不“工程化”？

因为它刚好适合教学。

它能让你一眼看到：

- 数据在哪里
- 哪个函数改了数据
- 改完之后页面会读到什么

等你先把这份最小版看懂，再去学数据库、ORM、事务，会轻松很多。

## 动手练习

运行：

```bash
python3 Study/chapters/00_minimal_runnable_example/mini_unit.py
```

然后尝试做两个小实验：

1. 注释掉 `storage_finish_run()` 里追加 assistant 消息那一行，再运行。
   你会发现状态完成了，但页面里没有 AI 回复。
2. 把 `task["status"] = "complete"` 注释掉，再运行。
   你会发现答案已经写回来了，但任务状态不对。

这两个实验会帮助你体会：

- “写消息”和“写状态”不是一回事
- 页面看到的结果依赖后端有没有把事实完整写好

## 自测题

1. `frontend_send_message()` 为什么不直接生成答案？
2. `api_send_message()` 为什么要创建 `run_id`？
3. `runner_start()` 和 `fake_agent()` 的职责差别是什么？
4. 为什么 `storage_finish_run()` 之后才适合让前端重新读取状态？
5. 这个例子里哪些部分是核心逻辑，哪些部分是为了贴近真实项目加的对齐检查？

标准答案见同目录 `answers.md`。

## 如果以后把它改成生产代码，还需要补什么

- 真实的 HTTP 路由、请求体、响应体
- 参数校验和错误处理
- 真实数据库和文件存储
- 真正的后台异步 runner、取消和超时
- SSE 流式事件和重连恢复
- 上传文件、产物、task-scoped 工具权限
- 模型 provider、密钥管理、配置读取
- 前后端字段转换，例如 `snake_case` 到 `camelCase`
- 鉴权、CORS、本地优先安全边界
- 单元测试、集成测试、浏览器 E2E、截图证据
- 日志、监控、异常恢复、多任务并发

## 下一步读哪里

如果你已经跑完这章，建议继续按这个顺序读：

1. `Study/chapters/01_big_picture/README.md`
2. `Study/chapters/02_backend_api_schemas/README.md`
3. `Study/chapters/04_runner_deepagents/README.md`
4. `Study/chapters/07_frontend_workspace/README.md`

这样你会先有“最短骨架”，再去看真实项目里每一层是怎么展开的。
