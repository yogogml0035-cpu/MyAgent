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

The progress-log spec seeds a temporary running task through the same Postgres-backed task/runs/messages/events contract, verifies collapsed row layout in the browser, expands status/tool/generation rows, captures screenshots, marks the temporary task complete, and deletes it through the public API.

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
