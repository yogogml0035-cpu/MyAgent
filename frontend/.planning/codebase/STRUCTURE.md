# 前端代码结构

**分析日期：** 2026-05-19

## 目录布局

```text
frontend/
├── app/
│   ├── page.tsx                 # 首页入口
│   ├── layout.tsx               # 根布局和 metadata
│   ├── globals.css              # 全局样式和设计 token
│   ├── task-state.ts            # 后端 payload 归一化和安全 helper
│   ├── workspace-view.ts        # 纯展示投影
│   ├── file-upload.ts           # 上传扩展名过滤
│   └── model-ui.ts              # 模型展示信息
├── components/chat/             # 聊天工作区组件
├── hooks/                       # React 工作流 hook
├── lib/                         # 浏览器 API adapter
├── tests/                       # Node 测试
├── e2e-playwright/              # Playwright specs 和截图证据
├── package.json                 # npm scripts 和依赖
├── next.config.mjs              # Next 配置
├── tsconfig.json                # TypeScript strict 配置
└── eslint.config.mjs            # ESLint 配置
```

## 关键文件

- `frontend/app/page.tsx`：app router 首页。
- `frontend/components/chat/TaskWorkspace.tsx`：主工作区组合组件。
- `frontend/components/chat/ChatSidebar.tsx`：历史会话侧栏。
- `frontend/components/chat/TaskConversation.tsx`：对话、日志和产物展示。
- `frontend/components/chat/ChatComposer.tsx`：输入、上传和发送区域。
- `frontend/hooks/use-task-workspace.ts`：主要工作流状态和副作用。
- `frontend/lib/task-api.ts`：REST、SSE 和 artifact 请求。
- `frontend/app/task-state.ts`：后端字段转换、事件归一化、artifact 安全。
- `frontend/app/workspace-view.ts`：日志分组、对话流、展示标签。
- `frontend/app/globals.css`：视觉样式。

## 新代码放置规则

- 新 API 调用：`frontend/lib/task-api.ts`。
- 新后端字段或事件：`frontend/app/task-state.ts`。
- 新展示投影：`frontend/app/workspace-view.ts`。
- 新任务工作流：`frontend/hooks/use-task-workspace.ts`。
- 新 UI：`frontend/components/chat/`，样式在 `frontend/app/globals.css`。
- 新上传规则：`frontend/app/file-upload.ts`。
- 新模型展示逻辑：`frontend/app/model-ui.ts`。
- 新 Node 测试：`frontend/tests/<concern>/test_*.test.ts`。
- 新浏览器验收：`frontend/e2e-playwright/test_*.spec.mjs`。

## 测试目录

- `frontend/tests/state/`：状态和安全归一化。
- `frontend/tests/workspace/`：workspace projection 和源码边界。
- `frontend/tests/upload/`：上传过滤和上传 UI 相关测试。
- `frontend/tests/model/`：模型展示 helper。
- `frontend/e2e-playwright/`：浏览器验收。

## 生成目录

- `.next/`：生产构建产物。
- `.next-dev/`：本地 dev 产物。
- `.next-dev-e2e/`：E2E dev 产物。
- `node_modules/`：依赖。
- `frontend/e2e-playwright/e2e-*/`：本地截图、trace、下载证据。
- `frontend/test-results/` 和 Playwright report：测试产物。
