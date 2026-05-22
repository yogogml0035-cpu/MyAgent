# Codebase Concerns

**Analysis Date:** 2026-05-22

## Tech Debt

**Workspace orchestration hook:**
- Issue: `frontend/hooks/use-task-workspace.ts` centralizes API bootstrapping, task selection, SSE connection/retry, submission, uploads, history mutation, copy feedback, artifact download, and artifact preview in one 826-line client hook.
- Files: `frontend/hooks/use-task-workspace.ts`, `frontend/components/chat/TaskWorkspace.tsx`, `frontend/lib/task-api.ts`
- Impact: Small behavior changes can accidentally couple unrelated state flags such as `isSubmittingTask`, `isSwitchingConversation`, `isMutatingConversation`, and `isStoppingTask`. Regression risk is highest around send protection, active task switching, and history mutation.
- Fix approach: Split into focused hooks such as `useTaskBootstrap`, `useTaskStream`, `useTaskSubmission`, `useConversationHistory`, and `useArtifacts`, keeping `frontend/components/chat/TaskWorkspace.tsx` as the composition boundary.

**Normalization and display formatting module size:**
- Issue: `frontend/app/task-state.ts` combines public API types, backend payload normalization, event-specific trace normalization, translation copy, artifact URL validation, and request failure formatting in one 1,240-line module.
- Files: `frontend/app/task-state.ts`, `frontend/lib/task-api.ts`, `frontend/tests/state/test_task_state.test.ts`
- Impact: Adding a backend event type or trace schema requires editing a large shared module that also owns unrelated URL/security helpers. This increases merge conflict and accidental behavior-change risk.
- Fix approach: Keep exported types in `frontend/app/task-state.ts`, but move event trace normalizers to `frontend/app/task-events.ts`, artifact URL helpers to `frontend/app/artifacts.ts`, and translation tables to `frontend/app/task-copy.ts`.

**Conversation rendering helper size:**
- Issue: `frontend/app/workspace-view.ts` is 1,585 lines and owns history item shaping, live log grouping, diagnostics JSON, progress copy, artifact/run grouping, sorting, placeholder suppression, and keyboard intent helpers.
- Files: `frontend/app/workspace-view.ts`, `frontend/components/chat/TaskConversation.tsx`, `frontend/tests/workspace/test_workspace_view.test.ts`
- Impact: UI rendering rules and pure data transformations are tightly coupled. Tests are extensive, but the file is difficult to reason about during changes to progress logs, streaming answer placement, or artifact grouping.
- Fix approach: Split by domain: `frontend/app/log-view.ts`, `frontend/app/run-groups.ts`, `frontend/app/conversation-stream.ts`, and `frontend/app/history-view.ts`, with tests moved beside the extracted behavior groups.

**Source-string tests as architecture locks:**
- Issue: Several tests assert implementation text with `readFileSync`, `.includes()`, and regexes rather than executing behavior.
- Files: `frontend/tests/workspace/test_frontend_architecture.test.ts`, `frontend/tests/workspace/test_task_workspace.test.ts`, `frontend/tests/upload/test_upload_preview_design.test.ts`, `frontend/tests/workspace/test_workspace_view.test.ts`
- Impact: Refactors that preserve behavior can fail tests, while behavior regressions can pass if the guarded strings remain present.
- Fix approach: Prefer exported pure helpers and component/browser assertions. Keep source-string guards only for intentional architectural constraints such as "home route delegates to `TaskWorkspace`".

## Known Bugs

**Frontend documentation drift on Next build output:**
- Symptoms: `frontend/README.md` says the dev server and production builds both write `.next`, while `frontend/next.config.mjs` uses `.next-dev` for development and `.next` for production. `frontend/e2e-playwright/README.md` also mentions `.next/dev`, which does not match `frontend/next.config.mjs`.
- Files: `frontend/README.md`, `frontend/e2e-playwright/README.md`, `frontend/next.config.mjs`, `frontend/tests/workspace/test_frontend_architecture.test.ts`
- Trigger: A developer follows the README while diagnosing manifest/build-output issues or cleaning generated files.
- Workaround: Treat `frontend/next.config.mjs` as authoritative: development output is `frontend/.next-dev`, production build output is `frontend/.next`.
- Fix approach: Update the README text and any E2E guide references to match `distDir: isDevServer ? ".next-dev" : ".next"`.

## Security Considerations

**Browser-visible access token boundary:**
- Risk: `NEXT_PUBLIC_MYAGENT_TOKEN` and legacy `NEXT_PUBLIC_AGENT_CHAT_TOKEN` are compiled into browser code and sent as `X-MyAgent-Token` on fetch requests. SSE appends the same token as a `token` query parameter because `EventSource` cannot send custom headers.
- Files: `frontend/lib/task-api.ts`, `frontend/.env.example`, `frontend/README.md`, `frontend/e2e-playwright/test_runtime_contracts.spec.mjs`
- Current mitigation: The token is optional, `.env.local` is ignored by `frontend/.gitignore`, and artifact fetches validate trusted origins before sending headers through `frontend/app/task-state.ts`.
- Recommendations: Treat these tokens as local browser access tokens only, never provider secrets. Prefer short-lived development tokens, avoid logging full SSE URLs, and keep provider/API credentials exclusively in backend environment files.

**Artifact URL and HTML preview protections are critical:**
- Risk: Backend-provided artifact metadata can include a URL and HTML artifacts can contain script. Any relaxation of URL validation or sandbox preview logic can leak the browser token or execute untrusted report code.
- Files: `frontend/app/task-state.ts`, `frontend/hooks/use-task-workspace.ts`, `frontend/components/chat/TaskConversation.tsx`, `frontend/tests/state/test_task_state.test.ts`, `frontend/tests/workspace/test_task_workspace.test.ts`, `frontend/e2e-playwright/test_runtime_contracts.spec.mjs`
- Current mitigation: `buildArtifactRequest` rejects external origins, wrong task routes, query strings, hashes, encoded slash/backslash segments, and mismatched artifact names. HTML reports are opened through `buildSandboxedArtifactPreviewDocument` inside an `iframe sandbox=""` with a restrictive CSP.
- Recommendations: Keep artifact fetches centralized in `frontend/lib/task-api.ts`. Do not render HTML artifacts with `dangerouslySetInnerHTML`, top-level `location.replace(blobUrl)`, or direct backend URLs.

**Raw diagnostics can expose sensitive runtime context:**
- Risk: Expanded progress rows and copy actions expose diagnostic JSON, including event payloads, tool parameters, file audit metadata, and memory/context summaries.
- Files: `frontend/app/workspace-view.ts`, `frontend/components/chat/TaskConversation.tsx`, `frontend/tests/workspace/test_workspace_view.test.ts`, `frontend/e2e-playwright/README.md`
- Current mitigation: Tests verify that selected raw provider chunks, private source paths, and hidden diagnostic values do not appear in rendered normalized logs.
- Recommendations: Keep redaction tests for every new event payload field. Treat screenshots and copied diagnostics as sensitive local evidence; do not commit timestamped E2E evidence folders or logs containing customer documents.

**Upload filtering is extension-only in the browser:**
- Risk: `frontend/app/file-upload.ts` accepts files by filename suffix and does not inspect MIME, size, JSON validity, or document structure before upload.
- Files: `frontend/app/file-upload.ts`, `frontend/components/chat/ChatComposer.tsx`, `frontend/tests/upload/test_file_upload.test.ts`, `frontend/e2e-playwright/test_runtime_contracts.spec.mjs`
- Current mitigation: Unsupported extensions are rejected client-side, and backend validation is expected to reject invalid JSON or oversized multipart payloads.
- Recommendations: Keep backend validation authoritative. Add optional client-side size warnings and JSON parse preflight only as UX improvements, not as security controls.

## Performance Bottlenecks

**Unvirtualized history, logs, diagnostics, and messages:**
- Problem: The frontend renders every task summary, conversation item, live log row, expanded details block, and full diagnostics `<pre>` directly in the DOM.
- Files: `frontend/components/chat/ChatSidebar.tsx`, `frontend/components/chat/TaskConversation.tsx`, `frontend/app/workspace-view.ts`
- Cause: `fetchTaskSummaries()` retrieves all visible task summaries, `buildConversationStreamItems()` processes all messages/groups, and each progress group can render complete JSON diagnostics.
- Improvement path: Add pagination or windowing for `historyItems`, virtualize `.logList`, and lazy-build `runDiagnosticsText` only when the diagnostics panel is opened.

**Repeated sorting and regrouping on every state change:**
- Problem: `buildRunActivityGroups()`, `buildConversationStreamItems()`, and `buildLiveLogItems()` repeatedly sort logs/runs and reconstruct maps as arrays grow.
- Files: `frontend/app/workspace-view.ts`, `frontend/hooks/use-task-workspace.ts`, `frontend/components/chat/TaskConversation.tsx`
- Cause: `useMemo` boundaries still recompute full derived structures whenever `logs`, `runs`, `artifacts`, or `messages` change. SSE streams can append many small events.
- Improvement path: Keep merged logs sorted incrementally by `seq` in `frontend/hooks/use-task-workspace.ts`, memoize per-run derived live items by `(runId, lastLogId, status)`, and avoid JSON diagnostics generation for collapsed rows.

**Sequential clear-all deletion:**
- Problem: `handleClearConversations()` deletes task summaries one by one in a `for...of` loop.
- Files: `frontend/hooks/use-task-workspace.ts`, `frontend/components/chat/ChatSidebar.tsx`, `frontend/e2e-playwright/test_history_scroll_clear.spec.mjs`
- Cause: The frontend has no bulk-delete API contract and waits for each delete before starting the next.
- Improvement path: Add a backend bulk deletion endpoint or use bounded parallel deletes with clear partial-failure reporting.

**Large upload path has no client-side size feedback:**
- Problem: The UI can select and upload large supported files without preflight size copy or progress feedback.
- Files: `frontend/app/file-upload.ts`, `frontend/components/chat/ChatComposer.tsx`, `frontend/lib/task-api.ts`, `frontend/e2e-playwright/test_resource_upload_harness.spec.mjs`
- Cause: `uploadTaskFiles()` sends one multipart request with all selected files and no progress callback.
- Improvement path: Display aggregate size before send, warn near backend upload limits, and add upload progress if large office documents become common.

## Accessibility & UX Fragility

**Custom listbox/menu behavior is only partially keyboard-complete:**
- Files: `frontend/components/chat/ChatComposer.tsx`, `frontend/components/chat/ChatSidebar.tsx`, `frontend/app/globals.css`, `frontend/e2e-playwright/test_skill_selector.spec.mjs`, `frontend/e2e-playwright/test_history_menu_affordance.spec.mjs`
- Why fragile: The skill picker handles ArrowUp, ArrowDown, Enter, and Escape from the textarea, but the model picker only handles click plus Escape and does not implement roving focus or Arrow navigation. History menu items are buttons with `role="menuitem"` but no menu arrow-key handling.
- Safe modification: When editing menus, test with keyboard only: Tab to trigger, Enter/Space to open, Arrow keys across options, Escape to close, and focus return to the trigger.
- Test coverage: Playwright covers several pointer and basic keyboard paths, but there is no automated accessibility audit or complete ARIA interaction test.

**Hidden hover/focus affordances reduce discoverability:**
- Files: `frontend/app/globals.css`, `frontend/components/chat/ChatSidebar.tsx`, `frontend/components/chat/TaskConversation.tsx`, `frontend/components/chat/ChatComposer.tsx`
- Why fragile: `.historyMenuButton`, `.removeFileButton`, and user-message copy buttons begin at `opacity: 0`; `.historyMenuButton:focus-visible` removes the default outline.
- Safe modification: Preserve visible focus indicators for keyboard users and validate hover-hidden controls at desktop and mobile widths.
- Test coverage: Existing E2E specs capture hover/default states for upload and history affordances, but they do not run an accessibility checker.

**Native confirm dialogs own destructive workflows:**
- Files: `frontend/hooks/use-task-workspace.ts`, `frontend/components/chat/ChatSidebar.tsx`
- Why fragile: `window.confirm()` blocks the event loop, cannot match the app's visual system, and is awkward to test across browsers. Delete and clear-all flows also have no undo.
- Safe modification: Replace native confirms with an app modal or inline confirmation component that traps focus, announces the destructive action, and supports cancel/confirm through keyboard.
- Test coverage: Runtime E2E deletes seeded history rows, but no test verifies focus management or cancellation behavior for a custom confirmation UI.

## Scaling Limits

**Event-log scale:**
- Current capacity: No explicit event-count cap exists in frontend state. `mergeExecutionLogs()` de-duplicates by id, then the UI groups and renders all retained events.
- Limit: Long-running tasks with thousands of SSE/tool events can cause high render cost, large diagnostics strings, and slow copy-to-clipboard payloads.
- Scaling path: Add backend event pagination, frontend log windowing, and "download diagnostics" instead of rendering full JSON for every run.

**Task-history scale:**
- Current capacity: The sidebar renders every summary returned by `/api/tasks`.
- Limit: Large local task stores make `frontend/components/chat/ChatSidebar.tsx` and `frontend/hooks/use-task-workspace.ts` pay O(n) render/mutation costs for selection, clear-all, and title updates.
- Scaling path: Add paginated task summaries and server-side search/filter endpoints before history grows beyond a local working set.

**Single-page application surface:**
- Current capacity: The app has one route, `frontend/app/page.tsx`, which delegates to `frontend/components/chat/TaskWorkspace.tsx`.
- Limit: More top-level workflows will add pressure to the already-large workspace hook/components unless route-level boundaries are introduced.
- Scaling path: Add route groups or nested workspace panels only after extracting shared task orchestration state from `frontend/hooks/use-task-workspace.ts`.

## Dependencies at Risk

**Framework and tooling version drift:**
- Risk: `frontend/package.json` uses caret ranges for Next, React, TypeScript, Playwright, ESLint, and related types. `npm outdated --json` reports patch/minor updates available and major releases available for Next, ESLint, and TypeScript.
- Impact: `npm install` can update dependency versions inside allowed ranges, while `npm ci` follows `frontend/package-lock.json`. Major upgrades such as Next 16 or TypeScript 6 can break app-router types, ESLint config, or generated Next type paths.
- Migration plan: Use `npm ci` for reproducible work, update dependencies in explicit maintenance phases, and run `npm run typecheck && npm test && npm run lint && npm run build` plus targeted Playwright specs after upgrades.

**No detected production audit vulnerability:**
- Risk: Not detected by `npm audit --omit=dev --json` on 2026-05-22.
- Impact: No immediate production dependency security action is identified from the frontend package audit.
- Migration plan: Keep audit checks in dependency-update phases and review devDependency advisories separately when they affect local build or E2E tooling.

## Missing Critical Features

**No automated accessibility gate:**
- Problem: The frontend has custom menus, listboxes, disclosure panels, hidden controls, and focus-sensitive chat interactions, but no axe or equivalent accessibility test.
- Blocks: Regressions in ARIA roles, focus indicators, keyboard navigation, and reduced-motion behavior can ship without failing `npm test` or Playwright specs.

**No bulk task-management API contract in the UI:**
- Problem: Clear-all deletes every task one request at a time.
- Blocks: Efficient history cleanup and reliable partial-failure reporting for large local task stores.

**No client-side upload limit copy:**
- Problem: Supported file extensions are shown, but the frontend does not show the backend upload limit or selected aggregate size before submission.
- Blocks: Predictable user recovery when large DOCX/XLSX/XLSM uploads exceed backend limits.

## Build/Test Risks

**Frontend dev script is WSL/POSIX-oriented:**
- Files: `frontend/package.json`, `frontend/README.md`, `scripts/dev-terminal-runner.sh`
- Risk: `frontend/package.json` uses inline environment assignments in `npm run dev`, which are suitable for WSL/bash but not native PowerShell. The README tells developers to use the WSL path for frontend work.
- Impact: Running the frontend directly from Windows PowerShell can fail or produce mixed Windows/WSL generated output.
- Fix approach: Keep WSL as the default local development path or introduce a cross-platform dev script using `cross-env` or a Node launcher.

**E2E specs require a large live-service contract:**
- Files: `frontend/e2e-playwright/README.md`, `frontend/e2e-playwright/test_runtime_contracts.spec.mjs`, `frontend/e2e-playwright/test_session_context_memory.spec.mjs`, `frontend/e2e-playwright/test_resource_upload_harness.spec.mjs`
- Risk: Many Playwright specs require real frontend/backend services, Postgres container details, optional Qdrant/memory setup, access tokens, and timestamped evidence directories.
- Impact: E2E coverage is strong but easy to skip or misconfigure; failures can come from environment drift rather than frontend regressions.
- Fix approach: Keep scenario-specific commands documented, add preflight checks for required env vars/services, and provide one smoke E2E script that validates the minimum live contract.

**Mixed E2E env naming:**
- Files: `frontend/e2e-playwright/test_storage_memory_e2e.mjs`, `frontend/e2e-playwright/README.md`, `frontend/e2e-playwright/test_runtime_contracts.spec.mjs`
- Risk: Most specs use `MYAGENT_E2E_BASE_URL` and `MYAGENT_E2E_EVIDENCE_DIR`, while `test_storage_memory_e2e.mjs` uses `MYAGENT_E2E_FRONTEND_URL` and `MYAGENT_E2E_OUTPUT_DIR`.
- Impact: Agents and developers can run the wrong command shape and misdiagnose missing env vars as application failures.
- Fix approach: Align env var names or document `test_storage_memory_e2e.mjs` as a legacy/manual script with an explicit npm script.

## Test Coverage Gaps

**React component behavior under real rendering:**
- What's not tested: Most unit tests exercise pure functions or source text; there is no React Testing Library layer for `frontend/components/chat/ChatComposer.tsx`, `frontend/components/chat/ChatSidebar.tsx`, or `frontend/components/chat/TaskConversation.tsx`.
- Files: `frontend/components/chat/ChatComposer.tsx`, `frontend/components/chat/ChatSidebar.tsx`, `frontend/components/chat/TaskConversation.tsx`, `frontend/tests/workspace/test_task_workspace.test.ts`
- Risk: Prop wiring, focus movement, DOM state, and component lifecycle regressions can require Playwright to catch.
- Priority: Medium

**SSE reconnection behavior inside the hook:**
- What's not tested: `frontend/hooks/use-task-workspace.ts` has unit tests for retry constants and event type membership, but not hook-level reconnection behavior with fake `EventSource`, task status changes, and event backfill.
- Files: `frontend/hooks/use-task-workspace.ts`, `frontend/lib/task-api.ts`, `frontend/e2e-playwright/test_event_cursor_recovery.spec.mjs`
- Risk: Changes to retry, backfill, or active task switching can lose events or leave stale errors without a fast unit-level failure.
- Priority: High

**Accessibility regression testing:**
- What's not tested: Full keyboard behavior, focus trapping/return, aria relationships, visible focus indicators, and screen-reader names for custom menus and listboxes.
- Files: `frontend/components/chat/ChatComposer.tsx`, `frontend/components/chat/ChatSidebar.tsx`, `frontend/components/chat/TaskConversation.tsx`, `frontend/app/globals.css`
- Risk: UI changes can degrade keyboard and assistive-technology use while passing existing tests.
- Priority: High

**Large-data performance:**
- What's not tested: Rendering thousands of events, hundreds of history rows, large diagnostics strings, or large multi-file upload selections.
- Files: `frontend/app/workspace-view.ts`, `frontend/components/chat/TaskConversation.tsx`, `frontend/components/chat/ChatSidebar.tsx`, `frontend/hooks/use-task-workspace.ts`
- Risk: Local task stores and long-running DeepAgents tasks can become sluggish without failing correctness tests.
- Priority: Medium

---

*Concerns audit: 2026-05-22*
