# DeepAgents 平台知识包

## 背景与范围

本知识包记录 MyAgent 的 DeepAgents 驱动通用 agent 平台。它覆盖后端 agent 架构、模型 provider、工具、事件流、SubAgent、技能加载、API 路由、前端进度日志展示和测试布局。

修改以下范围时优先阅读并同步本文件：

- `backend/app/agent/`、`backend/app/runner/`、`backend/app/models/`
- `backend/app/tools/`、`backend/app/execution/`、`backend/app/streaming/`
- `backend/app/api/`、`backend/app/storage.py`、`backend/app/memory.py`
- `backend/skills/`、`frontend/app/task-state.ts`、`frontend/app/workspace-view.ts`
- `frontend/components/chat/TaskConversation.tsx`
- 前后端任务 API、SSE、上传、产物、模型、技能、长期记忆和浏览器 E2E

## 平台总规则

- 平台唯一执行引擎是 DeepAgents SDK 的 `create_deep_agent()`，返回可执行的 LangGraph `CompiledStateGraph`。
- 默认 agent builder 是 `backend/app/agent/factory.py` 的 `build_agent()`。
- `build_agent()` 负责传入模型、工具、workspace backend、只读 skill backend、scratch state、store 和 `max_concurrent_subagents`。
- `create_deep_agent()` 会自动注入 `TodoListMiddleware`、`FilesystemMiddleware`、`SummarizationMiddleware` 和 `PatchToolCallsMiddleware`；不要再通过 `middleware` 参数重复传入这些默认 middleware。
- Skills 和 SubAgents 通过 `create_deep_agent(skills=..., subagents=...)` 传入，不走 middleware 参数。
- 当前平台是 DeepSeek-only；浏览器安全模型 ID 只有 `deepseek-v4-flash` 和 `deepseek-v4-flash-thinking`。
- 后端是任务、run、message、event、长期记忆元数据、上传和产物的权威来源；前端只渲染后端 HTTP/SSE 投影。

## 模型 provider 规则

- 模型创建入口是 `backend/app/models/provider.py#create_model()`。
- `MODEL_REGISTRY` 只列出 `deepseek-v4-flash` 和 `deepseek-v4-flash-thinking`。
- `/api/models` 只返回浏览器安全模型元数据和 `available` 标记，不暴露 provider key。
- 默认模型是 `deepseek-v4-flash`，可由 `MYAGENT_DEFAULT_MODEL` 调整。
- 后端 API 在 task 创建和 message 发送前校验模型 ID 和 availability；不可用模型不能进入 runner。
- thinking 模型使用 `DeepSeekThinkingChatModel`；non-thinking 路径保持原生 `ChatDeepSeek` 行为。
- DeepSeek thinking tool-call 历史必须通过 `backend/app/models/deepseek_thinking.py` 的本地 adapter 序列化。
- 只有原始 assistant turn 同时包含 provider 返回的 `reasoning_content` 和 `tool_calls` 时，后续请求才能回放 `reasoning_content`。
- non-thinking 或缺失 reasoning 的历史必须剥离 thinking 专属字段，不能从 event、旧 run 或推断中伪造。
- 自动标题生成发生在后端任务 API 边界，首条用户消息开始 run 时用选中模型生成不超过 10 个可见字符的紧凑标题。
- 标题生成和 `set_task_title_if_empty()` 都是 best-effort；一旦 `storage.start_run()` 成功，标题失败不能阻止 `runner.start_background()`。
- 用户手动重命名权威，高优先级于后续自动标题。

## 工具、资源和上传

- 工具是 LangChain `@tool` 函数，包括 DeepAgents filesystem tools、task-scoped resource tools 和可选 SearXNG 搜索。
- SearXNG 通过 `settings.searxng_url` 注册和调用，默认本地 `http://127.0.0.1:8181/`。
- 上传文件是 task Resource，不是自动上下文。
- 支持上传格式：`.md`, `.json`, `.txt`, `.docx`, `.xlsx`, `.xlsm`。
- v1 不接受 `.doc`, `.xls`, `.csv` 或任意本地路径。
- 上传事件类型为 `file_uploaded`，包含稳定 `resource_ref` 和 media type：`markdown`, `json`, `text`, `word`, `excel`。
- 资源执行入口是 `backend/app/execution/resources.py` 的 `LocalResourceExecutionAdapter`。
- 资源工具包括 `list_uploaded_resources`、`inspect_resource`、`read_resource_text`、`read_resource_table`；当 run context 和 storage 可用时，还会提供 `create_word_document` 用于把 Markdown/纯文本转换为 Word 原生标题、列表和表格，并生成登记当前 run 的 `.docx` 产物。
- 工具失败返回 `{ok:false,error:{code,message,retryable}}` JSON，不让 runner 崩溃。
- 用户输入错误（例如无效 Excel range）应是 `retryable:false`。
- Word/docx 读取必须走资源工具；Word/docx 交付生成必须走 `create_word_document`，模型只选择文件名和 Markdown/纯文本参数，标题、列表、表格等 Word 结构由工具环境转换。当前 DeepAgents backend 不提供 shell/python/execute 命令执行能力，prompt 必须明确禁止模型为 Word 生成调用 `bash`、`execute` 或把简单文档生成委派给 `task` 子代理。
- Word/Excel handle 在成功和失败路径都必须关闭。
- 资源工具只能解析当前 task 的 `uploads/`；未来若支持本地路径，必须先注册或复制为当前 task resource。
- Runner 注入资源 manifest 时只包含 filename、resource_id、format、size、digest，不能包含上传正文。

## 技能和 SubAgent

- 项目技能遵循 DeepAgents `SKILL.md` 约定：YAML frontmatter 包含 `name` 和 `description`，正文是 Markdown 指令。
- 运行时技能来源来自 `settings.skills_dirs`，默认相对 `backend/` 的 `./skills`。
- 技能在 DeepAgents composite backend 中以只读虚拟路径挂载，默认模型可见路径是 `/skills/`。
- progressive-disclosure 读取使用 `/skills/<skill>/SKILL.md` 这类路径；task 文件写入仍限制在 task workspace。
- 浏览器项目技能发现是独立安全边界：`GET /api/skills` 只读取仓库 `backend/skills`，只返回 name/description。
- `/api/skills` 不得读取 `settings.skills_dirs`、`MYAGENT_SKILLS_DIRS`、`.agents/skills`、Codex 全局技能、用户 home、技能正文或额外 frontmatter。
- message submission 可带 `skills` 数组；后端先校验项目技能名，再把可见 `[$skill]` 引用加入传给 storage、标题生成和 runner 的有效消息。
- Composer 的 skill picker/chips 是浏览器交互，不应在普通 UI marker 前显示 `$`；`$` 只保留给持久化 message reference 合同。
- SubAgents 是包含 `name`、`description`、`system_prompt` 和可选 model/tools/skills 的定义；当前内置 researcher、coder、file-analyst。

## 任务生命周期与运行状态

- `TaskRunner` 生命周期：build agent -> recall long-term memory -> stream events -> convert -> collect -> persist events -> update terminal status -> emit final answer event -> schedule completed-run memory write。
- `TaskRunner.__init__` 从 `main.py` 接收 settings、storage 和可选 memory service。
- `storage.start_run()` 创建 run id；`runner.start_background()` 必须接收该 run id，确保 storage 和 streaming events 统一归属。
- `TaskRunner.start()` 与 `start_background()` 都要把 streamed `EventRecord.run_id` 规范化为当前 run，防止 provider/status/answer delta 串到其他 run。
- terminal events 包括 `task_completed`、`task_failed`、`task_cancelled` 和 terminal status update。
- cancellation 快速路径由 `POST /api/tasks/{id}/cancel` 调用 `TaskRunner.request_cancel()` 后立即把当前 run 标记为 `cancelled` 并追加 run-scoped `task_cancelled` event；`TaskRunner.cancel()` 仍保留给需要等待后台 task 收敛的内部/测试路径。后台 task 后续若收到 `CancelledError`，不得再追加第二个取消事件。
- `asyncio.timeout()` 通过 `settings.agent_timeout_seconds` 防止 agent run 无界运行。
- 不同 task/session 可以并行运行；同一 task 运行中必须互斥。
- `backend/app/api/tasks.py#send_message()` 的同 task 互斥是双层保护：先查 `runner.is_running(task_id)` 返回 409，再由 `storage.start_run(... expected_statuses=...)` 兜底。
- `backend/app/storage.py#list_task_summaries()` 只把至少有一条非空 user message 的 task 暴露给历史栏；E2E seed 历史时不能只改 title。
- 缺上传、缺正文且没有可复用上下文时，runner 应在真正启动 agent 前写一条普通 assistant 澄清消息，并结束当前 run；这个场景不应生成用户可见的 `needs_input` warning 或“配置提醒”。
- `needs_input` 是可继续、可删除、可清空的非运行状态；删除/清空只应阻止 `running` 或 `runner.is_running(task_id)` 仍为真。

## 事件、SSE 和恢复语义

- Streaming 使用 `agent.astream(input, stream_mode=["messages", "updates"], version="v2")`。
- LangGraph v2 chunk 当前为 dict：`{type, ns, data}`；adapter 仍要兼容旧 tuple 格式。
- `backend/app/streaming/v2_adapter.py` 负责标准化 chunk。
- `backend/app/streaming/event_converter.py` 负责生成 `EventRecord`。
- tool-call chunk 是增量的，adapter 必须按 tool-call index/id 累积，让持久化 `tool_call` event 有可用 tool name 和参数项。
- tool-call partial 可能按字符级流式到达；adapter 只能按参数长度 bucket 发送少量 partial 进度，最终完整 tool call 仍需发送。event converter 必须截断 partial payload 中超长的 `args`/`raw_args`，保留 `*_truncated` 和 `*_original_chars` 元数据，避免把同一巨型参数重复写入 Postgres 和 SSE。
- SSE endpoint `GET /api/tasks/{task_id}/stream` 使用 `EventSource`；token 通过 query 参数传入。
- SSE `_event_stream` 每 0.5 秒轮询 `storage.read_events(task_id, after_id=last_event_id)`。
- `last_event_id` 初始值必须是 `None`，不能是空字符串；空字符串会导致初次轮询误跳过所有事件。
- event pagination cursor 是 best-effort 客户端提示，不是权威。
- `storage.read_events(task_id, after_id=...)` 找不到 cursor 时必须 fail open，返回该 task 的完整有序事件流。
- `storage.read_events(..., run_id=...)` 可以做 run-scoped diagnostics，但 cursor 仍是 task-scoped：先按 task-wide `seq` 解析 `after_id`，再套 run filter。
- Event seq 由 `tasks.latest_event_seq` 递增并与 event insert 在同一数据库事务中完成；不要恢复每次 append 扫全量日志。

## 最终答案与中间过程边界

`assistant_thinking_delta` 和 `assistant_answer_delta` 是中间过程 token，不是最终答案。

后端职责：

- `extract_final_answer()` 从 root graph state 的 `messages` 反向查找最后一个有 content 且无 `tool_calls` 的 `AIMessage`。
- reasoning chunk 转为 `assistant_thinking_delta`，完整 reasoning 放在 `payload.content`，默认展示文案使用稳定的 `"AI正在思考..."`。
- thinking chunk 如果与 tool-call 同 turn 到达，应在 diagnostics payload 带 `tool_call_id`、`tool_call_ids` 或标准化 `tool_calls`。
- subgraph output 不能变成 root `message_chunk`，subgraph `values_snapshot` 不能用于 final answer extraction。
- `TaskRunner.start()` 只用 root `values_snapshot` 更新 latest state。
- `runner/core.py` 必须先把 final answer 存为 `ChatMessage`，再追加 `final_answer` event，避免前端刷新竞态。
- `final_answer` event 使用 `type="final_answer"`、`level="success"` 和 `payload={"content": ...}`。

前端职责：

- `buildLiveLogItems()` 把 thinking/answer delta 作为 progress/diagnostics 信号。
- collapsed rows 只显示 `"AI正在思考"`、`"AI正在生成结果"` 等稳定中文标签。
- expanded JSON 和 run-level raw JSONL 下载保留完整 normalized content。
- `final_answer` 不在进度 timeline 中单独显示，但保留在 raw JSONL 和刷新触发逻辑中。
- AI reply card 只来自 run 完成后刷新得到的 `messages` 数组。
- 不要把 `streamedAnswer` 或最后一个 answer delta 当权威最终答案。

禁止：

- 禁止把最后一个 `assistant_answer_delta` 当 final answer。
- 禁止把 subgraph message chunk 或 subgraph values snapshot 替换 root answer/state。
- 禁止在 ChatMessage 存储前发 `final_answer` event。
- 禁止把 thinking/answer delta 渲染成独立 AI reply card。

## 进度日志展示规则

- 进度日志是 append-only event log 的用户可见投影。
- collapsed timeline 保持后端 `EventRecord.seq` 顺序；没有 seq 的 legacy event 才 fallback 到 `created_at`。
- reasoning delta 只合并到连续 `"AI正在思考"` 片段，answer delta 只合并到连续 `"AI正在生成结果"` 片段。
- `status_update` 默认折叠为 `"状态已更新"`，不要暴露 middleware/internal node 文案。
- `final_answer` 不作为独立 collapsed row 展示。
- tool progress 拆成阶段行：`selecting_tool`、`using_tool`、`tool_result`。
- 同一 stage、同一 `tool_call_id` 的 tool-call chunk 才合并，避免参数增量刷出重复行。
- 同一 stage、同一 `tool_call_id` 的 partial tool-call delta 在前端只保留最新 compact diagnostics 和 `delta_count`；不能把几千条 partial raw record 合并进同一个 row 的 `<pre>`。
- 主对话默认只展示关键阶段、当前动作、警告、错误和终态；完整 `assistant_thinking_delta`、`assistant_answer_delta`、`values_snapshot` 与 `final_answer` 正文不能作为默认长段落回流到主页面。
- 行级展开和复制使用 compact display JSON；run-level raw JSONL 下载才是完整诊断导出。
- 完整 run 日志必须通过用户点击后生成的 run-scoped JSONL 下载获得，不能在 render 阶段预构造完整诊断字符串，也不能默认渲染完整 `<pre>`。为了保护浏览器主线程，超长 partial tool-call 参数和超长 closed stream raw diagnostics 在复制/下载投影中也要保留事件边界但压缩 payload 正文。
- `ExecutionLog.rawRecord` 必须保持 non-enumerable，避免 raw provider chunk、tool payload、内部 node name 泄露进默认渲染或 `JSON.stringify(state.logs)`。
- `frontend/app/task-state.ts` 标准化时保留完整 `payload.content`；截断只能发生在 collapsed preview projection。
- 前端 SSE 合并必须按浏览器帧批量 flush；不能让每条 event 都触发一次 React 全量日志 projection。
- trace-level `"全部展开"` / `"全部折叠"` 控制必须在同一次点击内让按钮状态和所有可见 `<details open>` 状态收敛；浏览器测试断言稳定 post-click open-count。
- 诊断 JSON 容器保持中性暗面视觉，不要给普通排障输出加红色错误框。

## 上下文与长期记忆

- `ConversationContextBuilder` 每次 run 都从当前 task 的 Postgres message history 构建确定性同会话上下文。
- 上下文可包含 bounded session summary、最近消息和新鲜 tool-cache context。
- 普通上下文不能回放 `assistant_thinking_delta`、raw tool-call arguments、tool-result payload 或其他 run diagnostics。
- Runner 在同会话上下文之后追加长期记忆 recall 和 resource manifest message。
- 长期记忆只写稳定的 `preference`、`profile_fact`、`project_rule`、`stable_workflow`。
- `reasoning_content` 只能留在当前 run 事件日志和展开诊断中，不能进入普通 messages、conversation context、长期记忆、Qdrant payload 或默认 artifact。
- Postgres 是长期记忆 canonical store，Qdrant 是语义索引，可通过 admin CLI 重建。
- recall/write 失败不应阻塞 event loop、延迟 final answer 或把成功 run 改成 failed。

## 存储、上传和产物

- Postgres 是 tasks、runs、messages、events、agent store、tool cache、long-term memories 的权威存储。
- task 文件 workspace 位于 `settings.workspace_root / task_id`。
- workspace 顶层稳定目录当前限制为 `uploads/` 和 `artifacts/`。
- `uploads/` 保存源文件；`artifacts/` 保存 run-scoped generated files 和 legacy mirrored standard reports。
- `artifacts/` 应在写 run manifest 或真实 artifact 时懒创建，启动 run 本身不应创建空 artifact dir。
- 不要新增 `logs/`、`subagents/` 或 root-level manifest 等顶层 task 文件夹，除非先设计稳定文件合同。
- 删除非 running task 必须同时删除 Postgres task row 和 matching local task workspace。
- task workspace 内真实生成的 `.docx`、`.pptx`、`.xlsx`、`.xlsm`、`.pdf`、`.html`、`.md` 文件需要先通过 run-scoped artifact 登记或安全复制到 `artifacts/runs/{run_id}/`，再暴露给前端下载。
- 用户明确要求的交付文件，或 final answer 明确声称“已生成/已保存”的文件，必须存在且已登记为当前 run artifact；否则 task/run 不能标记为成功完成。
- 交付成功优先按当前 run 已登记 artifact 类型判定：Word 看任意 `.docx`，PPT 看任意 `.pptx`，Excel 看任意 `.xlsx`/`.xlsm`，报告看任意 `.html`/`.md`/`.pdf`；只要类型满足请求，就不要因为 final answer 推断出的文件名和 artifact 文件名不同而误报失败。
- 缺失交付文件时应给出可见的 `文件未生成或未登记为产物` 修正提示，并保持 artifact API 不暴露不可下载的本地路径或伪链接。
- 真实缺失交付文件时，后台交付保护仍应把 task/run 留在失败修正路径，但前端用户可见 payload 只应暴露简短说明和安全重试入口，不能泄露 `reason`、`repair_hint`、`missing_artifact_names`、`missing_deliverables`、`requested_deliverable_types`、`promoted_artifacts` 等内部字段名。
- Artifact routes：
  - latest/legacy：`GET /api/tasks/{id}/artifacts/{name}`
  - run-scoped：`GET /api/tasks/{id}/runs/{run_id}/artifacts/{name}`
- 前端 artifact fetch 只允许当前 API origin 和当前 task artifact routes；拒绝外部 origin、非 artifact path、错误 task id、query/hash redirect、artifact name mismatch 后才能附加 token。
- HTML artifact 预览必须在 popup `about:blank` 中写 preview shell，再把 blob 放进 `iframe sandbox=""`，不得 top-level navigation 到 same-origin `blob:`。

## API 和认证边界

- REST routes：
  - `POST /api/tasks`
  - `GET /api/tasks`
  - `GET /api/tasks/{id}`
  - `PATCH /api/tasks/{id}`
  - `DELETE /api/tasks/{id}`
  - `POST /api/tasks/{id}/messages`
  - `POST /api/tasks/{id}/cancel`
  - `GET /api/tasks/{id}/events`
  - artifact routes
- `GET /api/tasks/{id}?include_events=false` 是轻量刷新路径，返回同样 task shape，但 events 为空。
- 上传错误映射必须稳定：duplicate 409，size/count/request limits 413，unsupported extension 或 invalid JSON 400，missing task 404。
- multipart request limit 必须在 FastAPI `UploadFile` parsing 前由 middleware/receive wrapper 第一层拦截，storage 限制是第二层防线。
- auth middleware 默认 loopback-only；非本地访问需要 `MYAGENT_ACCESS_TOKEN`。
- SSE query token 是浏览器 `EventSource` 限制带来的兼容方案；不要记录完整 URL。
- 本地 WSL dev 默认后端/前端绑定 `127.0.0.1`；绑定 `0.0.0.0` 是显式 LAN 暴露模式，必须配 token 和 CORS。

## 前端运行和构建边界

- 前端 dev server 使用 `.next-dev`，production build 使用 `.next`；这是 `frontend/next.config.mjs` 的当前权威事实。
- 复用中的 `3001` dev server 旁边运行 build/typegen/E2E 时，依赖 `.next-dev` 和 `.next` 分仓，避免 dev/build manifest 互相污染。
- WSL mounted Windows path 文件通知可能不稳定，保留 polling watchers：frontend 使用 `watchOptions.pollIntervalMs`、`WATCHPACK_POLLING=true`、`CHOKIDAR_USEPOLLING=true`；backend reload 可用 `WATCHFILES_FORCE_POLLING=true`。
- `next typegen && tsc --noEmit` 是前端 typecheck 入口；`next-env.d.ts` 是生成文件且 ignored。
- `npm run lint` 使用 `eslint . --max-warnings=0`，warning 也是阻塞项。

## 验证规则

后端行为变更常用：

```bash
cd backend
uv run pytest
uv run ruff check .
uv run mypy app tests
```

前端行为变更常用：

```bash
cd frontend
npm run typecheck
npm test
npm run lint
npm run build
```

跨系统或浏览器可见行为变更还必须运行实际服务上的 Playwright E2E，并把截图/证据保存在 `frontend/e2e-playwright/e2e-YYYYMMDDHHMMSS/`，证据目录不提交。

文档-only 变更至少运行：

```bash
git diff --check
```

如果任务包含 push、PR 或 merge，必须等待远程 GitHub checks 完成并确认通过后再声明完成。

## 回归风险清单

- 重复注入 DeepAgents 默认 middleware。
- 删除 storage compatibility shim 而未改完调用方。
- `/api/models` 不再返回 availability，或 API 对 unavailable provider 仍调度 run。
- DeepSeek thinking adapter 伪造旧 run 缺失的 `reasoning_content`。
- reasoning/tool diagnostics 进入普通 messages、context、memory、Qdrant 或默认 artifact。
- `assistant_thinking_delta` 的 top-level `message` 或 `payload.live.display_text` 泄露完整 reasoning。
- `final_answer` event 早于 ChatMessage 存储，引发前端刷新竞态。
- subgraph output 污染 root final answer。
- `read_events(after_id="")` 或 unknown cursor 返回空，导致 SSE 恢复丢事件。
- task-scoped run filter 破坏 task-scoped cursor 语义。
- front-end progress log 只按时间排序，导致同秒流事件乱序。
- `rawRecord` 变成 enumerable，导致 raw provider/tool payload 进入默认 JSON。
- re-enable `streamedAnswer` AI reply card，把中间 token 当最终回复。
- artifact URL validation 放宽，导致 token 发往外部或错误 task URL。
- HTML preview 重新 top-level 跳转 blob 或允许 scripts。
- upload error 又冒成 500。
- multipart body limit 后移到 storage-only，导致 parser 先吃完整请求。
- 删除/清空 task 只做前端状态修改，不调用后端 DELETE。
- dev/build 输出目录回退到同一个 `.next`，导致复用 dev server 时 manifest 污染。
- UI 行为变更只跑单测，跳过真实浏览器 E2E 和截图证据。
- 用一次性 DevTools 调试替代 Playwright 稳定断言。
- PR 工作在远程 checks 结束前声明完成。

---

*知识包刷新：2026-05-24*
