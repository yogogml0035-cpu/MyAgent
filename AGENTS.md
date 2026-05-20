# MyAgent Agent Map

本文件是仓库级导航入口，适用于整个 `/mnt/d/AgentProject/MyAgent`。它负责说明先读哪里、边界在哪里、哪些规则需要同步维护；系统说明放在 `ARCHITECTURE.md` 和 `INTERFACES.md`，实现事实放在 `backend/.planning/codebase/`、`frontend/.planning/codebase/` 和 `asset/`。

## 仓库定位

MyAgent 是一个本地优先的 DeepAgents 任务工作台：

- `backend/`：FastAPI 后端、DeepAgents 运行时、Postgres 任务存储、上传和产物文件管理。
- `frontend/`：Next.js app router 前端、聊天工作区、任务状态编排、REST/SSE/API 适配。
- `asset/`：长期主题知识包，保存稳定业务规则、运行边界和回归风险。
- `backend/.planning/codebase/`：后端代码事实层，由 `$gsd-map-codebase` 生成。
- `frontend/.planning/codebase/`：前端代码事实层，由 `$gsd-map-codebase` 生成。
- `.planning/codebase/`：仓库级历史事实层。需要全仓旧事实时可参考；后续规划应优先读取子项目级事实文档。

## 技术栈速览

| 子系统 | 主要技术 | 验证入口 |
| --- | --- | --- |
| 后端 | Python 3.11、FastAPI、Pydantic、DeepAgents、LangGraph、Postgres、Qdrant、DashScope-compatible embeddings、SearXNG | `cd backend && uv run pytest && uv run ruff check . && uv run mypy app tests` |
| 前端 | Next.js 15 app router、React 19、TypeScript 5、browser REST/SSE/blob adapters | `cd frontend && npm run typecheck && npm test && npm run lint && npm run build` |
| 浏览器验收 | Playwright，基于实际前后端服务和截图证据 | `cd frontend && npm run e2e:runtime-contracts` 或按场景运行 spec |

## 文档分层

- `AGENTS.md`：全局索引、阅读顺序、维护规则和最低执行边界。
- `ARCHITECTURE.md`：系统边界、子系统职责、理解路径和稳定目录职责。
- `INTERFACES.md`：前后端、存储、外部服务、运行脚本和 CI 的跨系统接口说明。
- `backend/.planning/codebase/`：后端当前事实，包含架构、结构、技术栈、集成、测试、约定和风险。
- `frontend/.planning/codebase/`：前端当前事实，包含架构、结构、技术栈、集成、测试、约定和风险。
- `asset/`：长期主题知识包。影响稳定业务规则、输入输出、用户路径、运行边界或测试入口时，优先更新对应知识包。
- `DESIGN.md`：前端视觉和交互调整的必读设计依据。

不要把 `.planning/codebase/` 的实现细节复制进 `AGENTS.md`；需要事实时直接读取对应事实文档。

## 本地代理工具

- `.agents/` 和 `scripts/ralph/` 是 `$auto-coding-init` 复制的本地 Auto-Coding 工具目录，必须保持在 `.gitignore` 中。
- `.agents/skills/create-rules/SKILL.md` 是刷新本文件的本地规则入口；使用时应融合现有仍正确的仓库规则，删除过时命令、路径和假设。
- 不要把 `.agents/` 中的模板内容当作产品实现事实；产品事实仍以 `ARCHITECTURE.md`、`INTERFACES.md`、子项目 `.planning/codebase/` 和 `asset/` 为准。

## 推荐阅读顺序

通用上手：

1. `AGENTS.md`
2. `ARCHITECTURE.md`
3. `INTERFACES.md`
4. `backend/.planning/codebase/ARCHITECTURE.md`
5. `frontend/.planning/codebase/ARCHITECTURE.md`
6. 相关子项目的 `STRUCTURE.md` 和 `CONCERNS.md`

后端任务、API、存储、权限、模型或运行时：

1. `ARCHITECTURE.md`
2. `INTERFACES.md`
3. `backend/.planning/codebase/ARCHITECTURE.md`
4. `backend/.planning/codebase/STACK.md`
5. `backend/.planning/codebase/INTEGRATIONS.md`
6. `backend/app/` 和 `backend/tests/`

前端表单、任务状态、URL 映射、产物打开或轮询：

1. `INTERFACES.md`
2. `frontend/.planning/codebase/STRUCTURE.md`
3. `frontend/.planning/codebase/CONVENTIONS.md`
4. `frontend/app/page.tsx`
5. `frontend/hooks/use-task-workspace.ts`
6. `frontend/lib/task-api.ts`
7. `frontend/app/task-state.ts`
8. `frontend/tests/`

前端视觉、样式、布局、动效、菜单、弹窗、按钮或表单外观：

1. `DESIGN.md`
2. `frontend/.planning/codebase/CONVENTIONS.md`
3. `frontend/app/globals.css`
4. 相关组件和测试

招投标分析、文档分类、证据归一化或报告生成：

1. `asset/bid_analysis_workflow_knowledge_pack.md`
2. `asset/tender_workflow_breakdown.md`
3. `asset/deepagents_platform_knowledge_pack.md`
4. 相关后端实现和测试

## 子系统边界

- 后端负责 HTTP API、任务生命周期、runner 调度、Postgres 事实状态、事件日志、上传资源、产物下载、模型 Provider、长期记忆和安全边界。
- 前端负责浏览器工作区、状态转换、REST/SSE 调用、上传交互、产物打开下载、日志展示和视觉体验。
- 前后端字段边界是后端 `snake_case`、前端 `camelCase`。字段转换集中在 `frontend/app/task-state.ts`。
- Postgres 是任务、运行、消息、事件日志和长期记忆的权威存储；`backend/storage/sessions/` 默认保存上传和产物文件。
- 当前 runner 是进程内单 worker 模型，不允许绕过 `WEB_CONCURRENCY`、`UVICORN_WORKERS`、`GUNICORN_WORKERS` 的单进程保护。
- SSE 是持久化事件的投影，不是状态来源；恢复游标只作为客户端提示，不能替代后端有序事件日志。

## 必守执行边界

- 搜索优先用 `rg` 或 `rg --files`。
- 只改文档时至少运行 `git diff --check`，并说明未运行代码测试和未做 E2E 截图验收的理由。
- bug 修复、功能新增、接口调整、状态流调整、交互优化或其他行为变更，必须同步代码、测试、浏览器端 E2E、截图证据和知识包；单测或接口自测不能替代浏览器 E2E。
- 行为变更的 E2E 必须基于实际前后端服务，截图留存在 `frontend/e2e-playwright/e2e-YYYYMMDDHHMMSS/`，截图证据不提交 git。
- 涉及前端视觉时必须先读 `DESIGN.md`，并保持暖色画布、珊瑚色主色、字体、圆角、间距和现有 CSS 变量一致。
- 本地开发或 E2E 默认优先复用用户已运行的 `3001` 和 `8001` 服务；不得为了干净环境直接 kill 或重启用户服务。
- provider 密钥、数据库 URL、Qdrant URL、embedding 凭据和客户资料只能放在后端运行环境或被忽略的本地 env 文件中，不能写入文档、测试夹具或知识包。
- `NEXT_PUBLIC_*` 会暴露给浏览器，不能包含 provider 密钥、客户数据或私密样例。
- 若执行提交、推送、创建 PR、更新 PR 或合并 PR，并且依赖远程检查结果，必须等待远程 CI/checks 结束并确认通过后再声明完成。

## 知识回写

- 平台级任务 API、状态机、runner、事件日志、产物、上传、前端任务流程、模型 Provider、访问令牌、CORS、本地优先安全边界、上传/JSON 限制或测试布局：优先更新 `asset/deepagents_platform_knowledge_pack.md`。
- 招投标分析流程、Markdown/JSON 文档分类、围串标分析类别、sub-agent 分派、证据归一化或报告生成：优先更新 `asset/bid_analysis_workflow_knowledge_pack.md`，必要时同步 `asset/deepagents_platform_knowledge_pack.md`。
- 本地启动脚本、WSL 端口清理或开发终端启动方式：通常更新 `README.md` 和本文件；只有形成稳定子系统时才新增知识包。

## 运行入口

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

文档和空白检查：

```bash
git diff --check
```

本地开发默认端口：后端 `8001`，前端 `3001`。脚本入口见 `scripts/start-dev-wsl.ps1`、`scripts/dev-terminal-runner.sh`、`scripts/stop-dev-ports.sh`。

## 维护规则

- 根 `AGENTS.md` 保持导航型，不承载接口明细、低层实现和频繁变化目录说明。
- `.agents/` 和 `scripts/ralph/` 保持 ignored；除非任务明确要求初始化或维护本地 agent tooling，否则不要手改其中内容。
- 系统边界变化时先更新 `ARCHITECTURE.md` 和 `INTERFACES.md`，再同步本文件入口。
- 子系统事实变化时优先刷新对应的 `backend/.planning/codebase/` 或 `frontend/.planning/codebase/`，不要手工复制事实摘要到根文档。
- 新增稳定业务规则或运行边界时同步 `asset/` 知识包；临时排障时间线和一次性脚本路径不进入长期文档。
