# External Integrations

**Analysis Date:** 2026-05-19

## APIs & External Services

**MyAgent Backend REST API:**
- Purpose: Model availability, task CRUD, history, file upload, message send, cancellation, event polling, and artifact blob fetching.
- SDK/Client: Browser `fetch` wrappers in `frontend/lib/task-api.ts`.
- Auth: `X-MyAgent-Token` header from `NEXT_PUBLIC_MYAGENT_TOKEN` or legacy `NEXT_PUBLIC_AGENT_CHAT_TOKEN`.
- Base URL: `TASK_API_BASE_URL` derived by `resolveApiBaseUrl()` in `frontend/app/task-state.ts`.
- Wire format: Backend `snake_case`; frontend normalizes to `camelCase` in `frontend/app/task-state.ts`.

**MyAgent Backend SSE Stream:**
- Purpose: Live task progress, tool calls/results, answer deltas, memory/context events, and terminal events.
- SDK/Client: Browser `EventSource` created by `createTaskEventSource()` in `frontend/lib/task-api.ts`.
- Auth: SSE query parameter `token` because EventSource cannot send custom headers.
- Recovery: `useTaskWorkspace()` retries with exponential backoff, refreshes summaries, and falls back to event polling through `fetchTaskEvents()`.

**Artifact Blob Fetching:**
- Purpose: Open or download run-scoped and latest artifacts.
- SDK/Client: Browser `fetch`, object URLs, `window.open()`, and sandboxed iframe wrapper in `frontend/hooks/use-task-workspace.ts`.
- Security boundary: `buildArtifactRequest()` only trusts artifact URLs on the configured backend origin and current task artifact routes.

## Data Storage

**Browser State:**
- React state in `useTaskWorkspace()` stores current task ID, status, messages, logs, artifacts, runs, history, model selection, selected files, and notices.
- No browser database, localStorage, IndexedDB, or cookie persistence is detected.

**Backend Storage:**
- The frontend treats backend API responses as authoritative.
- Task history is reloaded through `fetchTaskSummaries()` and task details through `fetchTask()`.

**File Storage:**
- Selected files are kept as browser `File` objects until `uploadTaskFiles()` posts them as multipart form data.
- Playwright run-specific evidence is stored locally under ignored `frontend/e2e-playwright/e2e-YYYYMMDDHHMMSS/`.

## Authentication & Identity

**Auth Provider:**
- No frontend login, session, OAuth, or cookie flow is implemented.
- A browser-visible access token may be sent to backend REST and SSE.

**Token Handling:**
- Header token for `fetch` requests is centralized in `requestTaskJson()` and `fetchArtifactBlob()`.
- SSE token is added as a query string in `createTaskEventSource()`.
- Never put provider keys, database URLs, customer data, or private examples in `NEXT_PUBLIC_*`.

## Monitoring & Observability

**Error Tracking:**
- No Sentry, OpenTelemetry, analytics, or external browser telemetry package is detected in `frontend/package.json`.

**User-Visible Diagnostics:**
- Backend events are normalized as `ExecutionLog` objects in `frontend/app/task-state.ts`.
- Logs are grouped and rendered as progress rows in `frontend/app/workspace-view.ts` and `frontend/components/chat/TaskConversation.tsx`.
- Raw event JSONL can be copied via `buildLogClipboardText()`.

**Browser Evidence:**
- Playwright specs capture screenshots and downloaded artifacts into ignored evidence folders.
- `frontend/e2e-playwright/README.md` documents evidence directory conventions and env vars.

## CI/CD & Deployment

**Hosting:**
- Local Next.js server on port 3001 by default.
- No Vercel, Netlify, Docker, or cloud hosting config is present under `frontend/`.

**CI Pipeline:**
- Root frontend CI runs `npm ci`, typecheck, Node tests, lint with zero warnings, and Next build.
- Playwright specs exist but are not described as default CI gates in this subproject's package scripts, except `e2e:runtime-contracts` is available manually.

## Environment Configuration

**Development:**
- `NEXT_PUBLIC_MYAGENT_API_BASE_URL=auto` lets the frontend call backend port 8001 on the current hostname.
- `NEXT_PUBLIC_MYAGENT_TOKEN` must match backend `MYAGENT_ACCESS_TOKEN` when backend token auth is enabled.
- Dev server polling is configured by `WATCHPACK_POLLING`, `CHOKIDAR_USEPOLLING`, and `NEXT_WATCH_POLL_INTERVAL_MS`.

**E2E:**
- `MYAGENT_E2E_BASE_URL` points to frontend.
- `MYAGENT_E2E_API_URL` points to backend.
- `MYAGENT_E2E_EVIDENCE_DIR` is required by screenshot-producing specs.
- Some specs require Postgres container/user/db env vars or task-root env vars, documented in `frontend/e2e-playwright/README.md`.

## Webhooks & Callbacks

**Incoming:**
- No frontend API routes or webhook endpoints are present.

**Outgoing:**
- REST calls to backend from `frontend/lib/task-api.ts`.
- SSE connection to backend from `createTaskEventSource()`.
- Artifact blob fetches to backend artifact routes.

---

*Integration audit: 2026-05-19*
*Update when browser/backend contract, auth, E2E, or external telemetry changes*
