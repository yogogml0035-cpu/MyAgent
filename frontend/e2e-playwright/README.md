# 浏览器 E2E 证据

本目录保存可复用的 Playwright 验收入口，以及本地按时间戳归档的证据目录。

- 可复用 spec 需要提交，例如 `test_runtime_contracts.spec.mjs`。
- 单次运行的截图和下载产物放在 `e2e-YYYYMMDDHHMMSS/` 下。
- 不要提交带时间戳的证据目录；它们只是交付说明中引用的本地验收凭证。
- 截图中不要出现客户文档、provider key、访问 token 或私密本地路径。

启动后端和前端后，从 `frontend/` 运行 runtime-contract 验收：

```bash
MYAGENT_E2E_BASE_URL=http://127.0.0.1:3001 \
MYAGENT_E2E_API_URL=http://127.0.0.1:8001 \
MYAGENT_E2E_TASK_ROOT=/tmp/myagent-e2e/tasks \
MYAGENT_E2E_EVIDENCE_DIR=./e2e-playwright/e2e-YYYYMMDDHHMMSS/runtime-contracts \
MYAGENT_E2E_EXPECT_UPLOAD_LIMIT_BYTES=2048 \
MYAGENT_E2E_ACCESS_TOKEN=... \
MYAGENT_E2E_POSTGRES_CONTAINER=PostgreSQL \
MYAGENT_E2E_POSTGRES_USER=postgres \
MYAGENT_E2E_POSTGRES_DB=myagent \
npm run e2e:runtime-contracts
```

runtime-contract spec 会通过真实 Postgres 存储契约和任务产物目录播种一个已完成 run。Postgres 环境变量只应保留在本地 E2E 命令中，不要提交凭据。
当后端以较小的 `MYAGENT_MAX_UPLOAD_REQUEST_BYTES` 启动时，设置 `MYAGENT_E2E_EXPECT_UPLOAD_LIMIT_BYTES`，用于验证超限 multipart 上传会在浏览器侧被拒绝，且不会写入存储。

修改聊天进度时间线、行诊断、时间戳或展开交互时，从 `frontend/` 运行 progress-log disclosure 验收：

```bash
MYAGENT_E2E_BASE_URL=http://127.0.0.1:3001 \
MYAGENT_E2E_API_URL=http://127.0.0.1:8001 \
MYAGENT_E2E_EVIDENCE_DIR=./e2e-playwright/e2e-YYYYMMDDHHMMSS/progress-log-disclosure \
MYAGENT_E2E_ACCESS_TOKEN=... \
MYAGENT_E2E_POSTGRES_CONTAINER=PostgreSQL \
MYAGENT_E2E_POSTGRES_USER=postgres \
MYAGENT_E2E_POSTGRES_DB=myagent \
npx playwright test e2e-playwright/test_progress_log_disclosure.spec.mjs --reporter=line
```

progress-log spec 会通过同一套 Postgres-backed task/runs/messages/events 契约播种一个临时运行中任务，在浏览器中验证折叠行布局，展开 status/tool/generation 行，检查 trace 级一键折叠控件，捕获桌面和窄屏截图，把临时任务标记完成，并通过公开 API 删除。

修改长运行日志投影、run 级完整日志下载、最终回复产物卡片或历史交付失败提示展示时，从 `frontend/` 运行 task-log artifact delivery 验收：

```bash
MYAGENT_E2E_BASE_URL=http://127.0.0.1:3001 \
MYAGENT_E2E_API_URL=http://127.0.0.1:8001 \
MYAGENT_E2E_TASK_ROOT=/tmp/myagent-e2e/tasks \
MYAGENT_E2E_EVIDENCE_DIR=./e2e-playwright/e2e-YYYYMMDDHHMMSS/task-log-artifact-delivery \
MYAGENT_E2E_ACCESS_TOKEN=... \
MYAGENT_E2E_POSTGRES_CONTAINER=PostgreSQL \
MYAGENT_E2E_POSTGRES_USER=postgres \
MYAGENT_E2E_POSTGRES_DB=myagent \
npx playwright test e2e-playwright/test_task_log_artifact_delivery.spec.mjs --reporter=line
```

task-log artifact delivery spec 使用 `3001` 的真实前端和 `8001` 的真实后端；它会播种一个包含 2000+ 事件且带超大 tool-call partial delta 的运行中任务、一个已完成的 `.docx` 产物 run，以及一个历史 `needs_input` 交付失败任务。浏览器流程会确认主工作区不会渲染 2000+ 个展开的实时行，超大 partial payload 尾部不会渲染到页面中，日志可见时页面仍保持可交互，最终回复区域展示 run 级下载卡片，`.docx` 下载以产物文件名开始，历史交付失败 run 显示 `文件未生成或未登记为产物` 或等价提示。截图和下载样本保存到 `e2e-YYYYMMDDHHMMSS/task-log-artifact-delivery/`，不要提交该证据目录。

修改跨会话 busy 范围、同会话发送保护、run 级诊断、thinking/tool 事件渲染或 run 级 JSONL 下载边界时，从 `frontend/` 运行 multi-session thinking audit 验收：

```bash
MYAGENT_E2E_BASE_URL=http://127.0.0.1:3001 \
MYAGENT_E2E_API_URL=http://127.0.0.1:8001 \
MYAGENT_E2E_EVIDENCE_DIR=./e2e-playwright/e2e-YYYYMMDDHHMMSS/multi-session-thinking-audit \
MYAGENT_E2E_ACCESS_TOKEN=... \
MYAGENT_E2E_POSTGRES_CONTAINER=PostgreSQL \
MYAGENT_E2E_POSTGRES_USER=postgres \
MYAGENT_E2E_POSTGRES_DB=myagent \
npx playwright test e2e-playwright/test_multi_session_thinking_audit.spec.mjs --reporter=line
```

该 spec 依赖 `3001` 的真实前端和 `8001` 的真实后端；不会用 mock 页面替代任一服务。浏览器流程会通过公开 API 创建或复用两个可见任务，通过 Postgres-backed task/runs/messages/events 契约播种 A/B run 状态以及 thinking/tool 事件，验证会话 A 保持发送保护的同时会话 B 仍可启动，展开 run 诊断以确认完整 `reasoning_content`，并把证据保存到 `e2e-YYYYMMDDHHMMSS/multi-session-thinking-audit/`。当该审计 spec 修改了进度时间线或展开展示面时，同一轮回归中还要运行 progress-log disclosure spec，确认折叠行和逐行展开/复制行为仍然成立。
前端配置会让 `next dev` 输出到 `.next-dev`，所以该 E2E 可以和 `npm run build` 在同一工作区共享已运行的 `3001` dev server，而不会破坏浏览器运行时。

修改已配置的 web-search 工具或 tool-call/result payload 时，运行 SearXNG search progress 验收：

```bash
MYAGENT_E2E_BASE_URL=http://127.0.0.1:3001 \
MYAGENT_E2E_API_URL=http://127.0.0.1:8001 \
MYAGENT_E2E_EVIDENCE_DIR=./e2e-playwright/e2e-YYYYMMDDHHMMSS/searxng-search-progress \
MYAGENT_E2E_ACCESS_TOKEN=... \
MYAGENT_E2E_POSTGRES_CONTAINER=PostgreSQL \
MYAGENT_E2E_POSTGRES_USER=postgres \
MYAGENT_E2E_POSTGRES_DB=myagent \
npx playwright test e2e-playwright/test_searxng_search_progress.spec.mjs --reporter=line
```

SearXNG spec 会通过公开 API 创建临时任务，通过 Postgres-backed 事件契约播种 `searxng_search` tool-call 和 tool-result 事件，验证浏览器进度日志在折叠行中隐藏原始工具名，同时在展开 JSON 中保留 `searxng_search` 诊断，捕获截图，并删除任务。

修改对话历史注入、记忆召回、按用户隔离的长期记忆，或可见的“已载入会话上下文 / 已载入长期记忆”日志行时，从 `frontend/` 运行 session-context and long-term-memory 验收：

```bash
MYAGENT_E2E_BASE_URL=http://127.0.0.1:3001 \
MYAGENT_E2E_API_URL=http://127.0.0.1:8001 \
MYAGENT_E2E_EVIDENCE_DIR=./e2e-playwright/e2e-YYYYMMDDHHMMSS/session-context-memory \
MYAGENT_E2E_ACCESS_TOKEN=... \
MYAGENT_E2E_POSTGRES_CONTAINER=PostgreSQL \
MYAGENT_E2E_POSTGRES_USER=postgres \
MYAGENT_E2E_POSTGRES_DB=myagent \
npx playwright test e2e-playwright/test_session_context_memory.spec.mjs --reporter=line
```

session-context spec 会通过真实浏览器 UI 发送一轮用户消息，在 Postgres 中播种一条规范化的长期偏好记忆，从该权威存储重建 Qdrant 索引，再发送一轮应召回上一条消息和偏好的追问，展开 context/memory 诊断，并为初始空工作区、首轮提示、首轮完成、追问草稿、展开的记忆日志和召回答案捕获截图。

修改历史侧栏菜单触发器、重命名/删除菜单、焦点状态或紧凑历史布局时，从 `frontend/` 运行 history-menu affordance 验收：

```bash
MYAGENT_E2E_BASE_URL=http://127.0.0.1:3001 \
MYAGENT_E2E_API_URL=http://127.0.0.1:8001 \
MYAGENT_E2E_EVIDENCE_DIR=./e2e-playwright/e2e-YYYYMMDDHHMMSS/history-menu-affordance \
MYAGENT_E2E_ACCESS_TOKEN=... \
MYAGENT_E2E_POSTGRES_CONTAINER=PostgreSQL \
MYAGENT_E2E_POSTGRES_USER=postgres \
MYAGENT_E2E_POSTGRES_DB=myagent \
npx playwright test e2e-playwright/test_history_menu_affordance.spec.mjs --reporter=line
```

history-menu spec 会通过公开 API 创建临时任务，通过同一套 Postgres-backed task 契约播种一条可见的用户消息历史行，验证三点菜单触发器的 hover 和打开状态，捕获截图，并在断言后删除任务。

修改历史列表滚动行为、侧栏高度约束或清空全部操作时，从 `frontend/` 运行 history-scroll-clear 验收：

```bash
MYAGENT_E2E_BASE_URL=http://127.0.0.1:3001 \
MYAGENT_E2E_API_URL=http://127.0.0.1:8001 \
MYAGENT_E2E_EVIDENCE_DIR=./e2e-playwright/e2e-YYYYMMDDHHMMSS/history-scroll-clear \
MYAGENT_E2E_ACCESS_TOKEN=... \
MYAGENT_E2E_POSTGRES_CONTAINER=PostgreSQL \
MYAGENT_E2E_POSTGRES_USER=postgres \
MYAGENT_E2E_POSTGRES_DB=myagent \
npx playwright test e2e-playwright/test_history_scroll_clear.spec.mjs --reporter=line
```

history-scroll-clear spec 会通过公开 API 创建临时任务，通过 Postgres 播种可见历史行，验证侧栏历史区域可独立滚动且底部“清空全部”按钮仍可用，捕获截图，并且只删除临时任务。

修改首条消息创建任务、自动历史命名或标题归一化时，从 `frontend/` 运行 auto-title 验收：

```bash
MYAGENT_E2E_BASE_URL=http://127.0.0.1:3001 \
MYAGENT_E2E_API_URL=http://127.0.0.1:8001 \
MYAGENT_E2E_EVIDENCE_DIR=./e2e-playwright/e2e-YYYYMMDDHHMMSS/auto-title-generation \
MYAGENT_E2E_ACCESS_TOKEN=... \
npx playwright test e2e-playwright/test_auto_title_generation.spec.mjs --reporter=line
```

auto-title spec 会通过真实浏览器 UI 发送第一条用户消息，等待公开 message API 响应，断言返回的历史标题非空且最多 10 个可见字符，验证左侧历史侧栏展示同一标题，为 start、ready、visible-title 和 selected-row 状态捕获截图，然后通过公开 API 取消/删除临时任务。

修改上传格式、uploaded-resource 契约或资源工具进度时，从 `frontend/` 运行 resource-upload harness 验收：

```bash
MYAGENT_E2E_BASE_URL=http://127.0.0.1:3001 \
MYAGENT_E2E_API_URL=http://127.0.0.1:8001 \
MYAGENT_E2E_TASK_ROOT=/tmp/myagent-e2e/tasks \
MYAGENT_E2E_EVIDENCE_DIR=./e2e-playwright/e2e-YYYYMMDDHHMMSS/resource-upload-harness \
MYAGENT_E2E_ACCESS_TOKEN=... \
MYAGENT_E2E_POSTGRES_CONTAINER=PostgreSQL \
MYAGENT_E2E_POSTGRES_USER=postgres \
MYAGENT_E2E_POSTGRES_DB=myagent \
npx playwright test e2e-playwright/test_resource_upload_harness.spec.mjs --reporter=line
```

resource-upload spec 会使用真实浏览器文件选择路径选择 `.docx`、`.xlsx`、`.json` 和 `.txt`，通过公开 API 上传这些文件，播种一个带 resource-tool 进度事件的已完成 run，并捕获选择、已上传状态、工具进度和完成状态截图。

修改已选文件预览卡片、上传交互或响应式 composer 布局时，从 `frontend/` 运行 upload-preview design 验收：

```bash
MYAGENT_E2E_BASE_URL=http://127.0.0.1:3001 \
MYAGENT_E2E_EVIDENCE_DIR=./e2e-playwright/e2e-YYYYMMDDHHMMSS/upload-preview-design \
npx playwright test e2e-playwright/test_upload_preview_design.spec.mjs --reporter=line
```

upload-preview spec 会通过真实浏览器文件选择路径选择受支持文件，验证独立的已选文件卡片、仅文件名展示、替换控件、hover 后显示的逐文件移除控件、核心 design-token 颜色，并捕获变更后预览卡片的桌面和窄屏截图。

修改 composer 技能 slash picker、chip shelf、键盘选择、删除行为或响应式技能选择样式时，从 `frontend/` 运行 skill selector 验收：

```bash
MYAGENT_E2E_BASE_URL=http://127.0.0.1:3001 \
MYAGENT_E2E_EVIDENCE_DIR=./e2e-playwright/e2e-YYYYMMDDHHMMSS/skill-selector \
npx playwright test e2e-playwright/test_skill_selector.spec.mjs --reporter=line
```

skill selector spec 会打开真实前端页面，为 `code-review` 和 `web-research` 提供受控的项目技能响应，验证 slash 过滤、键盘和鼠标选择、可移除 chip 行为、不会意外发送消息，并为打开 picker、已选 chip 和已移除 chip 状态捕获截图。

修改项目技能 payload、消息提交、任务历史重载或可见用户消息契约时，运行完整的 skill selector send-loop 验收：

```bash
MYAGENT_E2E_BASE_URL=http://127.0.0.1:3001 \
MYAGENT_E2E_API_URL=http://127.0.0.1:8001 \
MYAGENT_E2E_EVIDENCE_DIR=./e2e-playwright/e2e-YYYYMMDDHHMMSS/skill-selector-full-loop \
MYAGENT_E2E_ACCESS_TOKEN=... \
npx playwright test e2e-playwright/test_skill_selector_full_loop.spec.mjs --reporter=line
```

full-loop spec 不会 mock `/api/skills`、`/api/tasks` 或消息提交。它会打开真实前端，验证后端暴露 `code-review` 和 `web-research`，选择 `web-research`，发送带结构化 `skills` payload 的用户消息，检查持久化且用户可见的 `[$web-research]` 引用，重新加载任务历史，并捕获桌面和移动端截图。
