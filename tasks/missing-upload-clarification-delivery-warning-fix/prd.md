# PRD: 缺上传澄清与文件交付警告修复

## Introduction

MyAgent 当前已经有文件交付保护，用于避免 AI 声称生成 Word/PPT/Excel/报告但页面没有可下载 artifact 的情况。这个保护方向正确，但用户可见呈现过于技术化：缺上传或缺输入时会像运行配置问题一样出现警告，真实交付失败时也可能暴露 `reason`、`repair_hint`、`missing_artifact_names` 等内部字段。

本功能将缺输入场景改成普通 AI 澄清，将文件交付保护改成“后台保留、前台隐形”。用户看到的是自然追问、清晰失败说明和可点击下载卡片，而不是技术 JSON 或配置提醒。

## Goals

- 缺上传/缺内容时，AI 用普通对话追问用户补充文件或文本。
- 上传文件本身可以作为继续上一轮意图的有效用户输入。
- 文件交付成功以本轮页面是否存在满足请求的可下载 artifact 为准。
- 文件交付失败时保留后台保护，但用户只看到简短、可操作的失败说明和重新生成入口。
- `needs_input` 保持非运行状态，允许删除和清空会话。
- 行为变化同步前后端测试、浏览器 E2E 截图证据和长期知识包。

## User Stories

### US-001: 缺上传/缺内容时普通澄清

**描述：** 作为要求总结并生成 Word 的用户，我想在忘记上传文件时收到自然追问，以便知道下一步上传文件即可继续。

**Acceptance Criteria：**
- [ ] 空会话中发送“总结内容并生成 Word”，且没有上传文件、输入正文或可复用上下文时，系统返回普通 assistant 消息。
- [ ] 澄清文案表达“你是不是忘记上传文件了？上传后我继续帮你生成 Word”或等价意思。
- [ ] 该场景不创建用户可见的 `needs_input` 警告卡片。
- [ ] 页面不显示“配置提醒”“等待补充输入”或技术 JSON。
- [ ] `cd backend && uv run pytest tests/unit/runner/test_core.py tests/unit/api/test_tasks.py -q` 通过。
- [ ] `cd frontend && npm test -- tests/state/test_task_state.test.ts tests/workspace/test_workspace_view.test.ts` 通过。
- [ ] Typecheck 通过。

### US-002: 仅上传文件可继续上一轮待处理意图

**描述：** 作为收到澄清的用户，我想只上传文件并发送，以便系统自动继续上一轮“总结并生成 Word”的需求。

**Acceptance Criteria：**
- [ ] Composer 在只选择文件、输入框为空时仍允许发送。
- [ ] 仅上传文件发送后，用户消息在对话中可见，消息卡片可以只显示文件名和文件状态。
- [ ] 后端运行上下文能看到上一轮待处理意图和本轮上传资源。
- [ ] 模型不要求用户重新输入“总结并生成 Word”。
- [ ] 文件上传后启动的新 run 能通过资源工具读取上传文件。
- [ ] 使用 agent-browser 打开 `http://127.0.0.1:3001`，完成澄清后仅上传文件发送，页面出现文件消息并继续生成 Word。
- [ ] 页面无控制台错误。
- [ ] Typecheck 通过。

### US-003: 文件交付成功以可下载产物为准

**描述：** 作为接收交付物的用户，我想只要页面有满足请求的下载卡片就视为成功，以便不被文件名推断误报打断。

**Acceptance Criteria：**
- [ ] 当用户请求 Word 且本轮 run 已登记任意 `.docx` artifact 时，任务可成功完成。
- [ ] 当用户请求 PPT 且本轮 run 已登记任意 `.pptx` artifact 时，任务可成功完成。
- [ ] 当用户请求 Excel 且本轮 run 已登记 `.xlsx` 或 `.xlsm` artifact 时，任务可成功完成。
- [ ] 当用户请求报告且本轮 run 已登记 `.html`、`.md` 或 `.pdf` artifact 时，任务可成功完成。
- [ ] 如果 final answer 声称的文件名与实际 artifact 文件名不完全一致，但 artifact 类型满足本次请求，前端不显示缺文件警告。
- [ ] `cd backend && uv run pytest tests/unit/runner/test_core.py tests/unit/api/test_artifacts.py -q` 通过。
- [ ] Typecheck 通过。

### US-004: 文件交付失败对用户隐藏内部字段

**描述：** 作为用户，我需要知道文件没有成功生成并可以重试，但不需要看到内部诊断字段。

**Acceptance Criteria：**
- [ ] AI 声称生成文件但本轮没有任何满足请求的可下载 artifact 时，后台交付保护仍生效。
- [ ] 用户可见消息简短说明文件未成功生成或未能登记为下载文件。
- [ ] 用户可见区域不显示 `reason`、`repair_hint`、`missing_artifact_names`、`missing_deliverables`、`requested_deliverable_types`、`promoted_artifacts` 等内部字段名。
- [ ] 前端提供重新生成入口或等价可操作动作。
- [ ] 该失败说明不使用“配置提醒”标题或技术警告样式。
- [ ] `cd frontend && npm test -- tests/state/test_task_state.test.ts tests/workspace/test_workspace_view.test.ts` 通过。
- [ ] Typecheck 通过。

### US-005: 清空会话只阻止真实运行中任务

**描述：** 作为整理历史会话的用户，我想清空已结束或待补充的会话，以便 `needs_input` 不再像运行中任务一样阻塞我。

**Acceptance Criteria：**
- [ ] `complete`、`failed`、`cancelled`、`needs_input`、`interrupted` 会话都允许删除。
- [ ] `complete`、`failed`、`cancelled`、`needs_input`、`interrupted` 会话都允许被“清空所有会话”批量删除。
- [ ] 真实 `running` 会话仍阻止删除和清空。
- [ ] runner active 但状态尚未刷新时仍阻止删除和清空。
- [ ] 阻止文案说明“任务正在运行，等待完成或停止后再清空”或等价意思。
- [ ] `cd backend && uv run pytest tests/unit/api/test_tasks.py -q` 通过。
- [ ] `cd frontend && npm test -- tests/workspace/test_task_workspace.test.ts tests/workspace/test_workspace_view.test.ts` 通过。
- [ ] Typecheck 通过。

### US-006: 用户可见状态和日志口径统一

**描述：** 作为使用者，我想看到一致的人类语言状态，以便缺输入、失败和完成状态不会混成配置问题。

**Acceptance Criteria：**
- [ ] 缺输入澄清渲染为普通 AI 回复。
- [ ] 真实交付失败渲染为普通失败说明或重试提示。
- [ ] `needs_input` 如果仍作为后台状态存在，前端状态标签不再误导为运行中。
- [ ] 进度日志不默认展开交付保护的内部 JSON。
- [ ] 下载卡片仍显示文件名、下载按钮；HTML 报告仍使用安全打开入口。
- [ ] `cd frontend && npm test -- tests/workspace/test_workspace_view.test.ts tests/state/test_task_state.test.ts` 通过。
- [ ] Typecheck 通过。

### US-007: 浏览器 E2E 覆盖核心用户路径

**描述：** 作为项目维护者，我需要真实浏览器验收覆盖缺上传澄清、上传后继续、交付成功、交付失败和清空会话，以便避免单测误判。

**Acceptance Criteria：**
- [ ] Playwright 使用真实 frontend `3001` 和 backend `8001`。
- [ ] E2E 覆盖无上传“总结内容并生成 Word”出现普通澄清。
- [ ] E2E 覆盖澄清后仅上传文件发送，页面显示文件消息并继续上一轮意图。
- [ ] E2E 覆盖 `.docx` artifact 成功显示下载卡片且无缺文件警告。
- [ ] E2E 覆盖缺失 artifact 时显示友好失败说明且无内部字段。
- [ ] E2E 覆盖 `needs_input` 会话可清空，真实 `running` 会话仍阻止。
- [ ] 截图证据保存到 `frontend/e2e-playwright/e2e-YYYYMMDDHHMMSS/missing-upload-clarification-delivery-warning-fix/`，证据不提交 git。
- [ ] `cd frontend && npx playwright test e2e-playwright/test_missing_upload_clarification_delivery_warning.spec.mjs --reporter=line` 通过。
- [ ] Typecheck 通过。

### US-008: 同步长期知识包和质量门

**描述：** 作为后续维护者，我需要把新的状态、交付和用户路径规则写入长期知识包，以便后续改动不回退。

**Acceptance Criteria：**
- [ ] `asset/deepagents_platform_knowledge_pack.md` 记录缺上传应普通澄清，不默认显示技术警告。
- [ ] 知识包记录文件交付保护保留，但用户可见层隐藏内部字段。
- [ ] 知识包记录交付成功以本轮可下载 artifact 满足请求为准。
- [ ] 知识包记录 `needs_input` 不是运行中状态，删除/清空只阻止真实 running。
- [ ] 后端质量门通过：`cd backend && uv run pytest && uv run ruff check . && uv run mypy app tests`。
- [ ] 前端质量门通过：`cd frontend && npm run typecheck && npm test && npm run lint && npm run build`。
- [ ] `git diff --check` 通过。

## Functional Requirements

- FR-1: 系统必须在缺上传/缺内容时生成普通 assistant 澄清，而不是用户可见技术警告。
- FR-2: 系统必须允许文件-only 发送，并将其视为可启动后续 run 的有效用户输入。
- FR-3: 系统必须保留上一轮待处理意图，使文件-only 发送能继续上一轮需求。
- FR-4: 系统必须继续在后台防止“AI 声称生成文件但无可下载产物”的虚假成功。
- FR-5: 系统必须以本轮可下载 artifact 类型是否满足请求作为文件交付成功判断。
- FR-6: 系统不得因为 final answer 中推断文件名与 artifact 文件名不完全一致而误报失败，只要 artifact 类型满足请求。
- FR-7: 用户可见内容不得暴露交付保护内部字段名或内部 JSON。
- FR-8: 真实交付失败必须提供简短失败说明和重新生成入口。
- FR-9: `needs_input` 必须是可继续、可删除、可清空的非运行状态。
- FR-10: 只有真实 `running` 状态或 runner active 才能阻止删除/清空。
- FR-11: 行为变化必须同步 `asset/deepagents_platform_knowledge_pack.md`。
- FR-12: 行为变化必须用真实浏览器 E2E 和截图证据验收。

## Non-Goals

- 不新增外部 API endpoint。
- 不删除后台文件交付保护。
- 不把内部 repair/debug 字段作为用户指导展示。
- 不改变 provider、Postgres、Qdrant 或 embedding secret 管理方式。
- 不把上传文件正文写入长期记忆、知识包或截图证据。
- 不用一次性 DevTools 调试代替 Playwright E2E。

## Design Considerations

- 缺上传澄清应使用普通 AI 回复气泡，不使用黄色配置提醒。
- 文件-only 用户消息可以显示为文件 chip、文件列表或紧凑文件卡片，避免用冗长默认 prompt 污染对话。
- 失败说明要短，可操作，指向重新生成或重新发送，不展示内部 JSON。
- 下载卡片继续沿用现有 `messageArtifactFooter`、`downloadCard`、artifact 下载按钮样式。

## Technical Considerations

- 后端任务状态和 run 生命周期集中在 `backend/app/api/tasks.py`、`backend/app/runner/core.py`、`backend/app/storage.py`。
- 上传资源 manifest 和 Word 产物生成集中在 `backend/app/execution/resources.py`。
- 同会话上下文由 `backend/app/conversation_context.py` 生成，文件-only follow-up 需要保留上一轮用户意图。
- 前端发送、上传、清空历史和错误提示集中在 `frontend/hooks/use-task-workspace.ts`。
- 前端状态标准化和 `needs_input` 文案集中在 `frontend/app/task-state.ts`。
- 前端消息、日志和 artifact 展示集中在 `frontend/app/workspace-view.ts` 和 `frontend/components/chat/TaskConversation.tsx`。

## Success Metrics

- 缺上传时用户知道上传文件即可继续，且没有技术警告。
- 上传文件后用户不需要重复输入上一轮需求。
- 正常生成 Word 时页面只有成功结果和下载卡片，没有缺文件警告。
- 文件缺失时用户看到可理解的失败说明，不看到内部字段。
- `needs_input` 会话可以被清空。

## Open Questions

- 无。默认产品口径已在需求中确认。
