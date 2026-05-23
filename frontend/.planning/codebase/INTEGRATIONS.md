# 前端集成

**分析日期：** 2026-05-24

## 运行时服务集成

### MyAgent 后端 HTTP API

- 前端运行时只集成 MyAgent 后端。
- 客户端：`frontend/lib/task-api.ts` 中的浏览器 `fetch` wrapper。
- Base URL：`TASK_API_BASE_URL`，由 `frontend/app/task-state.ts` 的 `resolveApiBaseUrl` 推导。
- 认证：可选 `NEXT_PUBLIC_MYAGENT_TOKEN` 或 legacy `NEXT_PUBLIC_AGENT_CHAT_TOKEN`，HTTP 请求使用 `X-MyAgent-Token`。
- 常用 endpoint：
  - `GET /api/models`
  - `GET /api/skills`
  - `GET /api/tasks`
  - `POST /api/tasks`
  - `GET /api/tasks/{task_id}`
  - `PATCH /api/tasks/{task_id}`
  - `DELETE /api/tasks/{task_id}`
  - `GET /api/tasks/{task_id}/events?after_id=...`
  - `POST /api/tasks/{task_id}/files`
  - `POST /api/tasks/{task_id}/messages`
  - `POST /api/tasks/{task_id}/cancel`
  - `GET /api/tasks/{task_id}/artifacts/{artifact_name}`
  - `GET /api/tasks/{task_id}/runs/{run_id}/artifacts/{artifact_name}`

### MyAgent 后端 SSE

- 任务事件流使用浏览器 `EventSource`。
- endpoint：`GET /api/tasks/{task_id}/stream`。
- 认证：`EventSource` 不能设置自定义 header，因此 token 作为 query 参数。
- 消费者：`frontend/hooks/use-task-workspace.ts` 合并 stream events、刷新 summary、按有界重试恢复。
- fallback：SSE 失败或终态后，通过 `fetchTaskEvents` 和 `fetchTask` 恢复。

### 模型与技能目录

- 模型目录来自 `/api/models`，UI 限制为 `deepseek-v4-flash` 和 `deepseek-v4-flash-thinking`。
- 技能目录来自 `/api/skills`，前端只使用 name/description。
- 选中的技能名称随 `postTaskMessage` 发送。
- 前端不直接访问模型 provider、Postgres、Qdrant、SearXNG 或 embedding service。

## 数据存储

- 前端 runtime 没有数据库 client。
- task state、messages、events、runs、uploads、artifacts 都来自后端 HTTP/SSE。
- Playwright specs 可能通过后端/API/Postgres test setup seed 状态；这属于验收基础设施，不是浏览器 runtime 集成。

## 文件与 Blob

- 浏览器文件选择：`ChatComposer.tsx` 的 native file input。
- 上传过滤：`frontend/app/file-upload.ts`，当前扩展名 `.md`, `.json`, `.txt`, `.docx`, `.xlsx`, `.xlsm`。
- 上传传输：`FormData` + `POST /api/tasks/{task_id}/files`。
- 产物下载/预览：后端 artifact endpoint、`Response.blob()`、`URL.createObjectURL`、DOM download/open flow。
- HTML 预览：`buildSandboxedArtifactPreviewDocument` 在 popup 内写入 sandboxed iframe。

## 缓存

- 未检测到 Redis、浏览器 storage cache、service worker 或 data-fetch cache library。
- 运行时状态保存在 React state。
- 事件去重由 `mergeExecutionLogs` 在内存中完成。

## 认证与身份

- 自定义共享 token 由后端验证。
- HTTP 请求 token 来自 `NEXT_PUBLIC_MYAGENT_TOKEN` 或 legacy `NEXT_PUBLIC_AGENT_CHAT_TOKEN`，通过 `X-MyAgent-Token` 发送。
- SSE token 通过 query 参数发送。
- `NEXT_PUBLIC_*` 会进入浏览器 bundle，不能包含 provider key、数据库 URL、Qdrant URL、客户数据或私密样例。
- 未检测到登录页、OAuth、cookie session 或生产 runtime localStorage session store。

## 浏览器 API

- Network：`fetch`, `EventSource`。
- Files/Blobs：`File`, `FormData`, `Blob`, `URL.createObjectURL`, `URL.revokeObjectURL`。
- DOM/Clipboard：`navigator.clipboard.writeText`, `window.open`, `document.write`, `document.createElement("a")`, `window.confirm`, document listeners, `requestAnimationFrame`。
- Formatting：`Intl.DateTimeFormat`, `Intl.Segmenter`。

## 可观测性

- 未检测到前端错误追踪 SDK。
- 用户可见日志来自后端 task events，经 `task-state.ts` 标准化并由 `TaskConversation.tsx` 渲染。
- diagnostics JSON/JSONL copy 由 `workspace-view.ts` 生成。
- 浏览器 E2E evidence 存在本地时间戳目录，不能提交。

## CI/CD 与部署

- 未检测到 frontend-local CI workflow 或 hosting provider 配置。
- 生产命令为 `npm run build` + `npm run start`。
- 可用验证命令：`npm run typecheck`, `npm test`, `npm run lint`, `npm run build`, `npm run e2e:runtime-contracts`。

## 环境变量

- `NEXT_PUBLIC_MYAGENT_API_BASE_URL`：可选后端 URL。
- `NEXT_PUBLIC_MYAGENT_TOKEN`：可选浏览器 token。
- `NEXT_PUBLIC_API_BASE_URL`、`NEXT_PUBLIC_AGENT_CHAT_TOKEN`：legacy fallback。
- `NEXT_WATCH_POLL_INTERVAL_MS`：watch polling。
- E2E 变量：`MYAGENT_E2E_BASE_URL`, `MYAGENT_E2E_API_URL`, `MYAGENT_E2E_EVIDENCE_DIR`, `MYAGENT_E2E_ACCESS_TOKEN` 以及场景特定后端 setup 变量。
- `frontend/.env.local` 是 ignored 本地配置，不能读取、引用或提交。

## Webhook 和回调

- 未检测到 `frontend/app/api/` route handler 或 incoming webhook。
- outgoing 只指向 MyAgent 后端。
- 未检测到 telemetry、analytics、email、payment 或第三方 SDK callback。

---

*集成审计：2026-05-24*
