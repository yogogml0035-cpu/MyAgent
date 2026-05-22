# Testing Patterns

**Analysis Date:** 2026-05-22

## Test Framework

**Runner:**
- Unit runner: Node.js built-in `node:test`, invoked through `tsx` for TypeScript files.
- E2E runner: Playwright `@playwright/test` 1.60.x from `frontend/package.json`.
- Config: Not detected for Node test, Jest, Vitest, or Playwright config files in `frontend/`; tests rely on CLI defaults and per-spec setup.

**Assertion Library:**
- Unit assertions use Node assertions: `node:assert/strict` in most files and `node:assert` in `frontend/tests/workspace/test_task_api.test.ts` and `frontend/tests/workspace/test_task_workspace.test.ts`.
- E2E assertions use Playwright `expect` from `@playwright/test`.

**Run Commands:**
```bash
npm test                      # Run all Node unit tests from frontend/
npm run typecheck             # Generate Next types and run TypeScript no-emit checking
npm run lint                  # Run ESLint with zero warnings
npm run build                 # Build the Next.js production bundle
npm run e2e:runtime-contracts # Run the runtime contract Playwright spec
npx playwright test e2e-playwright/test_skill_selector.spec.mjs --reporter=line # Run one E2E spec
```

## Test File Organization

**Location:**
- Unit tests live under `frontend/tests/<area>/` and import modules from `frontend/app/`, `frontend/hooks/`, `frontend/lib/`, and `frontend/components/`.
- E2E acceptance specs live under `frontend/e2e-playwright/` and use local evidence folders under `frontend/e2e-playwright/e2e-YYYYMMDDHHMMSS/`.

**Naming:**
- Unit tests are named `test_*.test.ts`: `frontend/tests/state/test_task_state.test.ts`, `frontend/tests/workspace/test_workspace_view.test.ts`, `frontend/tests/upload/test_file_upload.test.ts`.
- Playwright specs are named `test_*.spec.mjs` for most browser specs: `frontend/e2e-playwright/test_runtime_contracts.spec.mjs`, `frontend/e2e-playwright/test_upload_preview_design.spec.mjs`.
- One Playwright file uses `.mjs` without `.spec`: `frontend/e2e-playwright/test_storage_memory_e2e.mjs`; run it explicitly when needed.

**Structure:**
```text
frontend/tests/
├── model/       # Model picker presentation helpers
├── state/       # Task state normalization, artifact request safety, payloads
├── upload/      # Upload file support and selected-file UI design guardrails
└── workspace/   # Workspace view helpers, hook boundaries, API exports, component source contracts

frontend/e2e-playwright/
├── README.md                         # E2E evidence and scenario command guide
├── test_runtime_contracts.spec.mjs   # Live backend/frontend artifact and upload contract
├── test_*_spec.mjs                   # Browser acceptance scenarios
└── e2e-YYYYMMDDHHMMSS/               # Local screenshots and artifacts, not committed
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

**Patterns:**
- Prefer top-level `test("behavior", () => {})` for pure helpers, as in `frontend/tests/state/test_task_state.test.ts` and `frontend/tests/workspace/test_workspace_view.test.ts`.
- Use `describe` / `it` only for grouped module export or source-boundary checks, as in `frontend/tests/workspace/test_task_api.test.ts` and `frontend/tests/workspace/test_task_workspace.test.ts`.
- Keep test names behavior-oriented and specific: examples include "buildArtifactRequest rejects external artifact URLs before sending tokens" in `frontend/tests/state/test_task_state.test.ts` and "scrollLogListToBottomIfPinned does not fight intentional upward scrolling" in `frontend/tests/workspace/test_task_conversation_scroll.test.ts`.
- Use direct assertions against full returned objects when the helper is pure and deterministic: `assert.deepEqual` in `frontend/tests/upload/test_file_upload.test.ts` and `frontend/tests/model/test_model_ui.test.ts`.
- Use source-text assertions only for architectural boundaries, visual token guards, or generated/config constraints that are otherwise hard to execute in Node: `frontend/tests/workspace/test_frontend_architecture.test.ts`, `frontend/tests/workspace/test_task_workspace.test.ts`, `frontend/tests/upload/test_upload_preview_design.test.ts`.

## Mocking

**Framework:** No standalone mocking framework is used.

**Patterns:**
```typescript
const originalFetch = globalThis.fetch;

globalThis.fetch = (async (input, init) => {
  return new Response(JSON.stringify([{ name: "web-research", description: "Search" }]), {
    status: 200,
  });
}) as typeof fetch;

try {
  assert.deepStrictEqual(await api.fetchSkillOptions(), [
    { name: "web-research", description: "Search" },
  ]);
} finally {
  globalThis.fetch = originalFetch;
}
```

**What to Mock:**
- Mock `globalThis.fetch` in Node unit tests when exercising browser REST adapters without a live backend, as in `frontend/tests/workspace/test_task_api.test.ts`.
- Mock DOM-like objects with minimal typed shapes for pure DOM helpers, as in `frontend/tests/workspace/test_task_conversation_scroll.test.ts`.
- Use `page.route` only for bounded browser scenarios that focus on frontend-only interactions, such as skill slash picker behavior in `frontend/e2e-playwright/test_skill_selector.spec.mjs` and resource upload harness message interception in `frontend/e2e-playwright/test_resource_upload_harness.spec.mjs`.

**What NOT to Mock:**
- Do not mock the runtime task contract path when validating backend/frontend integration; `frontend/e2e-playwright/test_runtime_contracts.spec.mjs` uses the real frontend, real backend API, task storage, and artifacts.
- Do not replace live browser acceptance with Node-only source assertions for behavior changes. `frontend/README.md` requires browser-side E2E for bug fixes, features, and behavior changes.
- Do not commit credentials, provider keys, access tokens, customer documents, or private local paths in mocks, fixtures, screenshots, or evidence folders.

## Fixtures and Factories

**Test Data:**
```typescript
function baseState(overrides: Partial<TaskState> = {}): TaskState {
  return {
    id: "task-1",
    status: "running",
    statusLabel: "running",
    runs: [],
    messages: [],
    logs: [],
    artifacts: [],
    uploadCount: 0,
    needsInput: null,
    ...overrides,
  };
}
```

**Location:**
- Keep small unit fixtures inline in the test file: `baseState` in `frontend/tests/state/test_task_state.test.ts`, `candidate` in `frontend/tests/upload/test_file_upload.test.ts`, `scrollElement` in `frontend/tests/workspace/test_task_conversation_scroll.test.ts`.
- Keep E2E fixture writers inside the spec that owns them: `writeFixtureFiles` in `frontend/e2e-playwright/test_upload_preview_design.spec.mjs`, `seedCompletedArtifactTask` in `frontend/e2e-playwright/test_runtime_contracts.spec.mjs`.
- Store run-specific screenshots and generated fixture files under `frontend/e2e-playwright/e2e-YYYYMMDDHHMMSS/<scenario>/`, as documented in `frontend/e2e-playwright/README.md`.

## Coverage

**Requirements:** No enforced coverage threshold or coverage command is detected in `frontend/package.json`.

**View Coverage:**
```bash
# Not configured in frontend/package.json.
```

**Notes:**
- `frontend/.gitignore` ignores `coverage/`, but no coverage tool is configured.
- Use focused unit tests plus Playwright acceptance evidence as the active verification practice.

## Test Types

**Unit Tests:**
- Scope pure transformations, data normalization, formatting, request building, security guards, source boundaries, and DOM-independent helpers.
- Main files: `frontend/tests/state/test_task_state.test.ts`, `frontend/tests/workspace/test_workspace_view.test.ts`, `frontend/tests/workspace/test_task_conversation_scroll.test.ts`, `frontend/tests/model/test_model_ui.test.ts`, `frontend/tests/upload/test_file_upload.test.ts`, `frontend/tests/state/test_skill_selection.test.ts`.
- Unit tests run in Node, so browser APIs must be mocked or avoided. Keep browser-heavy behavior in Playwright.

**Integration Tests:**
- Browser/runtime integration lives in Playwright specs under `frontend/e2e-playwright/`.
- `frontend/e2e-playwright/test_runtime_contracts.spec.mjs` verifies live task creation, model metadata, artifact open/download, upload limits, access token propagation, and browser-visible contract behavior.
- `frontend/e2e-playwright/test_skill_selector_full_loop.spec.mjs` verifies real `/api/skills`, task creation, message submission, selected skill payloads, persisted user-visible skill references, and history reload.
- Specs that seed backend state use public API calls plus Postgres-backed setup helpers through Docker, as in `frontend/e2e-playwright/test_progress_log_disclosure.spec.mjs`, `frontend/e2e-playwright/test_multi_session_thinking_audit.spec.mjs`, and `frontend/e2e-playwright/test_history_scroll_clear.spec.mjs`.

**E2E Tests:**
- Playwright E2E is required for frontend behavior changes.
- Use actual services on frontend `3001` and backend `8001` for runtime-contract and full-loop specs unless the spec is explicitly frontend-only.
- Save screenshots under `frontend/e2e-playwright/e2e-YYYYMMDDHHMMSS/<scenario>/` and keep these evidence folders uncommitted.
- For visual or interaction work, capture desktop and narrow/mobile states when the scenario affects responsive layout.

## Common Patterns

**Async Testing:**
```typescript
test("fetchSkillOptions keeps only browser-safe string fields", async () => {
  const api = await import("../../lib/task-api");
  const originalFetch = globalThis.fetch;

  globalThis.fetch = (async () =>
    new Response(JSON.stringify([{ name: "web-research", description: "Search" }]), {
      status: 200,
    })) as typeof fetch;

  try {
    assert.deepStrictEqual(await api.fetchSkillOptions(), [
      { name: "web-research", description: "Search" },
    ]);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
```

**Error Testing:**
```typescript
test("buildArtifactRequest rejects external artifact URLs before sending tokens", () => {
  assert.throws(
    () =>
      buildArtifactRequest(
        { id: "report", name: "report.html", url: "https://evil.example/report.html" },
        "task-1",
        "http://localhost:8001",
        "secret-token",
      ),
    /产物 URL 不受信任/,
  );
});
```

**Playwright E2E Pattern:**
```javascript
import fs from "node:fs";
import path from "node:path";
import { expect, test } from "@playwright/test";

const BASE_URL = process.env.MYAGENT_E2E_BASE_URL || "http://127.0.0.1:3001";
const EVIDENCE_DIR = process.env.MYAGENT_E2E_EVIDENCE_DIR;

test.use({ baseURL: BASE_URL });

test("scenario name", async ({ page }) => {
  const evidenceDir = requirePath(EVIDENCE_DIR, "MYAGENT_E2E_EVIDENCE_DIR");
  fs.mkdirSync(evidenceDir, { recursive: true });

  await page.goto("/");
  await expect(page.getByPlaceholder("尽管问...")).toBeVisible();
  await page.screenshot({ fullPage: true, path: path.join(evidenceDir, "01-ready.png") });
});
```

## Verification Practices

**Standard Quality Gate:**
- Run `npm run typecheck`, `npm test`, `npm run lint`, and `npm run build` from `frontend/` for code changes that affect TypeScript, React, or build behavior.
- Run `git diff --check` for whitespace and conflict marker checks when changing docs or code.

**Browser Acceptance:**
- For behavior changes, run a targeted Playwright spec plus any adjacent regression spec named in `frontend/e2e-playwright/README.md`.
- For runtime contracts, run `npm run e2e:runtime-contracts` with `MYAGENT_E2E_BASE_URL`, `MYAGENT_E2E_API_URL`, `MYAGENT_E2E_TASK_ROOT`, `MYAGENT_E2E_EVIDENCE_DIR`, and local access-token/Postgres env as needed.
- For UI-only controls that can be isolated safely, use bounded `page.route` mocks and still capture screenshots, as in `frontend/e2e-playwright/test_skill_selector.spec.mjs`.
- For full task lifecycle, do not mock `/api/tasks`, `/api/skills`, or message submission; use `frontend/e2e-playwright/test_skill_selector_full_loop.spec.mjs` or `frontend/e2e-playwright/test_runtime_contracts.spec.mjs`.

**Scenario Selection:**
- Upload formats or selected file preview: `frontend/tests/upload/test_file_upload.test.ts`, `frontend/tests/upload/test_upload_preview_design.test.ts`, `frontend/e2e-playwright/test_upload_preview_design.spec.mjs`, `frontend/e2e-playwright/test_resource_upload_harness.spec.mjs`.
- Skill slash picker or selected skill payloads: `frontend/tests/state/test_skill_selection.test.ts`, `frontend/tests/workspace/test_task_api.test.ts`, `frontend/e2e-playwright/test_skill_selector.spec.mjs`, `frontend/e2e-playwright/test_skill_selector_full_loop.spec.mjs`.
- Progress timeline, logs, diagnostics, or copy behavior: `frontend/tests/workspace/test_workspace_view.test.ts`, `frontend/tests/workspace/test_task_conversation_scroll.test.ts`, `frontend/e2e-playwright/test_progress_log_disclosure.spec.mjs`, `frontend/e2e-playwright/test_multi_session_thinking_audit.spec.mjs`.
- History sidebar rename/delete/clear or scroll behavior: `frontend/tests/workspace/test_frontend_architecture.test.ts`, `frontend/e2e-playwright/test_history_menu_affordance.spec.mjs`, `frontend/e2e-playwright/test_history_scroll_clear.spec.mjs`.
- Model picker or unavailable model behavior: `frontend/tests/model/test_model_ui.test.ts`, `frontend/tests/workspace/test_task_workspace.test.ts`, `frontend/e2e-playwright/test_runtime_contracts.spec.mjs`.
- Artifact URL safety, preview, download, or access tokens: `frontend/tests/state/test_task_state.test.ts`, `frontend/tests/workspace/test_task_workspace.test.ts`, `frontend/e2e-playwright/test_runtime_contracts.spec.mjs`.

---

*Testing analysis: 2026-05-22*
