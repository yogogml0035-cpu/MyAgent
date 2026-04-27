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
- Compact task metadata may stay visible once a task exists, but the empty state should prioritize the centered chat entry surface.
- User, assistant, and system messages render in the conversation stream; user messages align to the right with the primary accent treatment.
- Execution logs render as a progress-log card inside the conversation stream so users can read task output in chronological context.
- Markdown uploads use a hidden browser file input controlled by visible upload, replace, and remove controls.
- File selection remains client-side until task submission; submitting creates a task if one does not already exist, uploads files, then posts the message payload.
- The stop control is shown as the primary action while a task is running; otherwise the primary action submits the current message and selected files.
- Report-like artifacts stay available from the task stream and must open through token-aware blob fetching.
- Provider secrets must remain backend-only; this frontend may only send safe model IDs and the optional browser-visible task access token.

## Input And Output Examples

User starts a task with a Markdown file:

```text
Input: select one or more .md files, choose a model, enter a task prompt, press Send.
Output: the Kimi-style composer creates or reuses a task, uploads files, sends the prompt, clears the local input, and refreshes task state.
```

User starts a fresh draft:

```text
Input: press the left-rail new chat control.
Output: frontend clears the current local task state, selected files, input, logs, artifacts, and errors so the next send starts a new task.
```

Task emits execution events:

```text
Input: backend returns logs or incremental events for the current task.
Output: the progress-log card shows event time, level, title, optional detail, and a compact collection status.
```

Report artifact is available:

```text
Input: backend task state includes a report or .html artifact.
Output: an open button fetches the artifact with the configured access-token header and opens a blob URL in a new tab.
```

## Boundary Conditions

- Only `.md` files or `text/markdown` files should be accepted by the visible upload workflow.
- Clearing selected files must also reset the hidden file input so the same file can be selected again.
- Starting a new chat resets only frontend state; it does not delete already-created backend tasks.
- Polling only runs while `isTaskActive(status)` is true.
- Incremental event refresh must append only unseen log IDs.
- If the backend requires additional input, the warning banner should remain visible near the conversation stream.
- The UI must remain usable at mobile widths; message bubbles, file cards, log rows, and composer controls must wrap without overlapping.
- Browser-visible `NEXT_PUBLIC_*` values must not contain provider keys or private document content.

## Known Pitfalls

- Do not split logs into a detached side panel unless the user intentionally changes the workspace model; the durable UI contract is chat-first.
- Do not reintroduce Kimi's extra left-sidebar feature links or lower prompt example cards when maintaining this baseline.
- Do not fake backend progress totals as authoritative task state. The current progress summary is visual log collection context, while the real execution state still comes from task status and events.
- Do not store uploaded customer documents, generated sensitive reports, access tokens, or private local paths in fixtures or knowledge packs.
- Avoid native file-input-only affordances; the visible upload controls are part of the expected user path.
- Keep artifact opening token-aware, otherwise protected local deployments will fail to open reports.

## Related Code Paths

- `frontend/app/page.tsx`
- `frontend/app/globals.css`
- `frontend/app/layout.tsx`
- `frontend/app/task-state.ts`
- `frontend/app/workspace-view.ts`
- `backend/app/main.py`

## Related Test Paths

- `frontend/tests/task-state.test.ts`
- `frontend/tests/workspace-view.test.ts`
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
