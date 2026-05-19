# 前端编码约定

**分析日期：** 2026-05-19

## 命名

- 非组件模块使用 `kebab-case.ts`，例如 `task-state.ts`、`workspace-view.ts`。
- React 组件文件使用 `PascalCase.tsx`。
- hook 文件使用 `use-*.ts`。
- 函数和变量使用 `camelCase`。
- 事件处理函数使用 `handle*`。
- 常量使用 `UPPER_SNAKE_CASE`。
- 类型使用 `PascalCase`。
- Node 测试使用 `test_*.test.ts`。
- Playwright spec 使用 `test_*.spec.mjs`。

## 模块边界

- 组件不直接调用后端 API。
- API 请求集中在 `frontend/lib/task-api.ts`。
- 后端 payload 归一化集中在 `frontend/app/task-state.ts`。
- React 副作用集中在 `frontend/hooks/use-task-workspace.ts`。
- 纯 view projection 集中在 `frontend/app/workspace-view.ts`。
- 视觉样式集中在 `frontend/app/globals.css`。

## 导入

- 不使用 TypeScript path alias。
- 外部包导入放在本地模块导入前。
- 类型导入尽量使用 `type`。
- 组件和 hook 通过相对路径导入 app/helper。

## 错误处理

- `requestTaskJson()` 负责网络错误、HTTP 错误、JSON 解析和 token。
- 非 JSON 的成功响应要防御性处理。
- hook handler 捕获错误后设置用户可见 notice。
- unknown 后端状态归一化为 `unknown`，不要当成 `running`。
- SSE parse 或连接错误触发刷新和有界重试。
- artifact URL 验证失败时不能附带 token 请求。

## CSS 和视觉

- 视觉变更先读 `DESIGN.md`。
- 复用 `--canvas`、`--surface-card`、`--primary`、`--radius-md` 等现有 token。
- 不随意引入孤立色系或与当前暖色画布不一致的控件。
- 文案大小要匹配所在容器，避免按钮、卡片、侧栏文字溢出。

## 日志和注释

- 提交的前端应用代码避免 `console.log`。
- 用户可见问题通过 notice、日志面板或复制诊断表达。
- 注释只解释协议、安全或不直观的 projection 逻辑。
