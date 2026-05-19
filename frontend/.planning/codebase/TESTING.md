# 前端测试

**分析日期：** 2026-05-19

## 命令

```bash
cd frontend
npm run typecheck
npm test
npm run lint
npm run build
```

浏览器 E2E：

```bash
cd frontend
npm run e2e:runtime-contracts
npx playwright test e2e-playwright/test_upload_preview_design.spec.mjs --reporter=line
```

## 测试框架

- Node `node:test` + `tsx`：运行 TypeScript 单元和源码边界测试。
- `node:assert/strict`：断言。
- Playwright：浏览器 E2E、截图和下载证据。
- ESLint：warning 也按失败处理。

## 目录结构

```text
frontend/tests/
├── state/
├── workspace/
├── upload/
└── model/

frontend/e2e-playwright/
├── test_*.spec.mjs
└── e2e-YYYYMMDDHHMMSS/<scenario>/
```

## 测试重点

- `frontend/tests/state/`：任务状态归一化、事件归一化、artifact URL 安全。
- `frontend/tests/workspace/`：日志分组、对话流、组件边界、API export 和源码不变量。
- `frontend/tests/upload/`：上传扩展名过滤和上传预览设计约束。
- `frontend/tests/model/`：模型 UI 文案和 badge。
- `frontend/e2e-playwright/`：真实浏览器下的任务、上传、SSE、产物、历史菜单、视觉和响应式。

## E2E 证据

- 截图、下载和 trace 放在 `frontend/e2e-playwright/e2e-YYYYMMDDHHMMSS/`。
- 证据目录被忽略，不提交 git。
- 行为或视觉变更的交付说明应引用本地截图路径。
- 截图应覆盖关键状态变化，不只截最终页。

## 何时补测试

- 改状态归一化：补 `frontend/tests/state/`。
- 改展示投影：补 `frontend/tests/workspace/`。
- 改上传：补 `frontend/tests/upload/` 和相关 Playwright。
- 改模型展示：补 `frontend/tests/model/`。
- 改 UI 或用户流程：补 Playwright spec 和截图证据。
- 改 artifact URL 或 token 传递：补 state 安全测试和浏览器路径。

## 测试原则

- Node 测试适合纯函数和源码边界。
- 浏览器交互不能只靠 Node 测试替代。
- 视觉变更必须用截图证明确实没有破坏布局。
- Playwright 失败先看 error、trace、video、screenshot 和日志。
