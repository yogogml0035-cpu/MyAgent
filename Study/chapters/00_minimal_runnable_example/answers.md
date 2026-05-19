# 00 标准答案

## 自测题答案

1. `frontend_send_message()` 只负责发起流程。真实答案应该由后端和 Agent 产生，因为状态、工具、文件、密钥都在后端控制。
2. `api_send_message()` 需要 `run_id`，因为同一个 task 里可能会有很多次执行。没有 `run_id`，这次执行就没法单独追踪。
3. `runner_start()` 负责组织执行流程，`fake_agent()` 负责产出回答。你可以把它们理解成“项目经理”和“真正干活的人”。
4. 因为前端应该读取已经写好的事实，而不是读取一半状态。先写完状态和消息，再渲染，页面才不会乱。
5. 核心逻辑是 `frontend_send_message -> api_send_message -> runner_start -> fake_agent -> storage_finish_run -> frontend_render`。`assert_project_links()` 是对齐真实项目用的小检查，不是这条主链路本身。

## 练习观察点

如果你把 assistant 消息写回去那一行删掉，任务虽然能完成，但页面没有最终答案。这能帮你理解：完成状态和聊天消息是两份不同的数据。
