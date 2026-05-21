# 功能: 多会话并行与 Thinking 审计

下面这份计划应尽可能完整，但在真正开始实现前，仍然必须再次验证 DeepSeek 官方文档、LangChain/DeepAgents 当前消息序列化行为、代码库模式以及任务本身是否合理。

特别注意现有 utils、types、models 的命名，并确保从正确的文件中导入。`reasoning_content` 是高敏运行证据，只能存在于当前 run 的诊断事件链路中，不得进入长期记忆、普通聊天消息或默认产物。

## 功能描述

本功能让 MyAgent 支持不同会话真正并行运行任务，同时保持同一会话内单 run 互斥；修复 DeepSeek thinking 模型在工具调用后的 `reasoning_content` 回传问题；为新 run 保存完整可审计事件流；前端默认继续展示简洁进度，展开日志或复制诊断时可以看到完整 reasoning、provider 与工具链路证据。

## 用户故事

作为一名 MyAgent 本地任务工作台用户，
我想在会话 A 运行中切到会话 B 发起另一个任务，并且 thinking 模型工具调用不会因缺失 reasoning 回传失败，
以便多个独立任务可以并行推进，排障时也能按 run 追溯完整证据。

## 问题陈述

当前后端 runner 和 storage 已经具备按 `task_id/run_id` 归属运行状态的基础，但前端存在全局 `isBusy` 对会话切换和发送的阻塞风险，可能让“跨会话并行”在 UI 层无法自然发生。另一方面，后端流式链路已经能把 provider 暴露的 `reasoning_content` 转成 `assistant_thinking_delta` 事件，但还需要验证并补齐 DeepAgents/LangChain 在工具调用后的下一次 provider 请求中，是否把带 `reasoning_content` 与 `tool_calls` 的 assistant message 原样回传给 DeepSeek。若只保存 thinking 事件、不回传 provider 消息，仍会触发 DeepSeek 400。

## 方案陈述

采用“先表征、再最小补齐”的方案：

- 后端保留现有单进程、本地优先、按 task 互斥的运行边界，不引入全局并发队列或上限。
- 通过单元/集成测试先固定不同 task 可并行、同 task 409 互斥、run 事件隔离、thinking 工具调用消息必须回传 `reasoning_content` 的行为。
- 在 provider/agent 流式链路中补齐 thinking tool-call 需要的 assistant message 保真能力，必要时增加 DeepSeek thinking 消息适配层，确保同一 run 内工具结果后的下一次请求携带 `reasoning_content`、`content` 和 `tool_calls`。
- 将完整 `reasoning_content` 持久化为 run 事件诊断内容，继续禁止进入 `messages`、长期记忆、默认 artifact。
- 前端将“正在发送/切换/上传”的忙碌状态收敛到当前操作或当前 task，不用全局 `isBusy` 阻塞切换到其他会话并发送；同一会话运行中的发送保护保持不变。
- 前端默认进度行继续只显示稳定标签，展开/复制诊断展示当前 run 的完整 raw JSONL 和 normalized thinking 内容。

## 功能元数据

**功能类型**: 增强 + 缺陷修复  
**预估复杂度**: 高  
**主要受影响系统**: FastAPI task API、TaskRunner、DeepAgents streaming/provider adapter、Postgres event log、长期记忆写入边界、Next.js workspace hook、进度日志 UI、Playwright E2E  
**依赖项**: DeepSeek thinking API、langchain-deepseek、DeepAgents、LangGraph、Postgres、Next.js/React、Playwright

---

## 上下文参考

### 相关代码文件 重要：实现前必须先阅读这些文件！

- `tasks/multi-session-thinking-audit/prd.md` - 原因：功能目标、用户故事、验收口径和安全边界来源。
- `tasks/multi-session-thinking-audit/requirements.md` - 原因：原始对齐稿，明确 `reasoning_content` 不能进入长期记忆、普通聊天消息或默认产物。
- `AGENTS.md` (lines 84-115, 122-141) - 原因：行为变更必须同步代码、测试、浏览器 E2E、截图证据和知识包；本地服务默认端口为 `8001/3001`。
- `ARCHITECTURE.md` - 原因：确认 Postgres 是任务、运行、消息、事件日志和长期记忆的权威存储，SSE 只是投影。
- `INTERFACES.md` (lines 55-78, 120-121) - 原因：确认 snake_case/camelCase 边界、`run_id` 贯穿 storage/streaming/frontend、WSL 启动脚本入口。
- `DESIGN.md` - 原因：前端日志和交互变更必须保持现有暖色画布、珊瑚色主色、字体、圆角、间距和 CSS 变量。
- `asset/deepagents_platform_knowledge_pack.md` (lines 39, 236-271) - 原因：记录 runner、progress log、thinking/answer delta 作为过程日志的稳定业务规则；本功能完成后必须同步更新。
- `backend/app/api/tasks.py` (lines 81-103, 146-171) - 原因：创建 task 和发送消息时调用 `storage.start_run()` 与 `runner.start_background()`；同一 task 运行中通过 `runner.is_running(task_id)` 和 storage 状态返回 409。
- `backend/app/runner/core.py` (lines 99-207, 209-290, 431-434) - 原因：`_active_runs` 当前按 `task_id` 管理；stream events 在 `on_event` 中落库；最终答案只从 graph state 提取为普通 assistant message；长期记忆写入只接收 user goal 与 final answer。
- `backend/app/storage.py` (lines 333-393, 592-642, 681-705, 858-1007, 1288-1305) - 原因：Postgres schema、run 创建、active_run_id 保护、事件追加和事件读取的权威实现。
- `backend/tests/fakes.py` - 原因：InMemoryTaskStorage 需要镜像 storage contract，后端单测变更必须同步。
- `backend/app/models/provider.py` (lines 32-55) - 原因：当前只创建 `ChatDeepSeek` 并用 `extra_body={"thinking": {"type": thinking_mode}}` 打开/关闭 thinking；需要评估是否在此或相邻 adapter 中包裹 DeepSeek thinking 消息回传。
- `backend/app/agent/factory.py` (lines 140-181, 219-228) - 原因：agent 构建统一调用 `_create_model()`，适合接入 provider wrapper，但必须保持 DeepAgents backend/middleware 现有模式。
- `backend/app/conversation_context.py` (lines 69-112, 137-149) - 原因：跨 run 会话上下文只从 `ChatMessage` 构建 user/assistant/system 普通消息；不得把 run 诊断 reasoning 混入普通历史。
- `backend/app/streaming/v2_adapter.py` (lines 46-90, 172-205, 384-412) - 原因：当前从 `AIMessageChunk.additional_kwargs.reasoning_content` 等字段抽取 thinking chunk；需要验证是否捕获完整 sub-turn reasoning，并保留 raw provider 字段以供回传或诊断。
- `backend/app/streaming/event_converter.py` (lines 12-20, 58-100) - 原因：`thinking_chunk` 转 `assistant_thinking_delta`，payload 包含 `content` 和 display-safe live metadata。
- `backend/app/memory.py` and `backend/tests/unit/runner/test_memory.py` (lines 16-45, 102-146) - 原因：长期记忆只保存高层摘要并做脱敏；必须新增防止 reasoning/tool raw logs 进入 memory 的回归测试。
- `frontend/hooks/use-task-workspace.ts` (lines 183-192, 434-488, 558-580, 638-643) - 原因：全局 `isBusy` 与当前 `activeTask` 共同阻塞发送、技能选择和会话切换，是跨会话并行 UI 的主要疑点；清空所有会话继续阻止任意运行中 task 可保留。
- `frontend/components/chat/ChatComposer.tsx` (lines 54-85, 387, 497-514) - 原因：发送按钮、stop 按钮、placeholder 与 `activeTask/isBusy` 绑定；需要保持同会话运行中不可发送。
- `frontend/app/task-state.ts` (lines 30-49, 507-510, 960-1000, 1018-1050) - 原因：ExecutionLog 已有 `answerStream`、`thinkingStream`、non-enumerable `rawRecord`；当前 thinking/answer normalized content 有 8000 字符上限，和“展开诊断完整可见”存在冲突。
- `frontend/app/workspace-view.ts` (lines 192-194, 196-205, 372-381, 624-645, 1427-1438, 1482-1570) - 原因：progress log 构建、thinking row 合并、raw JSONL 复制、run 分组和 seq 排序的核心实现。
- `frontend/components/chat/TaskConversation.tsx` - 原因：进度日志展开/折叠、复制诊断、run activity groups 的实际渲染位置。
- `frontend/e2e-playwright/test_progress_log_disclosure.spec.mjs` (lines 1-45, 90-125, 450-480, 640-680) - 原因：已有基于真实前后端和 Postgres seed 的 progress log 披露验收，可复用截图、展开、复制、JSON 断言模式。
- `frontend/e2e-playwright/README.md` (lines 28-41, 58-71) - 原因：E2E 证据目录、环境变量和实际服务验收方式。
- `README.md` (lines 159-175) - 原因：项目启动脚本在 Windows PowerShell 中调用 WSL，后端/前端实际运行在 WSL，且默认开启 polling watcher。
- `scripts/start-dev-wsl.ps1` (lines 257-275) - 原因：启动脚本会转换 WSL 路径、预检 `uv/npm`、默认停止端口并打开 Windows Terminal 标签；本功能验收优先复用已有服务，若要启动应使用 `-NoStop` 避免杀用户服务。

### 需要创建的新文件

- `backend/tests/unit/models/test_deepseek_thinking_messages.py` - 表征并验证 thinking tool-call 后的 assistant message 必须包含完整 `reasoning_content`、`content`、`tool_calls`。
- `backend/tests/unit/runner/test_concurrency_and_thinking_audit.py` - 验证不同 task 可同时 active，同 task 仍互斥，run 事件和 reasoning 不串线。
- `frontend/e2e-playwright/test_multi_session_thinking_audit.spec.mjs` - 使用实际前后端服务覆盖跨会话并行、同会话互斥、expanded diagnostics 与截图证据。

可能需要创建，取决于表征测试结果：

- `backend/app/models/deepseek_thinking.py` - 若 `langchain-deepseek`/DeepAgents 默认没有保留 `reasoning_content` 回传，则新增 DeepSeek thinking 消息适配或 model wrapper。
- `backend/app/streaming/thinking_trace.py` - 若需要独立聚合 sub-turn reasoning 和 tool-call 关联元数据，可放置 run-local 聚合工具。

### 相关文档 实现前应该先阅读这些文档！

- [DeepSeek Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode)
  - 具体章节：`Input and Output Parameters`、`Tool Calls`、tool-call sample code。
  - 原因：官方说明 thinking 模式下 `reasoning_content` 与 `content` 同级返回；无 tool call 的多轮可以忽略历史 reasoning；一旦发生 tool call，后续请求必须完整回传 `reasoning_content`，否则会返回 400。
- [DeepSeek Tool Calls](https://api-docs.deepseek.com/guides/tool_calls)
  - 具体章节：tool call 消息结构。
  - 原因：确认 assistant `tool_calls` 与 tool result message 的 OpenAI-compatible 结构。
- LangChain / `langchain-deepseek` 当前安装版本源码或官方文档。
  - 具体章节：`ChatDeepSeek` message conversion、streaming chunk、tool calling。
  - 原因：本 repo 当前环境未能从 Windows 侧稳定读取 backend `.venv` 包源码，执行实现前必须在 WSL/后端环境里确认实际序列化入口。
- DeepAgents / LangGraph streaming 文档。
  - 具体章节：`create_deep_agent()`、`astream(..., stream_mode=["messages","updates","values"], subgraphs=True)`。
  - 原因：确认工具调用 sub-turn 中 assistant message 与 tool result 的流式事件顺序。

### 需要遵循的模式

**命名约定：**

- 后端 Python 使用 snake_case，Pydantic/API JSON 对外仍保持现有 schema；前端 TypeScript 使用 camelCase，字段转换集中在 `frontend/app/task-state.ts`。
- 事件类型沿用已有字符串：`assistant_thinking_delta`、`assistant_answer_delta`、`tool_call`、`tool_result`、`status_update`、`final_answer`。
- 新 helper 文件放在当前职责附近，例如 provider 适配放 `backend/app/models/`，stream 聚合放 `backend/app/streaming/`。

**错误处理：**

- API 层同一 task 运行中继续返回 409，不创建 run、不追加消息。
- thinking 回传缺失属于 provider adapter/streaming contract 的可测试错误；若 provider 仍返回 400，runner 应落 `task_failed` 与错误事件到当前 run，不影响其他 task。
- 自动标题、长期记忆等非关键增强必须 best-effort，不得阻断已创建 run 的调度。

**日志模式：**

- raw provider/tool 细节放 `EventRecord.payload` 与 raw JSONL 诊断；collapsed progress row 使用 `payload.live.display_text` 的简洁中文状态。
- `assistant_thinking_delta` 与 `assistant_answer_delta` 是过程 token，不是最终回答，不能渲染为普通 assistant reply card。
- 事件必须携带 `run_id`，前端按 `runId` 分组，缺失 `run_id` 只进入 legacy/fallback。

**安全边界：**

- `reasoning_content` 只进入当前 run 的诊断事件，不进入 `messages.content`、context summary、long-term memory、Qdrant payload、默认 artifact。
- `NEXT_PUBLIC_*` 不得新增 provider key、客户数据或私密样例。
- E2E 截图证据不提交 git。

---

## 实现计划

### 阶段 1：表征测试与文档校准

先用测试锁定当前行为，避免盲目重构。

**任务：**

- 阅读 DeepSeek thinking/tool-call 官方文档，记录实现所需的最小消息结构。
- 在 WSL 后端环境中确认 `langchain-deepseek` 和 DeepAgents 当前源码的消息序列化入口。
- 增加后端表征测试：不同 task 可并行，同 task 409；thinking tool-call 的后续请求必须包含 `reasoning_content`。
- 增加前端表征测试：当前 hook 中 `isBusy` 不应阻塞切换到其他非运行会话后发送。

### 阶段 2：后端并发与 Thinking 回传修复

在不引入全局队列的前提下补齐 provider/tool-call 消息保真。

**任务：**

- 保持 `TaskRunner._active_runs` 按 `task_id` 管理，必要时补测试而非重写。
- 若 DeepAgents/LangChain 没有自动保留 `reasoning_content`，实现 DeepSeek thinking 消息适配层，把同一 run 中带 tool call 的 assistant message 转成 provider 要求的 OpenAI-compatible dict。
- 确保 non-thinking 模型不接收 thinking 专属字段；thinking 模型也不伪造旧 run 缺失的 reasoning。
- 为 provider 400 缺失 reasoning 场景补回归测试，断言修复后不会构造缺字段请求。

### 阶段 3：Run 审计事件与安全边界

让新 run 的事件流完整可追溯，同时明确 reasoning 不进入普通上下文或长期记忆。

**任务：**

- 保持或扩展 `assistant_thinking_delta` payload，确保完整 `reasoning_content` 可从 raw run events/expanded diagnostics 读取。
- 确认 tool call、tool result、answer delta、status、error、final answer 都带正确 `run_id` 和顺序信息。
- 如果现有 `/tasks/{task_id}/events` 不能按 run 过滤，在不破坏现有客户端的前提下增加可选 `run_id` 查询参数；若前端已有 task 级读取再本地按 run 分组足够，则只补测试。
- 新增长期记忆负向测试：thinking/tool raw logs 即使存在于 events，也不会被 `remember_completed_run()` 或 context builder 消费。

### 阶段 4：前端跨会话并行与诊断展示

解除跨会话 UI 阻塞，保持同会话保护和简洁默认进度。

**任务：**

- 将 `useTaskWorkspace` 中的全局 `isBusy` 拆分或重命名为操作级 busy，例如 `isSubmittingCurrentTask`、`isSwitchingConversation`、`isMutatingConversation`，避免 A 会话发送请求期间永久阻塞选择/发送 B 会话。
- 发送按钮禁用条件以当前 task 的 `activeTask` 为准；会话 A 运行中切到 B，如果 B 非运行且当前没有 B 的提交操作，应允许发送。
- 保留同一会话运行中的 placeholder、stop 按钮、发送保护。
- 调整 thinking/answer diagnostics 的 8000 字符 normalized cap：默认 collapsed UI 不展示全文，但 expanded diagnostics 和 copy raw JSONL 必须保留完整内容。可以让 normalized diagnostic 使用完整内容，并只对 collapsed/summary 文本截断。
- 增加前端测试覆盖 run 分组隔离、完整 thinking diagnostics、跨会话 busy 作用域。

### 阶段 5：知识包、E2E 与回归验证

用实际服务完成闭环验收，并更新长期业务规则。

**任务：**

- 更新 `asset/deepagents_platform_knowledge_pack.md`，记录跨会话并行、同会话互斥、thinking `reasoning_content` 回传、run 诊断保存边界和前端展示规则。
- 新增或扩展 Playwright E2E，使用实际 `8001/3001` 服务和 Postgres-backed task/runs/messages/events contract。
- 按 AGENTS.md 要求保存截图到 `frontend/e2e-playwright/e2e-YYYYMMDDHHMMSS/`，不提交截图。
- 运行后端、前端、E2E 和 `git diff --check`。

---

## 分步任务

重要：严格按顺序执行所有任务，从上到下。每个任务都必须是原子性的，并且可独立测试。

### UPDATE 调研记录与表征测试清单

- **IMPLEMENT**: 在执行分支的工作记录或提交说明中记录 DeepSeek thinking 文档结论：tool call 后续请求必须包含完整 `reasoning_content`；无 tool call 的普通多轮不要求回传。
- **PATTERN**: `tasks/multi-session-thinking-audit/requirements.md` 已有外部依据；`asset/deepagents_platform_knowledge_pack.md:249-253` 已有 thinking delta 边界。
- **IMPORTS**: 无。
- **GOTCHA**: 不要把 DeepSeek 文档样例里的完整 CoT 内容复制进测试夹具；测试使用短 canary 字符串。
- **VALIDATE**: `git diff --check`

### CREATE backend/tests/unit/models/test_deepseek_thinking_messages.py

- **IMPLEMENT**: 新增 provider 层表征测试，构造 thinking assistant tool-call sub-turn，断言后续 provider request message 中包含 `role=assistant`、`content`、`reasoning_content`、`tool_calls`，且 tool result message 带 `tool_call_id`；再构造 non-thinking 模型，断言不会发送 `reasoning_content`。
- **PATTERN**: `backend/tests/unit/models/test_provider.py` 使用 monkeypatch 捕获 `ChatDeepSeek` 初始化参数；`backend/tests/unit/streaming/test_v2_adapter.py:99-121` 使用短 reasoning 字符串验证 thinking chunk。
- **IMPORTS**: `pytest`、`langchain_core.messages.AIMessage`/`ToolMessage`/`HumanMessage`、待实现的 provider helper。
- **GOTCHA**: 如果实际修复点在 model wrapper 而非纯函数，测试应捕获 wrapper 传给底层 DeepSeek/OpenAI client 的 messages，而不是只测自己构造的 dict。
- **VALIDATE**: `cd backend && uv run pytest tests/unit/models/test_deepseek_thinking_messages.py -q`

### CREATE backend/app/models/deepseek_thinking.py

- **IMPLEMENT**: 根据表征测试结果实现最小 DeepSeek thinking 消息适配。输入 LangChain message 或 provider message，输出 DeepSeek-compatible message；仅在当前 model registry 标记 thinking enabled 且 message 真有 tool call/reasoning 时保留 `reasoning_content`；non-thinking 路径剥离该字段。
- **PATTERN**: `backend/app/models/provider.py:32-55` 统一创建 chat model；`backend/app/conversation_context.py:137-149` 普通历史不含 reasoning。
- **IMPORTS**: `typing.Any`、`langchain_core.messages` 相关类型；如需要包裹 `BaseChatModel`，导入 `BaseChatModel` 并保持类型签名。
- **GOTCHA**: 不要将 `assistant_thinking_delta` events 反向注入跨 run 普通上下文；DeepSeek 要求的是 tool-call 发生时同一消息链中的 assistant message 保真，不是伪造旧历史 reasoning。
- **VALIDATE**: `cd backend && uv run pytest tests/unit/models/test_deepseek_thinking_messages.py -q`

### UPDATE backend/app/models/provider.py

- **IMPLEMENT**: 在 `create_model()` 中接入 thinking helper/wrapper。`thinking_mode` 为 enabled 时启用 DeepSeek thinking 兼容处理；disabled 时继续使用现有 `ChatDeepSeek` 行为并显式避免发送 reasoning 专属字段。
- **PATTERN**: `backend/app/models/provider.py:45-55` 读取 `MODEL_REGISTRY` 并设置 `extra_body`；`backend/tests/unit/models/test_provider.py` 捕获初始化参数。
- **IMPORTS**: 从 `app.models.deepseek_thinking` 导入 helper/wrapper。
- **GOTCHA**: DeepSeek 文档说明 thinking mode 不支持 temperature/top_p 等参数但兼容忽略；不要在本任务中扩大模型参数面。
- **VALIDATE**: `cd backend && uv run pytest tests/unit/models/test_provider.py tests/unit/models/test_deepseek_thinking_messages.py -q`

### UPDATE backend/app/streaming/v2_adapter.py

- **IMPLEMENT**: 保持现有 `thinking_chunk` 输出，同时确认 tool-call sub-turn 的 reasoning 能完整聚合。若需要，把 provider raw `reasoning_content` 与 tool-call id 的关联元数据加入 normalized event data，但不要改变 collapsed UI 文案。
- **PATTERN**: `backend/app/streaming/v2_adapter.py:172-205` 先处理 tool_call_chunks，再处理 reasoning，再处理 root answer text；`backend/app/streaming/v2_adapter.py:384-412` 窄口径抽取 reasoning 字段。
- **IMPORTS**: 尽量不新增依赖；如聚合需要，使用标准库 dataclass/typing。
- **GOTCHA**: sub-agent 的 answer text 仍不应作为 root answer delta；但 subgraph reasoning 是否作为诊断保存要保持当前 `is_subgraph` 标识。
- **VALIDATE**: `cd backend && uv run pytest tests/unit/streaming/test_v2_adapter.py -q`

### UPDATE backend/app/streaming/event_converter.py

- **IMPLEMENT**: 确保 `assistant_thinking_delta` payload 保存完整 content，并在 live metadata 中保留 display-safe `diagnostic_label=model.reasoning_content`；如新增 provider/tool linkage 字段，放 payload 顶层或 diagnostic 子对象，不放 collapsed display_text。
- **PATTERN**: `backend/app/streaming/event_converter.py:58-74` 是 thinking payload 当前结构；`backend/tests/unit/streaming/test_event_converter.py:184-211` 是断言模式。
- **IMPORTS**: 无或标准库。
- **GOTCHA**: `record.message` 当前等于 reasoning 文本，可能导致某些 legacy title 暴露 reasoning；如果修改为稳定文案，需同步所有测试和前端 fallback，确保 expanded JSON 仍完整。
- **VALIDATE**: `cd backend && uv run pytest tests/unit/streaming/test_event_converter.py -q`

### CREATE backend/tests/unit/runner/test_concurrency_and_thinking_audit.py

- **IMPLEMENT**: 增加 runner/storage 层测试：两个不同 task 可同时注册 active run；同 task 二次 start 或 API send 返回 409；每个 run append_event 后只读到自己的 `run_id`；provider failure 只把当前 task 标为 failed。
- **PATTERN**: `backend/tests/unit/runner/test_core.py` 使用 fake graph/monkeypatch 等待 background run；`backend/tests/unit/api/test_tasks.py` 捕获 `runner.start_background`；`backend/tests/fakes.py` 提供 InMemoryTaskStorage。
- **IMPORTS**: `pytest`、`asyncio`、现有 test fixtures。
- **GOTCHA**: 不要通过 sleep 做脆弱并发测试；用可控 `asyncio.Event` 或 monkeypatch 的 fake stream 挂起两个 task。
- **VALIDATE**: `cd backend && uv run pytest tests/unit/runner/test_concurrency_and_thinking_audit.py -q`

### UPDATE backend/app/storage.py and backend/tests/fakes.py

- **IMPLEMENT**: 如果需要按 run 查询事件，为 `read_events(task_id, after_id=None, run_id=None)` 增加可选过滤，并同步 API 查询参数；如果前端 task 级读取后本地分组已满足需求，则只补 tests 确认不同 `run_id` 事件不会互相污染。
- **PATTERN**: `backend/app/storage.py:976-1007` 当前按 task 和 seq 读取；`frontend/app/workspace-view.ts:1517-1523` 当前按 runId 过滤日志。
- **IMPORTS**: 无。
- **GOTCHA**: `seq` 是 task 内唯一且用于 SSE cursor；按 run 过滤不能破坏 after_id 的 task 级恢复语义。
- **VALIDATE**: `cd backend && uv run pytest tests/unit/storage/test_storage.py tests/unit/api/test_tasks.py -q`

### UPDATE backend/app/runner/core.py

- **IMPLEMENT**: 确认所有 streamed events、terminal events、error events、final_answer events 都使用同一个 `run_id`。如 thinking/tool-call adapter 需要 run-local trace state，在 `start()` 内创建并随 stream_agent/config 传递，不放全局变量。
- **PATTERN**: `backend/app/runner/core.py:227-236` event 落库携带 `record.run_id`；`backend/app/runner/core.py:254-284` terminal/final_answer 携带 `run_id`。
- **IMPORTS**: 视 adapter 设计导入 run-local helper。
- **GOTCHA**: `_active_runs` key 继续是 `task_id`，不要改成全局锁；`configurable.thread_id` 当前是 `task_id`，同 task 并行仍不允许。
- **VALIDATE**: `cd backend && uv run pytest tests/unit/runner/test_core.py tests/unit/runner/test_concurrency_and_thinking_audit.py -q`

### UPDATE backend/app/conversation_context.py

- **IMPLEMENT**: 增加或确认测试：context builder 只读取 `messages`，不会读取 events 里的 `assistant_thinking_delta`；同一会话后续切换 non-thinking 模型时不会把 reasoning 专属字段构造进普通历史。
- **PATTERN**: `backend/app/conversation_context.py:69-112` 构建上下文；`backend/app/conversation_context.py:137-149` 只生成 HumanMessage/AIMessage/SystemMessage。
- **IMPORTS**: 无。
- **GOTCHA**: 如果新增模型兼容处理，不要把它放到 conversation context；provider adapter 才知道当前模型是否 thinking。
- **VALIDATE**: `cd backend && uv run pytest tests/unit/runner/test_conversation_context.py -q`

### UPDATE backend/tests/unit/runner/test_memory.py

- **IMPLEMENT**: 新增负向测试，构造包含 `reasoning_content`、tool raw args/result 的 events，但调用 completed-run memory 写入时只传 `user_goal` 与 `final_answer`，断言 long-term memory/Qdrant payload 不包含 reasoning/tool raw canary。
- **PATTERN**: `backend/tests/unit/runner/test_memory.py:16-45` 测 high-level bounded memory；`backend/tests/unit/runner/test_memory.py:102-146` 测 canonical memory 与 Qdrant payload。
- **IMPORTS**: 复用现有 fake embedding/index/storage。
- **GOTCHA**: 测试 canary 字符串不要像真实密钥，避免被 secret scanner 测试误判。
- **VALIDATE**: `cd backend && uv run pytest tests/unit/runner/test_memory.py -q`

### UPDATE frontend/hooks/use-task-workspace.ts

- **IMPLEMENT**: 将全局 `isBusy` 拆成更细状态。`handleSubmit()` 只阻止当前 task active 或当前提交中；`handleSelectConversation()` 不应因为另一个会话刚提交/运行而长期阻塞；`handleNewConversation()` 和 `clear all` 继续按现有安全逻辑处理运行中任务。
- **PATTERN**: `frontend/hooks/use-task-workspace.ts:434-488` 发送流程；`frontend/hooks/use-task-workspace.ts:558-580` 会话切换；`frontend/hooks/use-task-workspace.ts:638-643` clear all 运行中保护。
- **IMPORTS**: React hooks 已有，无新增库。
- **GOTCHA**: 上传文件和发送消息是同一次当前 task 提交流程，不能让用户双击创建重复消息；但 A 的 running 状态不应阻塞 B。
- **VALIDATE**: `cd frontend && npm test -- tests/workspace/test_task_workspace.test.ts`

### UPDATE frontend/components/chat/ChatComposer.tsx

- **IMPLEMENT**: 根据 hook 暴露的新 busy 字段调整 disabled、placeholder、stop button。当前会话 active 时继续显示“回复生成中，请稍候...”和 stop；仅当前 submit busy 时显示发送中。
- **PATTERN**: `frontend/components/chat/ChatComposer.tsx:387` placeholder；`frontend/components/chat/ChatComposer.tsx:497-514` stop/send 按钮。
- **IMPORTS**: 无新增库。
- **GOTCHA**: 不要让 stop 按钮指向非当前会话；跨会话运行只在左侧/摘要体现，不应该让当前 B 的 composer 停止 A。
- **VALIDATE**: `cd frontend && npm test -- tests/workspace/test_task_workspace.test.ts tests/model/test_model_ui.test.ts`

### UPDATE frontend/app/task-state.ts

- **IMPLEMENT**: 调整 `normalizeAssistantThinkingStream()` 和相关 diagnostics，让 expanded/copy 路径保留完整 `payload.content`。如仍需 UI 性能保护，应只对 collapsed summary 或 preview 截断，并在 diagnostics metadata 中标注 preview/truncation，不改变 rawRecord。
- **PATTERN**: `frontend/app/task-state.ts:507-510` bounded content helper；`frontend/app/task-state.ts:981-1000` thinking stream normalization；`frontend/app/task-state.ts:1045-1049` rawRecord non-enumerable 保存。
- **IMPORTS**: 无。
- **GOTCHA**: 大 JSON 展开可能影响页面性能；默认 collapsed row 不渲染全文，expanded row 可按现有 `<pre>` 显示，但测试要覆盖长 reasoning 不丢失。
- **VALIDATE**: `cd frontend && npm test -- tests/state/test_task_state.test.ts`

### UPDATE frontend/app/workspace-view.ts

- **IMPLEMENT**: 确保 `buildThinkingStreamDiagnostics()` 聚合当前 run segment 的完整 content，`buildLogClipboardText()` 继续导出 raw JSONL；run grouping 只展示对应 run 的 logs，不混入其他 run。
- **PATTERN**: `frontend/app/workspace-view.ts:192-194` raw JSONL copy；`frontend/app/workspace-view.ts:624-645` thinking diagnostics；`frontend/app/workspace-view.ts:1482-1570` run activity groups。
- **IMPORTS**: 无。
- **GOTCHA**: thinking segment 在 tool_call 前后会分段，不能把 A run 的前段 thinking 合并到 B run，也不能把后续另一个 thinking row 合并进第一个 tool 前 row。
- **VALIDATE**: `cd frontend && npm test -- tests/workspace/test_workspace_view.test.ts`

### UPDATE frontend/components/chat/TaskConversation.tsx

- **IMPLEMENT**: 保持默认日志简洁，展开 `<details>` 时显示当前 row/current run 的 JSON；复制诊断以当前 run/group 为边界。必要时补充 aria-label 区分 run。
- **PATTERN**: `frontend/e2e-playwright/test_progress_log_disclosure.spec.mjs:450-480` 对 collapse/expand/copy 按钮的验收；`asset/deepagents_platform_knowledge_pack.md:241` 对 progress row 布局的规则。
- **IMPORTS**: 如需 icon，优先使用现有图标/按钮模式，不引入新 UI 库。
- **GOTCHA**: 前端视觉变更必须先对照 `DESIGN.md`，避免文字重叠、按钮撑开、默认暴露 reasoning。
- **VALIDATE**: `cd frontend && npm test -- tests/workspace/test_workspace_view.test.ts`

### UPDATE asset/deepagents_platform_knowledge_pack.md

- **IMPLEMENT**: 新增稳定规则：不同 task/session 可并行，同 task 保持互斥；thinking tool-call 后续 provider 请求必须回传 `reasoning_content`；reasoning 只作为 run diagnostics；expanded diagnostics 完整，collapsed UI 简洁；跨会话 busy 不阻塞非当前 task。
- **PATTERN**: `asset/deepagents_platform_knowledge_pack.md:236-271` 是 progress log 和 thinking delta 规则区域。
- **IMPORTS**: 无。
- **GOTCHA**: 知识包写稳定业务边界，不写一次性排障时间线、截图路径或临时命令输出。
- **VALIDATE**: `git diff --check`

### CREATE frontend/e2e-playwright/test_multi_session_thinking_audit.spec.mjs

- **IMPLEMENT**: 基于实际前后端服务创建/seed 两个 task：A 为 running/long task，B 可发起独立 run；验证 A 运行中切到 B 可发送；回到 A 发送被保护；为至少一个 run seed 或触发 thinking/tool events，展开日志看到完整 `reasoning_content`，复制诊断不混入另一个 run。
- **PATTERN**: `frontend/e2e-playwright/test_progress_log_disclosure.spec.mjs:1-45` env 与 SQL helper；`frontend/e2e-playwright/test_progress_log_disclosure.spec.mjs:640-680` expanded thinking row 与 clipboard 验收。
- **IMPORTS**: `@playwright/test`、`node:crypto`、`node:child_process`、`node:fs`、`node:path`。
- **GOTCHA**: E2E 必须连接实际 `MYAGENT_E2E_BASE_URL` 和 `MYAGENT_E2E_API_URL`；截图写入 `frontend/e2e-playwright/e2e-YYYYMMDDHHMMSS/`，不得提交。
- **VALIDATE**: `cd frontend && MYAGENT_E2E_BASE_URL=http://127.0.0.1:3001 MYAGENT_E2E_API_URL=http://127.0.0.1:8001 MYAGENT_E2E_EVIDENCE_DIR=./e2e-playwright/e2e-YYYYMMDDHHMMSS/multi-session-thinking-audit npx playwright test e2e-playwright/test_multi_session_thinking_audit.spec.mjs --reporter=line`

### UPDATE frontend/e2e-playwright/README.md

- **IMPLEMENT**: 记录新 E2E 的运行条件、环境变量、截图目录和覆盖场景；注明本仓库服务通过 WSL 启动脚本运行。
- **PATTERN**: `frontend/e2e-playwright/README.md:28-41` progress-log disclosure 文档；`frontend/e2e-playwright/README.md:58-71` session-context memory 文档。
- **IMPORTS**: 无。
- **GOTCHA**: 不要写入私密 token 示例；访问令牌只通过环境变量传入。
- **VALIDATE**: `git diff --check`

---

## 测试策略

### 单元测试

- Backend provider/model：验证 thinking enabled/disabled 的消息构造差异，尤其 assistant tool-call message 的 `reasoning_content` 保真。
- Backend streaming：验证 provider reasoning chunk 完整变成 `assistant_thinking_delta`，tool_call/tool_result 顺序不回退。
- Backend runner/storage：验证不同 task 并行，同 task 互斥，事件 run_id 隔离，provider failure 不污染其他 task。
- Backend memory/context：验证 reasoning/tool raw logs 不进入普通 conversation context、context summary、long-term memory、Qdrant payload。
- Frontend state/view：验证完整 thinking diagnostics、raw JSONL copy、run grouping、seq ordering、default collapsed labels。
- Frontend hook/composer：验证跨会话 busy 作用域，同会话运行中仍禁发。

### 集成测试

- API 集成：`POST /tasks` 和 `POST /tasks/{task_id}/messages` 对不同 task 可同时创建 running run，同 task running 时 409。
- Storage 集成：Postgres 表中 task/runs/messages/events 的 `active_run_id`、`run_id`、`seq` 一致；按 task 或 run 读取事件顺序稳定。
- Agent 集成：使用 fake model/fake stream 模拟 thinking tool-call sub-turn，断言后续 provider 请求携带 reasoning 且最终事件链完整。

### 浏览器 E2E

- 实际后端 `8001` 和前端 `3001` 服务。
- 场景覆盖：A 运行中切 B 发送、A 同会话禁发、thinking/tool expanded diagnostics、raw JSON copy、截图证据。
- 保留现有 progress-log disclosure E2E，必要时扩展而非删除。

### 边界情况

- A task 失败，B task 仍运行或完成。
- 同一 task 快速双击发送，只创建一个 run。
- thinking run 切换到 non-thinking 后续 turn，不发送 `reasoning_content`。
- non-thinking 历史切回 thinking，不伪造旧 reasoning。
- 旧 run 缺少 reasoning 时，诊断显示历史不可用或缺字段，不补造数据。
- 超长 `reasoning_content` 展开/复制完整，collapsed UI 不渲染全文、不撑破布局。
- after_id cursor 不存在时仍按现有规则返回完整 task 事件流。

---

## 验证命令

执行所有命令，确保零回归与功能正确。由于当前项目启动脚本在 WSL 中运行，浏览器验收前优先复用用户已有的 `8001/3001` 服务；如需要启动服务，从 Windows PowerShell 运行 WSL 启动脚本，并优先使用 `-NoStop` 避免停止用户已有服务：

```powershell
cd D:\AgentProject\MyAgent
.\scripts\start-dev-wsl.ps1 -NoStop
```

如果必须在 WSL 内手动启动，进入 `/mnt/d/AgentProject/MyAgent` 后使用 `scripts/dev-terminal-runner.sh backend` 和 `scripts/dev-terminal-runner.sh frontend` 对应入口，保持默认 `8001/3001`。

### 级别 1：语法与风格

```bash
cd backend && uv run ruff check .
cd frontend && npm run lint
git diff --check
```

### 级别 2：单元测试

```bash
cd backend && uv run pytest tests/unit/models/test_provider.py tests/unit/models/test_deepseek_thinking_messages.py -q
cd backend && uv run pytest tests/unit/streaming/test_v2_adapter.py tests/unit/streaming/test_event_converter.py -q
cd backend && uv run pytest tests/unit/runner/test_core.py tests/unit/runner/test_concurrency_and_thinking_audit.py tests/unit/runner/test_conversation_context.py tests/unit/runner/test_memory.py -q
cd backend && uv run pytest tests/unit/storage/test_storage.py tests/unit/api/test_tasks.py -q
cd frontend && npm test -- tests/state/test_task_state.test.ts tests/workspace/test_workspace_view.test.ts tests/workspace/test_task_workspace.test.ts
```

### 级别 3：类型检查与构建

```bash
cd backend && uv run mypy app tests
cd frontend && npm run typecheck
cd frontend && npm run build
```

### 级别 4：完整回归

```bash
cd backend && uv run pytest
cd frontend && npm test
cd frontend && npm run lint
cd frontend && npm run build
```

### 级别 5：浏览器 E2E 与截图证据

```bash
cd frontend
MYAGENT_E2E_BASE_URL=http://127.0.0.1:3001 \
MYAGENT_E2E_API_URL=http://127.0.0.1:8001 \
MYAGENT_E2E_EVIDENCE_DIR=./e2e-playwright/e2e-YYYYMMDDHHMMSS/multi-session-thinking-audit \
npx playwright test e2e-playwright/test_multi_session_thinking_audit.spec.mjs --reporter=line
```

同时保留或运行现有日志披露回归：

```bash
cd frontend
MYAGENT_E2E_BASE_URL=http://127.0.0.1:3001 \
MYAGENT_E2E_API_URL=http://127.0.0.1:8001 \
MYAGENT_E2E_EVIDENCE_DIR=./e2e-playwright/e2e-YYYYMMDDHHMMSS/progress-log-disclosure \
npx playwright test e2e-playwright/test_progress_log_disclosure.spec.mjs --reporter=line
```

---

## 验收标准

- [ ] 不同会话 A/B 可以同时启动 run，并独立完成或独立失败。
- [ ] 同一会话已有 running run 时，再次发送返回前端保护或后端 409，且不创建新 run、不追加待执行消息。
- [ ] thinking 模型发生 tool call 后，后续 provider 请求包含 DeepSeek 要求的 `reasoning_content`，不再出现缺失 reasoning 的 400。
- [ ] `reasoning_content` 按 run 完整保存为诊断事件，展开和复制诊断时完整可见。
- [ ] `reasoning_content` 不进入普通 assistant/user messages、conversation context、context summary、long-term memory、Qdrant payload 或默认 artifact。
- [ ] 前端默认进度只显示简洁状态，展开后显示当前 run 的 provider/tool/reasoning 细节。
- [ ] 同一会话后续切换 thinking/non-thinking 模型时，上下文回放按当前模型兼容处理，不向 non-thinking 发送 thinking 专属字段。
- [ ] 旧 run 不补数据、不伪造历史 reasoning。
- [ ] 后端 pytest、ruff、mypy 通过。
- [ ] 前端 typecheck、test、lint、build 通过。
- [ ] Playwright E2E 基于实际 WSL 启动的前后端服务通过，截图证据保存到 `frontend/e2e-playwright/e2e-YYYYMMDDHHMMSS/` 且不提交。
- [ ] `asset/deepagents_platform_knowledge_pack.md` 已同步稳定运行边界。

---

## 完成检查清单

- [ ] 已重新阅读 DeepSeek Thinking Mode 与 Tool Calls 文档。
- [ ] 已在 WSL 后端环境确认 LangChain/DeepAgents 实际消息序列化入口。
- [ ] 所有表征测试先失败或明确覆盖当前缺口。
- [ ] 后端 thinking tool-call 回传修复完成。
- [ ] 后端跨 task 并行、同 task 互斥和 run 事件隔离测试完成。
- [ ] 前端跨会话 busy 作用域修复完成。
- [ ] 前端默认简洁进度和 expanded 完整诊断测试完成。
- [ ] 长期记忆与普通上下文安全边界测试完成。
- [ ] 知识包更新完成。
- [ ] 所有验证命令成功执行。
- [ ] 浏览器 E2E 和截图验收完成。
- [ ] 无 lint、类型检查或 `git diff --check` 问题。

---

## 备注

- 计划置信分数：8/10。主要不确定性在 `langchain-deepseek` 与 DeepAgents 对 assistant message 中非标准 `reasoning_content` 字段的保真程度；必须先用 WSL 环境和表征测试定位真实注入点。
- 后端并发基础看起来已经按 task 隔离，最大风险不是后端全局锁，而是前端 `isBusy` 作用域和 provider thinking tool-call 消息回传。
- 不建议引入全局任务队列、全局并发上限或 worker 多进程改造；这些都超出 PRD 范围，并可能破坏本地优先单进程边界。
- 若实现中发现 `record.message` 暴露 reasoning 会影响默认 UI 或普通日志标题，应改为稳定文案并把 reasoning 仅放 payload diagnostics，同时同步前端与测试。
