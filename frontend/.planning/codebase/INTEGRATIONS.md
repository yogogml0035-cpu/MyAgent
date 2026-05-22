# External Integrations

**Analysis Date:** 2026-05-22

## APIs & External Services

**MyAgent Backend HTTP API:**
- MyAgent backend - The frontend uses the backend as its only runtime service integration.
  - SDK/Client: Browser `fetch` wrapped by `frontend/lib/task-api.ts`.
  - Base URL: `TASK_API_BASE_URL` in `frontend/lib/task-api.ts`, derived by `resolveApiBaseUrl` in `frontend/app/task-state.ts`.
  - Auth: optional `NEXT_PUBLIC_MYAGENT_TOKEN` or legacy `NEXT_PUBLIC_AGENT_CHAT_TOKEN`; sent as `X-MyAgent-Token` by `frontend/lib/task-api.ts`.
  - Endpoints:
    - `GET /api/models` - Fetch browser-safe model options in `frontend/lib/task-api.ts`.
    - `GET /api/skills` - Fetch project skill options in `frontend/lib/task-api.ts`.
    - `GET /api/tasks` - Fetch conversation/task summaries in `frontend/lib/task-api.ts`.
    - `POST /api/tasks` - Create a task with a selected model in `frontend/lib/task-api.ts`.
    - `GET /api/tasks/{task_id}` - Fetch task state, messages, events/logs, runs, uploads, and artifacts in `frontend/lib/task-api.ts`.
    - `PATCH /api/tasks/{task_id}` - Rename a conversation in `frontend/lib/task-api.ts`.
    - `DELETE /api/tasks/{task_id}` - Delete a conversation in `frontend/lib/task-api.ts`.
    - `GET /api/tasks/{task_id}/events?after_id=...` - Recover incremental event logs in `frontend/lib/task-api.ts`.
    - `POST /api/tasks/{task_id}/files` - Upload selected files as multipart form data in `frontend/lib/task-api.ts`.
    - `POST /api/tasks/{task_id}/messages` - Send user messages, selected model ID, mode, and selected skill names in `frontend/lib/task-api.ts`.
    - `POST /api/tasks/{task_id}/cancel` - Stop a running task in `frontend/lib/task-api.ts`.
    - `GET /api/tasks/{task_id}/artifacts/{artifact_name}` - Download task artifacts via `buildArtifactRequest` in `frontend/app/task-state.ts`.
    - `GET /api/tasks/{task_id}/runs/{run_id}/artifacts/{artifact_name}` - Download run-scoped artifacts via `buildArtifactRequest` in `frontend/app/task-state.ts`.

**MyAgent Backend SSE Stream:**
- Task event stream - The frontend follows running tasks through server-sent events.
  - SDK/Client: Browser `EventSource` created by `createTaskEventSource` in `frontend/lib/task-api.ts`.
  - Endpoint: `GET /api/tasks/{task_id}/stream`.
  - Auth: optional browser token is appended as a `token` query parameter by `frontend/lib/task-api.ts`.
  - Consumer: `frontend/hooks/use-task-workspace.ts` merges stream events into execution logs, refreshes task summaries, and retries with exponential backoff.
  - Fallback: `frontend/hooks/use-task-workspace.ts` calls `fetchTaskEvents` and `fetchTask` when SSE fails or sends terminal/state events.

**Model and Skill Catalogs:**
- Backend model registry - `frontend/hooks/use-task-workspace.ts` calls `fetchModelOptions` from `frontend/lib/task-api.ts`, filters UI selection to `deepseek-v4-flash` and `deepseek-v4-flash-thinking`, and displays availability through `frontend/app/model-ui.ts`.
  - SDK/Client: Browser `fetch` through `frontend/lib/task-api.ts`.
  - Auth: optional `X-MyAgent-Token`.
- Backend skill registry - `frontend/hooks/use-task-workspace.ts` calls `fetchSkillOptions`, normalizes only `name` and `description` in `frontend/app/skill-selection.ts`, and sends selected skill names through `postTaskMessage`.
  - SDK/Client: Browser `fetch` through `frontend/lib/task-api.ts`.
  - Auth: optional `X-MyAgent-Token`.

**External Provider Services:**
- Direct browser-to-provider integrations are not detected in `frontend/`.
- AI model providers, search tools, Postgres, Qdrant, and provider keys are backend responsibilities. `frontend/README.md` states provider secrets stay in backend `.env`; the browser sends only backend-registered model IDs.
- `frontend/app/workspace-view.ts` and `frontend/app/task-state.ts` display bounded backend event metadata for search, memory, orchestration, reasoning, and tool activity; they do not call those providers directly.

## Data Storage

**Databases:**
- No database client is used by the frontend runtime.
  - Connection: Not applicable in `frontend/`.
  - Client: Not detected in `frontend/package.json` or `frontend/package-lock.json`.
- Backend task state is read through MyAgent HTTP/SSE APIs in `frontend/lib/task-api.ts`.
- Playwright E2E specs such as `frontend/e2e-playwright/test_runtime_contracts.spec.mjs` and `frontend/e2e-playwright/test_session_context_memory.spec.mjs` use backend/API/Postgres test setup env vars to seed or verify backend state; this is acceptance-test infrastructure, not a browser runtime database integration.

**File Storage:**
- Local browser file selection uses the `File` API in `frontend/components/chat/ChatComposer.tsx`.
- Upload filtering lives in `frontend/app/file-upload.ts`; accepted filenames are `.md`, `.json`, `.txt`, `.docx`, `.xlsx`, and `.xlsm`.
- Upload transport uses `FormData` and `POST /api/tasks/{task_id}/files` in `frontend/lib/task-api.ts`.
- Artifact download and preview use backend artifact endpoints, `Response.blob()`, `URL.createObjectURL`, and DOM download/open flows in `frontend/hooks/use-task-workspace.ts`.
- HTML artifact previews are rendered in a new browser window with a sandboxed iframe document generated by `buildSandboxedArtifactPreviewDocument` in `frontend/hooks/use-task-workspace.ts`.

**Caching:**
- No Redis, browser storage cache, service worker, or data-fetch cache library is detected in `frontend/`.
- Runtime state is held in React state inside `frontend/hooks/use-task-workspace.ts`.
- Event deduplication happens in memory through `mergeExecutionLogs` in `frontend/app/task-state.ts`.

## Authentication & Identity

**Auth Provider:**
- Custom shared-token boundary handled by the backend.
  - Implementation: `frontend/lib/task-api.ts` reads `NEXT_PUBLIC_MYAGENT_TOKEN` or legacy `NEXT_PUBLIC_AGENT_CHAT_TOKEN`.
  - HTTP requests: Token is sent as `X-MyAgent-Token`.
  - SSE requests: Token is sent as a `token` query parameter because `EventSource` cannot set custom headers.
  - Browser exposure: All `NEXT_PUBLIC_*` values are bundled for the browser; do not put provider secrets, database URLs, Qdrant URLs, customer data, or private examples in these values.
- No frontend login page, OAuth provider, cookie session, or app runtime `localStorage` session store is detected in `frontend/app/`, `frontend/components/`, `frontend/hooks/`, or `frontend/lib/`.
- `frontend/e2e-playwright/test_storage_memory_e2e.mjs` uses `localStorage` only for an E2E harness token scenario; it is not used by the production app runtime.

## Browser APIs

**Network:**
- `fetch` - REST requests in `frontend/lib/task-api.ts`.
- `EventSource` - SSE stream requests in `frontend/lib/task-api.ts` and lifecycle management in `frontend/hooks/use-task-workspace.ts`.

**Files and Blobs:**
- `File` and file input selection - `frontend/components/chat/ChatComposer.tsx`.
- `FormData` - Multipart uploads in `frontend/lib/task-api.ts`.
- `Blob` / `Response.blob()` - Artifact retrieval in `frontend/lib/task-api.ts`.
- `URL.createObjectURL` and `URL.revokeObjectURL` - Artifact download and preview lifecycle in `frontend/hooks/use-task-workspace.ts`.

**DOM and Clipboard:**
- `navigator.clipboard.writeText` - Copy messages/logs/diagnostics in `frontend/hooks/use-task-workspace.ts`.
- `window.open`, `document.open`, `document.write`, and sandboxed iframe markup - HTML artifact previews in `frontend/hooks/use-task-workspace.ts`.
- `document.createElement("a")` - Download trigger in `frontend/hooks/use-task-workspace.ts`.
- `window.confirm` - Destructive conversation actions in `frontend/hooks/use-task-workspace.ts` and `frontend/components/chat/ChatSidebar.tsx`.
- `document.addEventListener` / `document.removeEventListener` - Outside-click and Escape-key handling in `frontend/components/chat/ChatComposer.tsx` and `frontend/components/chat/ChatSidebar.tsx`.
- `window.requestAnimationFrame` and `window.cancelAnimationFrame` - Composer focus and log auto-scroll behavior in `frontend/components/chat/ChatComposer.tsx` and `frontend/components/chat/TaskConversation.tsx`.
- `Intl.DateTimeFormat` and `Intl.Segmenter` - Time formatting and title grapheme segmentation in `frontend/app/workspace-view.ts` and `frontend/app/task-state.ts`.

## Monitoring & Observability

**Error Tracking:**
- None detected in `frontend/package.json`, `frontend/app/`, `frontend/components/`, `frontend/hooks/`, or `frontend/lib/`.

**Logs:**
- Frontend user-facing logs are backend task events normalized by `frontend/app/task-state.ts` and rendered by `frontend/components/chat/TaskConversation.tsx`.
- Diagnostic JSON and JSONL copy flows are generated client-side in `frontend/app/workspace-view.ts` and copied through `frontend/hooks/use-task-workspace.ts`.
- Browser E2E evidence is documented in `frontend/e2e-playwright/README.md` and stored in local timestamped `frontend/e2e-playwright/e2e-YYYYMMDDHHMMSS/` folders.

## CI/CD & Deployment

**Hosting:**
- No hosting platform configuration is detected inside `frontend/`.
- The production command is `npm run build` followed by `npm run start` from `frontend/package.json`.

**CI Pipeline:**
- No frontend-local CI workflow is detected inside `frontend/`.
- Validation commands available from `frontend/package.json` are `npm run typecheck`, `npm test`, `npm run lint`, `npm run build`, and `npm run e2e:runtime-contracts`.

## Environment Configuration

**Required env vars:**
- `NEXT_PUBLIC_MYAGENT_API_BASE_URL` - Optional browser backend base URL. Use `auto` or leave unset to derive port `8001` from the current page hostname. Defined in `frontend/.env.example`; resolved in `frontend/app/task-state.ts`.
- `NEXT_PUBLIC_MYAGENT_TOKEN` - Optional browser-exposed MyAgent access token. Defined in `frontend/.env.example`; read in `frontend/lib/task-api.ts`.
- `NEXT_PUBLIC_API_BASE_URL` - Legacy backend base URL fallback accepted by `frontend/lib/task-api.ts`.
- `NEXT_PUBLIC_AGENT_CHAT_TOKEN` - Legacy access-token fallback accepted by `frontend/lib/task-api.ts`.
- `NEXT_WATCH_POLL_INTERVAL_MS` - Optional watch polling interval for `frontend/next.config.mjs`.
- `MYAGENT_E2E_BASE_URL` - E2E frontend base URL for `frontend/e2e-playwright/*.mjs`.
- `MYAGENT_E2E_API_URL` - E2E backend API base URL for `frontend/e2e-playwright/*.mjs`.
- `MYAGENT_E2E_EVIDENCE_DIR` - E2E screenshot/evidence output path for `frontend/e2e-playwright/*.mjs`.
- `MYAGENT_E2E_ACCESS_TOKEN` - Optional E2E API token used by `frontend/e2e-playwright/*.mjs`.
- `MYAGENT_E2E_TASK_ROOT`, `MYAGENT_E2E_EXPECT_UPLOAD_LIMIT_BYTES`, `MYAGENT_E2E_POSTGRES_CONTAINER`, `MYAGENT_E2E_POSTGRES_USER`, `MYAGENT_E2E_POSTGRES_DB`, `MYAGENT_DEFAULT_USER_ID`, and `MYAGENT_E2E_PYTHON` - Scenario-specific E2E backend setup variables documented or used in `frontend/e2e-playwright/README.md` and specs.

**Secrets location:**
- `frontend/.env.local` exists and is ignored by `frontend/.gitignore`; do not read, quote, or commit its values.
- `frontend/.env.example` is safe documentation for browser-exposed variable names.
- Provider keys, database URLs, Qdrant URLs, and private customer data must remain in backend runtime configuration, not in `NEXT_PUBLIC_*` variables.

## Webhooks & Callbacks

**Incoming:**
- None detected in `frontend/`. The Next app has no route handlers under `frontend/app/api/`.

**Outgoing:**
- REST calls and SSE connections go to the MyAgent backend from `frontend/lib/task-api.ts`.
- No outbound webhook, telemetry, analytics, email, payment, or third-party SDK callbacks are detected in `frontend/`.

---

*Integration audit: 2026-05-22*
