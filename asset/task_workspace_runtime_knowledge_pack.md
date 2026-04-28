# Task Workspace Runtime Knowledge Pack

## Background And Scope

This package is the single durable knowledge source for the MyAgent task workspace. It absorbs the previous backend runtime, frontend workspace, and model-provider/security packages.

Use it when changing task APIs, task state transitions, runner behavior, event logs, artifact downloads, uploads, local JSON storage, frontend task creation, file selection, message submission, polling, artifact opening, model routing, environment variables, access tokens, CORS, or test layout.

## Business Rules

- A task is the durable conversation container. `POST /api/tasks` creates only an empty task shell; accepted user messages must go through `POST /api/tasks/{task_id}/messages` and start a run.
- `GET /api/tasks` is the backend source of truth for chat history. It returns only tasks with at least one non-empty user message, sorted by newest activity.
- A completed, failed, cancelled, interrupted, or needs-input task may accept a follow-up message. A running task must reject another message or upload with conflict semantics.
- Follow-up messages append to the same task conversation and reuse persisted uploads unless the user uploads more files before a new run starts.
- Uploads support `.md` and `.json` files through `POST /api/tasks/{task_id}/files`. Backend filename checks and JSON parsing are authoritative; MIME type alone is not trusted.
- Upload validation is atomic. Invalid file type, invalid JSON, duplicate names, file-count limits, file-size limits, request-size limits, or overlong filenames must reject the batch without partial persistence.
- Every new run has a non-empty `run_id`. New user messages, assistant messages, events, run records, and run-scoped artifacts should carry that `run_id`.
- User-visible backend messages, assistant warnings, needs-input text, report copy, and HTTP `detail` strings should be Chinese. Machine contracts stay stable: do not translate `event.type`, `TaskStatus`, `level`, payload keys, artifact names, model IDs, or environment variable names.
- Request validation failures should return a stable Chinese `detail` string instead of raw framework or parser messages.
- Report-like outputs are versioned under `artifacts/runs/{run_id}/`. Top-level artifact paths remain latest/legacy compatibility aliases.
- Run-scoped artifact access is allowlisted by the run's recorded artifact names and must reject traversal or unlisted files.
- The frontend is a chat-first task workspace, not a marketing page. The sidebar history comes from `GET /api/tasks`, not from the current in-memory message list.
- New Chat opens an unpersisted local draft, clears local workspace state, and must not create a backend history item until the first send succeeds and summaries refresh.
- Frontend file selection remains client-side until submit. Submit creates or reuses a task, uploads selected `.md`/`.json` files, posts the message, clears local input, and refreshes task state.
- The native file picker intentionally has no restrictive `accept` filter; the visible upload workflow queues only `.md` and `.json` filenames.
- Execution logs render as run-grouped cards inside the conversation stream. For a run with an assistant reply, activity appears after the user prompt and before the assistant reply.
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
Output: the same task gains a new run, prior messages remain, and previous uploads remain available.
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
- Do not expose provider credentials through `NEXT_PUBLIC_*` values.
- Do not document fixed private LAN IPs, customer documents, local absolute private paths, secrets, tokens, deleted filenames, temporary script paths, or dated patch timelines in knowledge packs.

## Related Code Paths

- `backend/app/main.py`
- `backend/app/runner.py`
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
- `frontend/tests/state/test_task_state.test.ts`
- `frontend/tests/workspace/test_workspace_view.test.ts`
- `frontend/tests/upload/test_file_upload.test.ts`
- `frontend/tests/model/test_model_ui.test.ts`

## Verification Commands

```bash
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
- Breaking create-task, upload, and message-send order so analysis runs without selected files.
- Dropping access-token headers when opening or downloading artifacts.
- Regressing upload support back to Markdown-only behavior.
- Moving tests without updating runner globs, imports, AGENTS.md, README.md, and this package index.
