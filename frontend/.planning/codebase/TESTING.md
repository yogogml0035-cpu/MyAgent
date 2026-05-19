# Testing Patterns

**Analysis Date:** 2026-05-19

## Test Framework

**Runner:**
- Node built-in `node:test` with `tsx` for TypeScript unit/source tests.
- Playwright via `@playwright/test` for browser E2E.

**Assertion Library:**
- `node:assert/strict` or `node:assert` for Node tests.
- Playwright `expect` for browser specs.

**Run Commands:**
```bash
cd frontend
npm test
npm run typecheck
npm run lint
npm run build
```

```bash
cd frontend
npm run e2e:runtime-contracts
npx playwright test e2e-playwright/test_upload_preview_design.spec.mjs --reporter=line
```

## Test File Organization

**Location:**
- State tests: `frontend/tests/state/test_*.test.ts`.
- Workspace/view/component boundary tests: `frontend/tests/workspace/test_*.test.ts`.
- Upload tests: `frontend/tests/upload/test_*.test.ts`.
- Model UI tests: `frontend/tests/model/test_*.test.ts`.
- Browser E2E specs: `frontend/e2e-playwright/test_*.spec.mjs`.
- Run-specific evidence: ignored `frontend/e2e-playwright/e2e-YYYYMMDDHHMMSS/`.

**Naming:**
- Node tests use `test_*.test.ts`.
- Playwright specs use `test_*.spec.mjs`.
- Existing standalone manual script `frontend/e2e-playwright/test_storage_memory_e2e.mjs` is not a normal Playwright `*.spec.mjs`.

**Structure:**
```text
frontend/tests/
├── model/test_*.test.ts
├── state/test_*.test.ts
├── upload/test_*.test.ts
└── workspace/test_*.test.ts

frontend/e2e-playwright/
├── test_*.spec.mjs
├── test_storage_memory_e2e.mjs
└── e2e-YYYYMMDDHHMMSS/<scenario>/ screenshots and local evidence
```

## Test Structure

**Suite Organization:**
```typescript
import assert from "node:assert/strict";
import test from "node:test";

import { normalizeTaskState } from "../../app/task-state";

test("normalizeTaskState maps unknown backend statuses to unknown instead of running", () => {
  const state = normalizeTaskState({ task_id: "task-1", status: "paused" }, "fallback");
  assert.equal(state.status, "unknown");
});
```

```javascript
import { test, expect } from "@playwright/test";

test("selected upload preview matches the warm-canvas design", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByLabel(/上传/)).toBeVisible();
});
```

**Patterns:**
- Pure state/projection tests call exported helpers directly.
- Architecture tests inspect source files for boundary invariants.
- Browser E2E specs use public API seeding where needed, then verify visible browser behavior and screenshots.
- Screenshot evidence goes under a scenario-specific evidence directory.

## Mocking

**Framework:**
- Node tests mainly use pure function inputs and source inspection rather than heavy mocks.
- Playwright specs use browser/page/request fixtures and may seed backend state through real public API or Postgres-backed contracts.

**What to Mock:**
- In Node tests, mock by passing representative backend payload objects to normalizers/projection helpers.
- Source-inspection tests may read component and CSS files to guard architecture/design invariants.

**What NOT to Mock:**
- Do not replace browser E2E with Node tests for behavior-changing UI or full-stack flows.
- Do not weaken artifact URL security by bypassing `buildArtifactRequest()`.
- Do not assume every backend event payload is trusted; normalizer tests should include malformed and unknown fields.

## Fixtures and Factories

**Test Data:**
- Inline backend payload objects in `frontend/tests/state/test_task_state.test.ts`.
- Inline `ExecutionLog`, `TaskRunRecord`, and artifact records in `frontend/tests/workspace/test_workspace_view.test.ts`.
- Playwright specs create temporary files and evidence directories under `MYAGENT_E2E_EVIDENCE_DIR`.

**Location:**
- Shared fixtures are not currently centralized; keep small factories near the test that needs them.
- Stable browser acceptance instructions belong in `frontend/e2e-playwright/README.md`.

## Coverage

**Requirements:**
- No numeric coverage threshold is configured.
- Delivery rules require relevant Playwright coverage and screenshot evidence for behavior-changing UI/full-stack work.

**View Coverage:**
```bash
# No coverage command is configured in frontend/package.json.
```

## Test Types

**Unit/Source Tests:**
- State normalization and artifact security: `frontend/tests/state/test_task_state.test.ts`.
- View projections and log rows: `frontend/tests/workspace/test_workspace_view.test.ts`.
- Component/API export boundaries: `frontend/tests/workspace/test_task_workspace.test.ts`, `frontend/tests/workspace/test_task_api.test.ts`.
- Architecture and CSS invariants: `frontend/tests/workspace/test_frontend_architecture.test.ts`.
- Upload filtering/design source checks: `frontend/tests/upload/`.
- Model display helpers: `frontend/tests/model/`.

**Browser E2E Tests:**
- Runtime contracts: `frontend/e2e-playwright/test_runtime_contracts.spec.mjs`.
- Progress log disclosure: `frontend/e2e-playwright/test_progress_log_disclosure.spec.mjs`.
- SearXNG progress: `frontend/e2e-playwright/test_searxng_search_progress.spec.mjs`.
- Session context/memory: `frontend/e2e-playwright/test_session_context_memory.spec.mjs`.
- Event cursor recovery: `frontend/e2e-playwright/test_event_cursor_recovery.spec.mjs`.
- History menu affordance: `frontend/e2e-playwright/test_history_menu_affordance.spec.mjs`.
- Auto title generation: `frontend/e2e-playwright/test_auto_title_generation.spec.mjs`.
- Resource upload harness: `frontend/e2e-playwright/test_resource_upload_harness.spec.mjs`.
- Upload preview design: `frontend/e2e-playwright/test_upload_preview_design.spec.mjs`.

## Common Patterns

**Async Testing:**
```typescript
import { describe, it } from "node:test";
import assert from "node:assert";

void describe("task-api exports", () => {
  void it("should export expected functions", async () => {
    const api = await import("../../lib/task-api");
    assert.strictEqual(typeof api.fetchTask, "function");
  });
});
```

**Error Testing:**
```typescript
assert.throws(
  () => buildArtifactRequest(badArtifact, "task-1", "http://localhost:8001", "secret-token"),
  /产物 URL 不受信任/,
);
```

**Browser Evidence:**
- Require `MYAGENT_E2E_EVIDENCE_DIR` for screenshot-producing specs.
- Capture screenshots at meaningful states, not only at the final page.
- Keep evidence folders ignored and reference paths in delivery notes.

---

*Testing analysis: 2026-05-19*
*Update when frontend test commands, organization, or E2E contracts change*
