# 前端集成

**分析日期：** 2026-05-19

## 后端 REST API

前端通过 `frontend/lib/task-api.ts` 调用 FastAPI 后端：

- `/api/models`：模型列表。
- `/api/tasks`：任务创建和历史。
- `/api/tasks/{task_id}`：任务详情、重命名、删除。
- `/api/tasks/{task_id}/messages`：发送消息。
- `/api/tasks/{task_id}/files`：上传文件。
- `/api/tasks/{task_id}/events`：事件轮询。
- `/api/tasks/{task_id}/artifacts/...`：产物获取。
- `/api/tasks/{task_id}/cancel`：取消运行。

## SSE

- 前端使用 `EventSource` 创建 SSE 连接。
- SSE 事件来自后端持久化事件日志。
- token 通过 query 参数传递。
- 连接失败后，hook 会刷新摘要、拉取增量事件，并进行有界重连。

## 字段转换

- 后端 wire format 是 `snake_case`。
- 前端 UI state 是 `camelCase`。
- 转换在 `frontend/app/task-state.ts`。
- 组件只应消费归一化后的数据。

## Artifact

- artifact blob 通过浏览器 `fetch` 获取。
- token 只附加到可信后端 artifact URL。
- HTML artifact 使用 sandboxed iframe 预览。
- 下载通过临时 anchor 和 object URL 完成。

## 上传

- 浏览器保存用户选择的 `File` 对象。
- 发送消息前，hook 会先上传选中文件。
- 前端扩展名过滤只做 UX；后端负责权威校验。

## 浏览器状态

- 任务状态、历史、日志、文件选择、模型选择和通知保存在 React state。
- 未发现 localStorage、IndexedDB、cookie session 或浏览器数据库持久化。

## 观测和证据

- 用户可见诊断来自后端事件。
- 前端没有外部埋点、Sentry 或 analytics。
- Playwright specs 将截图和下载证据保存到 `frontend/e2e-playwright/e2e-YYYYMMDDHHMMSS/`。

## 部署边界

- 前端默认本地端口是 `3001`。
- 后端默认本地端口是 `8001`。
- 未发现 Vercel、Netlify、Docker 或云部署配置。
