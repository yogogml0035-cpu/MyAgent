# 前端代码结构

**分析日期：** 2026-05-24

## 目录布局

```text
frontend/
|-- app/                         # Next route、全局 CSS、纯状态/视图 helper
|   |-- layout.tsx               # Root app shell 和 metadata
|   |-- page.tsx                 # 根路由，委托 TaskWorkspace
|   |-- globals.css              # 全局 token 和工作区样式
|   |-- task-state.ts            # 后端 payload 标准化和前端状态合同
|   |-- workspace-view.ts        # 会话/历史/进度日志 view model
|   |-- file-upload.ts           # 上传文件规则
|   |-- model-ui.ts              # 模型展示元数据
|   `-- skill-selection.ts       # 技能标准化和 slash picker helper
|-- components/
|   `-- chat/                    # 聊天工作区组件
|-- hooks/                       # React 控制器 hooks
|-- lib/                         # 浏览器传输/API adapter
|-- tests/                       # Node test runner 单测和边界测试
|-- e2e-playwright/              # Playwright specs 和本地证据目录
|-- .planning/codebase/          # 前端事实文档
|-- package.json                 # scripts 和依赖
|-- package-lock.json            # npm lockfile
|-- next.config.mjs              # Next dev/build 配置
|-- tsconfig.json                # TypeScript 配置
|-- eslint.config.mjs            # ESLint flat config
|-- .env.example                 # 浏览器公开 env 示例
`-- README.md                    # 前端 setup 和 E2E 指南
```

## 目录职责

- `frontend/app/`：Next shell、根路由、全局样式、纯状态/视图/helper 模块。
- `frontend/components/chat/`：聊天工作区 React 组件，包括 sidebar、conversation、composer、avatar、typewriter。
- `frontend/hooks/`：跨组件状态机和浏览器副作用，当前核心是 `use-task-workspace.ts`。
- `frontend/lib/`：后端 REST/SSE/blob 传输 adapter。
- `frontend/tests/`：Node test-runner 单测和架构边界测试。
- `frontend/e2e-playwright/`：浏览器验收 specs 和未提交的截图/证据输出。
- `frontend/.planning/codebase/`：本文件所在的前端事实层。
- root config：package scripts、Next distDir、TypeScript、ESLint、公开 env 示例和 README。

## 关键文件

### 入口

- `frontend/app/layout.tsx`：root layout、metadata、icon、global CSS。
- `frontend/app/page.tsx`：根 `/` route，渲染 `TaskWorkspace`。
- `frontend/components/chat/TaskWorkspace.tsx`：client workspace composition boundary。
- `frontend/hooks/use-task-workspace.ts`：工作区运行时状态和动作边界。
- `frontend/lib/task-api.ts`：后端 API/SSE/blob 边界。

### 配置

- `frontend/package.json`：dev、build、start、typecheck、test、E2E、lint scripts。
- `frontend/next.config.mjs`：开发输出 `.next-dev`，生产输出 `.next`，关闭 dev indicators，配置 polling watch interval。
- `frontend/tsconfig.json`：strict TypeScript，包含 `.next/types` 和 `.next-dev/types`。
- `frontend/eslint.config.mjs`：Next core web vitals 和 TypeScript lint，忽略生成目录。
- `frontend/.env.example`：安全公开变量名来源，不读取 `.env.local`。
- `frontend/README.md`：setup、WSL/Windows 路径提醒、API base URL、endpoint summary、E2E 指南。

### 核心逻辑

- `frontend/app/task-state.ts`：类型、payload normalization、event/log normalization、artifact URL trust、错误文案。
- `frontend/app/workspace-view.ts`：conversation ordering、run grouping、progress log display、diagnostics JSON、status label。
- `frontend/hooks/use-task-workspace.ts`：task create/upload/message/cancel、SSE retry/backfill、history mutation、artifact open/download。
- `frontend/lib/task-api.ts`：tasks/models/skills/events/files/messages/cancel/artifacts 的 HTTP method 和 path。
- `frontend/app/file-upload.ts`：上传扩展名规则。
- `frontend/app/model-ui.ts`：模型 picker 展示。
- `frontend/app/skill-selection.ts`：技能标准化、过滤和 slash-token 行为。

### UI 组件

- `TaskWorkspace.tsx`：把 hook state 传入 sidebar、conversation、composer。
- `ChatSidebar.tsx`：历史列表、重命名、删除、清空。
- `TaskConversation.tsx`：transcript、Markdown、progress logs、diagnostics、artifact actions。
- `ChatComposer.tsx`：textarea、file input、upload preview、model picker、skill picker、send/stop。
- `RobotAvatar.tsx`：共享 AI avatar。
- `TypewriterText.tsx`：客户端 Markdown typewriter。

### 测试

- `frontend/tests/workspace/test_frontend_architecture.test.ts`：source boundary 和配置期望。
- `frontend/tests/workspace/test_task_workspace.test.ts`：hook 行为、SSE helper、artifact preview、model/skill wiring。
- `frontend/tests/workspace/test_task_api.test.ts`：API adapter exports 和 payload。
- `frontend/tests/workspace/test_workspace_view.test.ts`：conversation/log/diagnostics/order/display helper。
- `frontend/tests/state/test_task_state.test.ts`：状态标准化、artifact security、message payload、event translation。
- `frontend/tests/state/test_skill_selection.test.ts`：slash skill helper。
- `frontend/tests/model/test_model_ui.test.ts`：模型展示 helper。
- `frontend/tests/upload/test_file_upload.test.ts`：上传规则。
- `frontend/e2e-playwright/test_runtime_contracts.spec.mjs`：真实前后端运行合同验收。

## 命名约定

- Next route 文件使用框架名：`layout.tsx`, `page.tsx`。
- `frontend/app/` 纯 helper 使用 kebab-case：`task-state.ts`, `workspace-view.ts`。
- React component 文件使用 PascalCase。
- hook 文件使用 `use-*.ts`。
- API adapter 按领域命名：`task-api.ts`。
- Node tests 使用 `test_*.test.ts`。
- Playwright specs 使用 `test_*.spec.mjs`。
- 导出：组件 PascalCase，hook 用 `use*`，纯函数 camelCase，类型 PascalCase。

## 新代码落位

- 新 route：加在 `frontend/app/`，共享 UI 放 `frontend/components/`。
- 新工作区行为：状态/副作用放 `use-task-workspace.ts`；标准化放 `task-state.ts`；展示分组/标签放 `workspace-view.ts`；UI 放 chat component 和 `globals.css`。
- 新后端 API 操作：`frontend/lib/task-api.ts` 增加 transport，`task-state.ts` 增加类型/normalizer，hook 接入。
- 新 conversation rendering 规则：纯 projection 在 `workspace-view.ts`，JSX 在 `TaskConversation.tsx`，样式在 `globals.css`。
- 新 composer control：UI 状态在 `ChatComposer.tsx`，跨组件/后端行为在 hook，复用规则抽到 `frontend/app/`。
- 新上传格式：先改 `file-upload.ts`，再配套 composer、后端、单测和 E2E。
- 新模型行为：`model-ui.ts`、hook availability gating、`ChatComposer.tsx`。
- 新技能选择行为：`skill-selection.ts`、`ChatComposer.tsx`、`task-api.ts`、hook。

## 特殊目录

- `.planning/codebase/`：生成的前端事实文档，按任务需要提交。
- `.next/`：生产 build 输出，忽略。
- `.next-dev/`：dev server 输出，忽略。
- `node_modules/`：依赖安装，忽略。
- `test-results/`：Playwright/local test 输出，忽略。
- `e2e-playwright/e2e-YYYYMMDDHHMMSS/`：本地验收截图和证据，忽略但可在交付说明引用。
- `next-env.d.ts`：Next 生成，忽略。
- `tsconfig.tsbuildinfo`：TypeScript 增量缓存，忽略。
- `.env.local`：本地浏览器公开 env override，忽略且不安全读取。

---

*结构分析：2026-05-24*
