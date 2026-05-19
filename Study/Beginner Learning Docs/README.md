# MyAgent 最小可运行示例

这个目录里的示例把真实 MyAgent 项目压缩成一个文件：

```text
用户输入 -> 创建 task -> 记录 event -> 执行 task -> 写入 assistant 消息 -> 打印结果
```

真实项目里有 FastAPI、Postgres、DeepAgents、SSE、Next.js 前端、上传文件和产物下载。这个学习版先全部删掉，只保留你理解项目时最需要的核心逻辑：**一个任务如何从输入流到结果**。

## 运行方式

在仓库根目录运行：

```bash
python3 "Study/Beginner Learning Docs/mini_myagent_flow.py"
```

你会看到三类输出：

- `任务状态`：任务最后是 `completed`。
- `消息`：用户消息和 assistant 回复。
- `事件`：任务执行过程中发生过什么。

## 代码分段解释

### 1. `append_event(task, event_type, text)`

这段代码做一件事：往任务里追加一条事件。

```python
def append_event(task, event_type, text):
    task["next_event_seq"] = task["next_event_seq"] + 1
    task["events"].append(
        {
            "seq": task["next_event_seq"],
            "type": event_type,
            "text": text,
        }
    )
```

初学者可以这样复述：

> 每发生一件事，就给它一个递增编号，然后把这件事放进 `task["events"]` 列表里。

数据怎么流动：

1. 函数收到一个 `task`。
2. 先把 `task["next_event_seq"]` 加 1。
3. 再把 `{seq, type, text}` 这个事件字典放进 `task["events"]`。
4. 这个函数没有 `return`，因为它直接修改了传进来的 `task`。

对应真实项目里的概念：

- 这里的 `events` 对应后端持久化事件日志。
- 这里的 `seq` 对应真实系统里按顺序恢复事件的编号。

### 2. `create_task(user_text)`

这段代码负责创建任务。

```python
def create_task(user_text):
    task = {
        "id": "task-1",
        "status": "queued",
        "messages": [],
        "events": [],
        "next_event_seq": 0,
    }

    task["messages"].append({"role": "user", "content": user_text})
    append_event(task, "task_created", "用户创建了一个任务")

    return task
```

初学者可以这样复述：

> 创建一个任务盒子，把用户说的话放进消息列表，再记一条“任务创建了”的事件，最后把任务盒子交出去。

数据怎么流动：

1. `user_text` 是用户输入的文字。
2. `task` 是一个字典，用来装这个任务的所有信息。
3. `messages` 存聊天内容。
4. `events` 存过程记录。
5. 调用 `append_event(...)` 后，`task["events"]` 多了一条事件。
6. `return task` 把创建好的任务交给下一步。

对应真实项目里的概念：

- `status: "queued"` 表示任务已经排队，还没开始跑。
- 真实项目会用后端 API 和数据库创建 task；这里用一个普通字典代替。

### 3. `run_task(task)`

这段代码模拟 Runner 执行任务。

```python
def run_task(task):
    task["status"] = "running"
    append_event(task, "run_started", "Runner 开始执行任务")

    user_text = task["messages"][0]["content"]
    answer = "我收到你的任务：" + user_text

    task["messages"].append({"role": "assistant", "content": answer})
    append_event(task, "assistant_message", "Assistant 生成了回复")

    task["status"] = "completed"
    append_event(task, "task_completed", "任务完成")
```

初学者可以这样复述：

> Runner 把任务状态改成运行中，读取第一条用户消息，生成一个回复，把回复放回消息列表，然后把任务标记为完成。

数据怎么流动：

1. `task` 从 `create_task(...)` 来。
2. `task["status"]` 从 `queued` 变成 `running`。
3. `user_text` 从 `task["messages"][0]["content"]` 读出来。
4. `answer` 根据 `user_text` 拼出来。
5. assistant 回复被放进 `task["messages"]`。
6. `task["status"]` 最后变成 `completed`。
7. 每个关键动作都会调用 `append_event(...)` 记录过程。

对应真实项目里的概念：

- 真实项目里的 Runner 会调用 DeepAgents、工具、模型和文件系统。
- 这个学习版只用字符串拼接代替真实 Agent 回复。

### 4. `show_task(task)`

这段代码负责把最终任务打印出来。

```python
def show_task(task):
    print("任务状态:", task["status"])

    print("\n消息:")
    for message in task["messages"]:
        print("-", message["role"] + ":", message["content"])

    print("\n事件:")
    for event in task["events"]:
        print("-", event["seq"], event["type"], event["text"])
```

初学者可以这样复述：

> 从任务盒子里取出状态、消息、事件，然后一行一行打印出来。

数据怎么流动：

1. 读取 `task["status"]`。
2. 遍历 `task["messages"]`，打印用户消息和 assistant 消息。
3. 遍历 `task["events"]`，打印每一步发生过什么。

对应真实项目里的概念：

- 真实项目前端会把状态、消息、事件渲染成页面。
- 这个学习版用 `print(...)` 代替页面展示。

### 5. 程序入口

```python
if __name__ == "__main__":
    user_text = "请用一句话说明 MyAgent 的任务流"
    task = create_task(user_text)
    run_task(task)
    show_task(task)
```

初学者可以这样复述：

> 这个文件被直接运行时，先准备一段用户输入，再创建任务，再执行任务，最后展示任务。

函数调用顺序：

```text
mini_myagent_flow.py
  -> create_task(user_text)
       -> append_event(...)
  -> run_task(task)
       -> append_event(...)
       -> append_event(...)
       -> append_event(...)
  -> show_task(task)
```

完整数据流：

```text
user_text
  -> task["messages"][0]
  -> run_task 读取 user_text
  -> answer
  -> task["messages"][1]
  -> show_task 打印 messages

task 执行过程
  -> append_event 写入 events
  -> show_task 打印 events
```

## 你可能会追问的问题

### 1. 为什么用字典，不用类？

因为这是第一版学习代码。字典更直观：你能直接看到 `task` 里面有哪些字段。生产代码里会更适合用 Pydantic model、dataclass 或数据库表结构。

你可以这样复述：

> 这里用字典是为了让我先看懂数据长什么样。

### 2. 为什么 `messages` 是列表？

因为聊天不是只有一句话。用户可以发第一句，assistant 回复一句，用户再继续追问，所以消息天然是一条一条按顺序排列。

你可以这样复述：

> `messages` 是聊天记录，列表表示它有先后顺序。

### 3. 为什么 `events` 和 `messages` 要分开？

`messages` 是用户和 assistant 看得懂的对话内容。`events` 是系统执行过程，比如任务创建、开始运行、生成回复、任务完成。

你可以这样复述：

> `messages` 是聊天内容，`events` 是后台过程记录。

### 4. 为什么 `append_event(...)` 没有 `return`？

因为 `task` 是一个可修改的字典。函数内部执行 `task["events"].append(...)` 时，外面的那个 `task` 也被改了。

你可以这样复述：

> 函数没有返回新 task，而是直接往原来的 task 里加事件。

### 5. `task["messages"][0]["content"]` 是什么意思？

从左到右读：

```text
task
  -> 取 messages
  -> 取第 0 条消息
  -> 取这条消息里的 content
```

你可以这样复述：

> 它是在拿第一条消息的正文。

### 6. 为什么要有 `status`？

因为前端需要知道任务现在处于哪个阶段。最小版里只有三个状态：

- `queued`：已创建，等执行。
- `running`：正在执行。
- `completed`：执行完成。

你可以这样复述：

> `status` 是任务当前进度的标签。

### 7. 为什么不直接写成一串代码，非要有函数？

因为这个项目的核心就是几个动作按顺序发生：创建任务、记录事件、执行任务、展示任务。用函数把这些动作切开，刚好方便你看函数如何调用。

你可以这样复述：

> 函数不是为了高级，而是为了看清楚每一步叫什么。

### 8. 为什么没有 FastAPI、React、Postgres、SSE？

因为它们是工程外壳，不是理解第一条任务流的必要条件。你先看懂这个文件，再回到真实项目，就能认出：

- FastAPI 负责接收请求。
- Postgres 负责保存这里的 `task/messages/events`。
- Runner 负责执行这里的 `run_task(...)`。
- 前端负责展示这里的 `show_task(...)`。

你可以这样复述：

> 这个文件是骨架，真实项目是在骨架外面加上网络、数据库、页面和模型。

## 如果变成生产代码，还需要补什么？

如果这个学习版要变成真实 MyAgent 那样的生产代码，至少要补这些东西：

1. API：用 FastAPI 接收前端请求，而不是在文件里写死 `user_text`。
2. 数据模型：用明确的 schema 描述 task、message、event。
3. 数据库存储：把任务、消息、事件存到 Postgres，刷新页面后还能恢复。
4. 事件顺序：保证 `seq` 在并发和异常情况下仍然可靠递增。
5. 后台 Runner：API 先返回，耗时任务在后台执行。
6. 真实 Agent：接入模型、工具、文件资源和 DeepAgents 运行时。
7. 前端状态：把后端 `snake_case` 字段转换成前端 `camelCase` 状态。
8. SSE 或轮询：让浏览器实时看到事件，而不是最后一次性打印。
9. 错误和取消：处理失败、取消、超时、重试和半完成状态。
10. 安全边界：保护 provider key、访问 token、上传路径和产物下载。
11. 测试：补后端测试、前端测试、真实浏览器 E2E 和截图证据。
12. 文档和知识包：行为边界稳定后，同步更新项目文档和 `asset/` 知识包。

这一版先不要补这些。学习顺序应该是：

```text
先看懂一个 task 怎么流动
再看懂真实项目怎么把它拆到后端、数据库、Runner 和前端
最后再补生产级可靠性
```
