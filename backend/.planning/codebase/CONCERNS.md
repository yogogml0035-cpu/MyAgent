# Codebase Concerns

**Analysis Date:** 2026-05-19

## Tech Debt

**Storage module owns too many contracts:**
- Issue: `backend/app/storage.py` combines schema creation, lifecycle state, events, uploads, artifacts, agent store, tool cache, summaries, and long-term memory persistence.
- Files: `backend/app/storage.py`, `backend/tests/fakes.py`, `backend/tests/unit/storage/test_storage.py`.
- Impact: Small changes can affect several contracts, and fake/production drift is a recurring risk.
- Fix approach: Split storage by public contract while keeping shared contract tests that run against fake and Postgres storage.

**Long-term memory service is an all-in-one integration boundary:**
- Issue: `backend/app/memory.py` handles embedding HTTP, Qdrant collection management, semantic search, extraction prompts, sanitization, storage writes, and index upserts.
- Files: `backend/app/memory.py`, `backend/app/memory_admin.py`, `backend/tests/unit/runner/test_memory.py`.
- Impact: Privacy policy, availability, extraction quality, and index maintenance are coupled.
- Fix approach: Keep `AgentMemoryService` as orchestration API but isolate embedding client, vector index, parser, and sanitization policy.

**Subagent concurrency setting is currently inert:**
- Issue: `Settings.max_concurrent_subagents` is loaded in `backend/app/config.py`, but `build_agent()` does not pass it to `create_deep_agent()`.
- Files: `backend/app/config.py`, `backend/app/agent/factory.py`, `backend/tests/unit/agent/test_factory.py`.
- Impact: Operators can configure `MYAGENT_MAX_CONCURRENT_SUBAGENTS` without runtime effect.
- Fix approach: Pass the setting through and add a unit assertion around the DeepAgents call.

**Alternative middleware builder is easy to misuse:**
- Issue: `build_agent_with_middleware()` manually builds Skills/SubAgent middleware while also passing `skills` and `subagents` to `create_deep_agent()`.
- Files: `backend/app/agent/factory.py`, `backend/app/agent/middleware.py`.
- Impact: Future callers could duplicate middleware behavior.
- Fix approach: Prefer `build_agent()` for production unless extra middleware path gains explicit tests.

## Known Bugs

**Automatic title generation delays background runner scheduling:**
- Symptoms: After `storage.start_run()` marks a task `running`, API code awaits `_set_auto_title_if_empty()` before `runner.start_background()`.
- Files: `backend/app/api/tasks.py`, `backend/app/task_titles.py`, `backend/app/runner/core.py`.
- Trigger: Slow title provider on first-message task creation or message send.
- Workaround: Title failure is caught, but title timeout can still delay runner scheduling.
- Fix approach: Start the runner immediately after `storage.start_run()`, then title in best-effort background work.

**Excel inspection can leak workbook handles on exceptional paths:**
- Symptoms: `_inspect_excel()` closes workbooks after normal iteration, but exceptions during metadata inspection can bypass close.
- Files: `backend/app/execution/resources.py`, `backend/tests/unit/tools/test_resource_execution.py`.
- Trigger: Corrupt or unusual Excel files that fail after workbook load.
- Fix approach: Wrap workbook processing in `try/finally` and add a regression test.

## Security Considerations

**Browser-visible access token is expected but sensitive:**
- Risk: The backend accepts a token that the frontend exposes through `NEXT_PUBLIC_MYAGENT_TOKEN`; SSE also uses query-param auth.
- Files: `backend/app/main.py`, `frontend/lib/task-api.ts`.
- Current mitigation: Loopback-only default when no token is configured; token is required for non-loopback access.
- Recommendations: Treat it as browser-public session auth, use HTTPS outside loopback, and avoid logging query strings.

**Local env files must remain private:**
- Risk: `backend/.env` may contain provider keys, database URL, Qdrant URL, and embedding credentials.
- Files: `backend/.env`, `backend/.env.example`, `backend/.gitignore`.
- Current mitigation: Real env files are ignored.
- Recommendations: Never copy real env values into docs, tests, fixtures, or knowledge packs.

**Long-term memory redaction is regex-based:**
- Risk: `backend/app/security/scanner.py` cannot detect every customer-sensitive text or proprietary upload excerpt.
- Files: `backend/app/security/scanner.py`, `backend/app/memory.py`.
- Current mitigation: Memory extraction uses allowed memory types, sanitizes segments, and skips secret-like content.
- Recommendations: Keep uploaded source text, raw artifacts, and raw tool logs out of memory; add domain-specific redaction when needed.

**Office parsers process untrusted files in-process:**
- Risk: `python-docx` and `openpyxl` parse uploaded user files inside the API process.
- Files: `backend/app/execution/resources.py`, `backend/app/storage.py`.
- Current mitigation: Extension and size limits plus structured tool errors.
- Recommendations: Keep parsers patched and move parsing to a worker/process boundary before accepting larger files.

## Performance Bottlenecks

**Every storage method opens a new Postgres connection:**
- Problem: `PostgresTaskStorage._connect()` calls `psycopg.connect()` per operation; SSE polling can call `read_events()` every 0.5 seconds per stream.
- Files: `backend/app/storage.py`, `backend/app/api/streaming.py`.
- Improvement path: Introduce a bounded psycopg pool and measure concurrent SSE polling.

**Task reads and summaries are unpaginated:**
- Problem: `list_task_summaries()` and `get_task(include_events=True)` can load full histories.
- Files: `backend/app/storage.py`, `backend/app/api/tasks.py`.
- Improvement path: Add pagination/limits for summaries, events, and messages while preserving diagnostics routes.

**Upload handling does blocking IO under the storage lock:**
- Problem: `save_uploads()` holds the storage `RLock` while reading streams, writing temp files, validating JSON, hashing, and appending events.
- Files: `backend/app/storage.py`, `backend/app/api/files.py`.
- Improvement path: Stage/validate outside the global lock where possible, then commit metadata/events in a short critical section.

**Resource tools parse full documents repeatedly:**
- Problem: Resource inspection/read calls reopen and parse files on each tool call.
- Files: `backend/app/execution/resources.py`.
- Improvement path: Cache bounded metadata by digest and use read-only workbook modes where compatible.

## Fragile Areas

**Runner-storage lifecycle coupling:**
- Why fragile: Storage state, active async tasks, terminal events, final answers, SSE visibility, and memory writes must stay in order.
- Files: `backend/app/runner/core.py`, `backend/app/storage.py`, `backend/app/api/tasks.py`.
- Safe modification: Preserve `run_id` propagation from `storage.start_run()` into runner and terminal events; test runner and API together.
- Test coverage: Strong unit coverage, but browser E2E is still required for user-visible lifecycle changes.

**LangGraph/DeepAgents stream adapter:**
- Why fragile: Adapter depends on v2 chunk shapes, namespace semantics, tool-call chunk accumulation, provider reasoning fields, and final-answer extraction.
- Files: `backend/app/streaming/v2_adapter.py`, `backend/app/streaming/event_converter.py`.
- Safe modification: Treat converted events as public contract and update frontend projections/tests with each new shape.
- Test coverage: Unit tests exist under `backend/tests/unit/streaming/`.

**SSE cursor recovery:**
- Why fragile: Unknown cursors intentionally replay the full ordered stream, and frontend deduplication depends on stable event IDs.
- Files: `backend/app/api/streaming.py`, `backend/app/storage.py`.
- Safe modification: Keep `after_id` as a recovery hint, not an authoritative boundary.

**Artifact URL and run scoping:**
- Why fragile: Latest-artifact compatibility routes, run-scoped routes, frontend URL trust checks, and token attachment must stay aligned.
- Files: `backend/app/api/artifacts.py`, `backend/app/storage.py`, `frontend/app/task-state.ts`.
- Safe modification: Update backend artifact tests and frontend `buildArtifactRequest()` tests together.

**In-memory test fake mirrors production storage manually:**
- Why fragile: `backend/tests/fakes.py` reimplements many `PostgresTaskStorage` behaviors without transactions.
- Files: `backend/tests/fakes.py`, `backend/app/storage.py`.
- Safe modification: Add parity tests for new storage methods or state transitions.

## Scaling Limits

**Single-process runner ownership:**
- Current capacity: One backend process owns active runs in `TaskRunner._active_runs`.
- Limit: Multi-worker or multi-host deployments break cancellation and run ownership.
- Scaling path: Add durable queue/lease/heartbeat/run-owner records before enabling multiple workers.

**Local filesystem upload/artifact storage:**
- Current capacity: Files live under one local task root.
- Limit: Multiple hosts or ephemeral containers split file state from Postgres state.
- Scaling path: Use shared object storage or a durable mounted volume with retention controls.

**Unbounded event/message retention:**
- Current capacity: Every stream delta, tool call, status update, message, and artifact record persists indefinitely.
- Limit: Large local histories will slow reads and frontend normalization.
- Scaling path: Add pagination, compaction, retention, and diagnostics export endpoints.

## Dependencies at Risk

**DeepAgents and LangGraph streaming contracts:**
- Risk: SDK changes can alter stream modes/chunk shapes and silently break event conversion.
- Files: `backend/pyproject.toml`, `backend/uv.lock`, `backend/app/streaming/v2_adapter.py`.
- Migration plan: Pin upgrades behind streaming adapter tests and frontend progress-log E2E.

**Git-pinned `langgraph-checkpoint`:**
- Risk: Fresh installs depend on GitHub availability and a specific upstream commit.
- Files: `backend/pyproject.toml`, `backend/uv.lock`.
- Migration plan: Replace with PyPI release once the needed fix is released.

## Missing Critical Features

**No durable background job system:**
- Problem: Active runs are in-process async tasks with no persistent queue, lease, retry, heartbeat, or distributed cancellation.
- Blocks: Crash recovery and multi-worker deployment.
- Implementation complexity: High.

**No first-class retention/cleanup controls:**
- Problem: Workspaces, uploads, artifacts, events, messages, caches, and memories persist until task deletion or manual admin action.
- Blocks: Long-lived local deployments with many tasks.
- Implementation complexity: Medium to high.

**Authentication is local-token based, not user/session based:**
- Problem: One optional access token and one default memory user ID.
- Blocks: Multi-user isolation, per-user ownership, audit trails, and role-based access.
- Implementation complexity: High.

## Test Coverage Gaps

**Real Postgres/Qdrant integration is environment-gated:**
- What's not tested: Full storage/memory/index behavior in default local or CI runs.
- Risk: Production storage or Qdrant drift can escape until configured integration or browser E2E runs.
- Priority: High.

**Subagent concurrency propagation lacks regression coverage:**
- What's not tested: `MYAGENT_MAX_CONCURRENT_SUBAGENTS` into DeepAgents.
- Risk: Runtime knob remains inert or regresses.
- Priority: Medium.

**Excel inspect failure cleanup lacks coverage:**
- What's not tested: Workbook close when `_inspect_excel()` fails after load.
- Risk: File handle or memory leaks on repeated failed inspections.
- Priority: Medium.

---

*Concerns audit: 2026-05-19*
*Update as backend risks are fixed or newly discovered*
