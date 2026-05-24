# 功能: 缺上传澄清与文件交付警告修复

下面这份计划应尽可能完整，但在真正开始实现前，仍然必须再次验证文档、代码库模式以及任务本身是否合理。

特别注意现有 utils、types、models 的命名，并确保从正确的文件中导入。

## 功能描述

把“缺上传/缺输入”从用户可见技术警告改成普通 AI 澄清；把“文件交付保护”保留为后台兜底，但让前端只展示自然失败说明和重新生成入口；同时确保文件-only 上传能继续上一轮需求，`needs_input` 不阻止删除或清空会话。

## 用户故事

作为一名用 MyAgent 总结上传文件并生成 Word/PPT/Excel/报告的用户，我想在忘记上传文件时收到自然澄清，在上传后不用重复输入需求，并且只在真实无交付文件时看到可理解的失败说明，以便工作流清楚、结果可靠、历史会话可管理。

## 问题陈述

现有后台交付保护能防止虚假成功，但它把缺交付物以 `needs_input` 和 warning 形态暴露给前端。`formatNeedsInput()` 会把 payload 中除 `message` 外的字段拼成可见文案，因此 `reason`、`repair_hint`、`missing_artifact_names` 等内部字段可能进入用户界面。`buildStateNoticeMessages()` 又把 needs-input notice 标记为 warning，最终被 `formatMessagePanelStatus()` 渲染成“配置提醒”。此外，当前交付校验会同时检查请求类型和 final answer 中声称的具体文件名，导致页面已有满足请求的 `.docx` 下载卡片时仍可能因文件名不一致误报。

缺上传场景还缺少产品化澄清：用户说“总结内容并生成 Word”但没有内容时，应由 AI 普通追问，而不是进入交付失败警告。文件-only 发送当前虽然可以通过 `canSend` 触发，但默认消息是通用“请分析已上传文件...”，没有明确连接上一轮“总结并生成 Word”的待处理意图，且用户消息展示只能显示文本。

## 方案陈述

后端增加一个面向缺输入的轻量判定和提示策略：当本轮请求需要总结/生成交付文件，但没有用户正文、上传资源或可复用上下文时，run 以普通 assistant 澄清完成，不写用户可见 `needs_input`。文件-only 发送时，前端生成或传递“继续上一轮需求”的明确 follow-up，并让消息展示为文件卡片或紧凑文件列表。

交付保护继续位于 runner 完成前，但判断口径改为：如果用户请求的是 Word/PPT/Excel/报告，只要当前 run 有满足类型的可下载 artifact，就算交付成功；final answer 中的文件名只作为辅助，不再压过真实 artifact。若确实没有任何满足请求的 artifact，后端写入短用户消息和可重试动作，内部字段不进入用户可见 API/state notice。前端过滤或降级旧 payload，避免技术字段显示，并把相关状态渲染为普通失败/重试说明而不是“配置提醒”。

清空会话沿用 `isTaskActive(status) === status === "running"` 口径，同时补齐后端/前端/E2E 回归，确保 `needs_input` 可删除可清空，runner active 才阻止。

## 功能元数据

**功能类型**: 缺陷修复 + 用户体验增强  
**预估复杂度**: 高  
**主要受影响系统**: 后端 runner、任务 API、storage payload、上传资源上下文、前端 task-state、workspace-view、useTaskWorkspace、TaskConversation、ChatSidebar、Playwright E2E、平台知识包  
**依赖项**: FastAPI task API、PostgresTaskStorage、DeepAgents resource tools、Next.js 前端、Playwright

---

## 上下文参考

### 相关代码文件 重要：实现前你必须先阅读这些文件！

- `AGENTS.md` - 仓库执行边界：行为变更必须同步代码、测试、真实浏览器 E2E、截图证据和知识包。
- `ARCHITECTURE.md` - 后端是任务/run/message/event/upload/artifact 权威来源；前端只渲染 HTTP/SSE 投影。
- `INTERFACES.md` - 前后端任务 API、上传、artifact、字段转换和状态边界。
- `asset/deepagents_platform_knowledge_pack.md:41` - 上传资源和 `create_word_document` 的平台规则。
- `asset/deepagents_platform_knowledge_pack.md:159` - 存储、上传和产物的长期规则，目前记录缺失交付文件会给出修正提示，需要按新口径更新。
- `backend/app/api/tasks.py:142` - 删除会话时后端只阻止 `state.status == "running"` 或 `runner.is_running(task_id)`。
- `backend/app/api/tasks.py:170` - `send_message()` 允许从 `needs_input`、`failed`、`cancelled`、`interrupted` 等状态继续发送消息。
- `backend/app/api/files.py:21` - 上传接口在 runner active 时拒绝上传，非 running 状态允许上传。
- `backend/app/schemas.py:22` - `MessageRequest.message` 当前 `min_length=1`，文件-only follow-up 不能直接发送空 message。
- `backend/app/schemas.py:39` - `ChatMessage` 当前只有 role/content/run_id/level，没有附件字段。
- `backend/app/storage.py:600` - `start_run()` 将用户 message 写入 run 和 messages，并清空 task-level `needs_input`。
- `backend/app/storage.py:742` - `save_uploads()` 保存上传并追加 `file_uploaded` event。
- `backend/app/storage.py:788` - `file_uploaded` payload 包含 filename、bytes、resource_ref，可用于文件消息展示。
- `backend/app/storage.py:1728` - `_apply_task_update()` 更新 task/run status、needs_input、artifact_names 和 append_message。
- `backend/app/conversation_context.py:69` - 同会话上下文会排除当前消息并回放最近消息，文件-only follow-up 依赖这里保留上一轮意图。
- `backend/app/execution/resources.py:27` - 资源工具系统提示说明上传文件不是自动上下文、生成 Word 必须使用 `create_word_document`。
- `backend/app/runner/core.py:294` - runner 提取 final answer 后立即执行 `_ensure_run_deliverables()`。
- `backend/app/runner/core.py:302` - 当前交付缺失会把 task 置为 `needs_input` 并写 warning event。
- `backend/app/runner/core.py:524` - `_ensure_run_deliverables()` 计算请求交付类型和 final answer 声称文件名。
- `backend/app/runner/core.py:555` - 当前同时检查缺失类型和缺失文件名，是误报来源之一。
- `backend/app/runner/core.py:571` - 当前 payload 包含 `reason`、`missing_artifact_names`、`repair_hint` 等内部字段。
- `backend/app/runner/core.py:653` - terminal live metadata 会把 `reason` 放入 parameter_items；用户可见诊断需要避免暴露。
- `frontend/hooks/use-task-workspace.ts:205` - `canSend` 已允许输入为空但选择了文件。
- `frontend/hooks/use-task-workspace.ts:494` - `handleSubmit()` 上传文件后再调用 `postTaskMessage()`。
- `frontend/hooks/use-task-workspace.ts:507` - 文件-only 发送当前使用通用 `DEFAULT_FILE_PROMPT`。
- `frontend/hooks/use-task-workspace.ts:765` - 清空会话会检查 `activeTask` 和 `taskSummaries.some(isTaskActive)`。
- `frontend/app/task-state.ts:641` - `formatNeedsInputKey()` 只本地化少量字段，其余字段名会原样显示。
- `frontend/app/task-state.ts:657` - `formatNeedsInput()` 会把除 `message` 外的所有 payload 字段拼成用户文案。
- `frontend/app/task-state.ts:674` - `readOptionalNeedsInput()` 当前直接保留后端 payload。
- `frontend/app/task-state.ts:1003` - `normalizeMessage()` 只输出文本消息，没有附件投影。
- `frontend/app/task-state.ts:1349` - `isTaskActive()` 当前只把 `running` 视为 active，这是正确口径，需要测试锁定。
- `frontend/app/workspace-view.ts:105` - `buildStateNoticeMessages()` 将 needs-input notice 生成为 assistant message。
- `frontend/app/workspace-view.ts:122` - needs-input notice 当前 level 是 warning。
- `frontend/app/workspace-view.ts:1662` - `formatMessagePanelStatus()` 对 warning tone 返回“配置提醒”。
- `frontend/app/workspace-view.ts:1690` - `formatRunLogStatus()` 对 `needs_input` 返回“等待补充输入”，本需求需要避免缺上传澄清进入该日志终态。
- `frontend/app/workspace-view.ts:1838` - artifact summary 已能把有产物的 assistant reply 压缩为“已生成 N 个交付文件”。
- `frontend/app/workspace-view.ts:1878` - `buildRunActivityGroups()` 按 run 关联 logs 和 artifacts。
- `frontend/components/chat/ChatComposer.tsx:309` - composer 已有选中文件 chip，可复用视觉模式到已发送文件消息。
- `frontend/components/chat/TaskConversation.tsx:184` - 用户消息当前只渲染 `<p>{message.content}</p>`。
- `frontend/components/chat/TaskConversation.tsx:266` - assistant reply 的 artifact footer 已有下载入口。
- `frontend/components/chat/TaskConversation.tsx:312` - 无 assistant reply 时已有独立 artifact 下载卡。
- `frontend/components/chat/ChatSidebar.tsx:188` - 清空所有会话按钮只基于 history busy 和空历史禁用。
- `backend/tests/unit/runner/test_core.py:383` - 当前测试锁定缺交付文件进入 `needs_input` 且 payload 有 `reason`，需要按新口径更新。
- `backend/tests/unit/runner/test_core.py:468` - 已有测试覆盖 markdown linked claimed artifact 被接受。
- `backend/tests/unit/api/test_tasks.py:790` - 已有测试覆盖 `needs_input` 状态允许继续发送消息。
- `frontend/tests/state/test_task_state.test.ts:1223` - 当前测试锁定 `formatNeedsInput()` 拼接 payload 字段，需要调整为隐藏内部字段。
- `frontend/tests/workspace/test_workspace_view.test.ts:2575` - 当前测试锁定 warning message 显示“配置提醒”，需要为交付失败/缺输入新类型补覆盖。
- `frontend/e2e-playwright/test_task_log_artifact_delivery.spec.mjs:476` - 已有 `.docx` artifact 下载卡 E2E，可扩展或新增邻近 spec。
- `frontend/e2e-playwright/test_task_log_artifact_delivery.spec.mjs:555` - 已有 missing artifact warning E2E，需要改成友好失败且隐藏内部字段。

### 需要创建的新文件

- `frontend/e2e-playwright/test_missing_upload_clarification_delivery_warning.spec.mjs` - 覆盖缺上传澄清、文件-only follow-up、交付成功、交付失败和清空会话。

### 需要修改的现有文件

- `backend/app/runner/core.py` - 缺输入澄清策略、交付成功/失败判断、用户可见 payload 收敛。
- `backend/app/api/tasks.py` - 如文件-only follow-up 或 retry 入口需要后端兜底，保持 route 薄层并补状态测试。
- `backend/app/schemas.py` - 如选择引入 message attachments 或 upload follow-up 元数据，做 backward-compatible optional 字段。
- `backend/app/storage.py` - 如引入 message attachment 存储或 public needs-input payload，需要同步 DB schema 和 state projection。
- `backend/tests/fakes.py` - 同步 fake storage 的 message/needs_input/artifact 合同。
- `frontend/hooks/use-task-workspace.ts` - 文件-only follow-up 文案、pending intent、清空会话回归、友好重试入口。
- `frontend/app/task-state.ts` - needs_input payload 过滤、内部字段隐藏、可选 message attachments 标准化。
- `frontend/app/workspace-view.ts` - 缺输入/交付失败消息 tone、状态标签、artifact success 投影。
- `frontend/components/chat/TaskConversation.tsx` - 用户文件消息渲染、失败重试入口、避免普通澄清显示为 warning。
- `frontend/components/chat/TaskWorkspace.tsx` - 传递新增 handler 或 message attachment props。
- `frontend/components/chat/ChatSidebar.tsx` - 如需要清空按钮状态/提示微调，保持视觉不跳动。
- `frontend/app/globals.css` - 文件消息 chip、友好失败入口的样式，沿用现有 CSS 变量。
- `asset/deepagents_platform_knowledge_pack.md` - 同步平台长期规则。

### 相关文档 实现前你应该先阅读这些文档！

- `frontend/e2e-playwright/README.md`
  - 具体章节：真实服务、证据目录、访问 token 环境变量。
  - 原因：本任务必须用真实 `3001/8001` 运行浏览器 E2E。
- `backend/.planning/codebase/ARCHITECTURE.md`
  - 具体章节：任务运行路径、上传与资源工具路径、产物下载路径。
  - 原因：缺输入、上传和产物交付都跨 runner/storage/API。
- `frontend/.planning/codebase/ARCHITECTURE.md`
  - 具体章节：TaskWorkspace、useTaskWorkspace、task-state、workspace-view、TaskConversation。
  - 原因：前端实现必须保持组件、hook、纯展示模型分层。
- `frontend/.planning/codebase/TESTING.md`
  - 具体章节：上传、progress/log、history、artifact 场景选择。
  - 原因：选择正确单测和 Playwright 邻近回归。

### 需要遵循的模式

**状态口径：**
- `running` 才是运行中。`isTaskActive(status)` 当前只返回 `status === "running"`，这是本需求要锁定的正确模式。
- 后端删除 API 还必须结合 `runner.is_running(task_id)`，防止状态尚未刷新时误删 active run。

**用户可见 payload：**
- 用户可见 `needs_input` 或失败说明只保留短 message 和 action label。
- `reason`、`repair_hint`、`missing_artifact_names`、`promoted_artifacts` 等内部字段不能被 `formatNeedsInput()` 拼进 message。
- 如果需要保留诊断，放在后端日志或 non-default raw diagnostics 中，不能出现在普通 notice 文案。

**交付保护：**
- `run.artifact_names` 是本轮可下载交付物的权威来源。
- final answer 中的文件名只作为辅助线索；当本轮已有满足请求类型的 artifact 时，不能因为名称不一致判失败。
- artifact 下载仍走 `buildArtifactRequest()` 和 `fetchArtifactBlob()`，不信任模型输出的路径。

**文件-only follow-up：**
- `MessageRequest.message` 现在要求非空；文件-only 发送需要前端生成明确 follow-up，或后端以 backward-compatible optional 字段支持附件消息。
- 不要把上传文件正文放进普通消息、长期记忆、知识包或截图证据。
- 后端资源 manifest 只放 filename、resource_id、format、size、digest，不放正文。

**测试：**
- 纯格式化和状态转换用 Node unit tests。
- runner 和 API 状态用 backend unit tests。
- 用户路径必须使用真实 `3001/8001` Playwright E2E，并保存截图证据。

---

## 实现计划

### 阶段 1：后端缺输入澄清和待处理意图

**任务：**

- 增加缺输入判定：用户请求总结、分析、生成 Word/PPT/Excel/报告，但当前没有上传资源、没有实质用户正文、没有可复用上下文时，返回普通 assistant 澄清。
- 明确澄清不是 `needs_input` 终态，不写 warning event，不显示技术提示。
- 文件-only follow-up 需要让上下文包含上一轮待处理意图，例如“继续上一轮总结并生成 Word 的需求”。

### 阶段 2：文件-only 消息和前端展示

**任务：**

- 调整 `useTaskWorkspace.handleSubmit()`，文件-only 时发送明确 follow-up 文案或附件元数据。
- 让用户消息可显示上传文件，不强迫显示冗长默认 prompt。
- 复用 composer 的 file chip 视觉，保持移动端不溢出。

### 阶段 3：交付保护成功判断修正

**任务：**

- 修改 `_ensure_run_deliverables()`：先检查本轮 run artifact suffix 是否满足请求类型。
- 如果请求类型已被 artifact 满足，不因 final answer 声称的具体文件名不一致而失败。
- 如果没有请求类型但 final answer 声称文件名，仍需要保证该文件或同类型交付 artifact 可下载，避免虚假成功。

### 阶段 4：交付失败用户可见收敛

**任务：**

- 后端交付失败 payload 只向 API 暴露短用户消息和 action label。
- 前端过滤旧 payload 和内部字段，避免历史任务继续显示技术 JSON。
- 交付失败显示为普通失败/重试说明，不再是“配置提醒”。

### 阶段 5：清空会话状态口径回归

**任务：**

- 锁定后端删除只阻止 `running` 或 runner active。
- 锁定前端清空只阻止 `isTaskActive(summary.status)`，即 `running`。
- 补 E2E：`needs_input` 可清空，running 阻止清空。

### 阶段 6：测试、E2E、知识包

**任务：**

- 更新后端 runner/API/storage fake 单测。
- 更新前端 state/workspace/hook/component 单测。
- 新增或扩展 Playwright E2E，截图证据放入 timestamped evidence 目录。
- 更新 `asset/deepagents_platform_knowledge_pack.md`。
- 跑完整质量门。

---

## 分步任务

重要：严格按顺序执行所有任务，从上到下。每个任务都必须是原子性的，并且可独立测试。

### UPDATE `backend/app/runner/core.py`

- **IMPLEMENT**: 在 run 完成前增加缺输入澄清判断。建议新增小函数，例如 `_should_clarify_missing_source_input(user_message, task_id, storage)`，判断是否请求总结/生成交付文件但当前缺上传和可总结正文。
- **IMPLEMENT**: 缺输入时 append 普通 assistant `ChatMessage`，task/run 进入 `complete` 或等价非运行终态，不写 `needs_input` warning。
- **IMPLEMENT**: 修改 `_ensure_run_deliverables()`，先用 run `artifact_names` 的 suffix 判断请求类型是否已满足；满足时忽略 final answer 推断文件名不一致。
- **IMPLEMENT**: 交付失败 payload 至少提供 `message` 和 `action_label`；内部字段不进入用户可见 API payload。
- **PATTERN**: `backend/app/runner/core.py:325` 已有 complete + append assistant message 模式。
- **PATTERN**: `backend/app/runner/core.py:524` 已集中交付检查，优先在这里收敛逻辑。
- **GOTCHA**: 不要绕过 storage 直接访问任意本地路径；artifact 仍以 run `artifact_names` 为准。
- **VALIDATE**: `cd backend && uv run pytest tests/unit/runner/test_core.py -q`

### UPDATE `backend/app/storage.py`

- **IMPLEMENT**: 如果选择支持 message attachments，给 messages 表增加 backward-compatible JSONB metadata/attachments 字段，并在 `_message_from_row()` 和 `_insert_message()` 中兼容旧行。
- **IMPLEMENT**: 如果不改 schema，则确保文件-only follow-up 文案能被 summary/context 安全回放，并且不写上传正文。
- **PATTERN**: `backend/app/storage.py:1813` 是 message insert 入口，任何 message 字段变更都要从这里统一写入。
- **GOTCHA**: 不要把上传正文放进 messages；只允许文件名、size、resource ref 等安全摘要。
- **VALIDATE**: `cd backend && uv run pytest tests/unit/storage/test_storage.py -q`

### UPDATE `backend/app/api/tasks.py`

- **IMPLEMENT**: 保持 `send_message()` 从 `needs_input` 可继续运行的 expected statuses。
- **IMPLEMENT**: 如果新增文件-only metadata，扩展 request handling 时保持旧 `message` payload 可用，不新增外部 endpoint。
- **IMPLEMENT**: 删除 API 继续只阻止 `state.status == "running"` 或 `runner.is_running(task_id)`。
- **PATTERN**: `backend/app/api/tasks.py:147` 是删除状态保护。
- **PATTERN**: `backend/app/api/tasks.py:188` 已允许 `needs_input` 继续发送消息。
- **VALIDATE**: `cd backend && uv run pytest tests/unit/api/test_tasks.py -q`

### UPDATE `backend/tests/fakes.py`

- **IMPLEMENT**: 同步 fake storage 的 message metadata、needs_input public payload 或 artifact 成功判断。
- **PATTERN**: `backend/tests/fakes.py` 已模拟 run `needs_input` 和 `artifact_names`。
- **GOTCHA**: fake 行为必须和 Postgres storage 一致，否则 runner/API 单测会误判。
- **VALIDATE**: `cd backend && uv run pytest tests/unit/runner/test_core.py tests/unit/api/test_tasks.py -q`

### UPDATE `frontend/hooks/use-task-workspace.ts`

- **IMPLEMENT**: 替换文件-only 的 `DEFAULT_FILE_PROMPT` 为更明确 follow-up，例如“我已上传文件，请继续上一轮需求。本轮文件：...”。如果已有上一轮待处理意图，则显式引用“继续上一轮需求”。
- **IMPLEMENT**: 保留发送成功后才清空 input、selected skills、selected files 的现有模式。
- **IMPLEMENT**: 清空会话逻辑保持只阻止 `isTaskActive(status)`，并补测试覆盖 `needs_input` 不阻止。
- **PATTERN**: `frontend/hooks/use-task-workspace.ts:494` 是 submit 主流程。
- **PATTERN**: `frontend/hooks/use-task-workspace.ts:765` 是清空历史主流程。
- **GOTCHA**: 上传成功但 post message 失败时要 refresh task，避免文件已上传但 UI 丢状态。
- **VALIDATE**: `cd frontend && npm test -- tests/workspace/test_task_workspace.test.ts`

### UPDATE `frontend/app/task-state.ts`

- **IMPLEMENT**: 调整 `formatNeedsInput()` 或新增 public formatter，过滤 `reason`、`repair_hint`、`missing_artifact_names`、`missing_deliverables`、`requested_deliverable_types`、`promoted_artifacts` 等内部字段。
- **IMPLEMENT**: 对旧 payload 只显示 `message` 和安全 action label。
- **IMPLEMENT**: 如支持 message attachments，扩展 `ChatMessage` 类型和 `normalizeMessage()`，保持旧消息兼容。
- **PATTERN**: `frontend/app/task-state.ts:657` 是 needs-input 文案拼接位置。
- **PATTERN**: `frontend/app/task-state.ts:1003` 是 message 标准化入口。
- **GOTCHA**: `rawRecord` 仍应 non-enumerable，不要把内部 raw payload 默认 JSON.stringify 到 UI。
- **VALIDATE**: `cd frontend && npm test -- tests/state/test_task_state.test.ts`

### UPDATE `frontend/app/workspace-view.ts`

- **IMPLEMENT**: `buildStateNoticeMessages()` 对缺输入/交付失败不要默认 warning tone；必要时新增区分普通澄清、失败说明和配置 warning 的 tone helper。
- **IMPLEMENT**: `formatMessagePanelStatus()` 不应把交付失败/缺输入普通提示显示为“配置提醒”。
- **IMPLEMENT**: 对 `needs_input` run log 的用户文案谨慎收敛，避免缺上传澄清显示“等待补充输入”。
- **IMPLEMENT**: 确保有 artifact 的 assistant reply 继续压缩为摘要 + 下载卡片。
- **PATTERN**: `frontend/app/workspace-view.ts:122` 是 needs-input notice level。
- **PATTERN**: `frontend/app/workspace-view.ts:1662` 是 message panel status。
- **PATTERN**: `frontend/app/workspace-view.ts:1838` 是 artifact delivery note。
- **VALIDATE**: `cd frontend && npm test -- tests/workspace/test_workspace_view.test.ts`

### UPDATE `frontend/components/chat/TaskConversation.tsx`

- **IMPLEMENT**: 用户消息支持 file-only 显示。若 `message.content` 是内部 follow-up prompt，可渲染文件 chip 或“已上传文件”卡片，避免把 prompt 当用户原话展示。
- **IMPLEMENT**: 交付失败说明提供“重新生成”或等价入口，调用现有 submit/retry handler 或清晰引导用户重新发送。
- **IMPLEMENT**: assistant 普通澄清保持 default tone，不能使用 warning card。
- **PATTERN**: `frontend/components/chat/TaskConversation.tsx:184` 是 user message render 入口。
- **PATTERN**: `frontend/components/chat/TaskConversation.tsx:266` 是 assistant artifact footer。
- **GOTCHA**: 文本和文件名必须在窄屏内换行，不要撑破消息卡。
- **VALIDATE**: `cd frontend && npm test -- tests/workspace/test_task_workspace.test.ts tests/workspace/test_workspace_view.test.ts`

### UPDATE `frontend/components/chat/TaskWorkspace.tsx`

- **IMPLEMENT**: 如果 TaskConversation 需要 retry handler、file message metadata 或 uploaded file display props，从 workspace boundary 显式传入。
- **PATTERN**: 当前 TaskWorkspace 只负责组合 hook state 和子组件 props，保持这个分层。
- **VALIDATE**: `cd frontend && npm test -- tests/workspace/test_task_workspace.test.ts`

### UPDATE `frontend/app/globals.css`

- **IMPLEMENT**: 为已发送文件消息、友好失败入口添加样式，复用 `.fileChip`、`.downloadPrimaryButton`、`.downloadSecondaryButton` 等现有视觉语言。
- **GOTCHA**: 不要引入新的大面积渐变或卡片嵌套；保持现有工作区密度。
- **VALIDATE**: `cd frontend && npm run lint`

### ADD `frontend/e2e-playwright/test_missing_upload_clarification_delivery_warning.spec.mjs`

- **IMPLEMENT**: 使用真实 `3001`/`8001`，并通过 API/Postgres seed 必要状态。
- **IMPLEMENT**: 场景 1：无上传“总结内容并生成 Word”显示普通澄清，无“配置提醒”、无内部字段。
- **IMPLEMENT**: 场景 2：澄清后仅上传文件发送，用户消息显示文件，后续 run 继续上一轮需求。
- **IMPLEMENT**: 场景 3：本轮有 `.docx` artifact，显示下载卡片，无缺文件警告。
- **IMPLEMENT**: 场景 4：缺失 artifact，显示友好失败说明和重新生成入口，隐藏内部字段。
- **IMPLEMENT**: 场景 5：`needs_input` 会话可清空，running 会话阻止清空。
- **PATTERN**: 参考 `frontend/e2e-playwright/test_task_log_artifact_delivery.spec.mjs:476` 的 docx artifact 下载卡 seed 和截图保存。
- **GOTCHA**: 截图证据目录必须是 `frontend/e2e-playwright/e2e-YYYYMMDDHHMMSS/missing-upload-clarification-delivery-warning-fix/`，不要提交。
- **VALIDATE**: `cd frontend && npx playwright test e2e-playwright/test_missing_upload_clarification_delivery_warning.spec.mjs --reporter=line`

### UPDATE `asset/deepagents_platform_knowledge_pack.md`

- **IMPLEMENT**: 同步以下长期规则：缺上传普通澄清；交付保护后台保留前端隐形；交付成功以本轮可下载 artifact 满足请求为准；内部字段不进入用户可见提示；`needs_input` 非运行状态且可删除/清空。
- **GOTCHA**: 不写一次性排障时间线、截图路径、客户资料或 env 值。
- **VALIDATE**: `git diff --check`

---

## 测试策略

### 单元测试

- 后端 runner：缺输入普通澄清、交付成功类型匹配、文件名不一致不误报、真实缺 artifact 失败且 public payload 无内部字段。
- 后端 API：`needs_input` 可继续发送、可删除；running/runner active 仍阻止删除。
- 前端 state：`formatNeedsInput()` 隐藏内部字段；旧 payload 兼容；message attachments 或 file-only prompt 标准化。
- 前端 workspace：普通澄清不是 warning；交付失败不是“配置提醒”；`needs_input` 不算 active；清空只阻止 running。

### 集成测试

- 上传后消息发送：文件-only submit 仍调用 upload，再调用 post message，失败时 refresh task。
- artifact 投影：run `artifact_names` 满足请求类型时 assistant reply 附下载卡。

### 浏览器 E2E

- 使用真实 `http://127.0.0.1:3001` 和 `http://127.0.0.1:8001`。
- 截图覆盖澄清、文件消息、docx 下载卡、友好失败、清空会话。
- 证据目录不提交 git。

### 边界情况

- 用户输入很短：“生成 Word”，但没有上传和历史内容。
- 用户有文本正文但没有上传，应直接总结文本，不应要求上传。
- 用户有上传文件但输入为空，应继续上一轮意图或使用安全 follow-up。
- AI 声称 `foo.docx`，实际 artifact 是 `summary.docx`，本轮请求 Word，应成功。
- AI 声称 `foo.docx`，无任何 `.docx` artifact，应失败且隐藏内部字段。
- `needs_input` 历史任务混在 running 任务列表中，清空应被 running 阻止，但不是被 needs_input 阻止。

---

## 验证命令

执行所有命令，确保零回归与功能 100% 正确。

### 级别 1：语法与风格

```bash
git diff --check
cd backend
uv run ruff check .
uv run mypy app tests
cd ../frontend
npm run typecheck
npm run lint
```

### 级别 2：单元测试

```bash
cd backend
uv run pytest tests/unit/runner/test_core.py tests/unit/api/test_tasks.py tests/unit/storage/test_storage.py tests/unit/api/test_artifacts.py -q
cd ../frontend
npm test -- tests/state/test_task_state.test.ts tests/workspace/test_workspace_view.test.ts tests/workspace/test_task_workspace.test.ts
```

### 级别 3：完整回归

```bash
cd backend
uv run pytest
cd ../frontend
npm test
npm run build
```

### 级别 4：浏览器验收

```bash
cd frontend
npx playwright test e2e-playwright/test_missing_upload_clarification_delivery_warning.spec.mjs --reporter=line
npm run e2e:runtime-contracts
```

运行前确认实际服务复用用户已启动的端口：

```text
frontend: http://127.0.0.1:3001
backend:  http://127.0.0.1:8001
```

截图证据放到：

```text
frontend/e2e-playwright/e2e-YYYYMMDDHHMMSS/missing-upload-clarification-delivery-warning-fix/
```

### 级别 5：知识包检查

```bash
rg -n "缺上传|交付保护|needs_input|可下载 artifact|内部字段" asset/deepagents_platform_knowledge_pack.md
```

---

## 验收标准

- [ ] 缺上传/缺内容时显示普通 AI 澄清。
- [ ] 缺上传/缺内容时无“配置提醒”、无技术 JSON、无“等待补充输入”日志终态误导。
- [ ] 文件-only 发送可继续上一轮待处理意图。
- [ ] 文件-only 用户消息可显示文件，不要求用户重输原需求。
- [ ] 生成 `.docx` 后页面显示可下载卡片，无缺文件警告。
- [ ] 本轮已有满足请求类型的 artifact 时，不因 final answer 文件名不一致误报失败。
- [ ] 真实缺 artifact 时保留后台保护，但用户只看到友好失败说明和重新生成入口。
- [ ] 用户可见内容不暴露 `reason`、`repair_hint`、`missing_artifact_names` 等内部字段。
- [ ] `needs_input` 会话可删除可清空。
- [ ] 真实 running 会话仍阻止删除/清空。
- [ ] 后端单测、前端单测、真实浏览器 E2E、质量门和 `git diff --check` 通过。
- [ ] `asset/deepagents_platform_knowledge_pack.md` 已同步长期规则。

---

## 完成检查清单

- [ ] 所有任务均已按顺序完成。
- [ ] 每个任务的验证都已立即通过。
- [ ] 后端完整测试、ruff、mypy 通过。
- [ ] 前端 typecheck、unit、lint、build 通过。
- [ ] 真实 `3001/8001` Playwright E2E 通过。
- [ ] 截图证据已保存且未提交 git。
- [ ] 知识包已更新。
- [ ] 用户可见界面没有内部字段泄露。

---

## 备注

本需求的关键取舍是“保留保护，但隐藏技术细节”。不要把交付保护删掉；它仍然是防止虚假成功的必要后端安全网。真正要改的是判定口径和用户可见投影。

一次实现成功信心分数：8/10。主要风险在文件-only follow-up 的产品表达和数据结构选择：如果引入 message attachments，需要更广泛的 schema/storage/frontend 测试；如果只用 follow-up 文案，开发量小但文件消息展示能力较弱。
