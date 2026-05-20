# MyAgent Interfaces

本文件记录 MyAgent 的跨子系统接口边界。接口内部的具体字段和实现细节以 `backend/.planning/codebase/`、`frontend/.planning/codebase/` 和源码为准。

## 已确认接口边界

### Browser to Backend

前端通过 `frontend/lib/task-api.ts` 调用 FastAPI 后端。主要接口类型包括：

- 模型列表：前端读取可用模型并展示模型选择状态。
- 任务生命周期：创建、读取、列表、重命名、删除、发送消息、取消运行。
- 文件上传：multipart 上传到已存在且非运行中的任务。
- 事件读取：REST 事件轮询和 SSE 实时事件流。
- 产物读取：按 task/run 范围下载或打开 artifact blob。
- 项目 Skill：读取当前仓库 `backend/skills` 的浏览器安全 skill 投影。

后端路由位于 `backend/app/api/`，稳定公共 schema 位于 `backend/app/schemas.py`。

### Project Skills

- `GET /api/skills` 返回当前项目 skill 列表，响应为 `[{ "name": string, "description": string }]`。
- Skill 列表固定由后端代码定位到仓库内 `backend/skills`，不读取 `settings.skills_dirs`、`MYAGENT_SKILLS_DIRS`、`.agents/skills`、Codex 全局 skills 或用户主目录。
- 浏览器响应只能包含 `name` 和 `description`，不得包含本地路径、目录路径、环境变量、Markdown 正文或其他 frontmatter 字段。
- 当前默认项目 skill 包括 `code-review` 和 `web-research`；无有效项目 skill 时返回空数组而不是 500。

### Message Skills

- `POST /api/tasks/{task_id}/messages` 接受可选 `skills: string[]` 字段，同时继续兼容省略该字段的旧请求。
- 前端只发送已选 skill 名称；后端在创建 run 前校验这些名称是否属于当前项目 skill。未知名称返回 400。
- 后端把已选 skill 按用户选择顺序格式化为用户可见前缀，例如 `[$web-research]` 或 `[$code-review] [$web-research]`，并将同一个 effective message 传给消息存储、自动标题生成和 runner。

### REST and SSE

- REST 请求使用 browser `fetch`，JSON 响应在前端边界层归一化。
- SSE 使用 browser `EventSource`，后端返回 `text/event-stream`。
- EventSource 不能设置自定义 header，因此 SSE token 通过 `?token=` 传递。
- SSE 连接失败时，前端应刷新任务摘要、读取增量事件并做有界重试。
- 后端事件日志是权威事实；SSE 只负责投影和实时体验。

### Field Naming

- 后端 API 使用 `snake_case`。
- 前端 UI 状态使用 `camelCase`。
- 字段转换集中在 `frontend/app/task-state.ts`。
- 不要在组件中直接依赖后端原始字段名；组件应接收已经归一化的状态。

核心示例：

| 后端字段 | 前端字段 |
| --- | --- |
| `task_id` | `id` |
| `created_at` | `createdAt` |
| `updated_at` | `updatedAt` |
| `active_run_id` | `activeRunId` |
| `run_count` | `runCount` |
| `upload_count` | `uploadCount` |
| `artifact_names` | `artifactNames` |
| `needs_input` | `needsInput` |

### Uploads and Artifacts

- 前端上传过滤只是 UX 辅助，后端校验才是安全边界。
- 上传文件由后端保存到任务工作区，并写入事件日志。
- 产物 URL 和 run/task 范围必须由后端生成或验证。
- 前端携带 token 获取产物前，必须先通过 `frontend/app/task-state.ts` 的信任检查。
- HTML 产物预览视为不可信内容，应继续使用 sandboxed iframe。

### Runtime Storage

- Postgres 是任务、运行、消息、事件、工具缓存、长期记忆行和 LangGraph store item 的权威存储。
- 本地 filesystem 是上传和产物 bytes 的权威存储，默认路径为 `backend/storage/sessions/`。
- `TaskRunner` 的 active run registry 只存在于当前后端进程内。
- 当前单进程 runner 不支持多 worker 或多主机主动运行所有权。

### Runtime Contracts

- `storage.start_run()` 生成的 `run_id` 必须传入 `runner.start_background()`，保证 storage、streaming 和前端 run 归属一致。
- 任务进入 `running` 后，runner 调度应尽快发生；自动标题、摘要或日志装饰等增强不能阻断后台运行接管。
- Agent 运行产出的事件必须通过 storage 持久化为有序事件，终态必须同步写入任务状态和终态事件。
- 会调度后台 runner 的 FastAPI 端点必须保持 `async def`。
- 文件系统工具必须限定在当前任务工作区内，不能访问全局 sessions 根或其他任务目录。
- SSE 读取异常应转换为可见 error/done 信号，不能让连接无提示断裂。
- 取消运行时，runner 和 storage 状态必须同步，避免前端看到的任务状态和实际运行状态分叉。
- 前端 API adapter 必须防御非 JSON 的成功响应；SSE 重连必须有界退避，日志合并必须按事件 ID 去重。
- 对话自动滚动应保持 smart scroll：仅在用户未手动上滚时自动滚到底部。

### Model, Search, Memory

- 模型 provider 凭据只属于后端运行环境或被忽略的后端 env 文件。
- SearXNG 是本地搜索工具边界，由后端工具注册后暴露给 agent。
- DashScope-compatible embeddings 和 Qdrant 只用于长期记忆索引；Postgres 仍是长期记忆 canonical store。
- 记忆写入前必须遵守脱敏和内容边界，不能保存上传原文、完整产物正文、流式 token、工具原始日志、密钥或客户敏感内容。

### Auth and Environment

- 后端默认允许 loopback；非本机访问应设置 `MYAGENT_ACCESS_TOKEN` 和受限 CORS。
- 前端只可使用浏览器安全的 `NEXT_PUBLIC_*` 值。
- `NEXT_PUBLIC_MYAGENT_TOKEN` 是浏览器可见 token，不能等同于 provider key。
- `DEEPSEEK_API_KEY`、`OPENAI_API_KEY`、`ANTHROPIC_API_KEY`、`DASHSCOPE_API_KEY`、`MYAGENT_DATABASE_URL`、`MYAGENT_QDRANT_URL` 等只能在后端 env 或 ignored env 文件中出现。

## 开发和运行接口

后端默认运行：

```bash
cd backend
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

前端默认运行：

```bash
cd frontend
npm run dev
```

本地开发脚本：

- `scripts/start-dev-wsl.ps1`：Windows PowerShell 启动入口。
- `scripts/dev-terminal-runner.sh`：WSL 终端内服务 runner。
- `scripts/stop-dev-ports.sh`：默认或指定端口清理。

本地开发或 E2E 默认优先复用用户已运行的 `3001` 和 `8001` 服务。只有确认服务不可用、不是当前仓库、环境冲突或 E2E 需要隔离产物目录时，才考虑新启或换端口。

## 验证接口

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

浏览器 E2E：

```bash
cd frontend
npm run e2e:runtime-contracts
```

也可以按场景运行 `frontend/e2e-playwright/test_*.spec.mjs`。截图证据保存在 ignored 的 `frontend/e2e-playwright/e2e-YYYYMMDDHHMMSS/` 目录下，不提交 git。

文档和空白检查：

```bash
git diff --check
```

## 跨系统变更同步

- 新增或修改后端 API：同步 `backend/app/schemas.py`、`frontend/lib/task-api.ts`、`frontend/app/task-state.ts`、相关后端/前端测试和本文件。
- 修改任务状态或事件 payload：同步后端 storage/runner/streaming 测试、前端 state/view 测试和受影响 Playwright 场景。
- 修改上传或产物边界：同步后端文件/artifact 测试、前端 artifact URL 信任测试和浏览器验收。
- 修改 auth、CORS 或 token 传递：同步后端 middleware/API 测试、前端 API adapter 测试和安全说明。
- 修改模型 Provider、长期记忆或搜索能力：同步 `asset/deepagents_platform_knowledge_pack.md` 和相关后端测试。
- 修改招投标分析规则、分类、证据归一化或报告生成：同步 `asset/bid_analysis_workflow_knowledge_pack.md`，必要时同步平台知识包。

## 需确认或不应假设

- 当前没有 OAuth、cookie session、多用户账号模型或 RBAC。
- 当前没有 durable job queue、跨进程 runner ownership、worker lease 或 crash recovery。
- 当前没有云对象存储、Docker/Kubernetes 部署或多主机文件一致性方案。
- Playwright specs 存在，但并非所有浏览器路径都会被默认 npm 脚本自动覆盖；行为变更需要按影响面选择并运行对应 E2E。
