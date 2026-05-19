# 07 前端工作区

## 学习目标

你要理解前端不是一堆组件直接互相改状态，而是有清晰分工：

- `TaskWorkspace.tsx`：页面骨架，连接 sidebar、conversation、composer。
- `use-task-workspace.ts`：任务状态和动作编排。
- `task-api.ts`：所有 HTTP/SSE 请求。
- `task-state.ts`：后端数据归一化。
- `workspace-view.ts`：把状态投影成可见 UI 数据。
- `ChatComposer.tsx`：输入、上传、模型选择、发送/停止。
- `TaskConversation.tsx`：消息、进度日志、产物展示。

## 前置知识

- React hook：把状态和行为封装成可复用函数。
- 受控输入：输入框内容由 React state 控制。
- 组件组合：父组件把数据和回调传给子组件。

## 必读代码

- `frontend/app/page.tsx`
- `frontend/components/chat/TaskWorkspace.tsx`
- `frontend/hooks/use-task-workspace.ts`
- `frontend/lib/task-api.ts`
- `frontend/app/task-state.ts`
- `frontend/app/workspace-view.ts`
- `frontend/components/chat/ChatComposer.tsx`
- `frontend/components/chat/TaskConversation.tsx`

## 本章主线

前端学习不要先看 CSS。先追 `handleSubmit`：

```text
ChatComposer 点击发送
-> TaskWorkspace 把 onSubmit 指向 hook
-> useTaskWorkspace.handleSubmit()
-> ensureTask()
-> uploadTaskFiles()
-> 生成真正要发送的 taskContent
-> postTaskMessage()
-> refreshTask()/refreshTaskSummaries()
```

## 核心概念

### Hook 是前端编排中心

`useTaskWorkspace` 持有当前 task id、状态、消息、日志、产物、选中文件、模型、错误等。用户动作也在这里编排，例如：

```text
handleSubmit:
  校验是否可发送
  校验模型可运行
  ensureTask
  uploadTaskFiles
  生成 taskContent
  postTaskMessage
  refreshTask
  refreshTaskSummaries
```

### API 层单独封装

组件不直接写 fetch，统一通过 `task-api.ts`。好处是 token、base URL、错误格式、artifact 安全校验都有一个入口。

这也让测试更容易：前端状态测试可以验证 `buildMessageRequestPayload()`、`buildArtifactRequest()`，不用真的打开浏览器。

### UI 状态来自投影

后端原始 EventRecord 不直接等于 UI。`workspace-view.ts` 把日志、消息、run、artifact 组合成页面上可渲染的 conversation stream。

### 只上传文件、不输入文字时也会发送一条默认消息

这是当前源码里一个很容易忽略、但非常重要的产品行为：

- 如果用户输入框有文字，就发送用户输入
- 如果用户没有输入文字，但选择了文件，前端不会发空消息
- 它会改发一条默认提示词：`DEFAULT_FILE_PROMPT`

这样做的目的，是保证后端收到的仍然是一条“可以触发分析”的消息，而不是只有文件没有任务意图。

## 结合项目分析

当前真实代码的 `handleSubmit` 主路径可以更精确地写成：

```text
if (!canSend || isBusy || activeTask) return
-> guardModel
-> ensureTask()
-> uploadTaskFiles()
-> const taskContent = input.trim() || DEFAULT_FILE_PROMPT
-> postTaskMessage(id, taskContent, model)
-> refreshTask(id)
-> refreshTaskSummaries()
```

这里最适合初学者抓住的，不是 React 语法，而是“为什么这一行必须放在这里”：

- `guardModel` 先于创建 task / 上传文件
- `ensureTask` 先于 upload / post message
- `DEFAULT_FILE_PROMPT` 让文件-only 场景也能进入标准消息流

## 你可能卡住的问题

### 为什么发送时先 `ensureTask()`？

用户可能在新会话里直接输入消息或选文件。前端必须先确保有 task id，后续上传和发消息才能绑定到 task。

### 为什么模型不可用要在上传前拦截？

如果模型不可用还先创建 task 或上传文件，会留下无意义状态。前端先拦截可以避免用户误以为任务已经开始。

## 动手练习

运行：

```bash
node Study/chapters/07_frontend_workspace/mini_unit.mjs
```

尝试把 `submitPlan` 中 `guardModel` 移到 `uploadFiles` 后面，再运行。你会看到失败。这个失败对应真实代码中“模型不可用要先于创建任务/上传文件阻断”。

你也可以再做一个小实验：把 mini unit 里的 `chooseTaskContent("   ")` 改成返回空字符串，再运行。你会看到失败，因为文件-only 场景不应该发送空消息。

练习还会读取 `use-task-workspace.ts` 和 `TaskWorkspace.tsx`，确认 handler、组件分工、默认提示词和 artifact sandbox 逻辑在源码中存在。

## 自测题

1. `TaskWorkspace` 为什么不直接写一大堆业务逻辑？
2. `task-api.ts` 为什么要处理非 JSON 的 200 响应？
3. `buildSandboxedArtifactPreviewDocument` 解决了什么风险？
4. 为什么历史列表、会话流、进度日志不是直接在组件里临时拼？
5. 为什么“只上传文件、不输入文字”时，前端仍然要构造一条默认消息？

## 常见误区

- 误区：React 组件越大越方便。纠正：大组件会让 API、状态、展示、错误处理混在一起。
- 误区：`TaskWorkspace` 是业务核心。纠正：它主要是组合层，核心编排在 `useTaskWorkspace`。
- 误区：打开 artifact 就是 `window.location = url`。纠正：HTML artifact 要 sandbox 预览。
