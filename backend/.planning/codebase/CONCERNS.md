# Codebase Concerns

**Analysis Date:** 2026-05-22

## Tech Debt

**PostgresTaskStorage handles too many responsibilities:**
- Issue: One class owns database DDL, task lifecycle, event sequencing, upload storage, artifact resolution, tool cache, agent store, context summaries, and long-term memory records.
- Files: `backend/app/storage.py:313`, `backend/app/storage.py:329`, `backend/app/storage.py:738`, `backend/app/storage.py:976`, `backend/app/storage.py:1149`, `backend/app/storage.py:1234`, `backend/app/storage.py:1484`
- Impact: Small changes to uploads, events, artifacts, memory, or agent-store behavior require editing the same 1,700-line module. This increases regression risk and makes it hard to isolate failures in tests.
- Fix approach: Split by responsibility behind existing public contracts: task lifecycle/event repository, upload/artifact filesystem service, agent-store repository, tool-cache repository, and long-term-memory repository. Keep `PostgresTaskStorage` as a compatibility facade until callers are migrated.

**Application startup performs schema management in process:**
- Issue: Database schema creation and column changes are embedded in `initialize()` instead of a versioned migration system.
- Files: `backend/app/storage.py:329`, `backend/app/main.py:72`, `backend/README.md`
- Impact: Production startup mutates schema implicitly and has no downgrade, ordering, lock, or migration-history contract. Multi-instance startup and future schema changes become fragile.
- Fix approach: Introduce explicit migrations with a schema-version table or migration tool, then keep `initialize()` limited to startup checks.

**Request and message options are accepted but unused:**
- Issue: `MessageRequest.mode` and `MessageRequest.input_scope` are declared but not used in task execution.
- Files: `backend/app/schemas.py:22`, `backend/app/api/tasks.py:154`, `backend/app/runner/core.py:102`
- Impact: API clients can send mode/scope values that appear meaningful but do not change behavior, which creates product ambiguity and hidden assumptions in future work.
- Fix approach: Either wire these fields into runner behavior and tests, or remove them from the request schema until the feature exists.

**Configuration parsing is hand-written:**
- Issue: `.env` loading and environment parsing are custom and silently fall back on invalid values.
- Files: `backend/app/config.py:78`, `backend/app/config.py:141`, `backend/app/config.py:159`, `backend/app/config.py:170`, `backend/app/config.py:179`, `backend/.env.example`
- Impact: Invalid numeric limits, CORS origin formatting, and malformed `.env` quoting can be accepted without operator-visible errors. This makes production misconfiguration hard to diagnose.
- Fix approach: Use a typed settings library or fail-fast validators for required services, numeric bounds, URLs, and origin lists.

**Search tool cache and memory services are coupled through storage:**
- Issue: Tool cache, agent store, task storage, and long-term memory storage share one storage implementation and one Postgres connection path.
- Files: `backend/app/tools/searxng_search.py:53`, `backend/app/storage.py:1075`, `backend/app/agent_store.py:1`, `backend/app/memory.py:47`
- Impact: Cache behavior and memory behavior inherit task-storage locking and schema concerns. Independent cleanup, observability, and scaling are difficult.
- Fix approach: Extract cache and memory repositories, then make the runner depend on narrow protocols already sketched in `backend/app/runner/core.py:32` and `backend/app/memory.py:47`.

## Known Bugs

**Long-running memory write tasks are not drained on shutdown:**
- Symptoms: Completed task memory writes run as background tasks, but application lifespan does not await or cancel `TaskRunner._memory_tasks`.
- Files: `backend/app/runner/core.py:388`, `backend/app/runner/core.py:419`, `backend/app/main.py:71`
- Trigger: A run completes, `_schedule_completed_run_memory_write()` starts, and the backend process exits or reloads before the memory write finishes.
- Workaround: Rebuild Qdrant from canonical Postgres records with `backend/app/memory_admin.py:48` when the index is suspected stale.

**Configured task root is also used as agent workspace root:**
- Symptoms: `load_settings()` sets `workspace_root` to `task_root.resolve()` with no independent override.
- Files: `backend/app/config.py:79`, `backend/app/config.py:99`, `backend/app/runner/core.py:119`, `backend/app/execution/resources.py:231`
- Trigger: Operators expect `MYAGENT_TASK_ROOT` to control session metadata while agent file tools use a separate workspace. Both surfaces resolve to the same path.
- Workaround: Use a dedicated `MYAGENT_TASK_ROOT` directory and avoid placing non-task files under it.

**Query-string token authentication exposes credentials in URLs:**
- Symptoms: `/api/*` accepts `?token=...`, including the SSE stream endpoint.
- Files: `backend/app/main.py:207`, `backend/app/main.py:211`, `backend/tests/unit/security/test_auth.py:45`, `backend/tests/unit/security/test_auth.py:55`
- Trigger: Browser, proxy, access-log, or referrer logging captures the full URL used for authenticated API or SSE calls.
- Workaround: Prefer `Authorization: Bearer ...` or `X-MyAgent-Token` for non-SSE calls. For SSE, use a header-capable client/proxy pattern if possible.

**Task delete can leave orphaned files when filesystem deletion fails:**
- Symptoms: The database row is deleted first, then task files are removed with `ignore_errors=True`.
- Files: `backend/app/storage.py:560`, `backend/app/storage.py:564`, `backend/app/storage.py:565`, `backend/app/api/tasks.py:126`
- Trigger: Filesystem permission errors, locked files, antivirus locks, or disk errors during `shutil.rmtree()`.
- Workaround: Manually inspect and remove orphaned directories under `MYAGENT_TASK_ROOT` after failed filesystem cleanup.

## Security Considerations

**Bearer token in query parameters is allowed:**
- Risk: Access tokens can be captured by URL logs, browser history, copied links, and analytics/proxy logs.
- Files: `backend/app/main.py:207`, `backend/app/main.py:211`, `backend/tests/unit/security/test_auth.py:45`, `backend/tests/unit/security/test_auth.py:55`
- Current mitigation: Header tokens are supported with constant-time comparison through `compare_digest()`.
- Recommendations: Remove query-token support for normal API routes. If SSE needs browser-native `EventSource`, issue short-lived stream tokens or use a same-origin session/proxy that injects headers server-side.

**Local-only authorization depends on the direct client address:**
- Risk: Deployments behind proxies can make remote callers appear local if proxy headers or network topology are not controlled outside the app.
- Files: `backend/app/main.py:207`, `backend/app/main.py:224`, `backend/README.md`, `backend/.env.example`
- Current mitigation: Requests without `MYAGENT_ACCESS_TOKEN` are allowed only for loopback or `testclient` hosts.
- Recommendations: Require `MYAGENT_ACCESS_TOKEN` whenever the service binds beyond `127.0.0.1`; document proxy and LAN deployment requirements. Add tests for non-loopback clients and proxy deployments.

**SearXNG base URL is configurable without scheme or host validation:**
- Risk: A misconfigured or attacker-controlled `MYAGENT_SEARXNG_URL` can direct agent search traffic to arbitrary HTTP services and return untrusted content as tool output.
- Files: `backend/app/config.py:25`, `backend/app/config.py:102`, `backend/app/tools/searxng_search.py:117`, `backend/app/tools/searxng_search.py:129`, `backend/.env.example`
- Current mitigation: The default URL points to `http://127.0.0.1:8181/`, and the README describes a local SearXNG engine.
- Recommendations: Validate allowed schemes and host allowlists for `MYAGENT_SEARXNG_URL`. Treat remote search endpoints as an explicit production setting.

**Sensitive-output scanner is narrow and not enforced across all outbound surfaces:**
- Risk: Secret scanning focuses on provider names, bearer tokens, common key fields, and specific canaries, but artifact downloads, SSE events, uploaded documents, search results, and final answers are not centrally scanned before output.
- Files: `backend/app/security/scanner.py:8`, `backend/app/security/scanner.py:20`, `backend/app/security/scanner.py:120`, `backend/app/api/artifacts.py:32`, `backend/app/api/streaming.py:44`, `backend/app/runner/core.py:275`
- Current mitigation: Memory paths redact and skip sensitive text before recall or persistence in `backend/app/memory.py:497` and `backend/app/memory.py:514`; scanner unit tests cover common patterns in `backend/tests/unit/security/test_scanner.py`.
- Recommendations: Decide which output channels require automated scanning, then enforce scanner checks at artifact/event/final-answer boundaries or document why raw task output is allowed.

**Skill source directories can be configured as arbitrary filesystem paths:**
- Risk: `MYAGENT_SKILLS_DIRS` can mount arbitrary directories into the agent as read-only skill sources. This is safe only when the backend operator fully controls the environment.
- Files: `backend/app/config.py:90`, `backend/app/agent/factory.py:95`, `backend/app/agent/factory.py:102`, `backend/app/skills/loader.py:25`
- Current mitigation: Skill mounts are wrapped with `_ReadOnlyBackend`, blocking agent writes through that route.
- Recommendations: Restrict skill directories to approved roots or validate paths before mounting in deployments where environment variables can be influenced by users.

## Performance Bottlenecks

**SSE streaming polls Postgres for every connected client:**
- Problem: Each stream loops every 0.5 seconds and calls `storage.read_events()`, which opens a database connection and reads events after the last ID.
- Files: `backend/app/api/streaming.py:19`, `backend/app/api/streaming.py:44`, `backend/app/api/streaming.py:52`, `backend/app/storage.py:976`
- Cause: The streaming layer uses polling instead of a push queue, LISTEN/NOTIFY, or in-memory event broadcaster.
- Improvement path: Add a task-level event subscription mechanism. For Postgres, use `LISTEN/NOTIFY` or a bounded in-process queue for active runs, with polling as fallback.

**Task list loads full message/run state per task:**
- Problem: `list_task_summaries()` selects all task rows, then builds each state by loading runs, messages, uploads, and artifacts.
- Files: `backend/app/storage.py:504`, `backend/app/storage.py:506`, `backend/app/storage.py:509`, `backend/app/storage.py:1521`, `backend/app/api/tasks.py:106`
- Cause: Summary projection reuses the full `TaskState` assembly path.
- Improvement path: Query summaries directly with aggregates for run count and last message timestamp, and avoid per-task filesystem artifact/upload scans in list views.

**Resource inspection reads complete documents synchronously:**
- Problem: Text/JSON/DOCX/XLSX inspection and reads execute synchronously inside agent tool calls.
- Files: `backend/app/execution/resources.py:132`, `backend/app/execution/resources.py:304`, `backend/app/execution/resources.py:375`, `backend/app/execution/resources.py:437`, `backend/app/execution/resources.py:513`, `backend/app/execution/resources.py:536`
- Cause: Uploaded document parsing uses `path.read_text()`, `Document()`, and `load_workbook(..., read_only=False)` without CPU, page-count, sheet-size, or parse-time limits.
- Improvement path: Parse large resources through bounded worker threads, use `read_only=True` for Excel where possible, enforce per-resource parse budgets, and cache inspected structure by digest.

**Agent-store filtering is in-memory for filtered searches:**
- Problem: `search_agent_store_items()` fetches at least 1,000 records when a filter is supplied and applies `_value_matches_filter()` in Python.
- Files: `backend/app/storage.py:1185`, `backend/app/storage.py:1193`, `backend/app/storage.py:1207`
- Cause: JSONB filtering is implemented outside SQL.
- Improvement path: Translate supported filters to JSONB SQL predicates and add targeted indexes for common namespace/value queries.

**Long-term memory rebuild is sequential:**
- Problem: Rebuilding Qdrant loops through Postgres records and performs embedding plus Qdrant upsert one memory at a time.
- Files: `backend/app/memory.py:247`, `backend/app/memory.py:253`, `backend/app/memory.py:257`, `backend/app/memory.py:391`, `backend/app/memory_admin.py:48`
- Cause: No batching or parallelism is used for embedding calls or Qdrant upserts.
- Improvement path: Batch embedding requests where the provider supports it, batch Qdrant point writes, and add progress reporting for large memory sets.

## Fragile Areas

**Runner state is split between Postgres and an in-process task map:**
- Files: `backend/app/runner/core.py:99`, `backend/app/runner/core.py:210`, `backend/app/runner/core.py:350`, `backend/app/runner/core.py:423`, `backend/app/config.py:194`, `backend/app/main.py:72`
- Why fragile: Running tasks are tracked in `_active_runs` in one Python process, while task state lives in Postgres. The app rejects multi-worker env vars but has no distributed runner or lease model.
- Safe modification: Keep all runner lifecycle changes guarded by `update_task_if_status*()` and add tests for startup interruption, cancellation, and stale active-run IDs.
- Test coverage: Unit tests cover cancellation and concurrent runs in `backend/tests/unit/runner/test_core.py` and `backend/tests/unit/runner/test_concurrency_and_thinking_audit.py`; there is no distributed or multi-process runner coverage.

**Event sequencing and stream cursors are central to UI correctness:**
- Files: `backend/app/storage.py:976`, `backend/app/storage.py:998`, `backend/app/storage.py:1622`, `backend/app/api/streaming.py:47`, `backend/app/streaming/v2_adapter.py`
- Why fragile: SSE clients depend on monotonic `seq`, `after_id` cursor behavior, and full event-record serialization. Small changes can duplicate, skip, or reorder events.
- Safe modification: Preserve task-level sequence increments in `_append_event_with_cursor()` and keep run filtering semantics covered before changing event queries.
- Test coverage: Unit and e2e tests cover stream shape, drain-before-done, and cursor behavior in `backend/tests/unit/storage/test_storage.py`, `backend/tests/unit/api/test_tasks.py`, and `backend/tests/e2e/test_streaming_e2e.py`.

**Artifact names are path-sensitive and mirrored between run and top-level directories:**
- Files: `backend/app/storage.py:59`, `backend/app/storage.py:1404`, `backend/app/storage.py:1410`, `backend/app/storage.py:1484`, `backend/app/storage.py:1818`, `backend/app/api/artifacts.py:32`
- Why fragile: Fixed artifact names are mirrored to `artifacts/`, while run-scoped artifacts live under `artifacts/runs/{run_id}`. Incorrect normalization or mirror behavior can expose stale artifacts or break downloads.
- Safe modification: Use `normalize_artifact_name()` and `validate_run_id()` for every artifact path. Add tests for stale top-level mirrors when changing artifact resolution.
- Test coverage: Existing tests cover path traversal, run artifact recording, and mirrors in `backend/tests/unit/storage/test_storage.py` and `backend/tests/unit/api/test_artifacts.py`.

**DeepAgents and LangGraph stream adapter compatibility is hand-maintained:**
- Files: `backend/app/streaming/v2_adapter.py:54`, `backend/app/streaming/v2_adapter.py:92`, `backend/app/streaming/event_converter.py`, `backend/pyproject.toml`
- Why fragile: The adapter accepts multiple chunk formats and maps provider/graph events into frontend-facing event records. Dependency upgrades can alter stream payloads.
- Safe modification: Before upgrading `deepagents`, `langgraph`, or `langchain`, run streaming unit tests and the SSE e2e tests. Add fixture coverage for any newly observed chunk shape.
- Test coverage: Stream conversion tests are concentrated in `backend/tests/unit/streaming/test_v2_adapter.py`, `backend/tests/unit/streaming/test_event_converter.py`, and `backend/tests/e2e/test_streaming_e2e.py`.

**Memory persistence has two stores with different failure modes:**
- Files: `backend/app/memory.py:107`, `backend/app/memory.py:220`, `backend/app/storage.py:438`, `backend/app/storage.py:1234`, `backend/app/memory_admin.py:48`
- Why fragile: Canonical memory records are in Postgres, but recall depends on Qdrant vectors. Writes can partially succeed across the two stores.
- Safe modification: Treat Postgres as canonical, keep Qdrant rebuild tooling working, and add idempotency around memory extraction/upsert.
- Test coverage: Unit memory tests exist in `backend/tests/unit/runner/test_memory.py`; full Postgres/Qdrant tests in `backend/tests/integration/test_postgres_memory_storage.py` are skipped unless integration env vars are configured.

## Scaling Limits

**Single-process task execution:**
- Current capacity: One backend process can execute multiple asyncio tasks, limited by model calls, synchronous tool parsing, Postgres connections, and `agent_timeout_seconds`.
- Limit: Multi-worker deployments are rejected through `WEB_CONCURRENCY`, `UVICORN_WORKERS`, and `GUNICORN_WORKERS`, so horizontal process scaling does not support active task execution.
- Scaling path: Introduce a durable job queue with task leases, a worker heartbeat, distributed cancellation, and event publishing before enabling multiple workers.

**Per-request database connection creation:**
- Current capacity: Each storage method opens a new psycopg connection.
- Limit: Many polling streams, task list calls, or event writes can exhaust Postgres connection limits and add connection setup overhead.
- Scaling path: Add a connection pool and separate short-lived API reads from runner writes.

**Uploaded document parsing is bounded by upload size, not parse complexity:**
- Current capacity: Defaults allow 10 files and about 10 MB per file.
- Limit: DOCX/XLSX files can be expensive to parse even within byte limits, especially with large sheets, many styles, or complex workbook structures.
- Scaling path: Add parse-time limits, structural limits, digest-level parse caches, and safer Excel read modes.

**Task history and event history have no retention policy:**
- Current capacity: Tasks, messages, events, runs, artifacts, tool cache rows, and long-term memories remain until explicit deletion or cache expiry for tool results.
- Limit: Large task history increases task list latency, stream cursor query cost, disk usage, and Postgres storage.
- Scaling path: Add retention settings, archival, event compaction, artifact cleanup, and scheduled cache cleanup.

## Dependencies at Risk

**Git-pinned `langgraph-checkpoint`:**
- Risk: The dependency is pinned to a Git revision rather than a package release.
- Impact: Reproducibility depends on Git availability and the pinned commit remaining fetchable. Security and compatibility updates are not visible through normal version ranges.
- Migration plan: Move to a released `langgraph-checkpoint` package version when available, or vendor/lock the exact source with a clear upgrade process.

**DeepAgents/LangGraph/LangChain stream contract:**
- Risk: The app depends on event shapes from `deepagents`, `langgraph`, and `langchain`.
- Impact: Upgrades can break `stream_agent()`, reasoning deltas, tool events, and final-answer extraction.
- Migration plan: Upgrade with captured stream fixtures and run `backend/tests/unit/streaming/test_v2_adapter.py`, `backend/tests/unit/streaming/test_event_converter.py`, and `backend/tests/e2e/test_streaming_e2e.py`.

**External memory services are startup-critical:**
- Risk: `AgentMemoryService` requires DashScope and Qdrant during application startup when no test storage is injected.
- Impact: The backend fails startup if memory services are unavailable, even if task execution without memory would otherwise be useful.
- Migration plan: Consider a degraded mode where memory is disabled with an explicit health warning, or keep the current fail-fast policy and document it as production-required.

**Office document parsers process untrusted uploads:**
- Risk: `python-docx` and `openpyxl` parse user-uploaded DOCX/XLSX/XLSM files.
- Impact: Parser bugs, resource-heavy documents, and macro-enabled workbook handling can affect backend stability.
- Migration plan: Keep dependencies updated, parse in bounded workers, consider rejecting `.xlsm` unless macro-enabled files are explicitly required, and add malformed-file tests.

## Missing Critical Features

**No dedicated migration system:**
- Problem: Schema evolution is tied to application startup, with no migration history, rollback, or deployment sequencing.
- Blocks: Safe production schema upgrades and multi-instance deployment.

**No connection pooling or database health metrics:**
- Problem: Storage operations use direct `psycopg.connect()` per method and expose no pool stats.
- Blocks: Predictable scaling under multiple SSE streams and concurrent tasks.

**No centralized output redaction gate:**
- Problem: Memory has redaction, but final answers, event payloads, search results, and artifacts do not pass through a single configured output policy.
- Blocks: Strong guarantees that agent-visible secrets or uploaded sensitive data cannot be echoed through user-facing channels.

**No durable worker queue:**
- Problem: The task runner is in-process and cannot survive process exit except by marking running tasks interrupted on startup.
- Blocks: Horizontal execution scaling, resumable active runs, and reliable cancellation across processes.

**No task/artifact retention management:**
- Problem: There is no configured cleanup path for old tasks, event rows, artifacts, uploads, or expired tool-result cache rows.
- Blocks: Long-running local deployments with bounded disk and database growth.

## Test Coverage Gaps

**Production Postgres paths are mostly integration-skipped:**
- What's not tested: Real Postgres schema initialization, event sequencing, rename/delete, and memory storage run only when integration environment variables are configured.
- Files: `backend/tests/integration/test_postgres_memory_storage.py`, `backend/app/storage.py`
- Risk: CI without Postgres misses database regressions in the primary production storage backend.
- Priority: High

**Qdrant and DashScope behavior is lightly covered:**
- What's not tested: Network errors, collection dimension drift, partial memory write failures, rebuild performance, and recall threshold edge cases against real services.
- Files: `backend/app/memory.py`, `backend/app/memory_admin.py`, `backend/tests/integration/test_postgres_memory_storage.py`
- Risk: Memory recall can silently degrade, fail startup, or diverge between Postgres and Qdrant.
- Priority: High

**SearXNG configuration and hostile responses need more coverage:**
- What's not tested: Invalid base URLs, remote non-local URLs, very large result payloads, slow responses, redirects, and cache invalidation behavior under refresh language.
- Files: `backend/app/tools/searxng_search.py`, `backend/tests/unit/tools/test_searxng_search.py`
- Risk: Agent search can hang, leak traffic to unintended endpoints, or feed untrusted content into the model without clear operator visibility.
- Priority: Medium

**Uploaded Office document safety is under-tested:**
- What's not tested: Malformed DOCX/XLSX/XLSM files, zip-bomb-like structures, huge sheets within byte limits, formulas, external links, and parser timeouts.
- Files: `backend/app/execution/resources.py`, `backend/app/storage.py`, `backend/tests/unit/tools/test_resource_execution.py`, `backend/tests/unit/api/test_tasks.py`
- Risk: A valid upload extension can still trigger expensive parsing or parser exceptions during agent tool execution.
- Priority: High

**Auth tests do not cover non-loopback clients and proxy deployment:**
- What's not tested: Remote client rejection without token, proxy headers, LAN origin/CORS combinations, and token handling in access logs.
- Files: `backend/app/main.py`, `backend/tests/unit/security/test_auth.py`
- Risk: Deployment assumptions around local-only access can be wrong when the backend is exposed through a proxy or LAN binding.
- Priority: Medium

**Startup/shutdown lifecycle has limited coverage:**
- What's not tested: Shutdown cancellation of active runs, draining memory write tasks, interrupted runs with active Qdrant writes, and process exit during file writes.
- Files: `backend/app/main.py`, `backend/app/runner/core.py`, `backend/app/storage.py`, `backend/tests/unit/api/test_main.py`
- Risk: Reloads can leave tasks interrupted, memory indexes stale, or filesystem/database state partially updated.
- Priority: Medium

---

*Concerns audit: 2026-05-22*
