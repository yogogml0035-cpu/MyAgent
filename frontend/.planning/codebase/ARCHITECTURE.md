# 前端架构

**分析日期：** 2026-05-19

## 总览

`frontend/` 是 Next.js app router 单页任务工作区。它负责浏览器端交互、任务状态展示、REST/SSE 调用、上传体验、产物打开下载、日志展示和视觉设计。

## 核心层次

- App 入口：`frontend/app/page.tsx` 渲染 `TaskWorkspace`。
- API adapter：`frontend/lib/task-api.ts` 封装 backend base URL、token、REST、SSE、artifact blob。
- 状态归一化：`frontend/app/task-state.ts` 把后端 payload 转成前端可用状态，并做 artifact URL 信任检查。
- 工作流 hook：`frontend/hooks/use-task-workspace.ts` 管理模型、历史、任务创建、上传、发送消息、SSE 重试、轮询恢复、取消、重命名、删除和产物操作。
- View projection：`frontend/app/workspace-view.ts` 把任务、消息、事件、run、artifact 转成界面展示模型。
- 展示组件：`frontend/components/chat/` 渲染侧边栏、对话、composer、进度日志、产物和模型选择。
- 设计层：`frontend/app/globals.css` 和根级 `DESIGN.md` 控制视觉风格。

## 主要数据流

### 页面加载

1. Next.js 渲染 `/`。
2. `TaskWorkspace` 调用 `useTaskWorkspace()`。
3. hook 通过 API adapter 获取模型列表和任务历史。
4. 响应经过 `task-state.ts` 归一化。
5. 组件展示侧边栏、模型状态和空工作区。

### 发送消息

1. 用户在 composer 输入文本，可选上传文件。
2. hook 确保任务存在。
3. 如有文件，先调用上传接口。
4. hook 调用发送消息接口。
5. 后端返回 running 状态后，前端启动 SSE 监听。
6. SSE 事件合并进日志，view projection 转成用户可见进度。
7. 终态后刷新任务详情，展示最终助手消息和产物。

### SSE 恢复

1. EventSource 错误时，hook 关闭当前连接。
2. 前端刷新任务摘要。
3. 前端根据最后已知事件 ID 拉取增量事件。
4. 前端按事件 ID 去重合并。
5. 在最大次数内使用退避重连。

## 状态边界

- 后端是任务事实状态来源。
- React state 是浏览器 UI 投影。
- 后端原始字段不能直接进入组件展示。
- artifact URL 只有通过信任检查后才能携带 token 请求。
- 上传过滤是体验层，后端校验才是安全边界。

## 设计边界

- 视觉调整必须先读 `DESIGN.md`。
- 全局样式集中在 `frontend/app/globals.css`。
- 当前风格是暖色画布、珊瑚主色、克制圆角和密集工作台布局。
- 行为或视觉变化需要 Playwright 和截图证据。
