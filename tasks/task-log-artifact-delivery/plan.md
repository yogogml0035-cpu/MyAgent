# 功能: 任务日志与文件产物体验优化

下面这份计划应尽可能完整，但在真正开始实现前，仍然必须再次验证文档、代码库模式以及任务本身是否合理。

特别注意现有 utils、types、models 的命名，并确保从正确的文件中导入。

## 功能描述

把 MyAgent 主对话从“默认承载完整调试日志”调整为“默认展示关键进度，完整诊断按需下载”；同时把用户明确要求或 AI 声称已生成的 Word/PPT/Excel/报告文件登记为可下载 artifact，并在文件缺失时阻止虚假成功。

## 用户故事

作为一名使用 MyAgent 生成长报告和 Office 文档的用户，我想要主页面在大量事件下仍然可用，并且最终结果提供可点击下载的文件，以便我能可靠暂停任务、查看结果和拿到交付物。

## 问题陈述

thinking 模式会产生大量 `assistant_thinking_delta`、tool、status 和 snapshot 事件。当前前端会在 render 过程中构造可见日志项和完整诊断 JSON，并把大量 `<details>` 和 `<pre>` 放入 DOM，造成浏览器无响应。另一个问题是，后端只有登记到 run `artifact_names` 的文件才会成为前端可下载 artifact；如果 AI 只在最终回答中给出 `/root/xxx.docx`，用户拿不到文件，系统却可能显示完成。

## 方案陈述

前端侧把进度日志拆成轻量摘要投影和按需下载的完整 JSONL。主页面只渲染有限关键阶段，不预先构造完整诊断 JSON；点击“下载完整日志”时才生成当前 run 的 JSONL 文件。后端侧增加安全的交付文件推广/登记流程，把 task workspace 中的真实文件复制或登记为 run-scoped artifact；runner 在完成前检查“用户要求的交付文件”和“最终回复声称已生成的文件”是否存在并已登记，缺失则写入明确错误而不是成功完成。前端继续复用现有 artifact 卡片和下载逻辑，把最终回复呈现为简短摘要 + 文件入口。

## 功能元数据

**功能类型**: 缺陷修复 + 增强  
**预估复杂度**: 高  
**主要受影响系统**: 后端 runner、storage、artifact API、前端 workspace view、TaskConversation、useTaskWorkspace、Playwright E2E、平台知识包  
**依赖项**: 现有 FastAPI/Postgres task storage、Next.js 前端、Playwright、DeepAgents workspace backend

---

## 上下文参考

### 相关代码文件 重要：实现前你必须先阅读这些文件！

- `AGENTS.md` - 仓库执行边界：行为变更必须同步代码、测试、浏览器 E2E、截图证据和知识包。
- `INTERFACES.md` - 前后端 API、SSE、artifact download、字段转换和安全边界。
- `ARCHITECTURE.md` - 后端权威状态、前端浏览器工作区和 `asset/` 知识包职责。
- `frontend/app/workspace-view.ts:192` - `buildLogClipboardText()` 目前负责 JSONL copy 文本。
- `frontend/app/workspace-view.ts:196` - `buildRunDiagnosticsJson()` 当前会格式化完整 run 诊断 JSON。
- `frontend/app/workspace-view.ts:200` - `buildLiveLogItems()` 当前把 logs 投影为可见行。
- `frontend/app/workspace-view.ts:1513` - `buildRunActivityGroups()` 按 run 分组 logs 和 artifacts。
- `frontend/app/workspace-view.ts:1620` - `buildConversationStreamItems()` 决定消息、run、artifact 在主对话中的顺序。
- `frontend/app/workspace-view.ts:1648` - `pushArtifactItems()` 负责无 assistant reply 时的 artifact 卡片。
- `frontend/components/chat/TaskConversation.tsx:267` - assistant 回复底部已有 `messageArtifactFooter` artifact 列表。
- `frontend/components/chat/TaskConversation.tsx:312` - `renderArtifactMessage()` 已有独立 artifact 下载卡片。
- `frontend/components/chat/TaskConversation.tsx:355` - `renderRunItem()` 是 run 进度日志渲染入口。
- `frontend/components/chat/TaskConversation.tsx:359` - 每次 render 调用 `buildLiveLogItems(group.logs, group.status)`。
- `frontend/components/chat/TaskConversation.tsx:360` - 每次 render 构造 `buildRunDiagnosticsJson(group.logs)`。
- `frontend/components/chat/TaskConversation.tsx:460` - 完整诊断 JSON 当前作为 `<pre>{runDiagnosticsText}</pre>` 渲染。
- `frontend/hooks/use-task-workspace.ts:344` - SSE 失败/恢复时调用 `fetchTaskEvents()` 合并事件。
- `frontend/hooks/use-task-workspace.ts:791` - `handleDownloadArtifact()` 负责 artifact blob 下载。
- `frontend/hooks/use-task-workspace.ts:812` - `handleOpenArtifact()` 负责 HTML artifact 安全预览。
- `frontend/lib/task-api.ts:134` - `fetchTaskEvents()` 是增量事件恢复接口。
- `frontend/lib/task-api.ts:195` - `fetchArtifactBlob()` 通过 artifact request 安全下载文件。
- `frontend/app/task-state.ts:1087` - run `artifact_names` 标准化进入前端状态。
- `backend/app/storage.py:59` - `RUN_ARTIFACT_NAMES` 定义 legacy mirror 的固定 artifact 名称。
- `backend/app/storage.py:85` - `TYPE_MAP` 把后缀映射成前端 artifact type。
- `backend/app/storage.py:222` - `normalize_artifact_name()` 是 artifact 文件名安全边界。
- `backend/app/storage.py:1404` - `write_run_text()` 当前只覆盖文本写入并登记 artifact。
- `backend/app/storage.py:1447` - `record_run_artifact()` 更新 run `artifact_names` 并维护 manifest artifact refs。
- `backend/app/storage.py:1484` - `resolve_artifact()` 兼容 latest/legacy artifact 下载。
- `backend/app/storage.py:1495` - `resolve_run_artifact()` 校验 run-scoped artifact membership。
- `backend/app/storage.py:1781` - `_artifact_records_for_state()` 把 run artifact_names 投影成 API artifacts。
- `backend/app/api/artifacts.py:18` - `_artifact_response()` 用 `FileResponse` 返回 artifact 文件。
- `backend/app/api/artifacts.py:33` - latest artifact 下载 API。
- `backend/app/api/artifacts.py:40` - run-scoped artifact 下载 API。
- `backend/app/runner/core.py:123` - runner 构建 agent 时把 workspace 指向当前 task workspace。
- `backend/app/runner/core.py:245` - runner 从 final state 提取最终答案。
- `backend/app/runner/core.py:256` - runner 当前在这里把任务置为 complete。
- `backend/app/runner/core.py:278` - runner 在 complete 后写入 synthetic `final_answer` event。
- `backend/app/agent/factory.py:123` - `_make_backend()` 创建 DeepAgents workspace backend。
- `backend/app/agent/factory.py:135` - 默认 `FilesystemBackend(root_dir=root, virtual_mode=True)` 是 task workspace 文件边界。
- `asset/deepagents_platform_knowledge_pack.md:35` - 记录 streaming/event/log display 稳定规则。
- `asset/deepagents_platform_knowledge_pack.md:36` - 记录 progress-log display 是 append-only event log 的用户投影。
- `frontend/tests/workspace/test_workspace_view.test.ts:49` - 覆盖 JSONL copy 行为。
- `frontend/tests/workspace/test_workspace_view.test.ts:1012` - 覆盖 `final_answer` 不作为可见日志行。
- `frontend/tests/workspace/test_workspace_view.test.ts:1588` - 当前测试锁定“完整诊断 JSON”存在，改需求时需要更新。
- `frontend/tests/workspace/test_workspace_view.test.ts:2524` - 覆盖 artifact 附着到 assistant reply。
- `backend/tests/unit/api/test_artifacts.py:34` - 覆盖 run-scoped artifact 下载。
- `backend/tests/unit/api/test_artifacts.py:116` - 覆盖未登记 artifact 不可下载。
- `backend/tests/unit/storage/test_storage.py:240` - 覆盖自定义 run artifact 登记。
- `frontend/e2e-playwright/test_runtime_contracts.spec.mjs:179` - 覆盖 artifact open/download 的真实浏览器合同。
- `frontend/e2e-playwright/test_progress_log_disclosure.spec.mjs:390` - 覆盖进度日志 disclosure 的浏览器合同。

### 需要创建的新文件

- `frontend/e2e-playwright/test_task_log_artifact_delivery.spec.mjs` - 大量日志、文件下载、缺失文件失败的真实浏览器闭环。

### 需要修改的现有文件

- `frontend/app/workspace-view.ts` - 增加轻量日志投影、日志下载数据构造、去除默认完整诊断渲染依赖。
- `frontend/components/chat/TaskConversation.tsx` - 改 run 卡片操作区，提供下载完整日志，避免 `<pre>` 默认承载完整 JSON。
- `frontend/hooks/use-task-workspace.ts` - 增加 `handleDownloadRunLogs` 或等价 handler，复用现有下载/错误反馈模式。
- `frontend/components/chat/TaskWorkspace.tsx` - 传递新增下载完整日志 handler。
- `frontend/app/task-state.ts` - 如新增 artifact type 或 task error copy，需要同步标准化。
- `frontend/app/globals.css` - 调整日志下载按钮和简化日志区域样式，沿用现有 tokens。
- `frontend/tests/workspace/test_workspace_view.test.ts` - 更新日志投影、artifact 附着和源码边界测试。
- `frontend/tests/workspace/test_task_conversation_scroll.test.ts` - 覆盖大量事件下滚动不被强制抢回。
- `frontend/tests/state/test_task_state.test.ts` - 覆盖 artifact metadata 和缺失文件错误投影。
- `backend/app/storage.py` - 增加二进制/现有文件推广为 run artifact 的方法。
- `backend/tests/fakes.py` - 同步 fake storage 的 artifact 推广合同。
- `backend/app/runner/core.py` - 在 complete 前执行交付文件检查和 artifact 登记；缺失时写失败/修正提示。
- `backend/app/api/tasks.py` - 如需要公开缺失交付提示或重新生成入口，保持 route 层薄封装。
- `backend/tests/unit/storage/test_storage.py` - 覆盖二进制 artifact 推广、路径安全、manifest。
- `backend/tests/unit/api/test_artifacts.py` - 覆盖 `.docx` run artifact 下载和未登记文件不可下载。
- `backend/tests/unit/runner/test_core.py` - 覆盖要求文件时缺失不能 complete。
- `backend/tests/unit/api/test_tasks.py` - 覆盖 API state 的失败/提示可见。
- `asset/deepagents_platform_knowledge_pack.md` - 同步长期稳定规则。
- `frontend/e2e-playwright/README.md` - 记录新增 E2E 入口。

### 相关文档 实现前你应该先阅读这些文档！

- `frontend/e2e-playwright/README.md`
  - 具体章节：runtime-contract、progress-log disclosure、证据目录。
  - 原因：本任务必须保留真实浏览器 E2E 截图证据。
- `backend/.planning/codebase/ARCHITECTURE.md`
  - 具体章节：Runner、Storage、产物下载路径。
  - 原因：后端状态和文件边界必须通过 storage/runner。
- `frontend/.planning/codebase/ARCHITECTURE.md`
  - 具体章节：TaskConversation、useTaskWorkspace、workspace-view。
  - 原因：前端分层要求不允许组件直接 fetch task API。
- `frontend/.planning/codebase/TESTING.md`
  - 具体章节：progress/log/diagnostics、artifact URL/preview/download 场景选择。
  - 原因：选择正确的 unit + E2E 组合。

### 需要遵循的模式

**前端状态/展示分层：**
- API 调用在 `frontend/lib/task-api.ts`，hook 负责动作，`workspace-view.ts` 负责纯展示数据，`TaskConversation.tsx` 只渲染 props。
- 不要在组件中直接 fetch `/api/tasks` 或 artifact routes。

**日志边界：**
- `buildLiveLogItems()` 是用户可见进度投影，不应变成完整诊断承载层。
- `buildLogClipboardText()` 可继续作为 run-scoped JSONL 的基础，但下载内容应在点击时生成。
- `final_answer` 不应成为可见进度行；最终答案来自 stored `ChatMessage`。

**artifact 安全：**
- 前端下载必须走 `fetchArtifactBlob()` 和 `buildArtifactRequest()`。
- 后端必须通过 `normalize_artifact_name()`、run id 校验和 storage resolver 保护路径。
- 不要把 AI 回复中的 `/root/...`、绝对路径或外部 URL 直接渲染成链接。

**runner 终态：**
- `TaskRunner` 当前先更新 task complete，再追加 `final_answer` event。新增交付文件检查必须发生在 success complete 前。
- 如果文件缺失，写入 failed 或 needs-input 风格的可见提示，但不能让 status 成为 complete。

**测试：**
- 逻辑投影先用 Node unit tests 锁定。
- 浏览器行为必须用真实 `3001`/`8001` E2E 验证，并保存截图到 timestamped evidence 目录。

---

## 实现计划

### 阶段 1：轻量日志投影与下载合同

**任务：**

- 调整 `workspace-view.ts`，为主页面生成有限数量的关键日志项。
- 保留完整 run logs 作为下载数据源，不在 render 时格式化完整 pretty JSON。
- 添加 run-scoped JSONL 下载 helper，点击时生成 Blob。
- 更新 `TaskConversation` 的 run 卡片操作区，把“完整诊断 JSON”面板替换为“下载完整日志”。

### 阶段 2：后端交付文件 artifact 登记

**任务：**

- 在 `PostgresTaskStorage` 增加安全方法，把 task workspace 中的真实文件推广到 run artifact 目录并登记。
- 支持二进制文件，不再只依赖 `write_run_text()`。
- 同步 `backend/tests/fakes.py`。
- 确认 API state 和 artifact download routes 对 `.docx` 等文件可用。

### 阶段 3：runner 交付检查与失败提示

**任务：**

- 在 runner 完成前判断用户是否要求文件交付，解析最终回复中声称已生成的文件名。
- 对存在的交付文件登记为 artifact。
- 对缺失的交付文件阻止 success complete，写入明确提示。
- 避免把不可访问路径泄露为用户下载入口。

### 阶段 4：最终回复和 artifact 卡片体验

**任务：**

- 确保有 artifact 的 assistant reply 附带下载卡片。
- 文件卡片靠近最终回复，且无 assistant reply 时仍显示独立 artifact 卡片。
- 最终回复保持简短摘要和文件清单；必要时对交付文件场景增加简短交付提示。

### 阶段 5：测试、E2E、知识包

**任务：**

- 更新 unit tests。
- 新增 Playwright E2E 覆盖 2000+ 日志、`.docx` 下载、缺失文件失败。
- 更新 `asset/deepagents_platform_knowledge_pack.md` 和 `frontend/e2e-playwright/README.md`。
- 跑完整质量门。

---

## 分步任务

### UPDATE `frontend/app/workspace-view.ts`

- **IMPLEMENT**: 增加轻量日志投影策略，限制主页面可见日志项数量和类别；保留错误/警告、当前 active 状态、关键 tool stage、terminal 状态。
- **IMPLEMENT**: 新增或调整 run-scoped JSONL download helper，输出完整 `ExecutionLog[]` 的 JSONL 字符串。
- **REMOVE**: 主渲染路径对 `buildRunDiagnosticsJson(group.logs)` 的强依赖。
- **PATTERN**: 复用 `buildLogClipboardText()` 和 `byLogOrder` 现有排序/补字段模式。
- **GOTCHA**: 不要丢失完整 `payload.content`；截断只能发生在可见摘要层。
- **VALIDATE**: `cd frontend && npm test -- tests/workspace/test_workspace_view.test.ts`

### UPDATE `frontend/components/chat/TaskConversation.tsx`

- **IMPLEMENT**: 把 run card 的“完整诊断 JSON”面板替换为“下载完整日志”按钮或同等入口。
- **IMPLEMENT**: 点击下载按钮调用 hook 传入的 run log download handler。
- **IMPLEMENT**: 保持 artifact 卡片和最终回复附近的文件入口。
- **PATTERN**: `renderArtifactMessage()` 和 `messageArtifactFooter` 已有下载按钮样式可复用。
- **GOTCHA**: 不要在 render 时生成完整 JSON 字符串；不要在主页面渲染大量 `<pre>`。
- **VALIDATE**: `cd frontend && npm test -- tests/workspace/test_workspace_view.test.ts tests/workspace/test_task_conversation_scroll.test.ts`

### UPDATE `frontend/hooks/use-task-workspace.ts`

- **IMPLEMENT**: 新增 `handleDownloadRunLogs(logs, groupTitle/runId)`，点击时生成 JSONL Blob 并触发下载。
- **PATTERN**: 参考 `handleDownloadArtifact()` 的 `<a download>` + Blob 下载模式。
- **GOTCHA**: 下载文件名要安全、稳定，例如 `myagent-run-<runId>-logs.jsonl`；不要包含用户私密路径。
- **VALIDATE**: `cd frontend && npm test -- tests/workspace/test_task_workspace.test.ts tests/workspace/test_workspace_view.test.ts`

### UPDATE `frontend/components/chat/TaskWorkspace.tsx`

- **IMPLEMENT**: 把 `handleDownloadRunLogs` 作为 prop 传给 `TaskConversation`。
- **PATTERN**: 与 `onCopyLogs`、`onDownloadArtifact`、`onOpenArtifact` 的 prop 传递保持一致。
- **VALIDATE**: `cd frontend && npm test -- tests/workspace/test_task_workspace.test.ts`

### UPDATE `backend/app/storage.py`

- **IMPLEMENT**: 增加 `promote_run_artifact_file(task_id, run_id, source_path, artifact_name=None)` 或等价方法，把当前 task workspace 下的真实文件复制到 `artifacts/runs/{run_id}/` 并登记。
- **IMPLEMENT**: 支持二进制复制、digest、size、artifact_ref payload 和 manifest merge。
- **PATTERN**: 复用 `normalize_artifact_name()`、`run_artifact_dir()`、`record_run_artifact()`、`_artifact_ref_payload()`。
- **GOTCHA**: source path 必须在当前 task workspace 内；不能允许 `/root/...` 或任意绝对路径直接逃逸。AI 回复中的绝对路径只能作为候选文件名/提示，不能作为可信 host path。
- **VALIDATE**: `cd backend && uv run pytest tests/unit/storage/test_storage.py -q`

### UPDATE `backend/tests/fakes.py`

- **IMPLEMENT**: 同步 fake storage 的二进制 artifact 推广方法和 artifact_records 投影。
- **PATTERN**: 参考 fake `write_run_text()`、`record_run_artifact()`、`resolve_run_artifact()`。
- **VALIDATE**: `cd backend && uv run pytest tests/unit/runner/test_core.py tests/unit/api/test_tasks.py -q`

### UPDATE `backend/app/runner/core.py`

- **IMPLEMENT**: 在 `status="complete"` 前执行交付文件检查。
- **IMPLEMENT**: 从用户 message 判断是否请求 Word/PPT/Excel/报告文件；从 final answer 判断是否声称已保存/已生成文件。
- **IMPLEMENT**: 对真实存在的交付文件调用 storage artifact 推广/登记。
- **IMPLEMENT**: 若交付文件缺失，写入 failed 或修正提示事件，错误文案包含“文件未生成或未登记为产物”，并避免追加成功 final_answer。
- **PATTERN**: 保持 terminal event 和 run_id 归属与现有 complete/failed/cancelled 路径一致。
- **GOTCHA**: 不要在 ChatMessage 存储前发 success `final_answer` event；不要把缺失文件 run 标记为 complete。
- **VALIDATE**: `cd backend && uv run pytest tests/unit/runner/test_core.py -q`

### UPDATE `backend/tests/unit/api/test_artifacts.py`

- **IMPLEMENT**: 增加 `.docx` 或二进制 run artifact 下载测试。
- **IMPLEMENT**: 保留未登记 artifact 返回 404 的测试。
- **VALIDATE**: `cd backend && uv run pytest tests/unit/api/test_artifacts.py -q`

### UPDATE `backend/tests/unit/api/test_tasks.py`

- **IMPLEMENT**: 覆盖缺失交付文件时 task API state 暴露失败/修正提示。
- **VALIDATE**: `cd backend && uv run pytest tests/unit/api/test_tasks.py -q`

### UPDATE `frontend/tests/workspace/test_workspace_view.test.ts`

- **IMPLEMENT**: 更新“完整诊断 JSON”源码锁定测试，改为锁定下载完整日志入口。
- **IMPLEMENT**: 增加 2000+ events 输入下可见日志项数量受控的纯函数测试。
- **IMPLEMENT**: 保留 artifact attach tests，并增加 `.docx` artifact 卡片场景。
- **VALIDATE**: `cd frontend && npm test -- tests/workspace/test_workspace_view.test.ts`

### UPDATE `frontend/tests/state/test_task_state.test.ts`

- **IMPLEMENT**: 覆盖 run artifact metadata、`.docx` type fallback、缺失交付错误消息标准化。
- **VALIDATE**: `cd frontend && npm test -- tests/state/test_task_state.test.ts`

### CREATE `frontend/e2e-playwright/test_task_log_artifact_delivery.spec.mjs`

- **IMPLEMENT**: 使用真实前端和后端服务，seed 一个 2000+ 事件任务并验证主页面不渲染 2000+ 行。
- **IMPLEMENT**: 验证滚动、日志点击和停止/暂停控件在大量事件下仍响应。
- **IMPLEMENT**: seed 一个 `.docx` run artifact，验证下载卡片和下载文件名。
- **IMPLEMENT**: seed 一个文件缺失失败任务，验证可见错误/修正提示。
- **PATTERN**: 复用 `test_runtime_contracts.spec.mjs` 的 artifact seed 和 download 断言；复用 `test_progress_log_disclosure.spec.mjs` 的 event seed 模式。
- **VALIDATE**: `cd frontend && MYAGENT_E2E_BASE_URL=http://127.0.0.1:3001 MYAGENT_E2E_API_URL=http://127.0.0.1:8001 MYAGENT_E2E_EVIDENCE_DIR=./e2e-playwright/e2e-YYYYMMDDHHMMSS/task-log-artifact-delivery npx playwright test e2e-playwright/test_task_log_artifact_delivery.spec.mjs --reporter=line`

### UPDATE `asset/deepagents_platform_knowledge_pack.md`

- **IMPLEMENT**: 记录主对话默认精简日志、完整日志下载、交付文件 artifact 登记、缺失文件不能成功。
- **VALIDATE**: `git diff --check`

### UPDATE `frontend/e2e-playwright/README.md`

- **IMPLEMENT**: 记录新增 E2E 的环境变量、真实服务要求、证据目录。
- **VALIDATE**: `git diff --check`

---

## 测试策略

### 单元测试

- `frontend/tests/workspace/test_workspace_view.test.ts`：日志投影数量、run-scoped JSONL、artifact 附着。
- `frontend/tests/workspace/test_task_conversation_scroll.test.ts`：大量日志下滚动状态不被强制抢回。
- `frontend/tests/state/test_task_state.test.ts`：artifact metadata、错误消息标准化。
- `backend/tests/unit/storage/test_storage.py`：二进制 artifact 推广、路径安全、manifest。
- `backend/tests/unit/api/test_artifacts.py`：`.docx` 下载、未登记文件 404。
- `backend/tests/unit/runner/test_core.py`：交付文件缺失不能 complete。
- `backend/tests/unit/api/test_tasks.py`：API state 可见失败/修正提示。

### 集成测试

- `frontend/e2e-playwright/test_task_log_artifact_delivery.spec.mjs`：真实浏览器闭环覆盖大日志、下载、缺失失败。
- 邻近回归：`test_progress_log_disclosure.spec.mjs` 或 `test_runtime_contracts.spec.mjs`。

### 边界情况

- 单 run 0 条日志。
- 单 run 2000+ status/thinking/tool 事件。
- 多 run 同名 artifact。
- `.docx`、`.html`、`.json`、未知后缀 artifact。
- 用户要求文件但模型只返回摘要。
- 模型声称 `/root/foo.docx` 已保存，但 task workspace 中没有该文件。
- task workspace 中存在同名内部草稿，但不符合交付文件策略。
- artifact URL 外部 origin 或错误 task id 仍被前端拒绝。

---

## 验证命令

### 级别 1：语法与风格

```bash
cd backend
uv run ruff check .
uv run mypy app tests
```

```bash
cd frontend
npm run typecheck
npm run lint
```

### 级别 2：单元测试

```bash
cd backend
uv run pytest tests/unit/storage/test_storage.py tests/unit/api/test_artifacts.py tests/unit/runner/test_core.py tests/unit/api/test_tasks.py -q
```

```bash
cd frontend
npm test -- tests/workspace/test_workspace_view.test.ts tests/workspace/test_task_conversation_scroll.test.ts tests/state/test_task_state.test.ts tests/workspace/test_task_workspace.test.ts
```

### 级别 3：完整本地回归

```bash
cd backend
uv run pytest
uv run ruff check .
uv run mypy app tests
```

```bash
cd frontend
npm run typecheck
npm test
npm run lint
npm run build
```

### 级别 4：浏览器验收

```bash
cd frontend
MYAGENT_E2E_BASE_URL=http://127.0.0.1:3001 \
MYAGENT_E2E_API_URL=http://127.0.0.1:8001 \
MYAGENT_E2E_EVIDENCE_DIR=./e2e-playwright/e2e-YYYYMMDDHHMMSS/task-log-artifact-delivery \
npx playwright test e2e-playwright/test_task_log_artifact_delivery.spec.mjs --reporter=line
```

邻近回归：

```bash
cd frontend
MYAGENT_E2E_BASE_URL=http://127.0.0.1:3001 \
MYAGENT_E2E_API_URL=http://127.0.0.1:8001 \
MYAGENT_E2E_EVIDENCE_DIR=./e2e-playwright/e2e-YYYYMMDDHHMMSS/progress-log-disclosure \
npx playwright test e2e-playwright/test_progress_log_disclosure.spec.mjs --reporter=line
```

### 级别 5：空白检查

```bash
git diff --check
```

---

## 验收标准

- [ ] 主页面默认不渲染完整 run 诊断 JSON。
- [ ] 2000+ 事件任务不会创建 2000+ 可展开日志行。
- [ ] 完整日志可下载，且内容为当前 run 的 JSONL。
- [ ] 用户要求生成文件时，真实文件作为 artifact 卡片显示并可下载。
- [ ] AI 声称已生成文件但文件缺失时，任务不是 success complete。
- [ ] 缺失文件提示可见且明确。
- [ ] 后端、前端、浏览器 E2E 和 `git diff --check` 全部通过。
- [ ] `asset/deepagents_platform_knowledge_pack.md` 已同步稳定规则。

---

## 完成检查清单

- [ ] 所有任务均已按顺序完成。
- [ ] 每个任务的验证都已立即通过。
- [ ] 所有验证命令都已成功执行。
- [ ] 完整测试套件通过。
- [ ] 无 lint 或类型检查错误。
- [ ] 浏览器验收确认功能可用。
- [ ] 验收标准全部满足。
- [ ] 已完成知识包同步。

---

## 备注

信心分数：8/10。主要风险在 runner 如何可靠区分“交付文件”和“内部中间文件”，以及模型最终回复中的文件路径可能是幻觉。实施时应保持策略保守：只登记 task workspace 内真实存在且符合交付规则的文件；缺失时宁可失败并提示修正，也不要展示不可下载路径。
