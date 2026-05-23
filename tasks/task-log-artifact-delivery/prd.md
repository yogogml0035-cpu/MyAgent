# PRD: 任务日志与文件产物体验优化

## Introduction

MyAgent 的主对话页面当前承担了过重的运行诊断展示职责。thinking 模式下长任务会产生数千条事件，前端把大量日志行和完整诊断 JSON 参与实时渲染，导致页面滚动、点击日志、甚至暂停生成都可能卡死。另一方面，用户明确要求生成 Word 等文件时，AI 可能只在最终回复里给出容器路径，而没有把文件登记为可下载产物，造成“看起来完成但拿不到文件”的体验。

本功能将主对话体验调整为“默认精简进度 + 完整日志下载 + 可点击交付文件”，确保任务可控、结果可拿、失败可理解。

## Goals

- 长任务产生 2000+ 事件时，主页面仍能滚动、点击、暂停生成。
- 主对话默认只展示关键阶段、当前动作、错误/警告、完成状态和产物入口。
- 完整 reasoning/tool JSON 不在主页面实时渲染，改为按需下载完整日志。
- 用户要求的 Word/PPT/Excel/报告文件必须显示为可下载产物卡片。
- AI 声称已生成的文件必须登记为 artifact，否则不能显示任务成功。
- 最终回复保持简短摘要，正式交付以文件卡片为准。

## User Stories

### US-001: 精简主对话进度日志

**描述：** 作为运行长任务的用户，我想在主对话中只看到关键阶段和当前动作，以便页面始终可滚动、可暂停、可查看结果。

**Acceptance Criteria：**
- [ ] 进度日志默认只显示任务阶段、当前动作、错误/警告、完成或失败状态。
- [ ] `assistant_thinking_delta`、`assistant_answer_delta`、`values_snapshot`、完整 tool payload 和完整 final answer 不作为主页面实时大段内容渲染。
- [ ] 单轮 2000+ 原始事件不会在主页面创建 2000+ 可展开日志行。
- [ ] 点击或滚动进度日志时，输入区和暂停生成按钮仍可响应。
- [ ] `cd frontend && npm test -- tests/workspace/test_workspace_view.test.ts tests/workspace/test_task_conversation_scroll.test.ts` 通过。
- [ ] Typecheck 通过。

### US-002: 下载完整诊断日志

**描述：** 作为排障人员，我需要下载完整运行日志，以便在不拖慢主页面的前提下保留完整审计证据。

**Acceptance Criteria：**
- [ ] 每个 run 的进度区域提供“下载完整日志”入口。
- [ ] 下载内容包含该 run 的完整 JSONL 事件，包括 reasoning/tool/final_answer 诊断字段。
- [ ] 生成下载内容只在用户点击时发生，不在每次 React render 时预先构造完整诊断字符串。
- [ ] 空日志时下载入口不可用或给出明确空状态。
- [ ] `cd frontend && npm test -- tests/workspace/test_workspace_view.test.ts` 通过。
- [ ] Typecheck 通过。

### US-003: 登记真实生成的交付文件

**描述：** 作为需要 Word/PPT/Excel/报告交付的用户，我想让系统把真实生成的文件登记为可下载产物，以便不用依赖不可点击的容器路径。

**Acceptance Criteria：**
- [ ] 后端支持把当前 task workspace 中的真实生成文件复制或登记为 run-scoped artifact。
- [ ] 支持二进制文件产物，例如 `.docx`、`.pptx`、`.xlsx`，不能只支持文本 artifact。
- [ ] artifact name 继续经过安全文件名和路径边界校验。
- [ ] API state 中返回 artifact 的 name、type、url、run_id，前端可通过现有 artifact 下载链路获取文件。
- [ ] `cd backend && uv run pytest tests/unit/storage/test_storage.py tests/unit/api/test_artifacts.py -q` 通过。
- [ ] Typecheck 通过。

### US-004: 文件交付缺失时不能算成功

**描述：** 作为用户，我要求生成文件时，如果系统没有可下载产物，我需要看到明确失败或修正提示，以便不会被虚假的“已生成”误导。

**Acceptance Criteria：**
- [ ] 当用户消息明确要求生成 Word/PPT/Excel/报告文件时，runner 在完成前检查本轮是否登记了对应交付 artifact。
- [ ] 当最终回复声称已保存或已生成文件时，runner 检查该文件是否存在且已登记为 artifact。
- [ ] 如果要求的交付文件缺失，任务状态不能是成功完成。
- [ ] 缺失时 UI 可见消息包含“文件未生成或未登记为产物”或等价明确提示。
- [ ] 缺失时用户能看到重新生成或修复入口。
- [ ] `cd backend && uv run pytest tests/unit/runner/test_core.py tests/unit/api/test_tasks.py -q` 通过。
- [ ] Typecheck 通过。

### US-005: 最终回复展示简短摘要和文件卡片

**描述：** 作为接收交付物的用户，我希望最终回复简短说明结果，并在旁边看到文件下载卡片，以便明确真正交付的是可下载文件。

**Acceptance Criteria：**
- [ ] 有交付 artifact 时，最终助手气泡显示简短摘要、完成说明和文件清单。
- [ ] 文件下载卡片显示在最终回复旁边或紧随最终回复展示。
- [ ] 文件卡片包含文件名和下载按钮；HTML 报告仍可提供安全打开入口。
- [ ] 不把完整 Word/PPT/Excel 正文全部塞进聊天气泡作为交付替代品。
- [ ] `cd frontend && npm test -- tests/workspace/test_workspace_view.test.ts tests/state/test_task_state.test.ts` 通过。
- [ ] 使用 agent-browser 打开 `http://127.0.0.1:3001`，查看带 `.docx` artifact 的完成任务，确认最终回复旁边显示文件下载卡片。
- [ ] 页面无控制台错误。
- [ ] Typecheck 通过。

### US-006: 大日志和文件产物浏览器闭环验收

**描述：** 作为项目维护者，我需要真实浏览器验收覆盖“大量日志不卡 + 文件可下载 + 缺失文件不成功”的闭环，以便不会只通过单元测试误判完成。

**Acceptance Criteria：**
- [ ] 新增或更新 Playwright spec，使用真实 frontend `3001` 和 backend `8001`。
- [ ] E2E seed 一个包含 2000+ 事件的运行，主页面不渲染 2000+ 可展开日志行。
- [ ] E2E 验证滚动、点击日志、暂停生成或停止按钮在大量事件下仍可响应。
- [ ] E2E seed 一个 `.docx` run artifact，浏览器能看到下载卡片并成功下载。
- [ ] E2E seed 一个“要求文件但 artifact 缺失”的任务，浏览器显示明确失败/修正提示。
- [ ] 截图证据保存到 `frontend/e2e-playwright/e2e-YYYYMMDDHHMMSS/task-log-artifact-delivery/`，截图不提交 git。
- [ ] `cd frontend && npx playwright test e2e-playwright/test_task_log_artifact_delivery.spec.mjs --reporter=line` 通过。
- [ ] Typecheck 通过。

### US-007: 同步长期知识包和测试入口文档

**描述：** 作为后续维护者，我需要把日志默认精简、完整日志下载、交付文件登记和缺失文件失败的稳定规则写入知识包，以便后续改动不回退。

**Acceptance Criteria：**
- [ ] `asset/deepagents_platform_knowledge_pack.md` 记录主对话默认不渲染完整诊断 JSON。
- [ ] 知识包记录完整日志通过下载获得，并保持 run-scoped 边界。
- [ ] 知识包记录用户要求或最终回复声明的交付文件必须登记为 artifact。
- [ ] 知识包记录交付文件缺失时不能标记任务成功。
- [ ] `frontend/e2e-playwright/README.md` 记录新增 E2E 的运行方式和证据目录。
- [ ] `git diff --check` 通过。
- [ ] Typecheck 通过。

### US-008: 完整质量门回归

**描述：** 作为项目维护者，我需要在行为变更完成后跑完后端、前端和浏览器验收，以便确认核心任务工作区没有回归。

**Acceptance Criteria：**
- [ ] `cd backend && uv run pytest && uv run ruff check . && uv run mypy app tests` 通过。
- [ ] `cd frontend && npm run typecheck && npm test && npm run lint && npm run build` 通过。
- [ ] 运行新增 Playwright E2E 并通过。
- [ ] 运行现有 progress-log disclosure 或 runtime-contract 邻近回归并通过。
- [ ] `git diff --check` 通过。

## Functional Requirements

- FR-1: 主对话默认只展示关键运行阶段、当前动作、错误/警告、完成状态和产物入口。
- FR-2: 主对话不得实时渲染完整 reasoning/tool JSON、完整 run 诊断数组或 2000+ 原始事件行。
- FR-3: 每个 run 必须提供完整日志下载入口，下载内容为 run-scoped JSONL。
- FR-4: 用户明确要求的交付文件必须登记为 run-scoped artifact 并显示下载卡片。
- FR-5: AI 最终回复声明已保存或已生成的文件必须能被下载。
- FR-6: 交付文件缺失时，任务不能被标记为成功完成。
- FR-7: 最终回复应是简短摘要和文件清单，不应把完整交付正文作为聊天气泡替代文件。
- FR-8: 文件产物和日志下载必须遵守现有 token、artifact URL trust、路径校验和 run_id 边界。

## Non-Goals

- 不默认展示临时文件、内部 JSON、草稿或工具中间文件。
- 不允许前端直接访问后端私密配置、数据库、Qdrant、provider 或本地任意路径。
- 不把容器路径、本地绝对路径或第三方签名 URL 暴露为交付入口。
- 不用单元测试替代浏览器 E2E 验收。

## Design Considerations

- 继续沿用现有 warm canvas 视觉系统、`messageArtifactFooter`、`downloadCard` 和进度日志卡片风格。
- 完整日志下载入口应是清晰动作按钮，不占据主对话大量空间。
- 文件卡片应靠近最终回复，用户不需要翻日志才能下载交付物。
- 错误提示应直说“文件未生成或未登记为产物”，避免技术化路径泄露。

## Technical Considerations

- 前端日志展示当前集中在 `frontend/app/workspace-view.ts` 和 `frontend/components/chat/TaskConversation.tsx`。
- 前端 artifact 下载和打开当前由 `frontend/hooks/use-task-workspace.ts` 和 `frontend/lib/task-api.ts` 管理。
- 后端 artifact 的权威登记在 `backend/app/storage.py` 的 run `artifact_names` 和 `ArtifactRecord` 投影。
- 后端 runner 在 `backend/app/runner/core.py` 提取 final answer、更新终态并写入 `final_answer` event。
- 二进制交付文件需要避免只走 `write_run_text()`，应支持从 task workspace 安全推广真实文件。
- 行为变更必须同步 `asset/deepagents_platform_knowledge_pack.md` 和实际浏览器 E2E 截图证据。

## Success Metrics

- 2000+ 事件任务的主页面不会出现浏览器 Page Unresponsive 弹窗。
- 用户在长任务运行中仍可点击暂停生成。
- 用户要求生成 Word 文件后，最终结果中有可点击下载卡片。
- 交付文件缺失时，用户不会看到虚假的成功完成状态。

## Open Questions

- 无。
