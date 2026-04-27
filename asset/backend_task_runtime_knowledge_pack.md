# Backend Task Runtime Knowledge Pack

## Background And Scope

This package covers backend task storage and runtime behavior. A task is the durable conversation container; each accepted user message starts a run inside that task. It applies when changing task APIs, task state transitions, runner behavior, event logs, artifact downloads, cancellation/interruption, or local JSON storage.

## Business Rules

- `GET /api/tasks` is the backend source of truth for chat history. It returns only tasks with at least one non-empty user message, sorted by newest activity.
- A new blank frontend draft may create no visible history row. The history row appears only after a user message is accepted and persisted.
- `POST /api/tasks` must create only an empty task shell. Initial user messages are rejected there and must be sent through `POST /api/tasks/{task_id}/messages` so every accepted message starts a run.
- A completed, failed, cancelled, interrupted, or needs-input task may accept a follow-up message. A running task must reject another message with conflict semantics.
- Follow-up messages append to the same task conversation and reuse the task's persisted uploads.
- Every new run has a non-empty `run_id`. New user messages, assistant messages, and run events should carry that `run_id`.
- Legacy tasks without run records are synthesized as a single `legacy` run on read so old conversations remain visible.
- Report-like outputs are versioned under `artifacts/runs/{run_id}/`. Top-level artifact paths remain latest/legacy compatibility aliases.
- Run-scoped artifact access is allowlisted by the run's recorded artifact names and must reject traversal or unlisted files.
- Task APIs remain protected by the existing local-first/token boundary.

## Input And Output Examples

Create a visible conversation:

```text
Input: POST /api/tasks without a message, then POST /api/tasks/{task_id}/messages with "你好".
Output: task state contains a user message with run_id; GET /api/tasks includes a title derived from the first five visible characters.
```

Continue an old conversation:

```text
Input: POST /api/tasks/{task_id}/messages after the task is complete.
Output: the same task gains a second run, prior messages remain, and uploaded Markdown files are reused.
```

Open a run report:

```text
Input: GET /api/tasks/{task_id}/runs/{run_id}/artifacts/report.html.
Output: the report for that exact run is returned only if report.html is recorded in the run artifact allowlist.
```

## Boundary Conditions

- `idle`, `needs_input`, `complete`, `failed`, `cancelled`, and `interrupted` are startable states.
- `running` is not startable. Orphaned running tasks are marked interrupted before recovery actions proceed.
- Empty tasks are still stored on disk when created, but they must not appear in `GET /api/tasks` until they have a user message.
- A create-task request containing `message` should return 400 and must not create a task directory.
- Missing required Markdown uploads move the active run and task to `needs_input`.
- `TaskStorage.get_task()` should populate derived `events`, `artifacts`, `upload_count`, and `run_count` without persisting those derived fields back as authoritative data.
- Top-level artifact URLs resolve to the latest completed run containing that artifact name, then fall back to legacy top-level files.

## Known Pitfalls

- Do not overwrite old run artifacts when adding follow-up support.
- Do not reintroduce a create-task path that persists user messages outside `TaskRunner.start()`.
- Do not list blank draft tasks in history summaries.
- Do not create path-taking artifact APIs for run outputs; use `{run_id}` plus a normalized artifact name.
- Do not drop access-token checks from list, detail, event, upload, message, cancel, or artifact routes.
- Do not assume all old task states already contain `runs`; keep legacy synthesis readable.
- Do not put uploaded customer documents, generated sensitive reports, tokens, or private local paths into tests or knowledge packs.

## Related Code Paths

- `backend/app/schemas.py`
- `backend/app/storage.py`
- `backend/app/runner.py`
- `backend/app/analysis.py`
- `backend/app/main.py`
- `backend/storage/tasks/`

## Related Test Paths

- `backend/tests/test_workflow.py`

## Verification Commands

```bash
cd backend && uv run pytest
cd backend && uv run ruff check .
cd backend && uv run mypy app tests
git diff --check
```

## Regression Risks

- Follow-up messages accidentally starting a separate task instead of a new run in the existing task.
- A second run replacing the first run's report, evidence, or summary artifacts.
- Restart recovery losing run metadata, artifact URLs, or message `run_id` values.
- Artifact traversal through encoded separators or unlisted names.
- History ordering drifting from newest activity, making recent conversations hard to find.
