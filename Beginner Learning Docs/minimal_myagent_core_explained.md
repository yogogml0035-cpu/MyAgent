# MyAgent 最小可运行示例

这个示例把真实项目删到只剩一条最核心的数据流：

```text
用户输入
  -> frontend_send_message()
  -> backend_create_task()
  -> backend_run_agent()
  -> fake_agent()
  -> frontend_render_task()
  -> 终端打印状态、消息和事件
```

运行方式：

```bash
python3 "Beginner Learning Docs/minimal_myagent_core.py"
```

## 这个示例删掉了什么

为了让第一版容易看懂，这里故意没有保留这些真实项目能力：

- 没有 FastAPI、Next.js、React。
- 没有 Postgres，改成一个 Python 字典 `storage`。
- 没有真实 DeepAgents 和大模型，改成 `fake_agent()`。
- 没有 SSE 流式输出，改成最后一次性打印 `events`。
- 没有上传文件、产物下载、鉴权、配置、日志、测试和错误处理。

初学者可以这样复述：这个文件不是完整 MyAgent，它只是把 MyAgent 的骨架缩小到一条能跑通的链路。

## 代码逐段解释

### 1. `storage = {}`

```python
storage = {}
```

这行模拟真实项目里的 Postgres。

真实项目中，任务、消息、事件会存进数据库。这个最小示例里，我们只用一个字典保存数据。

可以复述成：`storage` 就是一个临时小仓库，程序运行时把任务放进去。

### 2. `frontend_send_message(user_text)`

```python
def frontend_send_message(user_text):
    print("Frontend: user clicked Send")

    task_id = backend_create_task(user_text)
    backend_run_agent(task_id)
    frontend_render_task(task_id)
```

这个函数模拟前端点击“发送”。

它按顺序做三件事：

1. 把用户输入交给后端创建任务。
2. 让后端 runner 执行任务。
3. 从后端数据里读取最新任务并展示。

数据怎么流动：

- `user_text` 是用户输入。
- `backend_create_task(user_text)` 把输入存起来，并返回 `task_id`。
- 后面的函数都用 `task_id` 找到同一个任务。

可以复述成：前端不自己干活，它把话交给后端，然后拿任务 ID 去看结果。

### 3. `backend_create_task(user_text)`

```python
def backend_create_task(user_text):
    task_id = "task-1"

    storage[task_id] = {
        "status": "running",
        "messages": [
            {"role": "user", "content": user_text},
        ],
        "events": [
            "task_created",
            "user_message_saved",
        ],
    }

    print("Backend: created task", task_id)
    return task_id
```

这个函数模拟后端创建任务。

它创建了一个任务对象，里面只有三块核心数据：

- `status`：任务现在是什么状态。
- `messages`：用户和助手的对话消息。
- `events`：任务运行过程中发生过什么。

为什么返回 `task_id`？

因为前端后续不需要拿着整个任务到处传，只要拿着任务 ID，就能再从 `storage` 里找到它。

可以复述成：后端收到用户输入后，先开一个任务档案，把用户消息和初始事件记下来。

### 4. `backend_run_agent(task_id)`

```python
def backend_run_agent(task_id):
    task = storage[task_id]
    user_message = task["messages"][-1]["content"]

    task["events"].append("agent_started")
    assistant_answer = fake_agent(user_message)
    task["events"].append("agent_finished")

    task["messages"].append(
        {"role": "assistant", "content": assistant_answer}
    )
    task["status"] = "complete"
    task["events"].append("task_completed")
```

这个函数模拟真实项目里的 `TaskRunner`。

它做了五步：

1. 用 `task_id` 从 `storage` 里拿到任务。
2. 从任务消息里取出最后一条用户消息。
3. 记录 `agent_started`，表示 agent 开始工作。
4. 调用 `fake_agent(user_message)` 得到助手回答。
5. 把助手回答、完成状态和完成事件写回任务。

这里最重要的是：runner 不直接打印结果，而是把结果写回 `storage`。

可以复述成：runner 负责干活，但干完后要把结果写回任务档案。

### 5. `fake_agent(user_message)`

```python
def fake_agent(user_message):
    return "我已经收到你的任务。最小版回答：先理解需求，再列出三步计划。你的原始输入是：" + user_message
```

这个函数模拟真实大模型或 DeepAgents。

真实项目里，这一步会调用模型、工具、skills、subagents。这里全部删掉，只返回一段固定格式的文字。

可以复述成：`fake_agent()` 是一个假的智能体，只为了让整条流程能跑起来。

### 6. `frontend_render_task(task_id)`

```python
def frontend_render_task(task_id):
    task = storage[task_id]

    print("\nFrontend: render latest task")
    print("Status:", task["status"])

    print("\nMessages:")
    for message in task["messages"]:
        print("-", message["role"] + ":", message["content"])

    print("\nEvents:")
    for event in task["events"]:
        print("-", event)
```

这个函数模拟前端页面渲染。

它从 `storage` 里拿任务，然后打印三类信息：

- 当前状态：比如 `running` 或 `complete`。
- 对话消息：用户说了什么，助手回了什么。
- 事件日志：任务运行过程中发生了什么。

可以复述成：前端只是把后端保存的数据读出来，整理成人能看的样子。

### 7. 程序入口

```python
frontend_send_message("请帮我生成一份投标分析提纲")
```

这一行让整个流程真正开始。

如果没有这一行，前面的函数只是“定义好了”，但不会自动执行。

可以复述成：函数像机器，入口这一行才是按下启动按钮。

## 函数调用顺序

实际运行时的调用顺序是：

1. Python 执行最后一行 `frontend_send_message(...)`。
2. `frontend_send_message()` 调用 `backend_create_task()`。
3. `backend_create_task()` 把任务写进 `storage`，返回 `task_id`。
4. `frontend_send_message()` 拿到 `task_id` 后调用 `backend_run_agent()`。
5. `backend_run_agent()` 调用 `fake_agent()` 生成回答。
6. `backend_run_agent()` 把回答和完成状态写回 `storage`。
7. `frontend_send_message()` 调用 `frontend_render_task()`。
8. `frontend_render_task()` 从 `storage` 读取任务并打印。

## 数据如何流动

同一份数据一直围绕 `task_id` 流动。

```text
用户文字
  -> 存进 storage["task-1"]["messages"]
  -> runner 读取最后一条 user message
  -> fake_agent 生成 assistant answer
  -> assistant answer 写回 storage["task-1"]["messages"]
  -> frontend_render_task 读取并打印
```

初学者可以这样复述：数据不是凭空跳到页面上的，它先被后端保存，再被 runner 修改，最后被前端读出来展示。

## 你可能会追问的问题

### 为什么要有 `task_id`？

因为以后可能有很多任务。`task_id` 就像任务编号，大家都靠这个编号找到同一份任务数据。

初学者复述：任务 ID 是“档案编号”。

### 为什么 `messages` 是一个列表？

因为对话不是只有一句话。列表可以按顺序保存多条消息：第一条用户消息、第二条助手回复、后续继续追问。

初学者复述：列表能记录一来一回的聊天历史。

### 为什么 `events` 和 `messages` 要分开？

`messages` 是给用户看的对话内容。`events` 是程序运行过程，比如任务创建、agent 开始、agent 结束。

初学者复述：消息是聊天内容，事件是后台流水账。

### 为什么不在 `fake_agent()` 里直接打印？

因为 agent 的职责是生成回答，不是决定页面怎么展示。展示交给前端函数。

初学者复述：干活的人只交结果，展示的人负责排版。

### 为什么真实项目还需要后端和前端？

真实项目里，浏览器、数据库、模型、文件和权限都不在一个简单 Python 文件里。这个示例把它们放到同一个文件，是为了看清最小骨架。

初学者复述：这个示例把不同房间的人都请到一张桌子上演示流程。

### `status` 有什么用？

前端需要知道任务现在是运行中、完成了，还是失败了。没有状态，页面就不知道该显示“停止按钮”还是“发送按钮”。

初学者复述：状态告诉前端任务现在走到哪一步了。

## 如果变成生产代码，还需要补什么

- HTTP API：用 FastAPI 接收真实浏览器请求。
- 前端页面：用 Next.js/React 渲染真实工作区。
- 数据库：用 Postgres 持久保存任务、消息和事件。
- 异步 runner：任务运行不能阻塞 API 请求。
- SSE：运行过程中实时把事件推给前端。
- 真实模型：接入 DeepAgents 和模型 Provider。
- 上传和产物：支持文件上传、工具读取、报告下载。
- 鉴权和安全：保护 token、文件路径、客户资料和 provider key。
- 错误处理：失败、取消、超时、网络断开都要有明确状态。
- 测试：后端单测、前端单测、浏览器 E2E 和截图证据。
- 配置和日志：不同环境的端口、数据库、模型 key、运行日志都要可维护。
- 并发和恢复：多任务同时运行、服务重启、任务恢复都需要更强的运行时设计。

一句话总结：这个文件教你“骨架怎么跑”，生产代码要补的是“真实世界会出问题时怎么办”。
