# MyAgent Playwright E2E

MyAgent already uses Playwright as the main browser-validation surface.

## Read first

- `AGENTS.md`
- `frontend/e2e-playwright/README.md`
- `frontend/package.json`
- the nearest neighboring spec under `frontend/e2e-playwright/`

## Evidence directory

Store local evidence under:

```text
frontend/e2e-playwright/e2e-YYYYMMDDHHMMSS/<feature>/
```

Do not commit timestamped evidence directories.

## Real-service expectation

For browser-visible regression work in this repo:

- prefer real frontend `http://127.0.0.1:3001`
- prefer real backend `http://127.0.0.1:8001` when the flow crosses API boundaries
- reuse repo env vars such as `MYAGENT_E2E_BASE_URL`, `MYAGENT_E2E_API_URL`, `MYAGENT_E2E_EVIDENCE_DIR`, and `MYAGENT_E2E_ACCESS_TOKEN`

## Common command shape

Run from `frontend/`:

```bash
MYAGENT_E2E_BASE_URL=http://127.0.0.1:3001 \
MYAGENT_E2E_API_URL=http://127.0.0.1:8001 \
MYAGENT_E2E_EVIDENCE_DIR=./e2e-playwright/e2e-YYYYMMDDHHMMSS/<feature> \
MYAGENT_E2E_ACCESS_TOKEN=... \
npx playwright test e2e-playwright/<spec>.spec.mjs --reporter=line
```

## Neighboring specs worth checking first

- `test_progress_log_disclosure.spec.mjs`
- `test_task_log_artifact_delivery.spec.mjs`
- `test_multi_session_thinking_audit.spec.mjs`
- `test_missing_upload_clarification_delivery_warning.spec.mjs`
- `test_runtime_contracts.spec.mjs`

Prefer extending the closest existing spec over inventing a new browser harness from scratch.
