# MyAgent 代理导航地图

本文件是仓库级导航入口，适用于整个 `/mnt/d/AgentProject/MyAgent`。它只说明先读哪里、边界在哪里、哪些规则需要同步维护；系统总览放在 `ARCHITECTURE.md`，跨系统接口放在 `INTERFACES.md`，子项目事实放在 `backend/.planning/codebase/` 和 `frontend/.planning/codebase/`。

## 仓库定位

MyAgent 是一个本地优先的 AI 智能体工作区，用于基于 Markdown/JSON/Office 文档的任务式分析和报告生成。

- `backend/`：FastAPI 后端、DeepAgents/LangGraph 运行时、Postgres 状态、上传/产物文件、长期记忆和 provider 集成。
- `frontend/`：Next.js app router 前端、浏览器聊天工作区、REST/SSE/API 适配、状态标准化和产物打开体验。
- `asset/`：长期主题知识包，保存稳定业务规则、运行边界和回归风险。
- `backend/.planning/codebase/`：后端当前事实层，由 `$gsd-map-codebase` 生成。
- `frontend/.planning/codebase/`：前端当前事实层，由 `$gsd-map-codebase` 生成。

## 文档分层

- `AGENTS.md`：全局索引、阅读顺序、执行边界和维护规则。
- `ARCHITECTURE.md`：系统边界、子系统职责、理解路径和稳定目录职责。
- `INTERFACES.md`：前后端、事件流、上传/产物、认证、provider 和存储的跨系统接口边界。
- `backend/.planning/codebase/`：后端架构、结构、技术栈、集成、测试、约定和风险事实。
- `frontend/.planning/codebase/`：前端架构、结构、技术栈、集成、测试、约定和风险事实。
- `asset/`：长期知识包。影响稳定业务规则、输入输出、用户路径、运行边界或测试入口时优先同步。
- `DESIGN.md`：外部视觉系统参考。涉及前端视觉时可读，但项目真实样式事实仍以 `frontend/app/globals.css` 和前端 codebase map 为准。

不要把 `.planning/codebase/` 的实现细节复制进 `AGENTS.md`；需要事实时直接读取对应事实文档。

## 推荐阅读顺序

通用上手：

1. `AGENTS.md`
2. `ARCHITECTURE.md`
3. `INTERFACES.md`
4. `backend/.planning/codebase/ARCHITECTURE.md`
5. `frontend/.planning/codebase/ARCHITECTURE.md`
6. 相关子项目的 `STRUCTURE.md`、`TESTING.md` 和 `CONCERNS.md`

后端任务、API、存储、权限、模型、记忆或 runner：

1. `ARCHITECTURE.md`
2. `INTERFACES.md`
3. `backend/.planning/codebase/ARCHITECTURE.md`
4. `backend/.planning/codebase/INTEGRATIONS.md`
5. `backend/.planning/codebase/TESTING.md`
6. `backend/app/` 和 `backend/tests/`

前端工作区、状态转换、URL 映射、上传、产物打开或 SSE：

1. `INTERFACES.md`
2. `frontend/.planning/codebase/ARCHITECTURE.md`
3. `frontend/.planning/codebase/INTEGRATIONS.md`
4. `frontend/.planning/codebase/CONVENTIONS.md`
5. `frontend/tests/` 和 `frontend/e2e-playwright/`

前端视觉、样式、布局、动效、菜单、弹窗、按钮或表单外观：

1. `DESIGN.md`
2. `frontend/.planning/codebase/CONVENTIONS.md`
3. `frontend/.planning/codebase/STRUCTURE.md`
4. `frontend/app/globals.css`
5. 相关组件、单测和浏览器 E2E

招投标分析、文档分类、证据归一化或报告生成：

1. `asset/bid_analysis_workflow_knowledge_pack.md`
2. `asset/tender_workflow_breakdown.md`
3. `asset/deepagents_platform_knowledge_pack.md`
4. `backend/.planning/codebase/ARCHITECTURE.md`
5. 相关后端实现和测试

## 子系统边界

- 后端负责 HTTP API、任务生命周期、runner 调度、Postgres 权威状态、事件日志、上传资源、产物下载、模型 provider、搜索、长期记忆和安全边界。
- 前端负责浏览器工作区、状态转换、REST/SSE 调用、上传交互、产物打开下载、日志展示和视觉体验。
- 前端运行时不直接访问模型 provider、Postgres、Qdrant、SearXNG 或后端私密配置。
- 前后端字段边界是后端 `snake_case`、前端 `camelCase`；字段转换集中在 `frontend/app/task-state.ts`。
- Postgres 是任务、运行、消息、事件日志和长期记忆元数据的权威存储；`backend/storage/sessions/` 默认保存上传和产物文件。
- 当前 runner 是进程内单 worker 模型，不允许绕过 `WEB_CONCURRENCY`、`UVICORN_WORKERS`、`GUNICORN_WORKERS` 的单进程保护。
- SSE 是持久化事件的投影，不是状态来源；恢复游标只作为客户端提示，不能替代后端有序事件日志。

## 必守执行边界

- 搜索优先用 `rg` 或 `rg --files`。
- 只改文档时至少运行 `git diff --check`，并说明未运行代码测试和未做 E2E 截图验收的理由。
- bug 修复、功能新增、接口调整、状态流调整、交互优化或其他行为变更，必须同步代码、测试、浏览器端 E2E、截图证据和知识包；单测或接口自测不能替代浏览器 E2E。
- 行为变更的 E2E 必须基于实际前后端服务，截图留存在 `frontend/e2e-playwright/e2e-YYYYMMDDHHMMSS/`，截图证据不提交 git。
- 涉及前端视觉时先读 `DESIGN.md` 和前端 codebase map，并保持现有 CSS 变量、布局边界和组件约定一致。
- 本地开发或 E2E 默认优先复用用户已运行的 `3001` 和 `8001` 服务；不得为了干净环境直接 kill 或重启用户服务。
- provider 密钥、数据库 URL、Qdrant URL、embedding 凭据和客户资料只能放在后端运行环境或被忽略的本地 env 文件中，不能写入文档、测试夹具、截图或知识包。
- `NEXT_PUBLIC_*` 会暴露给浏览器，不能包含 provider 密钥、客户数据或私密样例。
- 若执行提交、推送、创建 PR、更新 PR 或合并 PR，并且依赖远程检查结果，必须等待远程 CI/checks 结束并确认通过后再声明完成。

## 本地代理工具

- `.agents/` 和 `scripts/ralph/` 是 `$auto-coding-init` 复制的本地 Auto-Coding 工具目录，必须保持在 `.gitignore` 中。
- 不要把 `.agents/` 中的模板内容当作产品实现事实；产品事实仍以 `ARCHITECTURE.md`、`INTERFACES.md`、子项目 `.planning/codebase/` 和 `asset/` 为准。
- 刷新本文件时应融合仍正确的仓库规则，删除过时命令、路径和假设。

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

浏览器验收：

```bash
cd frontend
npm run e2e:runtime-contracts
```

文档和空白检查：

```bash
git diff --check
```

本地开发默认端口：后端 `8001`，前端 `3001`。脚本入口见 `scripts/start-dev-wsl.ps1`、`scripts/dev-terminal-runner.sh`、`scripts/stop-dev-ports.sh`。

## 知识回写

- 平台级任务 API、状态机、runner、事件日志、产物、上传、前端任务流程、模型 provider、访问令牌、CORS、本地优先安全边界、上传/JSON 限制或测试布局：优先更新 `asset/deepagents_platform_knowledge_pack.md`。
- 招投标分析流程、Markdown/JSON/Office 文档分类、围串标分析类别、sub-agent 分派、证据归一化或报告生成：优先更新 `asset/bid_analysis_workflow_knowledge_pack.md`，必要时同步 `asset/deepagents_platform_knowledge_pack.md`。
- 本地启动脚本、WSL 端口清理或开发终端启动方式：通常更新 `README.md` 和本文件；只有形成稳定子系统时才新增知识包。

## 维护规则

- 根 `AGENTS.md` 保持导航型，不承载接口明细、低层实现和频繁变化目录说明。
- 系统边界变化时先更新 `ARCHITECTURE.md` 和 `INTERFACES.md`，再同步本文件入口。
- 子系统事实变化时优先刷新对应的 `backend/.planning/codebase/` 或 `frontend/.planning/codebase/`，不要手工复制事实摘要到根文档。
- 新增稳定业务规则或运行边界时同步 `asset/` 知识包；临时排障时间线和一次性脚本路径不进入长期文档。
- `.agents/` 和 `scripts/ralph/` 保持 ignored；除非任务明确要求初始化或维护本地 agent tooling，否则不要手改其中内容。
