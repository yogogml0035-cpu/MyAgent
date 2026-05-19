# 学习计划

目标：你不是背文件名，而是能回答“用户点发送后，系统发生了什么”，并能定位相关代码。

## 第 1 阶段：建立地图

建议用时：1-2 天。

学习内容：

- 读 [architecture_map.md](./architecture_map.md)，先看数据流。
- 读 [glossary.md](./glossary.md)，把 Task、Run、Event、Artifact、Resource、Runner、Storage 区分开。
- 先跑 [00 最小可运行示例](./chapters/00_minimal_runnable_example/README.md)，把最短主链路追一遍。
- 完成 [01 大图景](./chapters/01_big_picture/README.md)。

你要能回答：

- 为什么一个 Task 可以有多个 Run？
- 为什么最终回答不是简单等于所有流式 token 拼接？
- 前端为什么需要同时处理 HTTP 刷新和 SSE？

阶段验收动作：

- 跑完 `00` 和 `01` 两个 mini unit。
- 不看文档，口头解释一次 `task` 和 `run` 的区别。
- 能说出“为什么前端不直接调模型”。

## 第 2 阶段：理解后端主链路

建议用时：3-5 天。

学习内容：

- [02 后端 API 与 Schema](./chapters/02_backend_api_schemas/README.md)
- [03 Storage 与事件日志](./chapters/03_storage_event_log/README.md)
- [04 Runner 与 DeepAgents](./chapters/04_runner_deepagents/README.md)

你要能画出：

```text
POST /api/tasks 带 message 或 POST /api/tasks/{id}/messages
  -> API 校验 task/model/status
  -> storage.start_run()
  -> title_generator 尝试生成标题，失败只记录 warning
  -> runner.start_background()
  -> runner.start()
  -> build_agent() + get_platform_tools()
     （resource tools + searxng_search）
  -> stream_agent()
  -> convert_stream_event()
  -> storage.append_event()
  -> storage.update_task_if_status_and_append_event()
  -> final_answer 事件和可选长期记忆写入
```

阶段验收动作：

- 把 `02`、`03`、`04` 的 mini unit 至少各改坏并修回一次。
- 能从 `api/tasks.py` 跳到 `storage.py`、`runner/core.py`，解释一条消息如何变成 run。

## 第 3 阶段：理解文件、工具、前端状态

建议用时：3-5 天。

学习内容：

- [05 上传资源、工具与产物](./chapters/05_uploads_tools_artifacts/README.md)
- [06 流式事件与前端状态](./chapters/06_streaming_frontend_state/README.md)
- [07 前端工作区](./chapters/07_frontend_workspace/README.md)

你要能解释：

- 上传文件为什么不直接塞进模型上下文？
- `read_resource_text` 和普通文件读取有什么边界区别？
- `searxng_search` 为什么走本地 SearXNG，而不是 provider API key？
- 前端为什么要把后端 `snake_case` 转成 `camelCase`？
- 进度日志为什么主要按 `seq` 排序？

阶段验收动作：

- 能不看文档，画出一次“先上传文件、再发送消息、再接 SSE”的前端链路。
- 能区分 `mergeExecutionLogs` 和 `workspace-view.ts` 的职责。

## 第 4 阶段：理解安全、记忆、业务扩展

建议用时：2-4 天。

学习内容：

- [08 安全、记忆与测试](./chapters/08_security_memory_testing/README.md)
- [09 招投标分析工作流](./chapters/09_bid_analysis_workflow/README.md)

你要能判断：

- 哪些数据不能进入长期记忆？
- 为什么本项目默认只允许 loopback 访问？
- 招投标分析应该沉淀在哪个知识包？
- 行为变更为什么必须有浏览器 E2E 和截图证据？

阶段验收动作：

- 能说出长期记忆允许保存的四类内容。
- 能解释“为什么招投标业务规则主要放知识包，而不是前端页面里”。

## 最终自测

请不看文档，用自己的话写出下面 5 个答案：

1. MyAgent 的后端入口、前端入口分别在哪里？
2. 用户发送消息后，`TaskRunner` 和 `TaskStorage` 各自负责什么？
3. SSE 连接断开后，前端如何补齐事件？
4. 上传文件经过哪几层校验，为什么工具只能读当前 task 的 uploads？
5. 如果你要新增一个模型提供方，需要改哪些模块和测试？

标准答案在各章节的 `answers.md` 中分散给出；你也可以把答案和章节文档互相对照。

## 学习检查清单

完成全部章节后，你应该能做到：

- 从一个 API 路由跳到对应 schema、storage 方法、测试文件。
- 看懂一个 `EventRecord` 如何从后端流式事件变成前端进度行。
- 判断某个文件读取需求是否越过 task workspace 安全边界。
- 说清楚短期会话上下文、长期记忆、上传资源 manifest 的区别。
- 分辨“当前源码已实现”和“知识包记录的未来业务边界”。

## 卡住时回看哪里

如果你在学习时出现下面这些典型卡点，可以直接回看对应章节：

- 分不清 `task`、`run`、`event`：回看 `00`、`01`、`glossary.md`
- 不知道消息为什么先过 API 再进 Runner：回看 `02`、`03`、`04`
- 不知道日志为什么乱序或为什么要 SSE：回看 `06`
- 不知道上传文件为什么不直接进 prompt：回看 `05`
- 不知道页面为什么要 hook + task-api + task-state + workspace-view 四层：回看 `07`
- 不知道什么能进长期记忆、什么绝对不能进：回看 `08`
- 不知道业务知识和平台代码怎么分层：回看 `09`
