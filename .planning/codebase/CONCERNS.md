# Codebase Concerns

**Analysis Date:** 2026-05-19

## Tech Debt

**Storage module owns too many contracts:**
- Issue: `backend/app/storage.py` combines schema creation, task lifecycle, event cursors, upload validation, file writes, artifact resolution, agent store, tool cache, context summaries, and long-term memory persistence in one 1,805-line class.
- Files: `backend/app/storage.py`, `backend/tests/fakes.py`, `backend/tests/unit/storage/test_storage.py`, `backend/tests/unit/api/test_tasks.py`, `backend/tests/unit/api/test_artifacts.py`
- Impact: Small lifecycle changes can unintentionally affect uploads, artifacts, SSE recovery, memory, or test fakes. The test fake mirrors production behavior in a separate 680-line implementation, so contract drift is a recurring risk.
- Fix approach: Split storage by public contract while preserving the current `TaskStorage` API: task/runs/messages, events, uploads/artifacts, agent store/cache, and memory. Keep `backend/tests/fakes.py` aligned through shared contract tests that run against both fake and `PostgresTaskStorage`.

**Frontend state normalization and live-log projection are oversized:**
- Issue: `frontend/app/task-state.ts` and `frontend/app/workspace-view.ts` contain backend schema mapping, legacy translations, event normalization, artifact URL validation, progress-log grouping, diagnostics shaping, stream accumulation, and conversation ordering.
- Files: `frontend/app/task-state.ts`, `frontend/app/workspace-view.ts`, `frontend/tests/state/test_task_state.test.ts`, `frontend/tests/workspace/test_workspace_view.test.ts`
- Impact: Any event payload change crosses several local parsers and display builders. Regression tests are necessarily large (`frontend/tests/workspace/test_workspace_view.test.ts` is 2,495 lines), which makes focused changes slow to review.
- Fix approach: Keep current behavior stable, but route new event schema work through small modules by concern: API field normalization, live metadata normalization, log projection, artifact security, and conversation ordering.

**Long-term memory service is an all-in-one integration boundary:**
- Issue: `backend/app/memory.py` handles embedding HTTP calls, Qdrant collection management, semantic search, memory extraction prompts, sensitive text filtering, Postgres writes, and Qdrant upserts in one module.
- Files: `backend/app/memory.py`, `backend/app/memory_admin.py`, `backend/tests/unit/runner/test_memory.py`, `backend/tests/integration/test_postgres_memory_storage.py`
- Impact: Privacy, availability, extraction quality, and index maintenance are coupled. A change to recall or extraction can alter startup checks, write behavior, and admin rebuild behavior.
- Fix approach: Keep `AgentMemoryService` as the orchestration API, but isolate embedding client, vector index, extraction parser, and sanitization policy behind testable adapters.

**Config value for subagent concurrency is not wired into agent creation:**
- Issue: `Settings.max_concurrent_subagents` is loaded from `MYAGENT_MAX_CONCURRENT_SUBAGENTS`, but `build_agent()` does not pass it to `create_deep_agent()`.
- Files: `backend/app/config.py`, `backend/app/agent/factory.py`, `backend/tests/unit/agent/test_factory.py`, `asset/deepagents_platform_knowledge_pack.md`
- Impact: Operators can set `MYAGENT_MAX_CONCURRENT_SUBAGENTS` and see no runtime effect. The knowledge pack states that `build_agent()` passes this value, so documentation and code diverge.
- Fix approach: Pass `max_concurrent_subagents=settings.max_concurrent_subagents` from `backend/app/agent/factory.py` and add an assertion in `backend/tests/unit/agent/test_factory.py`.

**Alternative middleware builder is easy to misuse:**
- Issue: `build_agent_with_middleware()` manually builds Skills/SubAgent middleware and also passes `skills` and `subagents` directly to `create_deep_agent()`.
- Files: `backend/app/agent/factory.py`, `backend/app/agent/middleware.py`, `backend/tests/unit/agent/test_factory.py`
- Impact: The default path uses `build_agent()`, but future callers may introduce duplicate Skills/SubAgent handling or default-middleware conflicts by choosing the alternative builder.
- Fix approach: Keep `build_agent()` as the only production builder unless the middleware path receives explicit tests that verify no duplicate middleware is installed.

## Known Bugs

**Automatic title generation delays background runner scheduling:**
- Symptoms: After `storage.start_run()` marks a task `running`, `create_task()` and `send_message()` await `_set_auto_title_if_empty()` before calling `runner.start_background()`.
- Files: `backend/app/api/tasks.py`, `backend/app/task_titles.py`, `backend/app/runner/core.py`, `backend/tests/unit/api/test_tasks.py`, `backend/tests/unit/models/test_task_titles.py`
- Trigger: First-message task creation or message sending when the title model/provider is slow. `generate_task_title()` has a 10-second timeout, so the task can remain `running` without an active background runner during that window.
- Workaround: The title generator falls back on provider failure, but it still blocks scheduling until completion or timeout.
- Fix approach: Schedule `runner.start_background()` immediately after `storage.start_run()`, then run title generation as best-effort background work or bound it before the status transition.

**Excel inspection can leak workbook handles on exceptional paths:**
- Symptoms: `_inspect_excel()` opens a workbook and calls `workbook.close()` only after iterating worksheets. Exceptions during sheet inspection bypass close.
- Files: `backend/app/execution/resources.py`, `backend/tests/unit/tools/test_resource_execution.py`
- Trigger: Corrupt or unusual `.xlsx`/`.xlsm` files that load successfully but fail while reading sheet metadata, merged ranges, or header guesses.
- Workaround: `_read_excel_table()` already uses `finally`; `_inspect_excel()` does not.
- Fix approach: Wrap `_inspect_excel()` workbook processing in `try/finally` and add a regression test that forces an exception after workbook load.

**Orphan browser E2E script is not a Playwright spec:**
- Symptoms: `frontend/e2e-playwright/test_storage_memory_e2e.mjs` launches Chromium directly and requires `MYAGENT_E2E_OUTPUT_DIR`, but it is not named `*.spec.mjs` and is not referenced by `frontend/package.json`.
- Files: `frontend/e2e-playwright/test_storage_memory_e2e.mjs`, `frontend/package.json`, `frontend/e2e-playwright/README.md`
- Trigger: Developers may assume every `frontend/e2e-playwright/test_*` file is part of Playwright acceptance. This script is standalone and uses a different env var set from the documented specs.
- Workaround: Run it manually with its required env vars.
- Fix approach: Convert it to a `*.spec.mjs` Playwright test or move it under a clearly documented manual-tools directory.

## Security Considerations

**Browser-visible access token and SSE query token are deliberate but sensitive:**
- Risk: `NEXT_PUBLIC_MYAGENT_TOKEN` is exposed to browser JavaScript, and EventSource auth sends the token as `?token=...`, which can appear in browser history, proxy logs, access logs, or diagnostics.
- Files: `frontend/lib/task-api.ts`, `backend/app/main.py`, `AGENTS.md`, `asset/deepagents_platform_knowledge_pack.md`
- Current mitigation: Backend defaults to loopback-only access when no token is configured; non-loopback access requires `MYAGENT_ACCESS_TOKEN`; frontend only attaches the token to trusted API/artifact routes.
- Recommendations: Treat the token as browser-public session auth, use HTTPS for non-loopback access, avoid logging query strings, and do not place provider keys or customer secrets in any `NEXT_PUBLIC_*` variable.

**Secret and local env files are present:**
- Risk: Local environment files exist and must not be read or committed. `frontend/.env.local` can expose `NEXT_PUBLIC_*` values to the browser build.
- Files: `backend/.env`, `backend/.env.example`, `frontend/.env.local`, `frontend/.env.example`, `.gitignore`, `backend/.gitignore`, `frontend/.gitignore`
- Current mitigation: `.gitignore`, `backend/.gitignore`, and `frontend/.gitignore` ignore real env files while allowing examples.
- Recommendations: Keep secrets only in `backend/.env` or backend runtime env. Keep `frontend/.env.local` limited to public API base/token values and never provider keys or customer data.

**Long-term memory redaction is regex-based and not a complete data-loss prevention system:**
- Risk: The scanner catches provider env names, API-key fields, bearer tokens, OpenAI-style secrets, and canaries, but it cannot detect all customer-sensitive text, personal data, or proprietary document content.
- Files: `backend/app/security/scanner.py`, `backend/app/memory.py`, `backend/app/conversation_context.py`, `backend/tests/unit/security/test_scanner.py`, `backend/tests/unit/runner/test_memory.py`
- Current mitigation: Memory extraction uses a whitelist of memory types, sanitizes text before embedding/upsert, and skips sensitive-looking content.
- Recommendations: Keep uploaded source text, full artifacts, raw tool logs, stream deltas, and customer-sensitive text out of Qdrant by policy and tests. Add domain-specific redaction patterns when new sensitive data classes appear.

**Generated HTML artifacts are sandboxed but remain untrusted content:**
- Risk: HTML artifacts are generated/user-controlled content. Preview currently writes a wrapper document and loads the artifact blob inside an iframe with `sandbox=""`, but large or misleading HTML can still consume browser resources or visually impersonate trusted UI inside the iframe.
- Files: `frontend/hooks/use-task-workspace.ts`, `frontend/app/task-state.ts`, `frontend/tests/state/test_task_state.test.ts`, `frontend/e2e-playwright/test_runtime_contracts.spec.mjs`
- Current mitigation: Artifact URLs are restricted to the current API origin and current task artifact routes; HTML preview disables scripts in the iframe.
- Recommendations: Keep the iframe sandbox empty, keep artifact-token attachment behind `buildArtifactRequest()`, and add size/type checks if large HTML artifacts become common.

**Local resource parsing processes untrusted office documents in-process:**
- Risk: Uploaded `.docx`, `.xlsx`, and `.xlsm` files are parsed by `python-docx` and `openpyxl` inside the FastAPI process.
- Files: `backend/app/execution/resources.py`, `backend/app/storage.py`, `backend/tests/unit/tools/test_resource_execution.py`
- Current mitigation: Upload extensions and sizes are limited; tools return structured errors instead of crashing normal tool calls.
- Recommendations: Keep parser dependencies patched, maintain upload limits, and move document parsing to a worker/process boundary before accepting larger or higher-risk files.

## Performance Bottlenecks

**Every storage method opens a new Postgres connection:**
- Problem: `PostgresTaskStorage._connect()` calls `psycopg.connect()` for each operation. SSE polling calls `read_events()` every 0.5 seconds per active browser stream.
- Files: `backend/app/storage.py`, `backend/app/api/streaming.py`, `backend/app/main.py`
- Cause: There is no connection pool or long-lived async DB layer.
- Improvement path: Introduce a bounded psycopg pool for synchronous storage calls, then measure SSE polling under concurrent browser sessions.

**Task list and task read paths are unpaginated:**
- Problem: `list_task_summaries()` iterates all tasks and builds full per-task state; `get_task(include_events=True)` loads all runs, messages, events, uploads, and artifact records.
- Files: `backend/app/storage.py`, `backend/app/api/tasks.py`, `frontend/lib/task-api.ts`, `frontend/hooks/use-task-workspace.ts`
- Cause: The current API is optimized for a local single-user history rather than large task/event volumes.
- Improvement path: Add pagination/limits for task summaries, event history, and message history while preserving full-event fetches for diagnostics.

**Upload handling performs blocking file IO under the storage lock:**
- Problem: `save_uploads()` holds the storage `RLock` while reading upload streams, writing temp files, validating JSON, replacing files, hashing saved files, and appending upload events.
- Files: `backend/app/storage.py`, `backend/app/api/files.py`
- Cause: The lock protects cross-contract consistency, but file IO and hashing are synchronous and can serialize unrelated tasks.
- Improvement path: Validate and stage uploads outside the global storage lock where possible, then commit metadata/events in a short critical section.

**Resource tools parse full documents repeatedly:**
- Problem: Resource inspection/text/table calls reopen and parse files on each tool call; Word table extraction materializes table rows, and Excel inspection uses non-read-only workbook loading.
- Files: `backend/app/execution/resources.py`, `backend/app/tools/registry.py`, `backend/tests/unit/tools/test_resource_execution.py`
- Cause: The in-process adapter has no parsed-resource cache.
- Improvement path: Cache bounded resource metadata by digest, use read-only modes where compatible, and invalidate cache on upload digest changes.

**Frontend live-log rendering rebuilds large diagnostics on every update:**
- Problem: `buildLiveLogItems()` sorts all logs, merges diagnostics, serializes JSON, and truncates tool-result display records whenever conversation stream items are rebuilt.
- Files: `frontend/app/workspace-view.ts`, `frontend/components/chat/TaskConversation.tsx`, `frontend/tests/workspace/test_workspace_view.test.ts`
- Cause: The projection is pure and simple, but not incremental.
- Improvement path: Keep the pure builders for tests, then memoize by run/log ids or virtualize expanded diagnostics for long-running tasks.

## Fragile Areas

**Runner-storage lifecycle coupling:**
- Files: `backend/app/runner/core.py`, `backend/app/storage.py`, `backend/app/api/tasks.py`, `backend/app/api/streaming.py`, `backend/tests/unit/runner/test_core.py`, `backend/tests/unit/api/test_tasks.py`
- Why fragile: Storage state, active in-process asyncio tasks, terminal events, final answer storage, SSE visibility, and memory writes must occur in a precise order.
- Safe modification: Start from runner and storage tests together; preserve `run_id` propagation from `storage.start_run()` into `runner.start_background()` and all terminal events.
- Test coverage: Good unit coverage exists, but live browser E2E is still required for user-visible lifecycle changes.

**LangGraph/deepagents streaming adapter:**
- Files: `backend/app/streaming/v2_adapter.py`, `backend/app/streaming/event_converter.py`, `frontend/app/task-state.ts`, `frontend/app/workspace-view.ts`, `backend/tests/unit/streaming/test_v2_adapter.py`, `backend/tests/unit/streaming/test_event_converter.py`, `frontend/tests/workspace/test_workspace_view.test.ts`
- Why fragile: The code depends on LangGraph v2 chunk shapes, namespace semantics, tool-call chunk accumulation, provider reasoning fields, and the final-answer-vs-intermediate-token boundary.
- Safe modification: Treat adapter output as a public contract. Add backend converter tests and frontend projection tests for every new event shape.
- Test coverage: Unit coverage is extensive; Playwright coverage should be selected by affected UI path.

**SSE cursor recovery semantics:**
- Files: `backend/app/api/streaming.py`, `backend/app/storage.py`, `frontend/hooks/use-task-workspace.ts`, `frontend/e2e-playwright/test_event_cursor_recovery.spec.mjs`
- Why fragile: `last_event_id` must start as `None`, unknown cursors must replay the full ordered stream, and frontend deduplication depends on stable event ids.
- Safe modification: Keep `after_id` as a recovery hint rather than an authoritative boundary.
- Test coverage: Dedicated E2E exists, but CI does not run it by default.

**Artifact URL and run scoping:**
- Files: `backend/app/api/artifacts.py`, `backend/app/storage.py`, `frontend/app/task-state.ts`, `frontend/hooks/use-task-workspace.ts`, `backend/tests/unit/api/test_artifacts.py`, `frontend/tests/state/test_task_state.test.ts`
- Why fragile: Latest-artifact compatibility routes, run-scoped routes, frontend URL trust checks, token attachment, and HTML preview safety must stay aligned.
- Safe modification: Add backend artifact tests and frontend `buildArtifactRequest()` tests whenever artifact URL shape changes.
- Test coverage: Unit and runtime-contract E2E exist; CI does not run browser artifact checks by default.

**In-memory test fake mirrors production storage manually:**
- Files: `backend/tests/fakes.py`, `backend/app/storage.py`, `backend/tests/unit/api/test_tasks.py`, `backend/tests/unit/runner/test_core.py`
- Why fragile: The fake implements task status, runs, events, uploads, artifacts, agent store, tool cache, and memory with different data structures and no DB transactions.
- Safe modification: Treat the fake as a public test adapter. Every new `TaskStorage` method or state transition needs parity assertions against `PostgresTaskStorage`.
- Test coverage: Existing tests use the fake heavily; production Postgres integration is skip-gated by environment.

## Scaling Limits

**Single-process runner ownership:**
- Current capacity: One backend process owns active runs in `TaskRunner._active_runs`; multi-worker env vars are rejected.
- Limit: Multiple uvicorn/gunicorn workers, multiple hosts, or process crashes cannot preserve active run ownership or cancellation.
- Scaling path: Add a durable queue/lease model, run ownership records, heartbeats, and worker-safe cancellation before enabling multi-worker deployment.
- Files: `backend/app/config.py`, `backend/app/main.py`, `backend/app/runner/core.py`, `backend/app/storage.py`

**Local filesystem artifact/upload storage:**
- Current capacity: Uploads and artifacts live under `backend/storage/sessions/` by task id.
- Limit: Horizontal scaling, container restarts without persistent volumes, or multiple hosts will split file state from Postgres task state.
- Scaling path: Move upload/artifact bytes to shared object storage or a mounted persistent volume with explicit cleanup and retention policies.
- Files: `backend/app/storage.py`, `backend/app/api/files.py`, `backend/app/api/artifacts.py`, `.gitignore`

**Unbounded event/message retention:**
- Current capacity: Event and message tables grow for every stream delta, tool call, status update, and final answer.
- Limit: Long-running tasks or many tasks will slow task reads, task summaries, frontend normalization, and JSONL copying.
- Scaling path: Add event pagination, retention/compaction, summary materialization, and per-run diagnostics download endpoints.
- Files: `backend/app/storage.py`, `frontend/app/task-state.ts`, `frontend/app/workspace-view.ts`, `frontend/components/chat/TaskConversation.tsx`

## Dependencies at Risk

**DeepAgents and LangGraph streaming contracts:**
- Risk: `backend/app/streaming/v2_adapter.py` relies on current deepagents/LangGraph stream modes, v2 chunk dictionaries, subgraph namespace behavior, and LangChain message chunk internals.
- Impact: SDK changes can silently drop stream events, misclassify subagent output, lose tool arguments, or extract the wrong final answer.
- Migration plan: Keep adapter tests focused on raw chunk fixtures and pin SDK upgrades behind backend streaming tests plus frontend progress-log E2E.
- Files: `backend/pyproject.toml`, `backend/uv.lock`, `backend/app/streaming/v2_adapter.py`, `backend/tests/unit/streaming/test_v2_adapter.py`

**Git-pinned `langgraph-checkpoint`:**
- Risk: `backend/pyproject.toml` pins `langgraph-checkpoint` to a specific upstream Git commit.
- Impact: Fresh installs depend on GitHub availability and a moving ecosystem around an unreleased checkpoint fix.
- Migration plan: Replace the Git source with a PyPI release once it includes the required warning fix; keep `uv lock --check` in CI.
- Files: `backend/pyproject.toml`, `backend/uv.lock`, `.github/workflows/backend-ci.yml`

**Office document parsers:**
- Risk: `python-docx` and `openpyxl` parse untrusted user uploads in the API process.
- Impact: Parser bugs, zip bombs within size limits, or high-memory workbooks can degrade availability.
- Migration plan: Keep upload limits tight, update dependencies promptly, add parser time/resource isolation before increasing accepted file size or format scope.
- Files: `backend/pyproject.toml`, `backend/app/execution/resources.py`, `backend/app/storage.py`

## Missing Critical Features

**CI does not run browser E2E acceptance:**
- Problem: `frontend/package.json` exposes only `e2e:runtime-contracts`, and `.github/workflows/frontend-ci.yml` runs typecheck, Node tests, lint, and build but no Playwright specs.
- Blocks: Browser regressions in task creation, upload, SSE, artifacts, progress logs, history menus, and screenshots can pass CI unless manually run.
- Files: `frontend/package.json`, `.github/workflows/frontend-ci.yml`, `frontend/e2e-playwright/README.md`, `frontend/e2e-playwright/test_runtime_contracts.spec.mjs`

**No durable background job system:**
- Problem: Active runs are in-process asyncio tasks with Postgres state but no persistent worker queue, lease, retry, heartbeat, or distributed cancellation.
- Blocks: Multi-worker deployment, crash recovery of active tasks, backpressure, scheduled retries, and operational run ownership.
- Files: `backend/app/runner/core.py`, `backend/app/storage.py`, `backend/app/config.py`

**No first-class retention/cleanup controls:**
- Problem: Task workspaces, uploaded files, artifacts, messages, events, tool caches, and memories persist until explicit task deletion or manual admin action.
- Blocks: Long-lived local deployments with many tasks need storage quotas, retention policies, and safe cleanup workflows.
- Files: `backend/app/storage.py`, `backend/app/memory_admin.py`, `backend/storage/sessions/`, `frontend/hooks/use-task-workspace.ts`

**Authentication is local-token based, not user/session based:**
- Problem: The API uses a single optional access token and `MYAGENT_DEFAULT_USER_ID` for memory scope.
- Blocks: Multi-user isolation, per-user task ownership, role-based artifact access, audit trails, and rotating browser sessions.
- Files: `backend/app/main.py`, `backend/app/config.py`, `backend/app/memory.py`, `frontend/lib/task-api.ts`

## Test Coverage Gaps

**Browser E2E specs are not default CI gates:**
- What's not tested: Playwright specs under `frontend/e2e-playwright/` are documented and reusable, but `.github/workflows/frontend-ci.yml` does not run them.
- Files: `frontend/e2e-playwright/`, `frontend/package.json`, `.github/workflows/frontend-ci.yml`
- Risk: The repository's delivery rules require browser E2E and screenshots, but automated CI does not enforce that rule.
- Priority: High

**Postgres/Qdrant integration is environment-gated:**
- What's not tested: Real Postgres memory storage and Qdrant/DashScope integration run only when external env is configured.
- Files: `backend/tests/integration/test_postgres_memory_storage.py`, `backend/app/memory.py`, `backend/app/storage.py`
- Risk: Most local and CI runs exercise fakes and mocked clients, so production storage/index drift can escape until live E2E or configured integration runs.
- Priority: High

**Subagent concurrency config has no regression test:**
- What's not tested: `MYAGENT_MAX_CONCURRENT_SUBAGENTS` / `Settings.max_concurrent_subagents` propagation into `create_deep_agent()`.
- Files: `backend/app/config.py`, `backend/app/agent/factory.py`, `backend/tests/unit/agent/test_factory.py`
- Risk: The concurrency knob remains inert or future fixes regress silently.
- Priority: Medium

**Excel inspect failure cleanup lacks coverage:**
- What's not tested: Workbook close behavior when `_inspect_excel()` raises after `load_workbook()`.
- Files: `backend/app/execution/resources.py`, `backend/tests/unit/tools/test_resource_execution.py`
- Risk: Repeated failed inspections can leak file handles or memory.
- Priority: Medium

**Standalone storage-memory E2E is outside the normal test shape:**
- What's not tested: `frontend/e2e-playwright/test_storage_memory_e2e.mjs` is not discoverable by the current Playwright command pattern and is not referenced by `frontend/package.json`.
- Files: `frontend/e2e-playwright/test_storage_memory_e2e.mjs`, `frontend/package.json`, `frontend/e2e-playwright/README.md`
- Risk: Storage/memory browser behavior covered only by this script can be skipped by maintainers expecting `*.spec.mjs` Playwright coverage.
- Priority: Medium

---

*Concerns audit: 2026-05-19*
