# MyAgent System Map

本地图帮助后续 AI 快速理解 MyAgent 的跨子项目结构、接口边界和修改前阅读路线。它综合根级文档、前后端 `.planning/codebase/` 事实层和 `asset/` 长期知识包；不替代这些源文档，也不承载底层实现细节。

## 系统目的和仓库形态

MyAgent 是一个本地优先的 AI 智能体工作区，用于围绕上传文档发起任务式分析、观察 agent 执行过程、查看最终回答和产物。当前仓库是前后端合并目录：

| 子项目 | 职责 | 事实入口 |
| --- | --- | --- |
| `backend/` | FastAPI API、DeepAgents/LangGraph runner、Postgres 权威状态、上传/产物文件、长期记忆、provider/search/storage 集成 | `backend/.planning/codebase/` |
| `frontend/` | Next.js 单页工作区、浏览器任务状态、REST/SSE/blob 适配、上传交互、日志/产物展示 | `frontend/.planning/codebase/` |
| `asset/` | 长期业务和平台知识包，保存稳定领域规则、运行边界、回归风险 | `asset/*.md` |
| 根文档 | 仓库导航、系统边界、跨系统接口 | `AGENTS.md`, `ARCHITECTURE.md`, `INTERFACES.md` |

当前已确认的运行形态偏本地同机：后端默认端口 `8001`，前端默认端口 `3001`，Postgres/Qdrant/SearXNG/模型 provider 由本地或外部服务提供。仓库内当前源文档未确认 Docker、云托管、OAuth、集中 CI/CD 或多 worker 部署方案。

## 跨子项目调用链和数据流

### 主任务路径

```text
Browser UI
  -> frontend/components/chat/TaskWorkspace.tsx
  -> frontend/hooks/use-task-workspace.ts
  -> frontend/lib/task-api.ts
  -> backend/app/api/tasks.py
  -> backend/app/storage.py
  -> backend/app/runner/core.py
  -> backend/app/agent/factory.py
  -> DeepAgents/LangGraph + model/tools/resources
  -> backend/app/streaming/* + backend/app/storage.py
  -> frontend SSE/event refresh
  -> conversation stream, logs, artifacts
```

已确认事实：

- 后端是任务、run、消息、事件、长期记忆元数据和上传/产物文件的权威边界。
- 前端只保存浏览器侧投影状态，所有任务状态来自后端 HTTP/SSE。
- `frontend/lib/task-api.ts` 是浏览器到后端的传输边界；组件不应直接散落 task API `fetch`。
- `frontend/app/task-state.ts` 负责把后端 payload 标准化为前端类型；后端 `snake_case` 和前端 `camelCase` 在这里相遇。
- SSE 是后端持久化事件的投影，不是权威状态来源；失败或断线后前端需要通过事件/任务刷新恢复。

### 上传和资源工具路径

```text
ChatComposer file input
  -> frontend/app/file-upload.ts
  -> POST /api/tasks/{task_id}/files
  -> backend/app/api/files.py
  -> backend/app/storage.py
  -> task uploads directory
  -> runner resource manifest
  -> backend/app/execution/resources.py tools
```

当前支持的上传格式以代码和事实层为准，已记录为 `.md`, `.json`, `.txt`, `.docx`, `.xlsx`, `.xlsm`。浏览器端只做 UX 层筛选，后端校验仍是安全和一致性的权威。上传内容不会自动塞入模型上下文；agent 通过资源工具按需 list/inspect/read。

### 产物下载和 HTML 预览路径

```text
backend run artifact registration
  -> task state artifact metadata
  -> frontend/app/task-state.ts buildArtifactRequest
  -> frontend/lib/task-api.ts fetchArtifactBlob
  -> frontend/hooks/use-task-workspace.ts open/download
```

已确认安全边界：

- 前端必须先验证 artifact URL 属于当前 API origin 和当前 task artifact route，才能附加浏览器 token。
- HTML 产物通过沙盒 iframe 预览，不应直接把 HTML 注入主页面或 top-level 跳转到同源 blob。
- 后端仍必须通过 storage artifact resolver 做路径校验；前端 allowlist 只是额外保护。

### 长期记忆、搜索和 provider 边界

```text
TaskRunner
  -> ConversationContextBuilder
  -> AgentMemoryService
  -> Postgres canonical memory rows
  -> DashScope-compatible embeddings
  -> Qdrant semantic index
  -> DeepSeek chat model
  -> optional SearXNG search tool
```

前端运行时不直接访问 DeepSeek、DashScope、Qdrant、Postgres 或 SearXNG。浏览器只发送后端注册的安全模型 ID 和可选浏览器访问 token。provider key、数据库 URL、Qdrant URL、embedding 凭据和客户资料必须留在后端环境或 ignored 本地 env 文件。

## 后端到前端的接口边界

主要后端 API 由 `frontend/lib/task-api.ts` 调用，根级接口说明见 `INTERFACES.md`。

| 边界 | 后端入口 | 前端入口 | 修改时优先阅读 |
| --- | --- | --- | --- |
| 模型选项 | `backend/app/api/models.py` | `fetchModelOptions` in `frontend/lib/task-api.ts` | `backend/.planning/codebase/INTEGRATIONS.md`, `frontend/.planning/codebase/INTEGRATIONS.md` |
| 技能选项 | `backend/app/api/skills.py` | `fetchSkillOptions` in `frontend/lib/task-api.ts` | `asset/deepagents_platform_knowledge_pack.md`, 前后端 `INTEGRATIONS.md` |
| 任务 CRUD | `backend/app/api/tasks.py` | task helpers in `frontend/lib/task-api.ts` | `INTERFACES.md`, 前后端 `ARCHITECTURE.md` |
| 消息/run 启动 | `backend/app/api/tasks.py`, `backend/app/runner/core.py` | `postTaskMessage`, `use-task-workspace.ts` | backend `ARCHITECTURE.md`, frontend `ARCHITECTURE.md` |
| 事件轮询 | `GET /api/tasks/{id}/events` | `fetchTaskEvents` | `asset/deepagents_platform_knowledge_pack.md` |
| SSE | `backend/app/api/streaming.py` | `createTaskEventSource` | 前后端 `INTEGRATIONS.md`, `INTERFACES.md` |
| 上传 | `backend/app/api/files.py`, `backend/app/storage.py` | `uploadTaskFiles` | 前后端 `TESTING.md`, `asset/deepagents_platform_knowledge_pack.md` |
| 产物下载 | `backend/app/api/artifacts.py` | `fetchArtifactBlob`, `buildArtifactRequest` | `INTERFACES.md`, frontend `CONCERNS.md` |
| 认证/CORS | `backend/app/main.py` | browser token config in `frontend/lib/task-api.ts` | `INTERFACES.md`, 前后端 `INTEGRATIONS.md` |

跨接口改动的最低阅读路线：

1. `INTERFACES.md`
2. `backend/app/schemas.py`
3. `backend/app/api/`
4. `frontend/app/task-state.ts`
5. `frontend/lib/task-api.ts`
6. `frontend/tests/state/`
7. `frontend/e2e-playwright/`

## 依赖和归属规则

已确认事实：

- `backend/` 可以依赖外部 provider、Postgres、Qdrant、SearXNG 和本地 filesystem。
- `frontend/` 只依赖 MyAgent 后端和浏览器 API。
- `asset/` 不参与运行时 import，是长期业务/平台约束输入。
- `.agents/` 和 `scripts/ralph/` 是本地 agent tooling，不是产品实现事实来源。

操作建议：

- 新后端行为先落在后端事实层，再把跨系统影响同步到 `INTERFACES.md` 和本地图。
- 新前端行为如果改变 API payload、SSE 解释、上传、产物或 token 行为，必须同步检查后端 API 和接口文档。
- 业务规则和稳定回归风险进入 `asset/`，不要只写在一次性任务文档里。
- 根级 `AGENTS.md` 保持导航用途，系统解释放 `ARCHITECTURE.md`，跨系统契约放 `INTERFACES.md`，内部事实放各子项目 `.planning/codebase/`。

## 按任务分类的阅读指南

### 后端业务、API、存储、runner 修改

先读：

1. `AGENTS.md`
2. `ARCHITECTURE.md`
3. `INTERFACES.md`
4. `backend/.planning/codebase/ARCHITECTURE.md`
5. `backend/.planning/codebase/INTEGRATIONS.md`
6. `backend/.planning/codebase/TESTING.md`
7. `backend/.planning/codebase/CONCERNS.md`

常见验证入口：

```bash
cd backend
uv run pytest
uv run ruff check .
uv run mypy app tests
```

高风险点：

- `backend/app/storage.py` 责任很重，涉及任务、事件、上传、产物、工具缓存、agent store 和长期记忆。
- `TaskRunner` 是进程内 active-run owner，多 worker/横向扩展不能只改配置。
- SSE 和事件读取要保持有序、可恢复，未知 cursor 应 fail open。
- provider key、数据库 URL、Qdrant URL 等不能进入文档、夹具、事件展示或前端公开配置。

### 前端工作区、状态、上传、产物、SSE 修改

先读：

1. `INTERFACES.md`
2. `frontend/.planning/codebase/ARCHITECTURE.md`
3. `frontend/.planning/codebase/INTEGRATIONS.md`
4. `frontend/.planning/codebase/CONVENTIONS.md`
5. `frontend/.planning/codebase/TESTING.md`
6. `frontend/.planning/codebase/CONCERNS.md`

常见验证入口：

```bash
cd frontend
npm run typecheck
npm test
npm run lint
npm run build
```

行为变更还需要浏览器验收，优先使用已有 Playwright specs 或补充对应场景。

高风险点：

- `frontend/hooks/use-task-workspace.ts` 是工作区控制器，易把提交、切换、上传、SSE、产物和历史 mutation 状态耦合在一起。
- `frontend/app/task-state.ts` 是后端 payload 和前端类型边界，改字段必须配套测试。
- artifact fetch 必须经过 `buildArtifactRequest`，避免 token 泄漏到不可信 URL。
- `NEXT_PUBLIC_*` 全都会暴露给浏览器，不能放 provider secret 或私密客户数据。

### 跨系统接口修改

先读：

1. `INTERFACES.md`
2. `backend/.planning/codebase/INTEGRATIONS.md`
3. `frontend/.planning/codebase/INTEGRATIONS.md`
4. `backend/.planning/codebase/TESTING.md`
5. `frontend/.planning/codebase/TESTING.md`
6. `asset/deepagents_platform_knowledge_pack.md`

检查清单：

- 后端 schema、API 路由、storage shape 是否一致。
- 前端 normalizer、transport adapter、UI view model 是否一致。
- SSE 事件和 HTTP polling fallback 是否都覆盖。
- 鉴权、CORS、token query/header 边界是否仍安全。
- E2E 是否覆盖真实前后端合同路径，而不是只测 Node helper。

### 视觉或 UX 修改

先读：

1. `DESIGN.md`
2. `frontend/.planning/codebase/CONVENTIONS.md`
3. `frontend/.planning/codebase/STRUCTURE.md`
4. `frontend/app/globals.css`
5. `frontend/components/chat/`
6. 相关 `frontend/tests/` 和 `frontend/e2e-playwright/` spec

注意：

- `DESIGN.md` 是外部视觉系统参考，不是代码事实；实际组件和 token 以 `frontend/app/globals.css` 为准。
- 自定义菜单/listbox 要验证键盘路径、焦点、Escape、移动端宽度和隐藏 hover 控件。
- 视觉变更需要浏览器截图证据，证据目录不提交。

### 领域流程或报告生成修改

先读：

1. `asset/bid_analysis_workflow_knowledge_pack.md`
2. `asset/tender_workflow_breakdown.md`
3. `asset/deepagents_platform_knowledge_pack.md`
4. `backend/.planning/codebase/ARCHITECTURE.md`
5. `frontend/.planning/codebase/ARCHITECTURE.md`

当前知识包强调：

- 招投标/PDF 比对应是阶段流水线，不是一次性自由聊天。
- PDF ingest、证据锚点、图像预核验、compare JSON/HTML 应保持 run-scoped、stage-aware。
- AI 负责页码、条目、短摘录和 match hints；后端 resolver 负责基于 layout/OCR 坐标生成高亮图或 fallback。
- 人工复核应作为覆盖层保存，不应覆盖 AI baseline。

## 集成风险检查清单

- API 字段变更是否同时更新 `backend/app/schemas.py`、前端 normalizer、tests 和接口文档。
- 新事件类型是否能被后端 event converter、SSE endpoint、前端 log merge 和 diagnostics copy 正确处理。
- 新上传格式是否有后端校验、资源工具读取策略、大小/页数/解析预算和 E2E。
- 新 artifact 类型是否有 run-scoped 注册、后端 resolver、前端 URL allowlist、预览/下载测试。
- 新 provider 或工具是否只在后端配置，且不把 secret 暴露给 `/api/models`、前端 bundle、日志或文档。
- 新长期记忆字段是否避免把 reasoning、raw diagnostics、客户全文、tool result payload 写进普通会话或 Qdrant。
- 新菜单、弹窗、选择器是否有键盘、焦点、移动端和截图验收。
- 多任务并行修改是否保持单 task 单 run、跨 task 互不污染、run diagnostics 不混流。
- 文档变更是否通过 `git diff --check`，行为变更是否跑对应代码测试和浏览器 E2E。

## 验证入口

后端：

```bash
cd backend
uv run pytest
uv run ruff check .
uv run mypy app tests
```

前端：

```bash
cd frontend
npm run typecheck
npm test
npm run lint
npm run build
```

浏览器合同验收：

```bash
cd frontend
npm run e2e:runtime-contracts
```

文档空白检查：

```bash
git diff --check
```

## 源文档索引

根级文档：

- `AGENTS.md`
- `ARCHITECTURE.md`
- `INTERFACES.md`
- `DESIGN.md`
- `README.md`

后端事实层：

- `backend/.planning/codebase/ARCHITECTURE.md`
- `backend/.planning/codebase/INTEGRATIONS.md`
- `backend/.planning/codebase/STRUCTURE.md`
- `backend/.planning/codebase/TESTING.md`
- `backend/.planning/codebase/CONVENTIONS.md`
- `backend/.planning/codebase/CONCERNS.md`
- `backend/.planning/codebase/STACK.md`

前端事实层：

- `frontend/.planning/codebase/ARCHITECTURE.md`
- `frontend/.planning/codebase/INTEGRATIONS.md`
- `frontend/.planning/codebase/STRUCTURE.md`
- `frontend/.planning/codebase/TESTING.md`
- `frontend/.planning/codebase/CONVENTIONS.md`
- `frontend/.planning/codebase/CONCERNS.md`
- `frontend/.planning/codebase/STACK.md`

长期知识包：

- `asset/deepagents_platform_knowledge_pack.md`
- `asset/bid_analysis_workflow_knowledge_pack.md`
- `asset/tender_workflow_breakdown.md`

## 维护规则

- 当 `backend/.planning/codebase/` 或 `frontend/.planning/codebase/` 刷新后，如果跨系统边界或阅读路线变化，同步刷新本文件。
- 当 `ARCHITECTURE.md` 或 `INTERFACES.md` 改变系统边界时，同步检查本文件是否过时。
- 不把 `.agents/`、`scripts/ralph/`、`.next/`、`.next-dev/`、`node_modules/`、测试证据目录或本地 env 文件当作产品事实来源。
- 证据不足时保留“当前源文档未确认”表述，不把推断写成硬规则。
