# 前端风险与关注点

**分析日期：** 2026-05-25

## 技术债

### 工作区控制 hook 过大

- 问题：`frontend/hooks/use-task-workspace.ts` 集中 API bootstrapping、task selection、SSE retry、submission、upload、history mutation、copy feedback、artifact open/download。
- 影响：提交、切换、停止、历史 mutation 等状态容易耦合。
- 建议：逐步拆成 `useTaskBootstrap`、`useTaskStream`、`useTaskSubmission`、`useConversationHistory`、`useArtifacts` 等 focused hooks。

### `task-state.ts` 职责过宽

- 问题：同一文件包含 API types、payload normalization、event trace normalization、翻译文案、artifact URL security、request failure formatting。
- 影响：新增 event type 或 trace schema 容易碰到无关逻辑。
- 建议：保留 exported types，逐步拆出 `task-events.ts`、`artifacts.ts`、`task-copy.ts`。

### `workspace-view.ts` 过大

- 问题：历史 shaping、live log grouping、diagnostics JSON、progress copy、artifact/run grouping、sorting、placeholder suppression、keyboard intent 都在同一文件。
- 影响：progress logs、streaming answer、artifact grouping 改动难理解。
- 建议：按 `log-view.ts`、`run-groups.ts`、`conversation-stream.ts`、`history-view.ts` 拆分并迁移测试。

### source-string tests 作为架构锁

- 问题：部分测试用 `readFileSync`、`.includes()`、regex 校验源码文本。
- 影响：行为不变的重构可能失败，行为回归也可能因字符串仍存在而通过。
- 建议：能执行的规则改为 exported helper 或 browser/component assertions；source guards 只保留有意架构约束。

## 已知问题

- 历史 README 曾与 `next.config.mjs` 的 distDir 不一致；当前事实以 `frontend/next.config.mjs` 为准：dev 输出 `.next-dev`，production build 输出 `.next`。

## 安全关注

- `NEXT_PUBLIC_MYAGENT_TOKEN` 和 legacy `NEXT_PUBLIC_AGENT_CHAT_TOKEN` 会编进浏览器 bundle；只能当本地浏览器访问 token，不能放 provider secret。
- SSE query token 可能进入 URL 日志；避免记录完整 SSE URL。
- artifact URL validation 和 HTML sandbox preview 是关键边界；不能直接渲染 backend URL 或用 `dangerouslySetInnerHTML`。
- diagnostics JSON/copy 可能包含 runtime context、工具参数、文件审计和 memory/context summary；截图和复制日志视为敏感本地证据。
- 浏览器上传过滤只是扩展名 UX；安全和一致性以后端校验为准。

## 性能瓶颈

- 历史、消息、日志、diagnostics 目前未虚拟化，长任务或大量历史会有 DOM 和字符串生成成本。
- `buildRunActivityGroups()`、`buildConversationStreamItems()`、`buildLiveLogItems()` 会随 state 变化重复排序/分组。
- 已对 SSE event 做浏览器帧级批量合并，并对 tool-call partial delta / closed stream raw diagnostics 做 compact projection；后续改动不能恢复“每条 event 一次全量渲染”或“把几千条 partial raw payload 合并进单个 `<pre>`”的行为。
- clear-all 逐个删除 task，缺少 bulk-delete API。
- 大文件上传没有客户端 size feedback 或 progress。

## 可访问性与 UX 脆弱点

- 自定义 listbox/menu 键盘支持不完整；编辑菜单时要验证 Tab、Enter/Space、Arrow、Escape 和焦点回归。
- 部分 hover/focus 控件默认透明，键盘可发现性依赖 visible focus。
- 删除/清空使用 `window.confirm()`，阻塞 event loop，样式不可控，未来可改为 app modal。
- progress diagnostics 的边框和失败状态应保持中性，不要把普通排障输出渲染成强错误色。

## 扩展限制

- event log 无前端数量上限，长任务可能导致 render、diagnostics 和 copy 卡顿。
- sidebar 渲染 `/api/tasks` 返回的所有 summary，历史多时 O(n) 成本明显。
- 应用当前只有单页 surface；更多顶层工作流会继续压迫 workspace hook，需先抽取共享任务编排。

## 依赖风险

- Next、React、TypeScript、Playwright、ESLint 等使用 caret range；`npm ci` 按 lockfile 更可复现。
- major upgrade 可能破坏 app-router types、ESLint config 或 Next generated type paths。
- 依赖升级应作为维护阶段执行，并运行 `typecheck && test && lint && build` 加目标 E2E。

## 缺失能力

- 没有自动化 accessibility gate。
- 没有 bulk task-management API。
- 没有客户端 upload limit copy 或 aggregate size feedback。
- React component 层缺少真实渲染 unit tests，很多交互依赖 Playwright 才能捕获。

## 构建/测试风险

- `npm run dev` 使用 POSIX/WSL 风格 env assignments；Windows 原生开发应使用 `scripts/start-dev-win.ps1`，由脚本设置环境变量并调用 `next.cmd`。切换 Windows/WSL 模式时要同步切换 `frontend/node_modules` junction 并避免复用另一模式缓存。
- E2E specs 依赖真实服务、Postgres、可选 memory setup、access token 和 evidence dir，容易因环境而失败。
- E2E env naming 有混用，`test_storage_memory_e2e.mjs` 使用不同变量名，应文档化为 legacy/manual 或统一。

## 测试缺口

- 组件真实 DOM 行为缺少 React Testing Library 层。
- hook-level SSE reconnection、fake EventSource、active task switching 覆盖不足。
- 键盘、focus、ARIA 和可见焦点缺少自动化可访问性回归。
- 大量 events/history/diagnostics/upload selection 的性能缺少测试。

---

*风险审计：2026-05-25*
