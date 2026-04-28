# Frontend Task Workspace Knowledge Pack

## Background And Scope

This package covers the Next.js task workspace UI, including the chat-first task surface, Markdown upload controls, model selection, message submission, event polling, execution-log rendering, report artifact opening, and visual layout boundaries.

It applies when editing:

- `frontend/app/page.tsx`
- `frontend/app/globals.css`
- `frontend/app/layout.tsx`
- `frontend/app/task-state.ts`
- `frontend/app/workspace-view.ts`
- `frontend/tests/`

## Business Rules

- The primary screen is a single chat workspace, not a marketing page.
- The default empty workspace follows a Kimi-style chat entry layout: a neutral history rail, large centered project wordmark, and a rounded prompt composer.
- The left rail should contain only the new-chat affordance and chat-history records; avoid adding feature navigation, examples, account links, or other non-history sections unless the user changes this product boundary.
- Chat history is backend-backed. Load task summaries from `GET /api/tasks`; do not derive sidebar history from the current in-memory message list.
- History rows show only the backend summary title and active state. Do not reintroduce subtitle, status, idle, timestamp, task id, or other secondary text in the row.
- New Chat opens an unpersisted local draft, clears the current workspace state, and leaves the backend-backed history list intact. It must not create a history item until the first send succeeds and summaries refresh.
- The top-right workspace metadata chips are intentionally absent; status belongs in run/log context, not in a floating metadata bar.
- User, assistant, and system messages render in the conversation stream; user messages align to the right with the primary accent treatment.
- Chat bubbles share one balanced sizing system: short user messages should keep a readable minimum width, timestamps stay inside the bubble without forcing tall narrow pills, and assistant/system bubbles mirror the same spacing, typography, and corner logic on the left.
- Execution logs and report artifacts render as run-grouped progress cards inside the conversation stream, ordered by run chronology while preserving one continuous message stream.
- Execution-log cards, state banners, file cards, model picker controls, and the composer should use the same neutral workbench visual language: compact density, 8px card radii, soft sage-gray borders, restrained shadows, and no detached decorative panels.
- Markdown uploads use a hidden browser file input controlled by visible upload, replace, and remove controls.
- The native file picker intentionally leaves its `accept` filter unset so users can see all downloaded files in the OS dialog; frontend selection logic still queues only Markdown uploads.
- File selection remains client-side until task submission; submitting creates a task if one does not already exist, uploads files, then posts the message payload.
- Model selection uses a custom compact picker rather than the browser-native select control. The trigger shows the selected label, the menu shows concise descriptions and a selected checkmark, and the frontend still sends only the selected model ID.
- The composer does not show a separate Agent mode toggle. The `deepseek-reasoner` model ID is displayed as `Deepseek` in the frontend picker and remains the default frontend and backend model path unless the model picker returns another supported model ID.
- The stop control is shown as the primary action while a task is running; otherwise the primary action submits the current message and selected files.
- Enter submits the composer; Shift+Enter inserts a newline; IME composition Enter must not submit.
- Report-like artifacts stay available from the task stream and must open through token-aware blob fetching. Prefer run-scoped artifact URLs when a `run_id` is available.
- Provider secrets must remain backend-only; this frontend may only send safe model IDs and the optional browser-visible task access token.
- The frontend API base URL may be explicit, but the local default is `auto`: derive `http://<current page hostname>:8001` so localhost and LAN-IP page URLs call matching backend hosts.
- Local development should keep the Next.js dev indicator hidden so it does not overlap the production-like chat surface.

## Input And Output Examples

User starts a task with a Markdown file:

```text
Input: select one or more .md files, choose a model, enter a task prompt, press Send.
Output: the Kimi-style composer creates or reuses a task, uploads files, sends the prompt, clears the local input, and refreshes task state.
```

User sees non-Markdown files in the picker:

```text
Input: open the upload picker in a Downloads folder that contains .json, .txt, and .md files.
Output: the OS dialog shows all files, while the composer queues only `.md` filenames and reports ignored non-Markdown files.
```

User starts a fresh draft:

```text
Input: press the left-rail new chat control.
Output: frontend clears the current local task state, selected files, input, logs, artifacts, and errors so the next send starts a new task, while existing backend history rows remain visible.
```

Task emits execution events:

```text
Input: backend returns `runs`, run-tagged logs, and report artifacts for the current task.
Output: the workspace keeps all chat messages in chronological order, then renders run-grouped progress cards with event time, level, title, optional detail, and run-specific report buttons.
```

Report artifact is available:

```text
Input: backend task state includes a run-scoped `report.html` artifact.
Output: an open button fetches `/api/tasks/{task_id}/runs/{run_id}/artifacts/{artifact_name}` with the configured access-token header and opens a blob URL in a new tab.
```

User changes models:

```text
Input: open the model picker and choose an option.
Output: the model picker closes and stores the selected model ID for subsequent task creation and message submission.
```

## Boundary Conditions

- The OS file picker should display all file types; do not set a restrictive file-input `accept` value for this workflow.
- Only filenames ending in `.md` should be queued and submitted by the visible upload workflow, matching backend validation.
- Clearing selected files must also reset the hidden file input so the same file can be selected again.
- Starting a new chat resets only frontend state; it does not delete already-created backend tasks.
- Backend summaries remain the source of truth for sidebar history after browser refresh, backend restart, and successful message sends.
- Polling only runs while `isTaskActive(status)` is true.
- Incremental event refresh must append only unseen log IDs.
- Network fetch failures should show an actionable Chinese backend-down message naming the configured backend URL. Backend `401` response details must remain visible for access-token mismatch diagnosis.
- `NEXT_PUBLIC_MYAGENT_API_BASE_URL=auto` assumes backend port `8001`; if the backend port changes, use an explicit URL or update the resolver and tests together.
- If the backend requires additional input, the warning banner should remain visible near the conversation stream.
- The UI must remain usable at mobile widths; message bubbles, file cards, log rows, and composer controls must wrap without overlapping.
- Long message text, long log titles, log details, selected filenames, and model labels must wrap or ellipsize inside their containers without changing the conversation layout width.
- The model picker menu opens below the centered empty-state composer and above the sticky composer during active conversations so it stays inside the viewport.
- Run only one Next.js dev server against `frontend/.next` at a time. Parallel `next dev` processes in the same frontend directory can corrupt generated runtime/chunk output and surface missing module errors.
- Browser-visible `NEXT_PUBLIC_*` values must not contain provider keys or private document content.

## Known Pitfalls

- Do not split logs into a detached side panel unless the user intentionally changes the workspace model; the durable UI contract is chat-first.
- Do not let short right-aligned user messages collapse into narrow vertical bubbles; keep the minimum bubble width and internal timestamp spacing symmetric with assistant messages.
- Do not reintroduce Kimi's extra left-sidebar feature links or lower prompt example cards when maintaining this baseline.
- Do not rebuild sidebar history from local messages; that loses persisted conversations on refresh and backend restart.
- Do not add a draft row to backend history before the first successful send.
- Do not flatten multi-run logs and reports into one undifferentiated report area; users need to reopen prior run outputs.
- Do not fake backend progress totals as authoritative task state. The current progress summary is visual log collection context, while the real execution state still comes from task status and events.
- Do not store uploaded customer documents, generated sensitive reports, access tokens, or private local paths in fixtures or knowledge packs.
- Avoid native file-input-only affordances; the visible upload controls are part of the expected user path.
- Do not reintroduce `.md`-only native picker filtering; users need to see adjacent downloaded files even though the frontend queues only `.md` filenames.
- Avoid reintroducing a native `<select>` for model selection unless there is a deliberate accessibility redesign; the current UI contract expects the polished compact picker.
- Do not reintroduce a local-only Agent toggle; model choice should remain the visible routing control.
- Keep artifact opening token-aware, otherwise protected local deployments will fail to open reports.
- Keep run-scoped artifact URL construction token-aware and path-free; do not fall back to local artifact paths when the backend supplies `run_id`.
- Do not hard-code a single LAN IP into frontend code for local development; IP addresses change, and the page hostname should be the source of truth when `auto` is configured.

## Related Code Paths

- `frontend/app/page.tsx`
- `frontend/app/globals.css`
- `frontend/app/layout.tsx`
- `frontend/app/file-upload.ts`
- `frontend/app/model-ui.ts`
- `frontend/app/task-state.ts`
- `frontend/app/workspace-view.ts`
- `frontend/next.config.mjs`
- `backend/app/main.py`

## Related Test Paths

- `frontend/tests/task-state.test.ts`
- `frontend/tests/workspace-view.test.ts`
- `frontend/tests/file-upload.test.ts`
- `frontend/tests/model-ui.test.ts`
- `backend/tests/test_workflow.py`

## Verification Commands

```bash
cd frontend && npm run typecheck
cd frontend && npm test
cd frontend && npm run lint
cd frontend && npm run build
git diff --check
```

## Regression Risks

- Breaking the create-task, upload, message-send order and causing messages to run without uploaded documents.
- Reintroducing a detached execution-log layout that hides task progress from the conversation flow.
- Making the hidden file input unreachable for keyboard or screen-reader users.
- Letting long filenames, long log details, or narrow mobile viewports overflow their containers.
- Dropping access-token headers when opening artifacts.
- Letting non-history sidebar links or example cards drift back into the Kimi-style entry screen.
- Regressing the model picker to a native control or letting its popover overlap the send button, composer text, or viewport edge.
- Adding local-only routing controls that do not map to a tested backend API field.
