# 最终自测：从用户动作反推代码

这个自测不要求你背诵文件名，而是检查你能不能用项目真实代码解释业务流程。

## Part A：闭卷问答

先不要看答案，写下你自己的回答。

1. 用户在空白页面输入消息并点击发送，前端经过哪些函数后发到后端？
2. 后端收到 `POST /api/tasks/{id}/messages` 后，为什么不能直接调用模型？
3. `TaskRunner.start()` 在当前用户消息前面可能注入哪三类上下文？
4. 上传文件为什么先变成 Resource，而不是直接变成 prompt 文本？
5. `assistant_answer_delta`、`final_answer`、`task_completed` 三类事件分别表示什么？
6. SSE 断开后，前端用什么方式补齐事件？
7. 为什么 artifact 下载要校验 origin、task id、run id 和 artifact name？
8. 长期记忆允许保存哪四类内容？哪些内容绝对不应该保存？
9. 当前招投标 PDF compare 哪些是知识包中的设计边界，哪些是源码中已实现的平台能力？
10. 如果你新增一个行为变更，为什么不能只写单元测试就交付？

## Part B：源码定位题

请在源码中找到这些位置，并写一行说明：

| 要找的东西 | 参考路径 |
| --- | --- |
| 创建 FastAPI app 并注册路由 | `backend/app/main.py` |
| 发送消息 API | `backend/app/api/tasks.py` |
| 任务运行编排 | `backend/app/runner/core.py` |
| DeepAgents 工厂 | `backend/app/agent/factory.py` |
| 事件转换 | `backend/app/streaming/event_converter.py` |
| SSE endpoint | `backend/app/api/streaming.py` |
| 上传资源工具 | `backend/app/execution/resources.py` |
| 前端任务编排 hook | `frontend/hooks/use-task-workspace.ts` |
| 前端状态归一化 | `frontend/app/task-state.ts` |
| 前端可见日志投影 | `frontend/app/workspace-view.ts` |

## Part C：最小修改实验

任选三项做：

1. 把 `Study/chapters/03_storage_event_log/mini_unit.py` 里未知 `after_id` 改成返回 `[]`，解释为什么失败。
2. 把 `Study/chapters/04_runner_deepagents/mini_unit.py` 里最终回答提取改成直接返回最后一条消息，解释为什么失败。
3. 把 `Study/chapters/06_streaming_frontend_state/mini_unit.mjs` 里展示排序改成只按 `createdAt`，解释为什么失败。
4. 把 `Study/chapters/07_frontend_workspace/mini_unit.mjs` 里 `guardModel` 移到 `uploadFiles` 后面，解释为什么失败。
5. 把 `Study/chapters/09_bid_analysis_workflow/mini_unit.py` 里对比分析允许 1 份 bid，解释为什么失败。

## 参考答案

1. `ChatComposer` 触发 submit，`TaskWorkspace` 把回调传给 composer，`useTaskWorkspace.handleSubmit()` 校验、ensureTask、uploadTaskFiles、postTaskMessage，再 refresh task 和 history。
2. API 需要先校验 task 是否存在、是否正在运行、模型是否注册且 provider key 可用，再由 storage 创建 run_id，最后 Runner 用同一 run_id 接管后台执行。
3. 同 task 会话上下文、长期记忆上下文、上传资源 manifest。
4. Resource 边界能限制文件范围、分页读取、避免上下文膨胀和敏感内容直接进入 prompt。
5. `assistant_answer_delta` 是中间流式片段；`final_answer` 是完成后从 graph state 提取的权威答案；`task_completed` 是任务终态事件。
6. EventSource 出错后，前端调用轻量 task refresh 和 `/events?after_id=...`，并指数退避重连。
7. 防止外部 URL 或错误 task/run/name 窃取 token 或打开不可信产物。
8. 允许 `preference`、`profile_fact`、`project_rule`、`stable_workflow`；不能保存上传原文、完整产物、密钥、授权头、原始工具日志、客户敏感文本。
9. 已实现平台能力包括 Task/Run/Event/Resource/Artifact/SSE/Runner；PDF ingest、compare renderer、evidence preview、manual override 当前主要是知识包设计边界，需要结合源码进一步确认。
10. 行为变更影响真实浏览器流程时，单元测试不能证明页面交互、异步状态、网络请求、产物打开和截图状态正确；项目规范要求对应浏览器 E2E 和截图证据。

