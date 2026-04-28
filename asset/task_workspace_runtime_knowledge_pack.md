# Task Workspace Runtime Knowledge Pack

## Background And Scope

This package is the single durable knowledge source for the MyAgent task workspace. It absorbs the previous backend runtime, frontend workspace, and model-provider/security packages.

Use it when changing task APIs, task state transitions, runner behavior, event logs, artifact downloads, uploads, local JSON storage, frontend task creation, file selection, message submission, polling, artifact opening, model routing, environment variables, access tokens, CORS, or test layout.

## Business Rules

- A task is the durable conversation container. `POST /api/tasks` creates only an empty task shell; accepted user messages must go through `POST /api/tasks/{task_id}/messages` and start a run.
- `GET /api/tasks` is the backend source of truth for chat history. It returns only tasks with at least one non-empty user message, sorted by newest activity.
- A completed, failed, cancelled, interrupted, or needs-input task may accept a follow-up message. A running task must reject another message or upload with conflict semantics.
- Follow-up messages append to the same task conversation, but each run resolves its own `mode` and `input_scope` before selecting files. Existing uploads are available task context, not implicit inputs for every later run.
- `POST /api/tasks/{task_id}/messages` accepts optional `mode` values `auto`, `chat`, `search`, `document_analysis`, and `deep_agent`; legacy `bid_analysis` is accepted as a document-analysis alias. It accepts optional `input_scope` values `auto`, `none`, and `task_uploads`; legacy `uploads` is accepted as a task-upload alias.
- In `auto`, weather/search/new casual questions resolve to `search` or `chat` with `input_scope=none`, even when old uploads exist. Clear continuation or document-analysis requests such as "继续根据刚才这些文件分析" resolve to `document_analysis` with `input_scope=task_uploads` when uploads exist.
- Uploads support `.md` and `.json` files through `POST /api/tasks/{task_id}/files`. Backend filename checks and JSON parsing are authoritative; MIME type alone is not trusted.
- Upload validation is atomic. Invalid file type, invalid JSON, duplicate names, file-count limits, file-size limits, request-size limits, or overlong filenames must reject the batch without partial persistence.
- Every new run has a non-empty `run_id`. New user messages, assistant messages, events, run records, and run-scoped artifacts should carry that `run_id`.
- User-visible backend messages, assistant warnings, needs-input text, report copy, and HTTP `detail` strings should be Chinese. Machine contracts stay stable: do not translate `event.type`, `TaskStatus`, `level`, payload keys, artifact names, model IDs, or environment variable names.
- Request validation failures should return a stable Chinese `detail` string instead of raw framework or parser messages.
- Report-like outputs are versioned under `artifacts/runs/{run_id}/`. Top-level artifact paths remain latest/legacy compatibility aliases.
- Run-scoped artifact access is allowlisted by the run's recorded artifact names and must reject traversal or unlisted files.
- DeepAgent integration is an optional backend adapter, not a required runtime dependency. Importing backend code and running tests must work when the third-party `deepagents` package is absent; tests may inject a mock agent factory.
- DeepAgent file access must go through audited workspace tools only. The agent receives callable tools such as `list_dir`, `read_file`, and `write_file`, never raw `Path` objects, workspace roots, or unrestricted filesystem handles. The `create_deep_agent` call must pass an `AuditedDeepAgentBackend` implementing the DeepAgents backend file-operation protocol so the framework's built-in filesystem surface also routes through audited `ls/read/write/edit/glob/grep` behavior, including file-name enumeration.
- DeepAgent runs use `agent_workspace/runs/{run_id}/` as their private workspace. Explicitly selected uploads are copied into read-only `uploads/` snapshots; writable agent files are restricted to `records/` and `outputs/`; promoted user-facing files are copied to run-scoped artifacts.
- File-tool audit events use event type `file_tool_audit` and payload keys including `run_id`, `tool_name`, `op`, `virtual_path`, `resolved_workspace_path`, `bytes`, `sha256`, `source`, `timestamp`, `promoted_artifact_id`, plus compatibility keys `tool`, `operation`, `requested_path`, `relative_path`, `status`, `reason`, and `partial`. Paths exposed through events must be virtual or task/run-relative, never raw local filesystem roots.
- Agent thinking shown in frontend logs uses only event type `reasoning_trace`. It is a safe, user-facing reasoning summary contract, not raw hidden chain-of-thought. Payloads contain `agent_id`, `phase` (`plan`, `observe`, `decide`, `next_step`, `final_summary`, `risk`), `summary`, optional `confidence`, optional safe `evidence_refs`, and optional `source_event_id`.
- `reasoning_trace` summaries may be synthesized only from structured evidence metadata, finding counts, category labels, filenames, virtual paths, and audited file metadata. They must not quote raw provider output, raw prompts, uploaded document bodies, DeepAgent message history, `/conversation_history/` contents, raw tool result content, provider key values, authorization headers, or absolute local paths.
- DeepAgent file-observation reasoning must be emitted only after `file_tool_audit` persistence succeeds, using the audit event id as `source_event_id` when available. The reasoning summary references virtual paths such as `uploads/a.md` or `outputs/summary.md`, not raw workspace paths or file contents.
- The frontend is a chat-first task workspace, not a marketing page. The sidebar history comes from `GET /api/tasks`, not from the current in-memory message list.
- New Chat opens an unpersisted local draft, clears local workspace state, and must not create a backend history item until the first send succeeds and summaries refresh.
- Frontend file selection remains client-side until submit. Submit creates or reuses a task, uploads selected `.md`/`.json` files, posts the message, clears local input, and refreshes task state.
- The native file picker intentionally has no restrictive `accept` filter; the visible upload workflow queues only `.md` and `.json` filenames.
- Execution logs render as run-grouped cards inside the conversation stream. For a run with an assistant reply, activity appears after the user prompt and before the assistant reply.
- Reasoning summaries render inside the same run-grouped progress card as operation logs, with a distinct `思考摘要` label. The frontend does not create a separate reasoning/history card.
- Backend task errors, needs-input notices, missing provider-key warnings, local upload warnings, copy failures, and artifact-open failures should stay in the conversation stream as robot-authored assistant notices, not detached banners.
- Report artifacts render as independent result/download cards and must open/download through token-aware blob fetching. Prefer run-scoped artifact URLs when a `run_id` is available.
- The frontend may map known fixed English backend legacy strings to Chinese through an explicit whitelist. Do not add broad automatic translation for user text, filenames, URLs, uploaded content, or model replies.
- Provider keys such as `DEEPSEEK_API_KEY` and `TAVILY_API_KEY` are backend-only. Browser-visible `NEXT_PUBLIC_*` values must not contain provider keys, customer text, or private credentials.
- Missing `DEEPSEEK_API_KEY` for simple chat is a provider-configuration warning, not a hard frontend error. Document-analysis fallback behavior should remain available.
- `NEXT_PUBLIC_MYAGENT_API_BASE_URL=auto` derives `http://<current page hostname>:8001`. Non-default backend ports require an explicit URL or a resolver/test change.
- Task APIs are local-first. Non-loopback access requires `MYAGENT_ACCESS_TOKEN`; browser calls send `NEXT_PUBLIC_MYAGENT_TOKEN` as `X-MyAgent-Token`.
- Backend CORS uses exact origins from `MYAGENT_CORS_ORIGINS`; scheme, host, and port must match the browser origin.
- The backend is single-process oriented because task runners and JSON task storage are in-process/local. Multi-worker deployment is blocked until ownership and storage are redesigned.
- Test files must be named with a `test_` prefix and live under the module/type directory that owns the behavior.

## Input And Output Examples

Create a visible conversation:

```text
Input: POST /api/tasks without a message, then POST /api/tasks/{task_id}/messages with "你好".
Output: the task stores a user message with run_id, starts a run, and GET /api/tasks includes the conversation title.
```

Upload a mixed source batch:

```text
Input: POST /api/tasks/{task_id}/files with tender.md, alpha.json, and beta.json.
Output: all valid files are stored under uploads/, upload_count includes them, and the next run manifest records source_format for each file.
```

Continue an old conversation:

```text
Input: POST /api/tasks/{task_id}/messages after the previous run is complete.
Output: the same task gains a new run and prior messages remain. Previous uploads are reused only when the resolved input scope is task_uploads.
```

Ask an unrelated follow-up after uploads:

```text
Input: POST /api/tasks/{task_id}/messages with "请告诉今天的天气" after earlier uploads.
Output: the run manifest records intent search or chat, input_scope none, selected_uploads [], and no document-analysis plan/subagent events.
```

Continue document work:

```text
Input: POST /api/tasks/{task_id}/messages with "继续根据刚才这些文件分析".
Output: the run manifest records intent document_analysis, input_scope task_uploads, and selected_uploads matching the task uploads.
```

Open a run report:

```text
Input: frontend opens report.html for run-2.
Output: it fetches /api/tasks/{task_id}/runs/run-2/artifacts/report.html with the configured access-token header before creating a blob URL.
```

Configure LAN access:

```text
Input: frontend is opened at http://<LAN_IP>:3001.
Output: backend MYAGENT_CORS_ORIGINS includes http://<LAN_IP>:3001, backend access token is set, and frontend NEXT_PUBLIC_MYAGENT_TOKEN matches that token.
```

## Boundary Conditions

- `idle`, `needs_input`, `complete`, `failed`, `cancelled`, and `interrupted` are startable states.
- `running` is not startable. Orphaned running tasks are marked interrupted before recovery actions proceed.
- Empty tasks may exist on disk, but they must not appear in `GET /api/tasks` until they have a user message.
- A create-task request containing `message` should return 400 and must not create a task directory.
- Missing required document uploads move the active run and task to `needs_input` with `required_file_type: markdown_or_json`.
- Needs-input payload keys such as `required_file_type`, `minimum_bidder_documents`, and `current_bidder_documents` remain machine-readable and stable.
- Runtime JSON parse failures after a previously valid upload indicate local storage drift or corruption and should fail the run with a filename-specific error.
- JSON upload and runtime parse failures should keep filenames visible but must not expose raw parser text such as Python or Pydantic English messages.
- `TaskStorage.get_task()` may derive `events`, `artifacts`, `upload_count`, and `run_count`, but derived fields are not persisted back as authoritative data.
- Top-level artifact URLs resolve to the latest completed run containing that artifact name, then fall back to legacy top-level files.
- Frontend message submission sends `mode` and `input_scope`; the composer exposes Auto, Do not use files, and Use files choices so file reuse is explicit.
- Frontend run activity grouping suppresses setup-only `task_created` and `file_uploaded` fallback history when real run cards exist, while preserving unmatched warning/error logs.
- Frontend normalizes `reasoning_trace` into `ExecutionLog.reasoning` only when the payload is valid. Malformed reasoning payloads fall back to normal log rendering and must not expose arbitrary payload JSON in DOM or copied logs.
- Frontend run cards show at most three info-level reasoning summaries by default; warning/error logs always remain visible. The expand/collapse control discloses the hidden reasoning count, and copied logs include all reasoning summaries.
- DeepAgent audited file tools normalize absolute paths inside the run workspace to workspace-relative paths. Traversal or outside-workspace paths are denied and audited without writing raw absolute paths into payloads.
- Windows drive-letter and UNC paths supplied to DeepAgent audited tools must be treated as absolute outside-workspace paths and redacted to `<outside-workspace>/<basename>` in audit payloads.
- DeepAgent audited writes are atomic: content is written to a temporary sibling file and published with replace only after completion. Cancellation during a write removes the temporary file, keeps the target unpublished, and records `status: cancelled` with `partial: true` only when bytes were written before cancellation.
- DeepAgent audited writes outside `records/` and `outputs/` are denied. Writes must not mutate upload snapshots or original task uploads.
- DeepAgents internal virtual paths `/large_tool_results/` and `/conversation_history/` are mapped into audited `records/deepagents/` storage, while the backend returns the original virtual paths to DeepAgents.
- Cancellation before or during DeepAgent file operations must raise through the existing cancellation controller and emit an audit record with `status: cancelled`.
- Upload request limits and JSON body limits are enforced before task mutation. Uploaded `.json` files use upload file/request limits, not the API JSON body limit.
- Invalid uploaded JSON rejects the upload request with no partial batch persistence.
- Task APIs are loopback-only when no access token is configured. Non-loopback task access without a configured token returns `403`; missing or wrong token returns `401` when a token is configured.
- CORS entries are origins, not URLs with paths. Use exact origins such as `http://<LAN_IP>:3001`.
- Frontend polling runs only while `isTaskActive(status)` is true, and incremental event refresh appends only unseen log IDs.
- Long messages, log details, filenames, model labels, file cards, and composer controls must wrap or ellipsize without overlapping at mobile widths.
- Run only one Next.js dev server against a single `frontend/.next` directory at a time.

## Known Pitfalls

- Do not reintroduce a create-task path that persists user messages outside `TaskRunner.start()`.
- Do not list blank draft tasks in history summaries.
- Do not overwrite old run artifacts when adding follow-up support.
- Do not create path-taking artifact APIs for run outputs; use `{run_id}` plus a normalized artifact name.
- Do not drop token checks from list, detail, event, upload, message, cancel, or artifact routes.
- Do not assume all old task states already contain `runs`; legacy synthesis must stay readable.
- Do not accept JSON uploads by MIME type alone or add a separate JSON upload endpoint unless JSON becomes a distinct workflow.
- Do not translate stored machine fields to satisfy UI copy requirements.
- Do not rebuild sidebar history from local messages; that loses persisted conversations on refresh and backend restart.
- Do not render backend task errors, needs-input notices, or frontend workspace warnings as full-width detached banners.
- Do not flatten multi-run logs and reports into one undifferentiated report area.
- Do not place report artifact actions only inside a log card footer.
- Do not let the sticky composer obscure the newest assistant output after logs or artifacts are inserted.
- Do not pass `AuditedWorkspaceTools` instances, task directories, or absolute paths directly into DeepAgent code; pass only the callables returned by the adapter.
- Do not add `deepagents` as a hard dependency unless the test strategy and fallback behavior are updated in the same change.
- Do not implement `reasoning_trace` aliases such as `agent_thinking` or `reasoning_step`, and do not reuse `model_result` as the frontend thinking-summary contract.
- Do not display raw hidden chain-of-thought or provider/model raw reasoning output. Product copy may say `思考摘要`, but the stored/displayed content must remain a safe summary.
- Do not expose provider credentials through `NEXT_PUBLIC_*` values.
- Do not document fixed private LAN IPs, customer documents, local absolute private paths, secrets, tokens, deleted filenames, temporary script paths, or dated patch timelines in knowledge packs.

## Related Code Paths

- `backend/app/main.py`
- `backend/app/runner.py`
- `backend/app/intent.py`
- `backend/app/deep_agent_runtime.py`
- `backend/app/orchestrator.py`
- `backend/app/storage.py`
- `backend/app/analysis.py`
- `backend/app/model_provider.py`
- `backend/app/settings.py`
- `backend/app/schemas.py`
- `backend/app/tools.py`
- `backend/storage/tasks/`
- `frontend/app/page.tsx`
- `frontend/app/file-upload.ts`
- `frontend/app/model-ui.ts`
- `frontend/app/task-state.ts`
- `frontend/app/workspace-view.ts`
- `frontend/app/globals.css`
- `frontend/app/layout.tsx`
- `frontend/next.config.mjs`
- `backend/.env.example`
- `frontend/.env.example`

## Related Test Paths

- `backend/tests/workflow/test_workflow.py`
- `backend/tests/runtime/test_intent_router.py`
- `backend/tests/runtime/test_deep_agent_runtime.py`
- `backend/tests/runtime/test_reasoning_trace.py`
- `frontend/tests/state/test_task_state.test.ts`
- `frontend/tests/workspace/test_workspace_view.test.ts`
- `frontend/tests/upload/test_file_upload.test.ts`
- `frontend/tests/model/test_model_ui.test.ts`

## Verification Commands

```bash
cd backend && uv run pytest tests/runtime/test_deep_agent_runtime.py
cd backend && uv run pytest tests/runtime/test_reasoning_trace.py
cd backend && uv run pytest
cd backend && uv run ruff check .
cd backend && uv run mypy app tests
cd frontend && npm run typecheck
cd frontend && npm test
cd frontend && npm run lint
cd frontend && npm run build
git diff --check
```

For documentation-only edits, `git diff --check` is the minimum check. For test-layout changes, run the affected backend and frontend test commands.

## Regression Risks

- Follow-up messages accidentally starting a separate task instead of a new run in the existing task.
- A later run replacing an earlier run's report, evidence, summary, or artifact metadata.
- Restart recovery losing run metadata, artifact URLs, or message `run_id` values.
- Artifact traversal through encoded separators or unlisted names.
- History ordering drifting from newest activity.
- New backend event sources emitting English user-visible text that bypasses the frontend legacy whitelist.
- Reasoning summaries accidentally leaking uploaded document bodies, raw prompts, raw provider output, DeepAgent internal history, provider key values, authorization headers, or absolute local paths.
- Frontend reasoning rendering expanding malformed payload JSON or hiding warning/error logs when collapsed.
- Breaking create-task, upload, and message-send order so analysis runs without selected files.
- Dropping access-token headers when opening or downloading artifacts.
- Regressing upload support back to Markdown-only behavior.
- Moving tests without updating runner globs, imports, AGENTS.md, README.md, and this package index.
