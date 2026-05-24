# 前端测试模式

**分析日期：** 2026-05-24

## 测试框架

- Unit runner：Node.js 内置 `node:test`，通过 `tsx` 执行 TypeScript。
- E2E runner：Playwright `@playwright/test`。
- 断言：Node `assert/strict` 或 `assert`，E2E 使用 Playwright `expect`。
- 未检测到 Jest、Vitest 或 Playwright config 文件；当前 specs 依赖 CLI defaults 和 spec 内配置。

## 常用命令

```bash
cd frontend
npm test
npm run typecheck
npm run lint
npm run build
npm run e2e:runtime-contracts
npx playwright test e2e-playwright/test_skill_selector.spec.mjs --reporter=line
```

## 测试组织

```text
frontend/tests/
|-- model/       # 模型 picker 展示 helper
|-- state/       # task state normalization、artifact security、payload
|-- upload/      # 上传规则和 preview guardrails
`-- workspace/   # workspace view、hook boundary、API exports、source contracts

frontend/e2e-playwright/
|-- README.md
|-- test_runtime_contracts.spec.mjs
|-- test_*_spec.mjs
`-- e2e-YYYYMMDDHHMMSS/   # 本地证据，不能提交
```

## 命名和结构

- unit tests：`test_*.test.ts`。
- Playwright specs：多数为 `test_*.spec.mjs`。
- `test_storage_memory_e2e.mjs` 是无 `.spec` 的手动/legacy 运行入口。
- 纯 helper 测试优先顶层 `test("behavior", () => {})`。
- `describe`/`it` 主要用于 grouped module export 或 source-boundary checks。
- 测试名写具体可观察行为。
- 对 deterministic helper 可直接 `assert.deepEqual` 完整返回对象。
- source-text assertion 只用于架构边界、视觉 token guard 或生成/config 约束。

## Mock 规则

应该 mock：

- Node unit tests 中的 `globalThis.fetch`，用于测试 REST adapter。
- DOM-like object 的最小 typed shape，用于纯 DOM helper。
- Playwright `page.route` 只用于明确 frontend-only 场景。

不应该 mock：

- runtime contract path；`test_runtime_contracts.spec.mjs` 必须使用真实前端、后端 API、task storage 和 artifacts。
- 行为变更不能只靠 Node source assertion 代替 browser E2E。
- mock/fixture/screenshot/evidence 不能包含 credentials、provider key、access token、客户文档或私密本地路径。

## Fixture 和数据

- 小型 unit fixture 放在测试文件内。
- E2E fixture writer 放在拥有该场景的 spec 内。
- 运行截图和 fixture 输出放在 `frontend/e2e-playwright/e2e-YYYYMMDDHHMMSS/<scenario>/`。

## 测试类型

### 单元测试

- 覆盖纯转换、数据标准化、格式化、request building、安全 guard、source boundary 和 DOM-independent helper。
- 主要文件：`test_task_state.test.ts`, `test_workspace_view.test.ts`, `test_task_conversation_scroll.test.ts`, `test_model_ui.test.ts`, `test_file_upload.test.ts`, `test_skill_selection.test.ts`。

### 集成测试 / 浏览器运行时

- 浏览器/runtime 集成在 Playwright specs。
- `test_runtime_contracts.spec.mjs` 覆盖 live task creation、model metadata、artifact open/download、upload limit、access token 和浏览器可见合同。
- `test_skill_selector_full_loop.spec.mjs` 覆盖真实 `/api/skills`、task 创建、message submission、selected skill payload、历史 reload。
- 一些 spec 通过公开 API 和 Postgres-backed 初始化流程播种后端状态。

### 端到端测试

- 前端行为变更必须跑 Playwright E2E。
- runtime-contract/full-loop specs 默认使用实际服务：frontend `3001`，backend `8001`。
- 视觉或交互改动需要保存截图到 timestamped evidence 目录。
- 影响响应式布局时应覆盖桌面和窄屏/移动状态。

## 常见断言模式

- API adapter：mock `fetch` 后断言 normalized browser-safe 结果。
- artifact security：`assert.throws` 校验外部 URL 在发送 token 前被拒绝。
- Playwright：设置 `baseURL`，进入页面，断言用户可见 UI，保存 screenshot。

## 标准质量门

- TypeScript/React/build 行为变更：`npm run typecheck`, `npm test`, `npm run lint`, `npm run build`。
- 文档或代码变更：`git diff --check`。
- 浏览器行为变更：运行目标 Playwright spec 和邻近 regression spec。
- runtime contract：设置 `MYAGENT_E2E_BASE_URL`, `MYAGENT_E2E_API_URL`, `MYAGENT_E2E_TASK_ROOT`, `MYAGENT_E2E_EVIDENCE_DIR`, access token/Postgres env 后运行。

## 场景选择

- 上传/文件 preview：`tests/upload/` 和 upload 相关 Playwright specs。
- skill picker/payload：skill selection unit tests、task API tests、skill selector E2E。
- progress/log/diagnostics/copy：workspace view tests、conversation scroll tests、progress-log/multi-session E2E。
- history rename/delete/clear/scroll：frontend architecture tests 和 history 相关 E2E。
- model picker/unavailable model：model UI tests、task workspace tests、runtime contracts。
- artifact URL/preview/download/token：task state tests、task workspace tests、runtime contracts。

---

*测试分析：2026-05-24*
