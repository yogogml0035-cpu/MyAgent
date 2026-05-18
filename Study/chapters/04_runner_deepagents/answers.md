# 04 标准答案

## 自测题答案

1. Runner 负责一次任务运行的生命周期；Agent factory 负责把 settings、model、tools、skills、workspace backend 组装成 DeepAgents 可执行图。
2. `values_snapshot` 包含完成后的图状态。最终回答需要从最终 state 中提取，而不是从任意中间 token 猜。
3. DeepAgents/LangGraph 的原始流格式会变，平台需要统一成 `EventRecord`，这样 storage、SSE、前端都只依赖自己的稳定事件契约。
4. 文件正文可能很大也可能敏感。manifest 只告诉模型“有哪些资源”，具体内容必须通过 task-scoped resource tools 按需读取。
5. Resource tools 只有在当前 run 有 `task_id` 时注册，因为它们必须绑定当前任务 uploads；`searxng_search` 只依赖 `settings.searxng_url`，默认指向本地 SearXNG 引擎。

## 练习观察点

带 `tool_calls` 的 AIMessage 往往是模型在准备调用工具，不是给用户看的最终回答。真实代码中 `extract_final_answer()` 会反向查找最后一个有文本且无工具调用的 AIMessage。
