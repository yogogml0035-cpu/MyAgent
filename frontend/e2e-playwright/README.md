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
npm run e2e:runtime-contracts
```
