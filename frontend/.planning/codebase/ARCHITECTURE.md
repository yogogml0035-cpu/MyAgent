<!-- refreshed: 2026-05-24 -->
# 前端架构

**分析日期：** 2026-05-24

## 系统总览

`frontend/` 是 MyAgent 的浏览器工作区。它是一个 Next.js App Router 单页应用，通过 React 组件、控制器 hook、传输适配器和纯状态/视图转换模块，把后端任务、SSE 事件、上传资源、模型/技能选项和产物下载呈现给用户。

```text
Next.js app shell
  -> TaskWorkspace
  -> ChatSidebar / TaskConversation / ChatComposer
  -> useTaskWorkspace
  -> frontend/lib/task-api.ts
  -> frontend/app/task-state.ts + workspace-view.ts
  -> backend HTTP API / SSE / artifact blob
```

## 组件职责

| 组件 | 职责 | 入口 |
| --- | --- | --- |
| Root layout | 加载全局 CSS、metadata、中文 shell 和 icon metadata | `frontend/app/layout.tsx` |
| Home route | 保持路由薄层，只渲染工作区组件 | `frontend/app/page.tsx` |
| TaskWorkspace | 组合历史侧栏、对话流、输入区，把 hook 状态和 handler 传给子组件 | `frontend/components/chat/TaskWorkspace.tsx` |
| ChatSidebar | 渲染历史会话、新建、重命名、删除、清空历史 | `frontend/components/chat/ChatSidebar.tsx` |
| TaskConversation | 渲染用户/AI 消息、运行进度、诊断 JSON、产物卡片、复制和自动滚动 | `frontend/components/chat/TaskConversation.tsx` |
| ChatComposer | 管理输入框、模型选择、文件选择、slash 技能选择、技能 chips、发送和停止控件 | `frontend/components/chat/ChatComposer.tsx` |
| useTaskWorkspace | 拥有浏览器 task state、初始化、提交、历史 mutation、SSE merge、artifact 打开/下载和错误提示 | `frontend/hooks/use-task-workspace.ts` |
| API adapter | 集中封装 fetch、multipart upload、EventSource、artifact blob、access token | `frontend/lib/task-api.ts` |
| State adapter | 标准化后端 payload，定义前端 task/message/log/artifact 类型，校验 artifact URL | `frontend/app/task-state.ts` |
| View adapter | 构建 history item、run group、conversation stream item、live log row、diagnostics JSON、显示标签 | `frontend/app/workspace-view.ts` |
| Helpers | 上传文件过滤、模型展示、技能选择和 slash token 逻辑 | `frontend/app/file-upload.ts`, `frontend/app/model-ui.ts`, `frontend/app/skill-selection.ts` |
| Styles | 视觉 token、两栏布局、聊天卡片、输入区、菜单、日志和响应式断点 | `frontend/app/globals.css` |

## 分层结构

### 路由与布局

- 位置：`frontend/app/layout.tsx`, `frontend/app/page.tsx`。
- 负责 Next.js app shell、metadata、global CSS import 和根路由委托。
- 不承载任务状态、API 调用或业务逻辑。

### 聊天 UI 组件

- 位置：`frontend/components/chat/`。
- 组件应由 props 控制，局部只保留 picker、menu、scroll、disclosure 等 UI 状态。
- 不直接调用后端 task API。

### 工作区控制器

- 位置：`frontend/hooks/use-task-workspace.ts`。
- 拥有 task 初始化、任务提交、文件上传、取消、会话切换、历史 mutation、SSE 生命周期、事件恢复、产物打开/下载、复制反馈等状态和副作用。

### 后端传输边界

- 位置：`frontend/lib/task-api.ts`。
- 所有后端 REST/SSE/blob 请求集中在这里。
- 负责 token header/query、错误格式化、artifact blob fetch 和 API path。

### 状态标准化与合同

- 位置：`frontend/app/task-state.ts`。
- 后端 JSON 在进入 React 状态前必须标准化。
- 这里处理 `snake_case` 到 `camelCase`、事件/log normalization、artifact URL trust、message payload 和错误文案。

### 视图模型与展示规则

- 位置：`frontend/app/workspace-view.ts`。
- 负责历史、run group、conversation stream、live log、diagnostics、copy text、status label、time/file formatting、keyboard intent。
- JSX 不应内联排序、分组或复杂日志规则。

### 功能 helper

- 位置：`frontend/app/file-upload.ts`, `frontend/app/model-ui.ts`, `frontend/app/skill-selection.ts`。
- 保持小型可测试规则独立于 React 组件。

### 样式层

- 位置：`frontend/app/globals.css`。
- 维护当前 warm-canvas 工作区视觉系统、响应式布局和组件 class。

## 关键数据流

### 主请求路径

1. Next.js 加载 `RootLayout` 和 `Home`。
2. `Home` 渲染 `TaskWorkspace`。
3. `TaskWorkspace` 调用 `useTaskWorkspace`，把状态和 handler 传给三个 chat 子组件。
4. hook 初始化模型、任务摘要和技能选项。
5. 发送时，hook 创建 task、上传文件、提交 message。
6. `frontend/lib/task-api.ts` 发送 HTTP 请求。
7. `frontend/app/task-state.ts` 标准化响应。
8. running task 通过 `createTaskEventSource` 接收 SSE，并用 `mergeExecutionLogs` 合并。
9. `workspace-view.ts` 构建 run group 和 conversation stream。
10. `TaskConversation` 渲染消息、日志和产物。

### 会话历史路径

- `fetchTaskSummaries` 读取 `/api/tasks`。
- `normalizeTaskSummaries` 转成 `TaskSummary[]`。
- `buildConversationHistoryItems` 生成 sidebar rows。
- 选择会话调用 `fetchTask`；重命名/删除/清空通过 hook handler 调用 API。

### 产物路径

- 后端 task state 附带 artifacts。
- `buildArtifactRequest` 校验当前 API origin、task id、run id、artifact name、query/hash 和路径穿越。
- 下载通过 `fetchArtifactBlob` + `<a download>`。
- HTML 预览在 `about:blank` popup 中写入沙盒 iframe，不直接注入主页面。

### 上传、模型、技能路径

- `ChatComposer` 管理文件 input、模型 listbox、skill slash picker 和 chips。
- `partitionSupportedUploadFiles` 过滤扩展名。
- `/api/models` 只用于浏览器安全模型选项，当前 UI 限定 DeepSeek V4 Flash 两个 ID。
- `/api/skills` 返回 name/description；选中的技能名称随 message payload 发送。

## 状态管理

- 运行时状态使用 React state/ref，没有外部客户端状态库。
- `useMemo` 构建 history、model display、selected skills、run groups、conversation stream。
- refs 只用于瞬态浏览器状态：latest logs、copy timer、scroll/detail、picker/file input、menu。
- 后端 task state 和持久化 events 是权威；SSE 只是投影，失败后通过 `fetchTaskEvents` 和 `fetchTask` 恢复。

## 关键抽象

- `TaskState`：前端任务详情、runs、messages、logs、artifacts、uploads 和 prompts 的稳定形状。
- `ExecutionLog`：保存后端 event record，同时暴露 live metadata、reasoning/search/tool/memory/file audit traces。
- `ConversationStreamItem`：把消息、run logs、产物卡片压平成一条有序渲染流。
- `RunActivityGroup`：按 run id 聚合 logs、artifacts、status 和 streamed diagnostics。
- `Task API adapter`：浏览器 REST/SSE/blob 请求的唯一传输边界。
- `ArtifactRequest`：防止 token 泄露到不可信 artifact URL。
- `ModelDisplayOption` / `SkillOption`：浏览器安全、显示友好的模型和技能记录。

## 入口

- `frontend/app/page.tsx`：根路由，只渲染 `TaskWorkspace`。
- `frontend/app/layout.tsx`：app shell、metadata、global CSS。
- `frontend/components/chat/TaskWorkspace.tsx`：工作区组件边界。
- `frontend/hooks/use-task-workspace.ts`：工作区控制器。
- `frontend/lib/task-api.ts`：后端 API 边界。
- `frontend/app/globals.css`：全局视觉系统。
- `frontend/tests/`, `frontend/e2e-playwright/`：自动化验证入口。

## 架构约束

- 前端运行在浏览器 event loop，SSE、file picker、clipboard、popup/blob 处理不能阻塞。
- 浏览器公开配置只能使用 `NEXT_PUBLIC_*`，不能包含 provider key、数据库 URL、Qdrant URL 或客户资料。
- 生产路由目前只有 `/`；新增路由必须有真实 URL surface。
- 后端字段在 `task-state.ts` 中标准化，组件消费前端 `camelCase` 类型。
- artifact 操作必须走 `buildArtifactRequest` 和 `fetchArtifactBlob`。
- 保持依赖方向：components -> hook -> API/state/view adapters；API -> state adapter；view adapter -> state types。
- 未配置 path alias，保持相对导入。
- `.next/`, `.next-dev/`, `node_modules/`, `test-results/`, E2E evidence、`next-env.d.ts`, `*.tsbuildinfo` 都是生成/本地文件。

## 反模式

- 不要在 chat 组件中直接调用 `/api/tasks`、`/api/models`、`/api/skills` 或 artifact routes。
- 不要在 JSX 中读取原始后端 `snake_case` 字段或 raw event payload。
- 不要在 JSX 中排序/分组 run logs；扩展 `workspace-view.ts`。
- 不要直接打开或链接 backend-provided artifact URL。
- 不要把产品逻辑放进 `frontend/app/page.tsx`。

## 错误处理

- `requestTaskJson` 统一处理 fetch failure、HTTP error 和用户可读错误。
- hook 捕获 action failure，设置 `error` 和 `errorLevel`，由 workspace notice 展示。
- 后端 task error 和 needs-input 由 `workspace-view.ts` 投影成 state notice。
- SSE error 解析后会刷新事件和 task summary。
- artifact URL 不可信时，在附加 token 前抛出安全错误。

## 横切关注点

- 前端没有应用 logger，用户可见日志来自后端事件。
- 后端 JSON 校验使用 `isRecord`、`readString` 等 reader 和 normalizer。
- 认证 token 来自 `NEXT_PUBLIC_MYAGENT_TOKEN` 或 legacy `NEXT_PUBLIC_AGENT_CHAT_TOKEN`；HTTP 用 header，SSE 用 query。
- `.env.local` 是 ignored 本地配置，不能读取或复制到文档。
- 样式集中在 `frontend/app/globals.css`，组件使用 class name。

---

*架构分析：2026-05-24*
