# Codebase Concerns

**Analysis Date:** 2026-05-19

## Tech Debt

**State normalization and view projection are oversized:**
- Issue: `frontend/app/task-state.ts` and `frontend/app/workspace-view.ts` contain many backend schema translations, event metadata normalizers, artifact trust checks, progress-log grouping, diagnostics JSON shaping, and conversation ordering rules.
- Files: `frontend/app/task-state.ts`, `frontend/app/workspace-view.ts`, `frontend/tests/state/test_task_state.test.ts`, `frontend/tests/workspace/test_workspace_view.test.ts`.
- Impact: Event payload changes can require edits across several dense sections and large tests.
- Fix approach: Keep behavior stable, then extract smaller modules by concern: wire normalization, artifact security, live metadata, run grouping, diagnostics rendering, and conversation ordering.

**Visual behavior is tightly coupled to global CSS class names:**
- Issue: Components rely on large global CSS selectors in `frontend/app/globals.css`.
- Files: `frontend/components/chat/*.tsx`, `frontend/app/globals.css`, `frontend/tests/workspace/test_frontend_architecture.test.ts`.
- Impact: Renaming a class or moving markup can silently affect multiple states and responsive views.
- Fix approach: Preserve class/test invariants when refactoring and add Playwright screenshots for visual changes.

**Runtime E2E scripts have mixed shapes:**
- Issue: Most browser specs are Playwright `*.spec.mjs`, but `frontend/e2e-playwright/test_storage_memory_e2e.mjs` launches Chromium directly and is not in `package.json`.
- Files: `frontend/e2e-playwright/test_storage_memory_e2e.mjs`, `frontend/package.json`, `frontend/e2e-playwright/README.md`.
- Impact: Maintainers can assume every `test_*` file is a normal Playwright spec and skip this script accidentally.
- Fix approach: Convert it to a Playwright spec or move it to a clearly named manual tools directory.

## Known Bugs

**No confirmed frontend-only functional bug is documented in source comments:**
- Symptoms: None documented as a current open frontend bug in code comments.
- Trigger: N/A.
- Workaround: N/A.
- Root cause: N/A.
- Note: System-level concerns still exist around E2E discoverability, SSE recovery, and event projection.

## Security Considerations

**Browser-visible token and SSE query token are sensitive:**
- Risk: `NEXT_PUBLIC_MYAGENT_TOKEN` is exposed to browser JavaScript, and SSE sends it as a query parameter.
- Files: `frontend/lib/task-api.ts`, `frontend/app/task-state.ts`.
- Current mitigation: Token use is centralized and artifact URLs are restricted before token attachment.
- Recommendations: Never put provider keys, customer data, database URLs, or private examples in `NEXT_PUBLIC_*`. Avoid logging full SSE URLs.

**Artifact URLs must stay first-party and task-scoped:**
- Risk: A malicious backend payload or future bug could try to send artifact requests to external origins with the token attached.
- Files: `frontend/app/task-state.ts`, `frontend/lib/task-api.ts`, `frontend/tests/state/test_task_state.test.ts`.
- Current mitigation: `buildArtifactRequest()` checks origin, path shape, task ID, run ID, artifact name, query, and hash.
- Recommendations: Keep all artifact fetches behind `buildArtifactRequest()`.

**HTML artifact preview is sandboxed but still untrusted content:**
- Risk: Large or misleading HTML artifacts can still consume resources or visually impersonate trusted UI inside the iframe.
- Files: `frontend/hooks/use-task-workspace.ts`.
- Current mitigation: Preview wrapper uses a sandboxed iframe with no scripts and a restrictive CSP.
- Recommendations: Keep sandbox empty and add size/type controls if large HTML artifacts become common.

**Upload filtering is client-side convenience, not security:**
- Risk: Browser extension filtering in `frontend/app/file-upload.ts` can be bypassed.
- Files: `frontend/app/file-upload.ts`, `frontend/hooks/use-task-workspace.ts`.
- Current mitigation: Backend performs authoritative extension and size validation.
- Recommendations: Treat frontend upload checks as UX only.

## Performance Bottlenecks

**Live-log projection rebuilds large diagnostics repeatedly:**
- Problem: `buildLiveLogItems()` sorts logs, merges diagnostics, serializes JSON, and caps tool-result display on each projection.
- Files: `frontend/app/workspace-view.ts`, `frontend/components/chat/TaskConversation.tsx`.
- Cause: Pure rebuilds are easy to test but not incremental.
- Improvement path: Memoize by run/log IDs and consider virtualizing diagnostics for long-running tasks.

**Task state normalization scales with full event history:**
- Problem: `normalizeTaskState()` maps all events and messages in a task response.
- Files: `frontend/app/task-state.ts`, `frontend/lib/task-api.ts`, `frontend/hooks/use-task-workspace.ts`.
- Cause: Backend `get_task()` can return full event history by default.
- Improvement path: Prefer `includeEvents=false` for lightweight refreshes and add pagination if task histories grow.

**Many ignored evidence folders exist locally:**
- Problem: `frontend/e2e-playwright/e2e-*` evidence folders accumulate screenshots and logs.
- Files: `frontend/e2e-playwright/`, `.gitignore`.
- Cause: Evidence is intentionally local and ignored.
- Improvement path: Add a local cleanup command or retention guidance if disk usage grows.

## Fragile Areas

**Backend event schema projection:**
- Why fragile: Frontend projections depend on `type`, `payload.live`, run IDs, seq values, tool names, answer/thinking stream chunks, and final-answer boundaries.
- Files: `frontend/app/task-state.ts`, `frontend/app/workspace-view.ts`, `backend/app/streaming/event_converter.py`.
- Safe modification: Add backend converter tests and frontend state/view tests for every new event shape.
- Test coverage: Strong Node tests; choose Playwright coverage by affected user-visible path.

**SSE retry and polling recovery:**
- Why fragile: Event replay can duplicate records, so merging by ID and last-event polling must remain aligned with backend cursor behavior.
- Files: `frontend/hooks/use-task-workspace.ts`, `frontend/lib/task-api.ts`, `frontend/e2e-playwright/test_event_cursor_recovery.spec.mjs`.
- Safe modification: Preserve `mergeExecutionLogs()` de-duplication and re-run cursor recovery E2E when changing stream behavior.

**Artifact open/download flow:**
- Why fragile: It combines backend URL shape, token attachment, object URL lifecycle, popup behavior, sandboxed preview, and downloads.
- Files: `frontend/app/task-state.ts`, `frontend/lib/task-api.ts`, `frontend/hooks/use-task-workspace.ts`.
- Safe modification: Keep `buildArtifactRequest()` as the only URL builder and update browser runtime-contract E2E for URL shape changes.

**History rename/delete menu:**
- Why fragile: Sidebar menu uses local open/rename/action state, outside-click/Escape listeners, `window.confirm`, and active-task delete guards.
- Files: `frontend/components/chat/ChatSidebar.tsx`, `frontend/hooks/use-task-workspace.ts`.
- Safe modification: Re-run history-menu Playwright spec and source invariant tests after changes.

**Upload preview and composer layout:**
- Why fragile: File input state, hidden input reset, replace/remove controls, model picker, send/stop button, and responsive CSS interact in a compact surface.
- Files: `frontend/components/chat/ChatComposer.tsx`, `frontend/app/globals.css`, `frontend/e2e-playwright/test_upload_preview_design.spec.mjs`.
- Safe modification: Use desktop and narrow screenshots for any visual or interaction change.

## Scaling Limits

**No frontend-side pagination or virtualization:**
- Current capacity: Local single-user task history and moderate log volume.
- Limit: Large histories or long-running event streams can slow render/projection.
- Symptoms at limit: Slow task switching, large log panels, expensive diagnostics JSON generation.
- Scaling path: Backend pagination plus frontend virtualization/memoization.

**Frontend assumes a single backend origin:**
- Current capacity: One configured backend base URL.
- Limit: Multi-tenant/multi-user or multiple backend environments require explicit routing/account model.
- Scaling path: Add login/session and environment selection before multi-user deployment.

## Dependencies at Risk

**Next/React major behavior changes:**
- Risk: App router, typegen, strict TypeScript, and React 19 behavior can change with upgrades.
- Files: `frontend/package.json`, `frontend/package-lock.json`, `frontend/app/`.
- Migration plan: Run typecheck, Node tests, lint, build, and selected Playwright specs after upgrades.

**Playwright specs depend on local service/env setup:**
- Risk: Specs fail or are skipped if backend/frontend services, Postgres container, tokens, or evidence dir env vars are missing.
- Files: `frontend/e2e-playwright/README.md`, `frontend/e2e-playwright/test_*.spec.mjs`.
- Migration plan: Keep README commands current and add helper scripts only if they preserve screenshot evidence requirements.

## Missing Critical Features

**Browser E2E is not a default frontend CI gate:**
- Problem: `frontend/package.json` exposes `e2e:runtime-contracts`, but the normal CI-oriented scripts are typecheck, Node tests, lint, and build.
- Blocks: Browser regressions can pass automated frontend CI unless manually selected E2E runs are performed.
- Implementation complexity: Medium; needs reliable service orchestration, env, and artifact handling.

**No user/session UI:**
- Problem: Frontend has no login or account model and uses one optional public token.
- Blocks: Multi-user task isolation, per-user history, role-based artifact access, and token rotation UX.
- Implementation complexity: High and coupled to backend auth changes.

**No retention/cleanup UI for local history/artifacts:**
- Problem: Users can delete individual conversations, but there is no quota, retention, bulk cleanup, or evidence cleanup UI.
- Blocks: Long-running local deployments with many tasks and artifacts.
- Implementation complexity: Medium.

## Test Coverage Gaps

**Real browser E2E remains manual/selected:**
- What's not tested by `npm test`: Actual browser flows for task creation, upload, SSE, artifacts, history menus, responsive layout, and screenshots.
- Risk: Node/source tests can pass while browser behavior regresses.
- Priority: High.

**Large log/task performance is not measured:**
- What's not tested: Thousands of events/messages/artifacts in a single task.
- Risk: Projection and rendering slowdowns can appear only in long-running sessions.
- Priority: Medium.

**Standalone storage-memory E2E is outside normal spec discovery:**
- What's not tested by standard Playwright commands: `frontend/e2e-playwright/test_storage_memory_e2e.mjs`.
- Risk: Storage/memory browser behavior covered there can be skipped.
- Priority: Medium.

---

*Concerns audit: 2026-05-19*
*Update as frontend risks are fixed or newly discovered*
