# Browser E2E Evidence

This directory contains reusable Playwright acceptance entrypoints plus local, timestamped evidence folders.

- Commit reusable specs such as `test_runtime_contracts.spec.mjs`.
- Store run-specific screenshots and downloaded artifacts under `e2e-YYYYMMDDHHMMSS/`.
- Do not commit timestamped evidence folders; they are local acceptance proof referenced in delivery notes.
- Keep screenshots free of customer documents, provider keys, access tokens, and private local paths.

Run the runtime-contract acceptance test from `frontend/` after starting the backend and frontend:

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

The runtime-contract spec seeds one completed run through the real Postgres-backed storage contract plus the task artifact directory. Keep the Postgres env values local to the E2E command and do not commit credentials.
Set `MYAGENT_E2E_EXPECT_UPLOAD_LIMIT_BYTES` when the backend is started with a small `MYAGENT_MAX_UPLOAD_REQUEST_BYTES` value to verify that oversized multipart uploads are rejected in the browser before storage writes.

Run the progress-log disclosure acceptance test from `frontend/` when changing the chat progress timeline, row diagnostics, timestamps, or disclosure affordance:

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

The progress-log spec seeds a temporary running task through the same Postgres-backed task/runs/messages/events contract, verifies collapsed row layout in the browser, expands status/tool/generation rows, checks the trace-level collapse-all control, captures desktop and narrow-screen screenshots, marks the temporary task complete, and deletes it through the public API.

Run the SearXNG search progress acceptance test when changing the configured web-search tool or tool-call/result payloads:

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

The SearXNG spec creates a temporary task through the public API, seeds `searxng_search` tool-call and tool-result events through the Postgres-backed event contract, verifies the browser progress log hides raw tool names in collapsed rows while preserving `searxng_search` diagnostics in expanded JSON, captures screenshots, and deletes the task.

Run the session-context and long-term-memory acceptance test from `frontend/` when changing conversation history injection, memory recall, per-user memory isolation, or the visible "已载入会话上下文 / 已载入长期记忆" log rows:

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

The session-context spec sends one user turn through the real browser UI, seeds a canonical long-term preference memory row in Postgres, rebuilds the Qdrant index from that canonical store, sends a follow-up turn that should recall the previous message and preference, expands the context/memory diagnostics, and captures screenshots for the empty workspace, first prompt, first completion, follow-up draft, expanded memory logs, and recalled answer.

Run the history-menu affordance acceptance test from `frontend/` when changing the history sidebar menu trigger, rename/delete menu, focus state, or compact history layout:

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

The history-menu spec creates a temporary task through the public API, seeds one visible user-message history row through the same Postgres-backed task contract, verifies the three-dot menu trigger in hover and open states, captures screenshots, and deletes the task after the assertion.

Run the auto-title acceptance test from `frontend/` when changing first-message task creation, automatic history naming, or title normalization:

```bash
MYAGENT_E2E_BASE_URL=http://127.0.0.1:3001 \
MYAGENT_E2E_API_URL=http://127.0.0.1:8001 \
MYAGENT_E2E_EVIDENCE_DIR=./e2e-playwright/e2e-YYYYMMDDHHMMSS/auto-title-generation \
MYAGENT_E2E_ACCESS_TOKEN=... \
npx playwright test e2e-playwright/test_auto_title_generation.spec.mjs --reporter=line
```

The auto-title spec sends a first user message through the real browser UI, waits for the public message API response, asserts the returned history title is non-empty and at most 10 visible characters, verifies the same title appears in the left history sidebar, captures screenshots for the start, ready, visible-title, and selected-row states, then cancels/deletes the temporary task through the public API.

Run the resource-upload harness acceptance test from `frontend/` when changing upload formats, uploaded-resource contracts, or resource tool progress:

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

The resource-upload spec uses the real browser file picker path for `.docx`, `.xlsx`, `.json`, and `.txt`, uploads those files through the public API, seeds a completed run with resource-tool progress events, and captures screenshots for selection, uploaded state, tool progress, and completion.

Run the upload-preview design acceptance test from `frontend/` when changing the selected-file preview card, upload affordances, or responsive composer layout:

```bash
MYAGENT_E2E_BASE_URL=http://127.0.0.1:3001 \
MYAGENT_E2E_EVIDENCE_DIR=./e2e-playwright/e2e-YYYYMMDDHHMMSS/upload-preview-design \
npx playwright test e2e-playwright/test_upload_preview_design.spec.mjs --reporter=line
```

The upload-preview spec uses the real browser file picker path for supported files, verifies separate selected-file cards, filename-only display, replace control, hover-revealed per-file removal, core design-token colors, and captures desktop plus narrow-screen screenshots of the changed preview card.

Run the skill selector acceptance test from `frontend/` when changing the composer skill slash picker, chip shelf, keyboard selection, deletion behavior, or responsive skill selector styling:

```bash
MYAGENT_E2E_BASE_URL=http://127.0.0.1:3001 \
MYAGENT_E2E_EVIDENCE_DIR=./e2e-playwright/e2e-YYYYMMDDHHMMSS/skill-selector \
npx playwright test e2e-playwright/test_skill_selector.spec.mjs --reporter=line
```

The skill selector spec opens the real frontend page, provides a bounded project skill response for `code-review` and `web-research`, verifies slash filtering, keyboard and pointer selection, removable chip behavior, no accidental message send, and captures screenshots for the open picker, selected chip, and removed-chip states.

Run the full skill selector send-loop acceptance test when changing project skill payloads, message submission, task history reload, or the visible user-message contract:

```bash
MYAGENT_E2E_BASE_URL=http://127.0.0.1:3001 \
MYAGENT_E2E_API_URL=http://127.0.0.1:8001 \
MYAGENT_E2E_EVIDENCE_DIR=./e2e-playwright/e2e-YYYYMMDDHHMMSS/skill-selector-full-loop \
MYAGENT_E2E_ACCESS_TOKEN=... \
npx playwright test e2e-playwright/test_skill_selector_full_loop.spec.mjs --reporter=line
```

The full-loop spec does not mock `/api/skills`, `/api/tasks`, or message submission. It opens the real frontend, verifies the backend exposes `code-review` and `web-research`, selects `web-research`, sends a user message with the structured `skills` payload, checks the persisted user-visible `[$web-research]` reference, reloads task history, and captures desktop plus mobile screenshots.
