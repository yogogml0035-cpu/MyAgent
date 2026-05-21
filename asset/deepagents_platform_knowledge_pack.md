# DeepAgents Platform Knowledge Pack

## Background And Scope

This package documents the DeepAgents-powered universal agent platform that replaced the original bid-analysis system. It covers the backend agent architecture, multi-model provider, tools, streaming, SubAgent system, skill loading, API routes, and test layout.

Use it when changing agent factory, middleware assembly, model provider, tool registration, streaming events, SubAgent definitions, SKILL.md loading, API routes, or test structure.

## Business Rules

- The platform uses `create_deep_agent()` from the `deepagents` SDK as the sole execution engine. It returns a `CompiledStateGraph` ready for `.invoke()` or `.stream()`.
- `build_agent()` (in `agent/factory.py`) is the default builder; it passes `checkpointer`, `store`, and `max_concurrent_subagents` directly to `create_deep_agent()`.
- `build_agent_with_middleware()` is an alternative builder that also assembles extra middleware (SkillsMiddleware, SubAgentMiddleware) via `agent/middleware.py` before calling `create_deep_agent()`. **Do NOT use `build_agent_with_middleware()` to add `SummarizationMiddleware`** — it is already auto-injected by `create_deep_agent()`.
- `create_deep_agent()` auto-injects `TodoListMiddleware`, `FilesystemMiddleware`, `SummarizationMiddleware`, and `PatchToolCallsMiddleware`. Do NOT pass these via the `middleware` parameter — it causes duplicate middleware assertion errors.
- Skills and SubAgents are passed via `create_deep_agent(skills=..., subagents=...)` keyword arguments, not via the middleware parameter.
- The platform is DeepSeek-only. Runtime chat models are created through `langchain_deepseek.ChatDeepSeek`, and the app-level safe model IDs are limited to `deepseek-v4-flash` and `deepseek-v4-flash-thinking`.
- The model provider validates `DEEPSEEK_API_KEY`, maps the safe app-level ID to the provider model `deepseek-v4-flash`, and toggles thinking mode via the request `thinking` field.
- `MODEL_REGISTRY` in `config.py` lists the only two supported models. The `/api/models` endpoint returns those two options with an `available` flag based on whether `DEEPSEEK_API_KEY` is configured. Task creation and message sending accept an optional `model`; the API layer resolves missing values from `settings.default_model`, validates registry membership, and rejects unavailable models before scheduling a run. Draft task creation without a message only needs registry validation.
- Frontend model IDs are the same two safe app-level IDs: `deepseek-v4-flash` and `deepseek-v4-flash-thinking`. The browser may still read `/api/models` to learn whether either DeepSeek option is marked `available=false`; when that happens, task creation/upload/message submission must be blocked before a run starts for that option.
- Default model is `deepseek-v4-flash` (configurable via `MYAGENT_DEFAULT_MODEL` env var).
- Automatic history naming happens at the backend task API boundary when the first user message starts a run. `task_titles.generate_task_title()` calls the selected chat model with a compact naming prompt, sanitizes the output to a non-empty title of at most 10 visible characters, and falls back to a deterministic first-message slice if the provider fails or times out. The API layer treats both title generation and `set_task_title_if_empty()` writes as best-effort: once `storage.start_run()` succeeds, title failures must be logged and must not block `runner.start_background()`. The storage method `set_task_title_if_empty()` must only fill a blank title so a user rename remains authoritative across later messages.
- Tools are LangChain `@tool` decorated functions: deepagents filesystem tools, task-scoped resource tools, and `searxng_search` (conditional on `settings.searxng_url`, defaulting to the local engine at `http://127.0.0.1:8181/`). SearXNG must be called through the settings-bound URL; do not register the tool from settings and then read only `os.environ` at runtime.
- Conversation context is assembled deterministically on every run by `ConversationContextBuilder`: it reads the current task's Postgres message history, injects a bounded session summary plus the most recent messages, and can add 10-minute tool-cache context before the current HumanMessage. The runner then appends long-term memory recall and resource manifest messages after that deterministic session layer.
- Uploaded files are harness-style task Resources, not automatic context. Supported upload formats are `.md`, `.json`, `.txt`, `.docx`, `.xlsx`, and `.xlsm`; `.doc`, `.xls`, `.csv`, and arbitrary local paths are not accepted in v1. Upload events keep `file_uploaded` and include a `resource_ref` with stable `media_type` values: `markdown`, `json`, `text`, `word`, or `excel`.
- Resource execution uses `app.execution.resources.LocalResourceExecutionAdapter` as an in-process Provision/Execute boundary. `list_uploaded_resources`, `inspect_resource`, `read_resource_text`, and `read_resource_table` are thin LangChain adapters over `ExecutionRequest`/`ExecutionResult`; failures return `{ok:false,error:{code,message,retryable}}` tool-call JSON rather than crashing the runner. User input errors such as invalid Excel ranges must be `retryable:false`, and document/workbook handles must be closed on both success and error paths before returning.
- Resource tools may only resolve current task uploads under `settings.workspace_root / task_id / uploads`. Future local-path support must first register or copy the file as a current-task resource; do not let a resource tool read arbitrary host paths directly.
- `TaskRunner.start()` injects deterministic conversation context and long-term memory context before the current HumanMessage, then appends a small resource manifest `SystemMessage` when uploads exist. The manifest includes filename, resource_id, format, size, and digest only; it must never include uploaded body text. `build_agent()` also passes `RESOURCE_TOOL_SYSTEM_PROMPT` so the model knows to inspect/list resources before reading pages or table ranges. The current built-in model-facing instruction layer is localized in Chinese across title generation, resource prompts, built-in subagents, bundled SKILL.md files, and SearXNG tool/result labels to avoid mixed-language runtime guidance. The runner emits `context_loaded` and `memory_recalled` events so the frontend can show that same-task history and per-user memory were loaded.
- Filesystem tools validate paths stay within `workspace_root` for security.
- SubAgents are `SubAgent` TypedDicts with `name`, `description`, `system_prompt`, and optional `model`/`tools`/`skills`. Three built-in: `researcher`, `coder`, `file-analyst`.
- Skills follow the DeepAgents SKILL.md convention: YAML frontmatter with `name` and `description`, plus Markdown instructions. Loaded from directories listed in `settings.skills_dirs`.
- Browser-facing project skill discovery is a separate safety boundary from runtime skill loading. `GET /api/skills` uses `backend/app/skills/project.py` to code-locate the repository `backend/skills` directory and returns only `name` and `description`; it must not read `settings.skills_dirs`, `MYAGENT_SKILLS_DIRS`, `.agents/skills`, Codex global skills, user home directories, skill paths, Markdown bodies, or extra frontmatter.
- Task message submission accepts optional selected skill names in `skills`. The backend validates them against the project skill projection before starting a run, then formats visible references such as `[$web-research]` into the effective message passed consistently to storage, automatic title generation, and `runner.start_background()`. The composer skill picker/chips are a separate browser affordance and should not show `$` in the leading marker; keep `$` only where the persisted message reference contract explicitly requires it.
- Streaming uses `agent.astream(input, stream_mode=["messages", "updates"], version="v2")` via the v2 adapter (`v2_adapter.py`). LangGraph v2 returns chunks as **dicts** with keys `{type, ns, data}`, not `(namespace, mode, payload)` tuples. The adapter must handle both formats for robustness. Events are converted to `EventRecord` objects via `event_converter.py`. Tool-call chunks are incremental: the adapter must accumulate chunks by tool-call index/id so the persisted `tool_call` event can expose the tool name plus usable parameter items before the matching `tool_result` row.
- Progress-log display is a user-facing projection over the append-only event log. The collapsed timeline must keep backend `EventRecord.seq` order, merge provider reasoning deltas only into contiguous `"AI正在思考"` segments, merge `assistant_answer_delta` only into contiguous `"AI正在生成结果"` segments, collapse `status_update` events into generic `"状态已更新"` rows, hide `final_answer` from collapsed rows while keeping it in merged diagnostics/raw JSONL, and render tool progress as stage-specific rows instead of one lifecycle row. `tool_call` rows should merge only same-`tool_call_id` chunks from the same stage so partial argument deltas do not spam duplicates; `selecting_tool` renders `"准备调用{工具标签}"`, `using_tool` renders `"调用{工具标签}"`, and `tool_result` renders a separate result row such as `"{工具标签}已返回结果"` or `"{工具标签}暂无可用结果"`. Row diagnostics carry raw merged records for internal/debug use, but per-row expansion and per-row copy use compact display-only JSON projections: thinking/answer rows expose only final `payload.*_stream.content`, status rows keep raw status diagnostics, tool-call rows expose one normalized `tool_call` object, and tool-result rows expose one normalized `tool_result` object. The run-level raw JSONL copy remains the authoritative full-fidelity debug export. `values_snapshot` stays out of collapsed rows and may be attached to nearby raw status diagnostics or remain available through raw JSONL copying. Terminal runner events must still include display-safe `payload.live` metadata for diagnostics and refresh semantics, but `final_answer` itself no longer renders as a separate visible progress row.
- SSE endpoint at `GET /api/tasks/{task_id}/stream` provides real-time output. Frontend uses `EventSource` API with token as query parameter.
- SSE `_event_stream` polls `storage.read_events(task_id, after_id=last_event_id)` every 0.5s. `last_event_id` must be initialized to `None` (not `""`) so the first poll returns all existing events. An empty string causes `read_events` to skip every event because `after_id is None` evaluates to `False` and no event has `id == ""`.
- Event pagination cursors are best-effort client hints, not authority. If `storage.read_events(task_id, after_id=...)` cannot find the supplied event id, it must fail open by returning the full ordered event stream for that task. Returning `[]` on an unknown cursor silently loses SSE/HTTP polling recovery events after browser reconnects, stale tabs, local state resets, or event-id format migrations.
- `TaskRunner` manages agent lifecycle: build agent → recall long-term memory → stream events → convert → collect → persist events to storage → update task status → emit final answer event → schedule completed-run memory write. `TaskRunner.__init__` receives `settings`, `storage`, and optional `memory_service` from `main.py`. `start_background()` accepts `run_id` from `storage.start_run()` to ensure unified run_id across storage and streaming events. After agent execution, events are persisted via `storage.append_event()` and task status is updated to terminal state (`complete`/`failed`/`cancelled`). The runner also writes run-scoped terminal events (`task_completed`, `task_failed`, `task_cancelled`) together with terminal status updates, so the UI can correlate completion, failure, or cancellation with the active run. Supports cancellation via `cancel()`. Enforces `settings.agent_timeout_seconds` via `asyncio.timeout()`.
- `create_app()` uses FastAPI `lifespan` instead of `@app.on_event("startup")`. Startup interruption of stale running tasks must stay inside that lifespan handler, and tests that need startup side effects must enter `TestClient` as a context manager (`with TestClient(app):`).
- API endpoints `create_task` and `send_message` are `async def` to allow `asyncio.create_task` on the event loop. `cancel_task` delegates terminal status and event persistence to `TaskRunner.cancel()`/the running background task rather than appending a second unscoped cancellation event.
- Filesystem tools are scoped to per-task workspace (`settings.workspace_root / task_id`), not the global sessions root. This prevents cross-task file access.
- Task API routes follow REST conventions: `POST /api/tasks` (create), `GET /api/tasks` (list), `GET /api/tasks/{id}` (read), `PATCH /api/tasks/{id}` (rename history title), `DELETE /api/tasks/{id}` (delete non-running task), `POST /api/tasks/{id}/messages` (send message), `POST /api/tasks/{id}/cancel` (cancel). `GET /api/tasks/{id}?include_events=false` is the lightweight refresh path and must return the same task shape with an empty `events` list. Artifact routes are first-class API routes: `GET /api/tasks/{id}/artifacts/{name}` for latest or legacy artifacts and `GET /api/tasks/{id}/runs/{run_id}/artifacts/{name}` for run-scoped artifacts.
- Frontend artifact fetches must only use the current API origin and current task artifact routes: `/api/tasks/{id}/artifacts/{name}` or `/api/tasks/{id}/runs/{run_id}/artifacts/{name}`. Reject external origins, non-artifact paths, wrong task IDs, query/hash redirects, and artifact-name mismatches before attaching `X-MyAgent-Token`.
- Opening an HTML artifact must not top-level navigate to a same-origin `blob:` URL. The frontend should keep the popup at `about:blank`, write a preview shell, and load the HTML blob inside an iframe with `sandbox=""` and no script permissions.
- Upload validation errors must map to stable client-facing HTTP status codes: duplicate filename conflicts return 409, size/count/request limits return 413, unsupported extensions or invalid JSON content return 400, and missing tasks return 404. JSON files are still validated at upload time; Word/Excel parsing happens later through resource tools. The storage layer may raise domain exceptions, but API routes must not leak these as 500 responses.
- Multipart upload request limits must be enforced before FastAPI `UploadFile` parsing reaches storage. `main.py` checks `Content-Length` and wraps the ASGI receive stream for `multipart/form-data`; storage-level per-file and aggregate limits remain a second line of defense.
- Auth middleware enforces loopback-only access by default; non-local access requires `MYAGENT_ACCESS_TOKEN`.
- Frontend local development and production builds both use Next.js's default `.next` output directory; stop the dev server before running `npm run build` so two Next processes do not write the same cache at once.
- Local development on WSL-mounted Windows paths such as `/mnt/c` or `/mnt/d` must assume native filesystem notifications can be unreliable. Keep polling watchers enabled for hot reload: frontend uses `watchOptions.pollIntervalMs`, `WATCHPACK_POLLING=true`, and `CHOKIDAR_USEPOLLING=true`; backend uses `WATCHFILES_FORCE_POLLING=true` with `uvicorn --reload`. `MYAGENT_DEV_FORCE_POLLING=0` is only for confirmed-stable WSL-native Linux paths.
- Local WSL dev scripts default backend and frontend bind hosts to `127.0.0.1`. Binding to `0.0.0.0` is an explicit LAN exposure mode and must be paired with access token and CORS configuration.
- Frontend type checking runs `next typegen && tsc --noEmit`; `next-env.d.ts` is generated and ignored instead of being version-controlled.
- Frontend CI treats lint warnings as failures because `frontend/package.json` runs `eslint . --max-warnings=0`; a warning-free local run is required before pushing, and a remote lint warning is a blocking CI failure, not a soft signal.
- Repository-level CI covers root docs, `asset/**`, scripts, workflow files, and `.gitattributes`; script changes must keep PowerShell help/dry-run, Shell syntax, stop-port dry-run, and whitespace checks passing.
- Structured task state uses Postgres as the production authority for tasks, runs, messages, and append-only events. The task file workspace under `settings.workspace_root / task_id` is intentionally limited to `uploads/` and `artifacts/`: uploads hold source file bytes, while artifacts hold run-scoped generated files and legacy mirrored standard reports. `uploads/` may be created eagerly with the task, but `artifacts/` should be created lazily only when the system writes a run manifest or a real artifact file; starting a run alone must not create an empty artifact directory. Do not create new top-level task folders such as `logs/`, `subagents/`, or root-level manifest files unless a new stable file contract is explicitly designed.
- Deleting a non-running task must remove both the Postgres task row (with cascading runs/messages/events) and the matching local task file workspace directory named by `task_id`. The browser history delete action depends on the public `DELETE /api/tasks/{id}` route for both halves; do not implement frontend-only deletion.
- Event seq is generated by incrementing `tasks.latest_event_seq` and inserting the event in one database transaction; do not restore per-append full log scans.
- Long-term memory uses Postgres as the canonical store and Qdrant as the semantic index, with DashScope-compatible embeddings. Startup requires Postgres, Qdrant, and embedding configuration to be available. Memory is written per user (`MYAGENT_DEFAULT_USER_ID` in v1), and the extracted memory whitelist is limited to stable `preference`, `profile_fact`, `project_rule`, and `stable_workflow` facts. Postgres stores the canonical memory rows; Qdrant stores schema v2 semantic payloads with `user_id`, `memory_id`, `memory_type`, `text`, `confidence`, `source_task_id`, and `source_run_id`. It must not store uploaded source text, complete artifacts, stream deltas, raw tool logs, secrets, authorization headers, API keys, provider key env names, customer canary markers, or customer-sensitive text. Memory summaries must be sanitized before embedding/upsert and must be skipped if sanitized text still scans as sensitive. Dedicated admin commands can `reset-qdrant` or `rebuild-qdrant`; the rebuild command deletes and recreates only the configured memory collection, then repopulates it from Postgres canonical rows.
- Long-term memory is an auxiliary subsystem. Runner recall and completed-run writes must run off the event loop thread (for example via `asyncio.to_thread`). Recall failures should degrade to running without memory context, and completed-run memory write failures must not block `task_completed`/`final_answer` emission or change a successful task to `failed`.
- Any bug fix, feature, or other behavior change must pass live browser E2E acceptance against a running frontend and backend, and screenshot evidence must be stored under `frontend/e2e-playwright/`. Unit, integration, API, lint, or build checks do not replace this requirement.
- Browser E2E follows a layered workflow: Chrome DevTools MCP may be used during development to explore local pages, console, network, DOM state, screenshots, and performance signals; once the flow is understood, stable expectations must be encoded as Playwright specs. CI and delivery gates only trust repeatable Playwright/test command results, not one-off DevTools observations.
- `frontend/e2e-playwright/` must keep a `README.md` comment file that explains the directory purpose, screenshot evidence role, and redaction expectations. If the repo lacks an E2E entrypoint for the changed scenario, add it in the same change before considering the work complete.
- Selected-file preview changes in the chat composer must preserve the `DESIGN.md` warm-canvas visual system: `--surface*`, `--hairline`, `--primary`, and compact neutral action controls. Multiple selected files render as separate filename-only cards, with per-file removal revealed on hover/focus. Browser acceptance for this path lives in `frontend/e2e-playwright/test_upload_preview_design.spec.mjs` and should verify desktop and narrow-screen card screenshots.
- Skill selector and chip changes in the chat composer must preserve the same warm-canvas system and use dedicated `.skillPicker*` / `.skillChip*` CSS selectors rather than coupling to `.modelPicker*`. The leading marker should be a neutral visual glyph, not a literal `$`; the slash character remains only the trigger typed in the textarea. Browser acceptance for this path lives in `frontend/e2e-playwright/test_skill_selector.spec.mjs`; evidence should include desktop and narrow-screen screenshots under `frontend/e2e-playwright/e2e-YYYYMMDDHHMMSS/`.
- The left history sidebar is height-constrained inside the viewport: `ChatSidebar` keeps the new-chat button at the top, the history list as an independently scrollable middle region, and the destructive clear-all action at the bottom. The clear-all action must confirm with the user, refuse while any visible/current task is running, and delete through the public `DELETE /api/tasks/{id}` route for each visible history item rather than mutating frontend state only.
- Repository-wide line-ending normalization is enforced with a root `.gitattributes`: text files default to LF, while PowerShell scripts use CRLF on checkout.
- If the work includes pushing a branch, opening/updating a PR, or merging a PR, completion requires the GitHub remote checks to finish successfully. Local green runs are necessary but not sufficient while remote Actions are still pending or failing.

## Input And Output Examples

- Create task: `POST /api/tasks` → `{"task_id": "...", "status": "idle", "model": "deepseek-v4-flash", ...}`
- Lightweight task refresh: `GET /api/tasks/{id}?include_events=false` → same task state shape with `"events": []`
- Send message: `POST /api/tasks/{id}/messages` body: `{"message": "搜索最新的AI新闻", "model": "deepseek-v4-flash"}`
- Auto-generated history title: first `POST /api/tasks/{id}/messages` response includes `"title": "AI新闻搜索"` (non-empty, ≤10 visible characters) and `GET /api/tasks` returns the same title for the left history list unless the user has renamed it.
- Rename history item: `PATCH /api/tasks/{id}` body: `{"title": "项目复盘"}` updates the custom title used by `GET /api/tasks`.
- Delete history item: `DELETE /api/tasks/{id}` removes a non-running task and its local task files; running tasks must be cancelled or completed before deletion.
- Download artifact: `GET /api/tasks/{id}/runs/{run_id}/artifacts/report.html` → `FileResponse` with the artifact MIME type and safe filename.
- Build agent: `build_agent(settings, tools=get_platform_tools(settings), skills=["./skills"])`
- Resource tool result: `{"ok": true, "data": {"schema_version": 1, "resources": [{"name": "brief.docx", "format": "word"}]}}`
- Resource tool error: `{"ok": false, "error": {"code": "resource_not_found", "message": "...", "retryable": false}}`
- Model ID format: `"deepseek-v4-flash"`, `"deepseek-v4-flash-thinking"`
- SSE event: `event: message\ndata: {"type": "agent_message", "text": "..."}\n\n`
- Context event: `{"type": "context_loaded", "payload": {"summary_present": true, "recent_message_count": 2, "cached_tool_result_count": 1, "live": {"display_text": "已载入会话上下文"}}}`
- Memory event: `{"type": "memory_recalled", "payload": {"user_id": "local-user", "memory_count": 1, "live": {"display_text": "已载入长期记忆"}}}`

## Boundary Conditions

- `create_deep_agent()` does NOT accept duplicate middleware instances — assertion error if duplicates found.
- `storage.py` still depends on compatibility shims in `app/contracts/__init__.py` and `app/reasoning_trace.py` for session events, resource refs, and reasoning trace payloads. Do not remove the shims until those contracts are replaced across storage, streaming, and tools.
- `schemas.py` inlines `TaskMode` and `InputScope` Literal types (previously from deleted `intent.py`).
- Missing API keys cause graceful errors in provider (not crashes). The SearXNG search tool returns an error string if the configured local engine is unavailable.
- Missing provider API keys make affected models unavailable at `/api/models` and must block run-starting requests before background scheduling. This avoids creating task runs that are guaranteed to fail only after storage state changes. The browser must honor DeepSeek `available=false` before task creation, upload, or send starts, even though the picker still renders only the DeepSeek V4 Flash / Thinking options.
- History rename/delete are real task API operations, not frontend-only state. Rename stores a bounded custom task title; delete must reject running tasks to avoid orphaning an active in-process runner.
- Automatic history naming is best-effort and must not block the task lifecycle indefinitely. Provider errors or timeout fall back to the local first-message title; unexpected title generator or storage write errors are logged and bypassed so the already-started run is still handed to `TaskRunner.start_background()`. Model output is still normalized server-side to remove prefixes/quotes/newlines and enforce the 10-character display contract. Do not overwrite an existing custom title when later messages are sent.
- Task file workspaces are not a second state store. Postgres owns lifecycle state; local task directories own only uploaded bytes and generated artifact bytes. `run.json` manifests, when used for artifact refs, live under `artifacts/runs/{run_id}/` rather than the task root.
- Artifact names are normalized file names only, not paths. Artifact download routes must resolve through `TaskStorage.resolve_artifact()` or `TaskStorage.resolve_run_artifact()` so path traversal and cross-run access stay blocked.
- Upload names are normalized leaf filenames only. Resource tool inputs may use resource_id or filename but must reject paths, traversal attempts, cross-task access, and unsupported suffixes.
- Run-scoped artifact registration uses `runs.artifact_names` as the authoritative index for frontend rendering and `resolve_run_artifact()` downloads. `write_run_text()` / `write_run_json()` must record every valid run-scoped artifact name, while `RUN_ARTIFACT_NAMES` only controls which standard artifacts are additionally mirrored to the legacy top-level `artifacts/` path.
- Test fakes must preserve the production artifact contract. `backend/tests/fakes.py::InMemoryTaskStorage` should mirror `PostgresTaskStorage` for run-scoped artifact registration, latest completed run resolution through `/api/tasks/{id}/artifacts/{name}`, fixed-artifact top-level mirroring, legacy fallback, and refusal to download unrecorded run files.
- Frontend artifact URL validation is an additional client boundary, not a replacement for backend path checks. Backend routes must keep resolving through storage, and frontend allowlists must continue to reject any URL that is not on the trusted API origin and artifact route shape.
- `SKILL.md` files without valid YAML frontmatter are silently skipped during discovery.
- `next typegen` loads `next.config.mjs` with the production build phase; keep any required config inputs available before running frontend type checks in CI.
- Remote CI status is part of the verification boundary for GitHub actions such as PR creation and merge. A pending run is not a pass, and a warning that escalates to job failure must be fixed the same as an error.
- DevTools MCP is a diagnostic aid, not an acceptance oracle. After a Playwright failure, first inspect Playwright error output, trace, screenshots, videos, and logs; use Chrome DevTools MCP only when live-page console/network/DOM/performance inspection is needed, then promote any stable failure signal back into Playwright or lower-level tests.

## Known Pitfalls

- **Middleware duplication**: Never pass `TodoListMiddleware`, `FilesystemMiddleware`, `SummarizationMiddleware`, or `PatchToolCallsMiddleware` via the `middleware` param — `create_deep_agent` auto-injects them.
- **Two-model boundary**: The product only supports `deepseek-v4-flash` and `deepseek-v4-flash-thinking`. Any other model ID must fail validation.
- **EventSource auth**: Browser `EventSource` API doesn't support custom headers; token must be passed as query parameter `?token=xxx` for SSE. Backend `authorize_task_request` reads token from headers (`X-MyAgent-Token`, `X-Agent-Chat-Token`, `Authorization: Bearer`) and query param.
- **SSE frontend backoff**: Browser-side SSE reconnect must be capped and use exponential backoff. Any backend SSE payload shaped as `{type: "error", detail: "..."}` is user-visible and should stop normal event processing for that message, then refresh task state defensively.
- **Run-scoped terminal events**: Do not append terminal events from API endpoints after calling the runner. The runner owns terminal status plus terminal event writes so the `run_id` stays consistent and duplicate unscoped events are not produced.
- **Pre-run enhancement gap**: After `storage.start_run()` marks a task `running`, only required scheduling code should stand between that call and `runner.start_background()`. Non-critical enhancements such as automatic titles must catch/log their own failures; otherwise a request can return 500 while leaving a `running` task with no background runner.
- **Task workspace drift**: `backend/storage/sessions/<task_id>/` is a file workspace, not the state authority. Creating root-level files or legacy folders there makes cleanup and mental models drift. Keep durable state in Postgres and durable bytes under `uploads/` or `artifacts/` only.
- **Delete cleanup drift**: Removing a task from Postgres without deleting the matching task directory leaves uploaded source files and generated artifacts orphaned on disk. The delete API and browser history deletion must stay coupled to storage-level directory cleanup.
- **Artifact route drift**: Frontend artifact cards depend on `ArtifactRecord.url` pointing to real backend routes. Adding new artifact storage locations requires updating both the URL generator and the corresponding FastAPI download route.
- **Run artifact index drift**: Do not make artifact registration depend on the legacy standard-report whitelist. If a run artifact is written but missing from `runs.artifact_names`, the file can exist on disk while the task state hides it and the run-scoped download route returns 404.
- **Fake storage drift**: API tests often use `InMemoryTaskStorage`; keep its artifact behavior aligned with `PostgresTaskStorage`. A fake that returns any file from disk or omits latest-run compatibility URLs can let tests pass while production download routes fail.
- **Artifact URL token leak**: Do not pass backend-provided artifact URLs directly to `fetch`. `buildArtifactRequest()` owns allowlist validation and is the only place that may attach `X-MyAgent-Token` for artifact downloads.
- **HTML artifact preview XSS**: Do not navigate an opened window to an artifact blob. HTML reports must render through a sandboxed iframe without `allow-scripts` so generated scripts cannot run in the app origin.
- **Upload exception leakage**: Storage upload validation exceptions should be translated by the API layer. A malformed user upload is a 4xx client error, never an unhandled 500.
- **Resource tool boundary drift**: Do not put document parsing directly in `TaskRunner` or upload API side effects. Uploaded bodies stay out of model context until a resource tool explicitly reads a page, block, sheet, or range.
- **Retryable resource errors**: Do not let malformed resource-tool input escape to the adapter safety net as `execution_error` with `retryable:true`. Classify invalid user input with a stable code such as `invalid_range` and `retryable:false`, and close any opened Word/Excel/file handles in `finally`.
- **Large document context blowup**: Resource tools must paginate or range-limit text/table output. Do not return complete Word/Excel contents by default.
- **storage.py coupling**: TaskStorage is now Postgres-backed for structured state, but still exposes compatibility methods for session events, artifact refs, and reasoning traces. Keep storage changes synchronized with API, runner, streaming, and file tools.
- **Single-process runtime**: The platform uses an in-process runner even though task state is in Postgres. Multi-worker deployment will break cancellation and active-run ownership until a lease/queue design is added.
- **Timeout enforcement**: `TaskRunner.start()` enforces `settings.agent_timeout_seconds` via `asyncio.timeout()`. If the deepagents SDK or LLM call hangs, the run is terminated after the configured timeout and a warning is logged.
- **checkpointer/store passthrough**: `build_agent()` passes `checkpointer` and `store` to `create_deep_agent()`, but the current deployment does not use LangGraph-native persistence. Task lifecycle state is managed by Postgres TaskStorage; enabling LangGraph-native persistence would be a separate design.
- **LangGraph checkpoint source pin**: `backend/pyproject.toml` pins `langgraph-checkpoint` through `tool.uv.sources` to the `langchain-ai/langgraph` Git commit `2e5025ec1ac8d435840ed4a972097de87aaa2eab` (`libs/checkpoint`). This is intentional: the latest PyPI stable release still emits the startup `LangChainPendingDeprecationWarning`, while that upstream commit already switched `jsonplus.py` to `Reviver(allowed_objects="core")`.
- **LangGraph v2 stream format**: `agent.astream(..., version="v2")` returns chunks as dicts `{type, ns, data}`, NOT tuples `(namespace, mode, payload)`. Unpacking as a 3-tuple silently iterates dict keys (`"type"`, `"ns"`, `"data"`), causing `mode = "ns"` to be logged and all events dropped. The v2_adapter must check `isinstance(chunk, dict)` and extract `chunk["type"]` / `chunk["data"]`.
- **Generated Next type files**: `next-env.d.ts` and route types are generated artifacts. Do not review or commit them as source changes; rerun `npm run typecheck` if they are missing locally.
- **Warning-as-error CI**: The frontend workflow fails on ESLint warnings because lint runs with `--max-warnings=0`. Treat “warning only” reports from GitHub Actions as blocking failures.
- **Local-vs-remote verification gap**: A local pass does not prove a PR is merge-ready. GitHub Actions may still fail because of workflow environment differences, matrix jobs, or warning-as-error settings; do not stop at push/PR creation when the request includes completing that remote action.
- **DevTools acceptance drift**: Chrome DevTools MCP checks are useful for exploration and root cause analysis, but they are not repeatable CI evidence. Do not close behavior changes on DevTools screenshots or console/network observations unless the stable expectation is also covered by Playwright or another automated test.
- **WSL mounted-path hot reload**: If frontend or backend changes only show up after a restart, first check whether the repo is under `/mnt/c` or `/mnt/d` and whether polling watcher env vars are active. Do not remove polling from dev scripts without replacing it with an equally reliable WSL-mounted-path strategy.

## Related Code Paths

- Backend config: `backend/app/config.py`
- Backend dependency source pin: `backend/pyproject.toml`, `backend/uv.lock`
- Model provider: `backend/app/models/provider.py`, `backend/app/models/registry.py`
- Automatic task titles: `backend/app/task_titles.py`, `backend/app/api/tasks.py`, `backend/app/storage.py`
- Agent factory: `backend/app/agent/factory.py`, `backend/app/agent/middleware.py`
- Tools: `backend/app/tools/searxng_search.py`, `backend/app/tools/filesystem_bridge.py`, `backend/app/tools/registry.py`, `backend/app/execution/resources.py`
- Streaming: `backend/app/streaming/v2_adapter.py`, `backend/app/streaming/event_converter.py`, `backend/app/streaming/sse.py`
- Runner: `backend/app/runner/core.py`
- SubAgents: `backend/app/subagents/definitions.py`, `backend/app/subagents/registry.py`
- Skills: `backend/app/skills/loader.py`, `backend/app/skills/registry.py`, `backend/app/skills/project.py`
- API routes: `backend/app/api/tasks.py`, `backend/app/api/files.py`, `backend/app/api/artifacts.py`, `backend/app/api/streaming.py`, `backend/app/api/models.py`
- Entry point: `backend/app/main.py`
- Skills directory: `backend/skills/web_research/SKILL.md`, `backend/skills/code_review/SKILL.md`
- Compatibility shims: `backend/app/contracts/__init__.py`, `backend/app/reasoning_trace.py`
- Memory service: `backend/app/memory.py`
- Conversation context / agent store / memory admin: `backend/app/conversation_context.py`, `backend/app/agent_store.py`, `backend/app/memory_admin.py`
- Frontend CI workflow: `.github/workflows/frontend-ci.yml`
- Backend CI workflow: `.github/workflows/backend-ci.yml`
- Repository CI workflow: `.github/workflows/repository-ci.yml`
- Frontend type generation and ignore rules: `frontend/package.json`, `frontend/.gitignore`, `frontend/tsconfig.json`
- Frontend artifact state/API/security: `frontend/app/task-state.ts`, `frontend/lib/task-api.ts`, `frontend/hooks/use-task-workspace.ts`
- Frontend progress-log projection/UI: `frontend/app/workspace-view.ts`, `frontend/components/chat/TaskConversation.tsx`, `frontend/app/globals.css`
- Frontend DeepSeek V4 Flash / Thinking model picker and availability guard: `frontend/components/chat/ChatComposer.tsx`, `frontend/hooks/use-task-workspace.ts`, `frontend/lib/task-api.ts`
- Frontend history sidebar scroll, rename/delete, and clear-all UI: `frontend/components/chat/ChatSidebar.tsx`, `frontend/hooks/use-task-workspace.ts`, `frontend/app/globals.css`
- Frontend selected upload preview UI: `frontend/components/chat/ChatComposer.tsx`, `frontend/app/globals.css`
- Local dev scripts: `scripts/start-dev-wsl.ps1`, `scripts/dev-terminal-runner.sh`, `scripts/stop-dev-ports.sh`
- Browser E2E acceptance evidence: `frontend/e2e-playwright/README.md`
- Resource upload harness E2E: `frontend/e2e-playwright/test_resource_upload_harness.spec.mjs`
- Automatic history title E2E: `frontend/e2e-playwright/test_auto_title_generation.spec.mjs`
- History sidebar E2E: `frontend/e2e-playwright/test_history_menu_affordance.spec.mjs`, `frontend/e2e-playwright/test_history_scroll_clear.spec.mjs`
- Upload preview design E2E: `frontend/e2e-playwright/test_upload_preview_design.spec.mjs`
- Skill selector E2E: `frontend/e2e-playwright/test_skill_selector.spec.mjs`
- Progress-log disclosure E2E: `frontend/e2e-playwright/test_progress_log_disclosure.spec.mjs`
- Repository line-ending policy: `.gitattributes`

## Related Test Paths

- Unit tests:
  - `backend/tests/unit/agent/`
  - `backend/tests/unit/models/`
  - `backend/tests/unit/tools/`
  - `backend/tests/unit/skills/`
  - `backend/tests/unit/streaming/`
  - `backend/tests/unit/runner/`
  - `backend/tests/unit/api/`
  - `backend/tests/unit/security/`
  - `backend/tests/unit/storage/`
  - `backend/tests/unit/runner/test_memory.py`
  - `backend/tests/unit/security/test_scanner.py`
  - `backend/tests/unit/session/`
- Runtime contract tests: `backend/tests/unit/api/test_artifacts.py`, `backend/tests/unit/api/test_models.py`, `backend/tests/unit/api/test_tasks.py`, `backend/tests/unit/runner/test_core.py`, `frontend/tests/state/test_task_state.test.ts`, `frontend/tests/workspace/test_task_workspace.test.ts`
- Conversation context/store tests: `backend/tests/unit/runner/test_conversation_context.py`, `backend/tests/unit/storage/test_agent_store.py`
- Automatic title tests: `backend/tests/unit/models/test_task_titles.py`, `backend/tests/unit/api/test_tasks.py`, `backend/tests/unit/storage/test_storage.py`, `frontend/e2e-playwright/test_auto_title_generation.spec.mjs`
- Resource execution tests: `backend/tests/unit/tools/test_resource_execution.py`, `backend/tests/unit/tools/test_registry.py`, `backend/tests/unit/runner/test_core.py`, `frontend/tests/upload/test_file_upload.test.ts`
- Upload preview design tests: `frontend/tests/upload/test_upload_preview_design.test.ts`, `frontend/e2e-playwright/test_upload_preview_design.spec.mjs`
- Integration tests: `backend/tests/integration/`
- E2E tests: `backend/tests/e2e/test_streaming_e2e.py`
- Real-service integration tests: `backend/tests/integration/test_postgres_memory_storage.py` (runs when Postgres/Qdrant/DashScope env is configured)
- Frontend tests:
  - `frontend/tests/state/`
  - `frontend/tests/workspace/`
  - `frontend/tests/upload/`
  - `frontend/tests/model/`
- Progress-log projection tests: `frontend/tests/workspace/test_workspace_view.test.ts`
- Browser E2E acceptance directory: `frontend/e2e-playwright/`
- Test fixture: `backend/tests/conftest.py` (provides `test_settings` fixture with tmp_path)

## Verification Commands

```bash
cd /mnt/d/AgentProject/MyAgent/backend
uv run ruff check app/
uv run pytest tests/ -v
uv run python -c "from app.main import create_app; create_app()"
```

```bash
cd /mnt/d/AgentProject/MyAgent/frontend
npm ci
npm run typecheck
npm test
npm run lint
npm run build
```

For any behavior-changing task, also run the relevant live browser E2E flow against the started app and save acceptance screenshots under `frontend/e2e-playwright/`. If the repo does not yet expose the needed E2E entrypoint for that flow, add it in the same change before closing the task.

For new, unstable, or failing browser flows, use Chrome DevTools MCP as the exploratory/debugging step: open the local page, observe console and network, inspect visible UI state, capture useful screenshots, and identify stable user-facing assertions. Encode those assertions in Playwright before treating the flow as covered. If Playwright fails, inspect its trace/video/screenshot/logs first, then use DevTools MCP for live diagnosis only when those artifacts are insufficient.

If the task includes pushing a branch, opening/updating a PR, or merging a PR, also wait for GitHub remote CI / checks to complete and confirm that all required jobs are green before closing the task.

## Frontend Stream Accumulation And Dynamic States

- `workspace-view.ts:accumulateStreamedAnswer` concatenates all `assistant_answer_delta` chunks by `streamIndex` order. Do NOT revert to `latestStreamedAnswer` (which only kept the last delta) — that caused isolated punctuation characters to appear as the full AI reply.
- AI reply card only appears when content passes `hasMeaningfulContent` (≥1 non-punctuation, non-whitespace character after stripping Chinese and ASCII punctuation). This prevents a lone period "。" from triggering the card.
- Dynamic loading status precedence: `agentActivity.phase` > `live.stage` > default fallback `"AI正在思考..."`. Phase mapping: `planning`→"正在规划任务...", `reasoning`→"AI正在思考...", `tool_use`→"正在调用工具...", `file_operation`→"正在处理文件...", `finalizing`→"AI正在生成结果".
- New DeepAgent stream events must include display-safe `payload.live` metadata for user-facing progress logs while preserving the raw event record for diagnostics. `tool_call`/`tool_result` live metadata carries tool category labels such as "联网搜索" or "读取文件", raw tool names, bounded parameter items, tool-call ids, and result status/count when available. `status_update` folds internal nodes like middleware hooks into raw diagnostic metadata, but the collapsed user-facing row must always use the generic text `"状态已更新"` rather than exposing node-specific text such as `"正在准备任务..."` or `"AI正在思考..."`. Middleware nodes containing `Tool` (for example `PatchToolCallsMiddleware.before_agent`) must never be classified as actual tool execution. Provider-exposed reasoning chunks use `assistant_thinking_delta` with `live.kind="think"` and remain process-log content only.
- `ExecutionLog.rawRecord` is preserved for row-level diagnostics and JSONL log copying, but it is non-enumerable after normalization so raw provider chunks, tool payloads, and internal node names do not leak into default rendering or `JSON.stringify(state.logs)` checks.
- `buildLogClipboardText()` copies raw diagnostic JSONL, one event per line, and must not be changed when adjusting row-level display. The default progress card remains a Chinese user-facing timeline; each row expansion must render JSON only (no derived metadata table/labels such as event type, display mode, thinking content, or result status). `LiveLogDiagnostics.records/rawJson` preserve raw merged diagnostics for internal/debug inspection, while `LiveLogDiagnostics.displayJson` is the only source for row expansion and row copy. Thinking and answer row `displayJson` keeps the outer event skeleton but replaces `chunks`, `chunk_count`, and `accumulated_content` with a single final `content` field under `payload.thinking_stream` or `payload.answer_stream`.
- `TodoListMiddleware.after_model` and other `after_model` nodes represent model-output completion/state synchronization, not task preparation. Backend status mapping must still classify these nodes correctly in raw `payload.live` diagnostics, but frontend collapsed rows for all `status_update` records remain the generic `"状态已更新"`.
- `buildLiveLogItems` checks `agentActivity.status` (`completed`/`failed`/`skipped`) as additional terminal condition alongside `isTerminalLiveStage(live.stage)`.
- Progress log rows in `TaskConversation.tsx` are always expandable `<details>` rows. The collapsed row layout must keep the timestamp in the leftmost column for both status rows and tool rows, the display label in the middle, the per-row JSON copy icon beside it, and the disclosure arrow on the right. Tool rows now use concise stage/result titles only in the collapsed summary; raw tool name, arguments, and result payload belong in expanded JSON rather than inline summary text. Expanded diagnostics show JSON only; the summary-level copy button copies `displayJson` for that row and must not toggle the disclosure state. The trace header includes a compact expand/collapse-all button in the previous collapse-control slot, styled like a dark-surface segmented control: border/background align with the adjacent JSONL copy button in both collapsed and expanded states, and the button text flips between `"全部展开"` and `"全部折叠"` with down/up chevrons. Its action is based on whether any visible progress-log `<details>` row is currently open: zero open rows means the button says `"全部展开"` and expands every visible row; one or more open rows means the button says `"全部折叠"` and collapses every visible row, including partial-open states. Bulk expand/collapse must update the button state synchronously before the expensive `<details>` DOM changes, so large JSON diagnostics cannot leave the header button showing the previous action for several seconds. It must not affect raw JSONL copy. Tool-call row `displayJson` is a normalized object with `type`, `stage`, `tool_name`, `tool_label`, `tool_call_id`, and `args`; tool-result row `displayJson` is a normalized object with `type`, `tool_name`, `tool_label`, `tool_call_id`, `status`, and `content`. Large result display is truncated with metadata without affecting raw JSONL export. Thinking and answer-generation stream chunks stay hidden behind stable collapsed labels such as `"AI正在思考"` and `"AI正在生成结果"`; their expanded JSON must show the complete normalized content, but they must not render as AI reply cards.
- Frontend log ordering must use backend `EventRecord.seq` as the primary order whenever present, falling back to `created_at` only for legacy events without seq. Do not sort progress logs only by wall-clock timestamps, because multiple streaming events can share the same displayed second and appear out of the natural model/tool/result sequence.
- Frontend history action controls should stay within the warm-canvas visual system from `DESIGN.md`: use `--surface*`, `--hairline`, `--primary`, and `--primary-active` tokens for the compact menu, rename form, and delete affordance. Avoid reintroducing blue system-menu colors or bright destructive red fills for history rename/delete actions unless the whole design system changes.
- The history sidebar three-dot menu trigger is an affordance, not a selected pill. Hover/open/focus states must not introduce a circular border or focus ring around the dots; use subtle color and the menu surface itself to communicate the open state. Browser acceptance for this lives in `frontend/e2e-playwright/test_history_menu_affordance.spec.mjs`.
- Progress log diagnostics may communicate status through copy and glyphs, but expandable row borders and failed trace card containers should remain neutral on the dark surface. Do not use red or warm-red outline boxes around expanded raw JSON diagnostics, including successful tool-result rows, because they make normal troubleshooting output look like a blocking UI error.

## Final Answer vs Intermediate Process Distinction

**Critical architectural boundary**: `assistant_thinking_delta` and `assistant_answer_delta` events are **intermediate process tokens**, NOT the final answer. They represent provider-exposed reasoning chunks and partial answer output during streaming, and must be treated as debug/progress content only.

**Backend responsibilities**:
- `extract_final_answer()` in `v2_adapter.py` walks `state["messages"]` in reverse to find the last `AIMessage` with content but no `tool_calls`. This is the authoritative final answer.
- `v2_adapter.py` converts provider-exposed reasoning content from `AIMessageChunk.additional_kwargs.reasoning_content` or equivalent reasoning blocks into `thinking_chunk`; `event_converter.py` persists it as `assistant_thinking_delta` with display-safe `live` metadata.
- `v2_adapter.py` treats any non-empty LangGraph namespace (`ns`) as subgraph output for both dict chunks and legacy tuple chunks. Namespace containers may be tuples/lists and their entries may be non-string values. Subgraph `message_chunk` events are intermediate sub-agent output and must not be emitted as main `message_chunk` deltas.
- `TaskRunner.start()` updates `latest_state` only from root graph `values_snapshot` events (`is_subgraph=false`). Subgraph snapshots may still be logged for diagnostics, but they are not a valid source for final answer extraction.
- `runner/core.py` emits a synthetic `final_answer` event AFTER storing the final answer as a `ChatMessage` via `storage.update_task_if_status()`. The event order matters: ChatMessage storage first, then the `final_answer` event, to avoid frontend race conditions.
- The `final_answer` event has `type="final_answer"`, `level="success"`, and `payload={"content": "..."}`.

**Frontend responsibilities**:
- `buildLiveLogItems()` treats `assistant_thinking_delta` and `assistant_answer_delta` as process-log signals only. Collapsed rows show stable labels (`"AI正在思考"`, `"AI正在生成结果"`), while expanded JSON aggregates and shows the complete normalized chunk content for that run segment. Pre-tool reasoning chunks must remain visible inside the thinking row JSON before the subsequent `tool_call` row. Repeated `tool_call` deltas with the same `tool_call_id` and same stage should merge into one visible tool row so partial argument chunks do not create duplicate rows, but `selecting_tool`, `using_tool`, and `tool_result` must remain separate visible rows.
- `buildLiveLogItems()` also hides `final_answer` from the visible progress timeline. The event must still remain in raw JSONL copy and merged row diagnostics, and `use-task-workspace.ts` still relies on the SSE `final_answer` event to trigger `refreshTaskSummary()`.
- `buildConversationStreamItems()` does NOT create streaming AI reply cards from `streamedAnswer` during active runs. The `pushStreamedAnswerItem()` function is kept but not called.
- The AI reply card only appears from the `messages` array after the run completes, when `refreshTaskSummary()` loads the stored `ChatMessage`.
- `use-task-workspace.ts` recognizes `"final_answer"` in the SSE `recognizedTypes` list and triggers `refreshTaskSummary()` when a `final_answer` event arrives.

**Anti-patterns to avoid**:
- NEVER use the last `assistant_answer_delta` chunk as the final answer — the last chunk could be a `state_update`, `tool_result`, or subgraph output.
- NEVER treat `streamedAnswer` (accumulated from deltas) as the authoritative final answer, and do not render it as an assistant message card.
- NEVER let subgraph `message_chunk` or subgraph `values_snapshot` events replace the root graph answer/state. Sub-agent output is process data, not the task's authoritative final response.
- NEVER emit the `final_answer` event before storing the `ChatMessage` — this causes a race where the frontend refreshes before the answer is persisted.
- NEVER display `assistant_thinking_delta` or `assistant_answer_delta` as a standalone AI reply card. They may appear only inside expandable progress-log diagnostics under stable collapsed labels.

## Regression Risks

- Middleware duplication if future developer re-adds default middleware to the stack.
- storage.py breakage if compatibility shims are deleted without rewriting storage.
- Memory privacy regression if Qdrant receives raw uploads, full reports, stream deltas, or tool logs instead of bounded high-level completed-task summaries.
- Memory terminal-state regression if Qdrant or embedding failures during recall/write block the event loop, delay final answer delivery, or convert an otherwise successful run to `failed`.
- Startup reliability regression if Postgres/Qdrant/embedding checks are bypassed while production code assumes those services exist.
- Model format mismatch if frontend sends malformed or non-registry IDs; only `deepseek-v4-flash` and `deepseek-v4-flash-thinking` are valid.
- Model availability regression if `/api/models` stops exposing `available` or task/message endpoints schedule runs for unavailable providers.
- Automatic title regression if first-message runs stop calling the selected model for a compact history title, provider failures block message submission instead of falling back, model output can exceed 10 visible characters, or later auto-title attempts overwrite a user's manual rename.
- Artifact download regression if `ArtifactRecord.url` no longer matches FastAPI routes or run-scoped artifacts fall back to the latest legacy artifact.
- Run artifact visibility regression if `write_run_text()` or `write_run_json()` stops recording non-standard artifact names in `runs.artifact_names`.
- Artifact security regression if external artifact URLs, same-origin non-artifact URLs, or wrong-task artifact URLs receive `X-MyAgent-Token`.
- HTML preview regression if the artifact popup returns to `location.replace(blob:)` or grants iframe `allow-scripts`.
- Upload API regression if duplicate names, limits, unsupported extensions, or invalid JSON again surface as 500 responses.
- Multipart DoS regression if upload size checks move back to storage-only enforcement after `python-multipart` has already parsed the request body.
- Terminal event regression if complete/failed/cancelled runs stop writing run-scoped terminal events, causing frontend run timelines to lose their closing signal.
- SSE resilience regression if frontend reconnect loops become unbounded or backend SSE error payloads are ignored.
- SSE auth bypass if EventSource query param support is removed without alternative auth.
- Timeout breakage if `asyncio.timeout()` is removed without an alternative mechanism to prevent runaway agent runs.
- Concurrency risk if `max_concurrent_subagents` is changed without testing subagent parallel execution limits.
- SSE event loss if `last_event_id` in `streaming.py` is reverted to `""` — the empty string causes `read_events(after_id="")` to return nothing because `after_id is None` is `False` and no event matches `id == ""`. E2E test `test_sse_drains_remaining_events_before_done` guards this.
- Event recovery regression if unknown `after_id` values return `[]`. Cursor misses must replay the full ordered stream so frontend deduplication can recover safely without losing terminal events.
- Stream accumulation regression if `accumulateStreamedAnswer` is reverted to taking only the last delta — this would re-introduce the isolated punctuation card bug.
- **Final answer extraction regression**: If `extract_final_answer()` is removed or modified to not filter out `tool_calls`, the final answer could include tool-calling artifacts (e.g., JSON function calls) instead of clean text.
- **Subgraph stream pollution regression**: If namespace handling stops recognizing tuple/list/non-string `ns` values, subgraph tokens or subgraph state snapshots can again overwrite the root graph final answer.
- **Intermediate/final confusion**: If `pushStreamedAnswerItem()` is re-enabled in `buildConversationStreamItems()`, intermediate tokens will again be displayed as AI reply cards during streaming, breaking the final/intermediate distinction.
- **Race condition regression**: If the `final_answer` event in `runner/core.py` is moved before `storage.update_task_if_status()`, the frontend may refresh before the ChatMessage is persisted, showing stale or missing final answers.
- **Log scroll regression**: `TaskConversation.tsx` keeps each log list pinned to the bottom while the user has not intentionally scrolled upward. If the pinned-state tracking or `conversationStreamItems` dependency is removed, progress log cards will stop following new rows and active-row text changes.
- **Progress row disclosure regression**: If status rows fall back to plain `<article>`, tool rows move timestamps back to the right side, or the trace-level collapse-all control stops tracking `<details open>` rows, progress logs become visually inconsistent and expanded diagnostics become tedious to close. Frontend regression tests should assert shared timestamp-left/disclosure-right CSS for `.liveStatusRow` and `.liveToolCard`, plus collapse-all behavior for expanded progress rows.
- **History menu trigger regression**: If `.historyMenuButton` regains a border, circular radius, or global focus ring, the sidebar again shows a selected-looking circle around the three dots. Unit CSS checks plus `test_history_menu_affordance.spec.mjs` guard the intended no-ring behavior.
- Acceptance drift if future changes rely only on unit/integration results and skip live browser E2E plus screenshot evidence; this repository now treats that as an incomplete delivery for behavior changes.
- DevTools/Playwright boundary drift if future changes treat one-off Chrome DevTools MCP exploration as CI-grade acceptance evidence instead of promoting stable assertions into Playwright specs.
- CI drift if future fixes stop after a local pass while remote GitHub Actions are still pending or red; PR-related work in this repo is incomplete until the remote checks finish successfully.
