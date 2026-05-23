# MyAgent 接口边界

本文件记录仓库级接口边界。具体端点实现和内部类型以
`backend/.planning/codebase/`、`frontend/.planning/codebase/` 和源代码为准。

## 已确认接口边界

### 前端到后端 HTTP API

前端运行时只依赖 MyAgent 后端，不直接调用模型、数据库、Qdrant、SearXNG 或 embedding provider。

主要调用集中在 `frontend/lib/task-api.ts`：

- `GET /api/models`：获取浏览器安全的模型选项。
- `GET /api/skills`：获取项目技能名称和描述。
- `GET /api/tasks`：获取任务/会话摘要。
- `POST /api/tasks`：创建任务。
- `GET /api/tasks/{task_id}`：读取任务状态、消息、事件、运行、上传和产物。
- `PATCH /api/tasks/{task_id}`：重命名会话。
- `DELETE /api/tasks/{task_id}`：删除会话。
- `GET /api/tasks/{task_id}/events?after_id=...`：恢复增量事件。
- `POST /api/tasks/{task_id}/files`：上传文件。
- `POST /api/tasks/{task_id}/messages`：发送用户消息、模型、模式和技能选择。
- `POST /api/tasks/{task_id}/cancel`：停止运行中的任务。
- `GET /api/tasks/{task_id}/artifacts/{artifact_name}`：下载任务级产物。
- `GET /api/tasks/{task_id}/runs/{run_id}/artifacts/{artifact_name}`：下载 run 级产物。

后端实现入口在 `backend/app/api/`，应用组装入口在 `backend/app/main.py`。

### 前端到后端 SSE

运行中任务通过 Server-Sent Events 投影后端持久化事件：

- 前端创建 `GET /api/tasks/{task_id}/stream` 的 `EventSource`。
- `EventSource` 无法设置自定义 header，因此浏览器 token 会作为 `token` query 参数发送。
- SSE 是持久化事件的投影，不是权威状态来源。
- 断线、终态或失败时，前端会回退到事件增量读取和任务状态刷新。

相关位置：

- `frontend/lib/task-api.ts`
- `frontend/hooks/use-task-workspace.ts`
- `backend/app/api/streaming.py`
- `backend/app/streaming/`
- `backend/app/storage.py`

### 字段和状态边界

- 后端 API 使用 Pydantic schema 和后端内部 `snake_case` 约定。
- 前端 UI 使用 TypeScript 类型和浏览器侧 `camelCase` 约定。
- 字段标准化、状态标签、产物 URL 信任检查和错误消息格式化集中在 `frontend/app/task-state.ts`。
- 展示分组、时间/文件格式化、日志视图和会话历史模型集中在 `frontend/app/workspace-view.ts`。

跨边界改字段时，优先同时检查：

1. `backend/app/schemas.py`
2. `backend/app/api/`
3. `frontend/app/task-state.ts`
4. `frontend/lib/task-api.ts`
5. `frontend/tests/state/`
6. `frontend/e2e-playwright/`

### 上传和产物边界

- 浏览器侧文件选择和过滤由 `frontend/components/chat/ChatComposer.tsx` 与 `frontend/app/file-upload.ts` 负责。
- 上传传输使用 `FormData` 和 `POST /api/tasks/{task_id}/files`。
- 后端文件校验、任务目录、上传目录和产物目录由 `backend/app/storage.py` 管理。
- 默认任务文件根在后端 `Settings.task_root`，默认落到 `backend/storage/sessions`。
- 支持的上传格式以源代码事实为准，当前事实层记录为 Markdown、JSON、TXT、DOCX、XLSX 和 XLSM。
- HTML 产物预览由前端生成沙盒 iframe 文档，避免直接把不可信 HTML 混入主页面。

### 模型和技能边界

- 浏览器只发送后端注册的模型 ID，不接触 provider key。
- 模型选项来自 `/api/models`，后端通过 `backend/app/models/` 和 `MODEL_REGISTRY` 生成安全元数据。
- 技能选项来自 `/api/skills`，后端读取 `backend/skills/*/SKILL.md` 并只暴露名称和描述。
- 选中的技能名称随 `POST /api/tasks/{task_id}/messages` 发送，由后端 runner 注入 agent 运行。

### 认证、CORS 和公开配置

- 后端 `/api/` 路由由 `backend/app/main.py` 中的自定义 token 或本地客户端 gate 保护。
- 设置访问令牌时，HTTP 请求可使用 `Authorization: Bearer <token>`、`X-MyAgent-Token`、`X-Agent-Chat-Token` 或 query token。
- 前端运行时读取 `NEXT_PUBLIC_MYAGENT_TOKEN` 或 legacy `NEXT_PUBLIC_AGENT_CHAT_TOKEN`，HTTP 请求使用 `X-MyAgent-Token`。
- `NEXT_PUBLIC_*` 会进入浏览器 bundle，不能包含 provider key、数据库 URL、Qdrant URL、客户资料或私密样例。
- CORS 默认面向本地前端端口 `3001`；跨主机或 LAN 暴露需要显式配置 token 和 CORS origin。

### 后端到外部服务

后端负责所有私密 provider 和存储连接：

- DeepSeek：chat model provider，用于任务运行、标题生成和长期记忆提取。
- DashScope-compatible embeddings：用于长期记忆向量化。
- Qdrant：长期记忆向量索引。
- PostgreSQL：任务、运行、消息、事件、agent store、工具缓存和长期记忆元数据。
- SearXNG：本地搜索工具，可被 agent 运行调用。
- Local filesystem：任务上传和产物文件。

## 未证实或需确认的关系

- 仓库内未检测到前端直接调用外部 AI provider、数据库、Qdrant 或 SearXNG 的运行时路径。
- 未检测到仓库级 CI 配置；当前验证入口主要是本地命令和 Playwright E2E。
- 未检测到 Docker、云托管或进程管理配置；当前文档以本地同机开发和运行边界为主。
- 多 worker 和横向扩展仍需设计外部队列、租约、心跳和跨进程事件发布后再推进。

## 任务排查建议

- API、状态字段、事件流、上传、产物或鉴权问题：先看 `INTERFACES.md`，再看后端和前端各自的 `INTEGRATIONS.md`。
- 后端 runner、存储、记忆或 provider 问题：先看 `backend/.planning/codebase/ARCHITECTURE.md` 和 `backend/.planning/codebase/CONCERNS.md`。
- 前端工作区、SSE 合并、状态转换或产物打开问题：先看 `frontend/.planning/codebase/ARCHITECTURE.md` 和 `frontend/.planning/codebase/CONCERNS.md`。
- 行为变更需要浏览器验收时，优先查 `frontend/.planning/codebase/TESTING.md` 和 `frontend/e2e-playwright/README.md`。

## 可扩展集成文档入口

如未来出现稳定部署、远程访问、多租户、队列 worker、CI/CD、OAuth 或审计日志方案，优先新增或更新：

- `DEPLOYMENT.md`
- `DECISIONS.md`
- `SECURITY.md`

在这些文档出现前，`INTERFACES.md` 只记录当前已确认的跨系统边界。
