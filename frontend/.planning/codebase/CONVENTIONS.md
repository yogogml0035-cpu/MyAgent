# 前端编码约定

**分析日期：** 2026-05-24

## 命名模式

- `frontend/app/`, `frontend/hooks/`, `frontend/lib/` 中的可复用 TS 模块使用 kebab-case。
- chat 组件文件使用 PascalCase。
- tests 使用 `test_*.test.ts`，Playwright specs 使用 `test_*.spec.mjs`。
- 函数/helper 使用 camelCase。
- 纯转换 helper 按意图加前缀：`normalize*`, `format*`, `build*`, `read*`, `is*`, `merge*`, `partition*`。
- 组件/hook event handler 使用 `handle*`，prop 使用 `on*`。
- React hook 使用 `use*` 命名，文件保持 kebab-case。
- state/derived values 用 camelCase；module constants 使用 uppercase const name。
- React refs 以 `*Ref` 结尾。
- 交互锁使用明确 busy boolean，例如 `isSubmittingTask`, `isSwitchingConversation`, `isMutatingConversation`, `isStoppingTask`。

## 类型约定

- object shape 和 union 优先使用 `type` alias。
- 共享类型从纯模块导出，并用 `import type` 导入。
- 组件 props 在组件文件附近定义为 `type <ComponentName>Props`。
- 渲染流使用 discriminated union，例如 `ConversationStreamItem.kind`。
- 边界 JSON 先当作 `unknown`，通过 reader/type guard 标准化，避免 `any`。

## 代码风格

- 未检测到 Prettier/Biome，格式跟随现有 TypeScript 风格。
- TypeScript、TSX、CSS、JSON、MJS 使用两个空格缩进。
- 多行对象、数组、函数参数、JSX props 和 import 使用 trailing comma。
- TypeScript/TSX/MJS/CSS 字符串使用双引号。
- ESLint flat config 来自 `frontend/eslint.config.mjs`，`npm run lint` 以零 warning 为门槛。
- `frontend/tsconfig.json` 启用 `strict`、`allowJs: false`、`isolatedModules`、`moduleResolution: "bundler"`。

## 导入组织

1. React、Next、第三方 import。
2. `frontend/app/` 纯 domain 模块。
3. 本地组件 import。

- 未配置 path alias，使用相对导入。
- type-only import 使用 `import type`。
- 需要 React value 和 type 时可以合并导入，跟随周围代码。

## 错误处理

- HTTP failure 集中在 `frontend/lib/task-api.ts` 的 `requestTaskJson`、`formatHttpErrorMessage`、`formatRequestFailure`。
- API/validation boundary 抛出用户可读中文 `Error`。
- hook 捕获错误后写入 `error` 和 `errorLevel`。
- 后端 task error 与本地 workspace error 分开存储。
- async mutation 使用 `try/catch/finally` 并在 `finally` 释放 busy flag。
- 可选启动数据降级：模型选项 fallback，技能选项 warning 不阻塞。
- SSE 防御式解析 payload，有界重试并刷新 task summary。
- artifact URL 先做 origin、route、task、run、filename、query/hash、路径穿越校验，再发送 token。

## 日志

- 应用代码不使用 browser console 作为日志系统。
- 不要新增 `console.log` 或 `console.error` 到应用模块。
- 用户可见日志来自 backend event logs 和 diagnostics copy。
- E2E specs 可以收集 console error 作为断言。

## 注释

- 只解释非显然行为、安全边界或兼容性要求。
- 避免复述赋值、prop 名或 JSX 结构。
- 配置注释保持短且操作性强。
- 不使用 JSDoc/TSDoc 作为常规文档；优先用明确类型和测试。

## 函数和模块设计

- 纯 helper 模块包含小函数；大型状态编排集中在 `use-task-workspace.ts`。
- 参数较多或有模式/可选项时使用 options object。
- 纯模块返回 normalized、UI-ready 对象。
- 纯数据标准化、格式化、排序、过滤、request building 放在 `frontend/app/*.ts` 或 `frontend/lib/*.ts`。
- hook 中对 derived array/display value 使用 `useMemo`。
- 返回给组件的 handler 使用 `useCallback`。
- document listener、timer、SSE connection、animation frame 都要有 cleanup。

## 模块边界

- `frontend/app/page.tsx` 只委托 `TaskWorkspace`。
- `TaskWorkspace.tsx` 只把 hook state/handler 绑定到 chat 组件。
- `use-task-workspace.ts` 拥有 task lifecycle、SSE、上传、artifact、history、model/skill state。
- `task-api.ts` 拥有 REST、SSE URL、auth header/query 和 response parsing。
- `task-state.ts`, `workspace-view.ts`, `model-ui.ts`, `file-upload.ts`, `skill-selection.ts` 拥有纯转换。
- 不使用 barrel files；直接从 owner module 导入。

## React 组件模式

- 只有用浏览器 API、React state/effect/ref/handler 的组件或 hook 添加 `"use client";`。
- route/layout 和纯模块保持 server-compatible。
- 组件由 `useTaskWorkspace` 的 props 控制，不直接 fetch。
- JSX 中调用 async handler 用 `void` 包裹。
- icon/menu/listbox/stateful 控件添加明确 `aria-label`, `aria-expanded`, `aria-haspopup`, `aria-selected`, `aria-current`。
- 使用语义区域：`main.agentShell`、历史 `aside`、任务对话 `section`。
- model/skill picker 使用 `role="listbox"` 和 `role="option"`。

## UX 约定

- 保持 `frontend/app/globals.css` 的 warm-canvas token：`--canvas`, `--workspace`, `--surface-card`, `--primary`, `--primary-active`, `--hairline`, `--ink` 等。
- 使用全局 CSS class，不引入 CSS modules，除非整体样式架构改变。
- icon-only 控件需要可访问名称和 title。
- 删除/清空等破坏性行为保持确认流程。
- 保持 `980px`, `760px`, `520px` 等响应式断点。
- selected file、skill、model picker、日志详情、历史菜单、artifact 控件应由测试 ID 或可访问查询覆盖。

---

*约定分析：2026-05-24*
