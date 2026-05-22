<!-- refreshed: 2026-05-22 -->
# Architecture

**Analysis Date:** 2026-05-22

## System Overview

```text
┌─────────────────────────────────────────────────────────────┐
│                 Next.js App Router Shell                    │
│ `frontend/app/layout.tsx` + `frontend/app/page.tsx`          │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                 Client Chat Workspace                       │
├──────────────────┬──────────────────┬───────────────────────┤
│  History Sidebar │  Conversation    │  Composer             │
│ `ChatSidebar.tsx`│ `TaskConversation`│ `ChatComposer.tsx`   │
└────────┬─────────┴────────┬─────────┴──────────┬────────────┘
         │                  │                    │
         └──────────────────┴──────────┬─────────┘
                                        ▼
┌─────────────────────────────────────────────────────────────┐
│                Workspace Controller Hook                    │
│ `frontend/hooks/use-task-workspace.ts`                      │
│ React state, effects, task actions, SSE lifecycle            │
└───────────────┬──────────────────────┬──────────────────────┘
                │                      │
                ▼                      ▼
┌──────────────────────────────┐ ┌────────────────────────────┐
│ REST/SSE API Adapter          │ │ Pure State/View Adapters   │
│ `frontend/lib/task-api.ts`    │ │ `frontend/app/task-state.ts`│
│ fetch/EventSource/blob calls  │ │ `frontend/app/workspace-view.ts` │
└───────────────┬──────────────┘ └────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────────────┐
│       Backend HTTP API, browser file/blob/clipboard APIs     │
│       `/api/tasks`, `/api/models`, `/api/skills`, SSE stream │
└─────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| Root layout | Loads global CSS, page metadata, Chinese locale shell, and icon metadata. | `frontend/app/layout.tsx` |
| Home route | Keeps routing thin and delegates the root page to the workspace component. | `frontend/app/page.tsx` |
| TaskWorkspace | Composes sidebar, conversation, and composer; passes only hook-owned values and handlers into child components. | `frontend/components/chat/TaskWorkspace.tsx` |
| ChatSidebar | Renders conversation history, new conversation, rename/delete menus, and clear-all action. | `frontend/components/chat/ChatSidebar.tsx` |
| TaskConversation | Renders user/assistant messages, run progress logs, diagnostics JSON, artifact cards, copy buttons, and auto-scroll behavior. | `frontend/components/chat/TaskConversation.tsx` |
| ChatComposer | Owns local picker UI for message input, model selection, file picker, slash skill picker, selected skill chips, send, and stop controls. | `frontend/components/chat/ChatComposer.tsx` |
| useTaskWorkspace | Owns browser task state, initialization effects, task submission, history mutations, polling/SSE merge logic, artifact open/download, and user-facing errors. | `frontend/hooks/use-task-workspace.ts` |
| Task API adapter | Centralizes backend REST, multipart upload, SSE EventSource, artifact blob fetch, and browser-safe access-token attachment. | `frontend/lib/task-api.ts` |
| Task state adapter | Defines task/message/log/artifact types, normalizes backend payloads, translates known backend text, builds message/artifact requests, and validates trusted artifact URLs. | `frontend/app/task-state.ts` |
| Workspace view adapter | Builds history items, run groups, conversation stream items, live log rows, diagnostics JSON, display labels, timestamps, and keyboard intent helpers. | `frontend/app/workspace-view.ts` |
| File/model/skill helpers | Keep upload file partitioning, model display metadata, and slash skill matching out of React components. | `frontend/app/file-upload.ts`, `frontend/app/model-ui.ts`, `frontend/app/skill-selection.ts` |
| Global styles | Defines design tokens, two-column shell, responsive workspace layout, chat cards, composer, history menu, progress logs, and mobile breakpoints. | `frontend/app/globals.css` |

## Pattern Overview

**Overall:** Single-route client workspace with a controller hook, transport adapter, and pure normalization/view-model modules.

**Key Characteristics:**
- Keep `frontend/app/page.tsx` as a routing delegate; put workspace behavior in `frontend/hooks/use-task-workspace.ts` and UI rendering in `frontend/components/chat/`.
- Route all backend I/O through `frontend/lib/task-api.ts`; do not call `fetch` for task APIs directly from components.
- Normalize backend payloads at `frontend/app/task-state.ts` before storing or rendering them.
- Build render-oriented collections in `frontend/app/workspace-view.ts` instead of embedding grouping/sorting rules in JSX.
- Use relative imports; `frontend/tsconfig.json` does not define path aliases.
- Keep browser-exposed configuration limited to `NEXT_PUBLIC_*` values documented in `frontend/.env.example` and `frontend/README.md`.

## Layers

**Routing and Layout:**
- Purpose: Provide the Next.js app shell and the single root route.
- Location: `frontend/app/layout.tsx`, `frontend/app/page.tsx`
- Contains: `RootLayout`, metadata, global CSS import, root `Home` route.
- Depends on: Next metadata types, `frontend/components/chat/TaskWorkspace.tsx`.
- Used by: Next.js app router.

**Chat UI Components:**
- Purpose: Render the workspace as stateless or locally-interactive UI surfaces.
- Location: `frontend/components/chat/`
- Contains: `TaskWorkspace`, `ChatSidebar`, `TaskConversation`, `ChatComposer`, `RobotAvatar`, `TypewriterText`.
- Depends on: `frontend/hooks/use-task-workspace.ts`, `frontend/app/workspace-view.ts`, `frontend/app/task-state.ts`, `react-markdown`, `remark-gfm`.
- Used by: `frontend/app/page.tsx`.

**Workspace Controller:**
- Purpose: Own browser state, side effects, task lifecycle actions, and child component props.
- Location: `frontend/hooks/use-task-workspace.ts`
- Contains: React state for the active task, status, messages, logs, artifacts, task summaries, uploads, models, skills, busy flags, copied feedback, and error notices.
- Depends on: `frontend/lib/task-api.ts`, `frontend/app/task-state.ts`, `frontend/app/workspace-view.ts`, `frontend/app/model-ui.ts`, `frontend/app/file-upload.ts`.
- Used by: `frontend/components/chat/TaskWorkspace.tsx`.

**Backend Transport:**
- Purpose: Adapt browser fetch/EventSource/blob calls to the backend API contract.
- Location: `frontend/lib/task-api.ts`
- Contains: `requestTaskJson`, model/skill/task fetchers, task creation, upload, message post, cancel, rename, delete, event cursor fetch, SSE creation, artifact blob fetch.
- Depends on: `frontend/app/task-state.ts` for URL resolution, normalization, payload builders, and error formatting.
- Used by: `frontend/hooks/use-task-workspace.ts`.

**State Normalization and Contracts:**
- Purpose: Convert untrusted backend JSON into typed frontend state and safe request structures.
- Location: `frontend/app/task-state.ts`
- Contains: `TaskState`, `ChatMessage`, `ExecutionLog`, `TaskRunRecord`, `TaskSummary`, `Artifact`, `ModelOption`, `SkillOption` re-exports, normalizers, log merge helpers, artifact URL trust checks, error message formatting.
- Depends on: `frontend/app/skill-selection.ts`.
- Used by: `frontend/lib/task-api.ts`, `frontend/hooks/use-task-workspace.ts`, `frontend/app/workspace-view.ts`, chat components, tests.

**View Models and Display Rules:**
- Purpose: Project normalized state into structures that are convenient for JSX.
- Location: `frontend/app/workspace-view.ts`
- Contains: conversation history items, state/workspace notices, run activity groups, live log rows, diagnostics JSON, copy text, status labels, time/file formatting, composer keyboard intent.
- Depends on: `frontend/app/task-state.ts`.
- Used by: `frontend/hooks/use-task-workspace.ts`, `frontend/components/chat/TaskConversation.tsx`, `frontend/components/chat/ChatComposer.tsx`, `frontend/components/chat/ChatSidebar.tsx`.

**Feature Helpers:**
- Purpose: Keep small domain rules reusable and testable.
- Location: `frontend/app/file-upload.ts`, `frontend/app/model-ui.ts`, `frontend/app/skill-selection.ts`
- Contains: upload extension support, model display descriptions, skill option normalization, slash token parsing, slash token replacement.
- Depends on: `frontend/app/task-state.ts` only for model type imports in `frontend/app/model-ui.ts`.
- Used by: `frontend/hooks/use-task-workspace.ts`, `frontend/components/chat/ChatComposer.tsx`, state/model/upload tests.

**Styling:**
- Purpose: Define the complete visual system for the shell and chat workspace.
- Location: `frontend/app/globals.css`
- Contains: CSS variables, shell layout, sidebar, conversation canvas, message cards, progress logs, composer, model and skill menus, responsive breakpoints.
- Depends on: class names emitted by `frontend/components/chat/`.
- Used by: `frontend/app/layout.tsx`.

## Data Flow

### Primary Request Path

1. Next.js loads `RootLayout` (`frontend/app/layout.tsx:14`) and the root `Home` route (`frontend/app/page.tsx:3`).
2. `Home` renders `TaskWorkspace` (`frontend/components/chat/TaskWorkspace.tsx:8`), which calls `useTaskWorkspace` and passes values/handlers into `ChatSidebar`, `TaskConversation`, and `ChatComposer`.
3. `useTaskWorkspace` initializes model options, task summaries, and skill options through `fetchModelOptions`, `fetchTaskSummaries`, and `fetchSkillOptions` (`frontend/hooks/use-task-workspace.ts:256`, `frontend/hooks/use-task-workspace.ts:263`, `frontend/hooks/use-task-workspace.ts:289`).
4. A send action enters `handleSubmit` (`frontend/hooks/use-task-workspace.ts:440`), creates a task if needed with `ensureTask` (`frontend/hooks/use-task-workspace.ts:308`), uploads selected files, and posts a message with selected model and skill names.
5. `frontend/lib/task-api.ts` sends the HTTP calls: `createTask` (`frontend/lib/task-api.ts:82`), `uploadTaskFiles` (`frontend/lib/task-api.ts:141`), and `postTaskMessage` (`frontend/lib/task-api.ts:155`) through `requestTaskJson` (`frontend/lib/task-api.ts:29`).
6. Backend responses are normalized by `normalizeTaskState` (`frontend/app/task-state.ts:1169`) and stored through `applyTaskState` in `frontend/hooks/use-task-workspace.ts`.
7. While the task is active, the hook starts SSE with `createTaskEventSource` (`frontend/hooks/use-task-workspace.ts:362`, `frontend/lib/task-api.ts:173`), merges incoming logs with `mergeExecutionLogs` (`frontend/app/task-state.ts:1322`), and refreshes summary/event projections.
8. The hook builds `runActivityGroups` and `conversationStreamItems` using `buildRunActivityGroups` (`frontend/app/workspace-view.ts:1513`) and `buildConversationStreamItems` (`frontend/app/workspace-view.ts:1620`).
9. `TaskConversation` renders messages, live log rows, artifacts, and notices (`frontend/components/chat/TaskConversation.tsx:91`).

### Conversation History Flow

1. `fetchTaskSummaries` reads `/api/tasks` (`frontend/lib/task-api.ts:78`) and `normalizeTaskSummaries` converts entries into `TaskSummary[]` (`frontend/app/task-state.ts`).
2. `buildConversationHistoryItems` maps summaries to sidebar rows (`frontend/app/workspace-view.ts:1323`).
3. `ChatSidebar` renders selection, rename, delete, and clear-all controls (`frontend/components/chat/ChatSidebar.tsx:15`).
4. Selection calls `handleSelectConversation` (`frontend/hooks/use-task-workspace.ts:565`) and then `fetchTask` (`frontend/lib/task-api.ts:97`).
5. Rename/delete/clear call `renameTask`, `deleteTask`, and repeated `deleteTask` through hook handlers (`frontend/hooks/use-task-workspace.ts:615`, `frontend/hooks/use-task-workspace.ts:655`, `frontend/hooks/use-task-workspace.ts:700`).

### Artifact Flow

1. Normalized `Artifact` entries are attached to task state by `normalizeTaskState` (`frontend/app/task-state.ts:1169`).
2. `buildRunActivityGroups` associates artifacts with run groups (`frontend/app/workspace-view.ts:1513`).
3. `TaskConversation` exposes open/download controls for artifact cards (`frontend/components/chat/TaskConversation.tsx:91`).
4. `handleDownloadArtifact` fetches a blob and triggers an `<a download>` click (`frontend/hooks/use-task-workspace.ts:791`).
5. `handleOpenArtifact` opens a blank window, fetches the blob, and writes a sandboxed iframe preview document (`frontend/hooks/use-task-workspace.ts:812`, `frontend/hooks/use-task-workspace.ts:105`).
6. `buildArtifactRequest` rejects untrusted artifact URLs before adding the browser token header (`frontend/app/task-state.ts:1205`).

### Upload, Model, and Skill Flow

1. `ChatComposer` renders a native file input, model listbox, slash skill listbox, selected file chips, and selected skill chips (`frontend/components/chat/ChatComposer.tsx:53`).
2. Selected files are filtered by `partitionSupportedUploadFiles` (`frontend/app/file-upload.ts:19`) before the hook stores them.
3. Model options are loaded from `/api/models` and restricted to DeepSeek V4 Flash IDs in `frontend/hooks/use-task-workspace.ts`.
4. Skill options are loaded from `/api/skills`, normalized by `normalizeSkillOptions`, filtered with `filterSkillOptions`, and selected through slash-token helpers (`frontend/app/skill-selection.ts:49`, `frontend/app/skill-selection.ts:59`, `frontend/app/skill-selection.ts:71`, `frontend/app/skill-selection.ts:106`).
5. `postTaskMessage` serializes selected skill names into the message payload (`frontend/lib/task-api.ts:155`).

**State Management:**
- Use React state and refs inside `frontend/hooks/use-task-workspace.ts`; there is no external client state library.
- Use derived state with `useMemo` for notices, history items, model display options, selected skills, run groups, and conversation stream items.
- Use refs only for browser-side transient state: latest logs for event cursor recovery and copy-feedback timer cleanup in `frontend/hooks/use-task-workspace.ts`, scroll/detail state in `frontend/components/chat/TaskConversation.tsx`, picker/file input state in `frontend/components/chat/ChatComposer.tsx`, and menu state in `frontend/components/chat/ChatSidebar.tsx`.
- Treat backend task state and persisted events as authoritative; SSE is a projection merged into local logs and backed by `fetchTaskEvents` recovery.

## Key Abstractions

**TaskState and Related Types:**
- Purpose: Stable frontend shape for task detail, runs, messages, logs, artifacts, uploads, errors, and needs-input prompts.
- Examples: `TaskState`, `ChatMessage`, `ExecutionLog`, `TaskRunRecord`, `TaskSummary`, `Artifact` in `frontend/app/task-state.ts`.
- Pattern: Normalize every backend response before it reaches React rendering.

**ExecutionLog Projection:**
- Purpose: Preserve raw backend event records while exposing typed live metadata, reasoning traces, file audit traces, search traces, orchestration traces, memory context, and answer/thinking streams.
- Examples: `normalizeLog` (`frontend/app/task-state.ts:1018`), `buildLiveLogItems` (`frontend/app/workspace-view.ts:200`), `buildRunDiagnosticsJson` (`frontend/app/workspace-view.ts:196`).
- Pattern: Store typed fields for UI, keep non-enumerable raw records for diagnostics JSON.

**ConversationStreamItem:**
- Purpose: Flatten messages, run logs, streamed answers, and artifact cards into a single ordered render stream.
- Examples: `ConversationStreamItem` and `buildConversationStreamItems` in `frontend/app/workspace-view.ts`.
- Pattern: Build ordering outside JSX and render by discriminated `kind`.

**RunActivityGroup:**
- Purpose: Associate logs, artifacts, status, and streamed answer content by backend run ID.
- Examples: `RunActivityGroup` and `buildRunActivityGroups` in `frontend/app/workspace-view.ts`.
- Pattern: Group run-scoped records before rendering progress cards.

**Task API Adapter:**
- Purpose: Provide one browser transport boundary for REST, multipart, SSE, delete, and artifact blob calls.
- Examples: `requestTaskJson`, `createTaskEventSource`, `fetchArtifactBlob` in `frontend/lib/task-api.ts`.
- Pattern: Return normalized frontend types from public API helpers whenever possible.

**ArtifactRequest:**
- Purpose: Prevent token leakage to untrusted artifact URLs and support run-scoped artifact routes.
- Examples: `buildArtifactRequest`, `trustedApiOrigin`, `assertTrustedArtifactUrl` in `frontend/app/task-state.ts`.
- Pattern: Construct or validate URLs before issuing browser fetches.

**ModelDisplayOption and SkillOption:**
- Purpose: Keep backend model/skill records browser-safe and display-ready.
- Examples: `frontend/app/model-ui.ts`, `frontend/app/skill-selection.ts`.
- Pattern: Normalize backend records and derive display copy separately from component state.

## Entry Points

**Application Route:**
- Location: `frontend/app/page.tsx`
- Triggers: Next.js request for `/`.
- Responsibilities: Render `TaskWorkspace` only; do not place task orchestration here.

**Root Layout:**
- Location: `frontend/app/layout.tsx`
- Triggers: Next.js app shell creation.
- Responsibilities: Set metadata, language, body shell, and global CSS.

**Workspace Component Boundary:**
- Location: `frontend/components/chat/TaskWorkspace.tsx`
- Triggers: Rendered by `frontend/app/page.tsx`.
- Responsibilities: Bind `useTaskWorkspace` to presentational chat components.

**Workspace Hook:**
- Location: `frontend/hooks/use-task-workspace.ts`
- Triggers: Called by `TaskWorkspace`.
- Responsibilities: Initialize backend data, mutate task state, manage SSE, expose handlers and derived values.

**Backend API Boundary:**
- Location: `frontend/lib/task-api.ts`
- Triggers: Called by `useTaskWorkspace` and tests.
- Responsibilities: Convert frontend actions into backend HTTP/SSE/blob requests.

**Global Styling:**
- Location: `frontend/app/globals.css`
- Triggers: Imported by `frontend/app/layout.tsx`.
- Responsibilities: Supply all runtime CSS for the chat workspace.

**Automated Checks:**
- Location: `frontend/tests/`, `frontend/e2e-playwright/`
- Triggers: `npm test`, `npm run e2e:runtime-contracts`, and direct `npx playwright test ...` commands from `frontend/`.
- Responsibilities: Guard architecture boundaries, state adapters, UI helpers, and browser acceptance flows.

## Architectural Constraints

- **Threading:** The frontend runs on the browser event loop. SSE callbacks, file picker events, clipboard writes, timers, and popup/blob handling must stay non-blocking inside React event/effect handlers.
- **Global state:** Module-level constants in `frontend/hooks/use-task-workspace.ts`, `frontend/lib/task-api.ts`, `frontend/app/task-state.ts`, `frontend/app/file-upload.ts`, and `frontend/app/model-ui.ts` are configuration or lookup constants. Mutable application state belongs in React hooks/components.
- **Runtime configuration:** `TASK_API_BASE_URL` and `TASK_API_ACCESS_TOKEN` are computed at module import in `frontend/lib/task-api.ts`. Browser-exposed configuration must use `NEXT_PUBLIC_MYAGENT_API_BASE_URL`, `NEXT_PUBLIC_API_BASE_URL`, `NEXT_PUBLIC_MYAGENT_TOKEN`, or `NEXT_PUBLIC_AGENT_CHAT_TOKEN`; provider secrets must not be added to frontend code or docs.
- **Routing:** The application has one production route, `/`, implemented by `frontend/app/page.tsx`. Add route folders under `frontend/app/` only when a real URL surface is required.
- **Backend field boundary:** Backend `snake_case` and alternative field names are normalized in `frontend/app/task-state.ts`. Components should consume `camelCase` frontend types.
- **SSE recovery:** SSE updates are merged into logs and complemented by `fetchTaskEvents` with the latest log ID. Do not treat EventSource delivery as the only durable state source.
- **Artifacts:** Artifact opening/downloading must use `fetchArtifactBlob` and `buildArtifactRequest`; do not render backend-provided artifact URLs directly into clickable links.
- **Circular imports:** Not detected in the explored frontend source. Preserve the current direction: components -> hook -> API/state/view adapters; API -> state adapter; view adapter -> state types.
- **Path aliases:** Not configured in `frontend/tsconfig.json`; keep local imports relative unless aliases are added deliberately to config and tests.
- **Generated directories:** `.next/`, `.next-dev/`, `node_modules/`, `test-results/`, timestamped E2E evidence folders, `next-env.d.ts`, and `*.tsbuildinfo` are generated or local artifacts.

## Anti-Patterns

### Fetching Task APIs From Components

**What happens:** A chat component calls `/api/tasks`, `/api/models`, `/api/skills`, or artifact routes directly.
**Why it's wrong:** It bypasses shared headers, access-token handling, error formatting, and payload normalization.
**Do this instead:** Add or extend a function in `frontend/lib/task-api.ts`, then call it from `frontend/hooks/use-task-workspace.ts`.

### Rendering Raw Backend Payloads

**What happens:** JSX reads `snake_case` backend fields or raw event payloads directly.
**Why it's wrong:** The UI depends on backend shape drift and duplicates translation/normalization rules.
**Do this instead:** Normalize fields in `frontend/app/task-state.ts` and build display structures in `frontend/app/workspace-view.ts`.

### Embedding Grouping and Log Ordering in JSX

**What happens:** `TaskConversation` sorts logs, groups runs, or filters placeholder messages inline while rendering.
**Why it's wrong:** The progress timeline is dense and already covered by pure tests around `frontend/app/workspace-view.ts`.
**Do this instead:** Extend `buildRunActivityGroups`, `buildConversationStreamItems`, or `buildLiveLogItems` in `frontend/app/workspace-view.ts`.

### Opening Artifact URLs Directly

**What happens:** A component links to `artifact.url` or opens a blob URL as the top-level document.
**Why it's wrong:** Untrusted URLs can leak the browser token or execute generated HTML outside the intended sandbox.
**Do this instead:** Use `handleDownloadArtifact` and `handleOpenArtifact` in `frontend/hooks/use-task-workspace.ts`, backed by `fetchArtifactBlob` in `frontend/lib/task-api.ts` and `buildSandboxedArtifactPreviewDocument` in `frontend/hooks/use-task-workspace.ts`.

### Adding Product Logic to Route Files

**What happens:** `frontend/app/page.tsx` gains state, handlers, task API calls, or rendering branches.
**Why it's wrong:** The root route is intentionally a stable delegation point and is guarded by `frontend/tests/workspace/test_frontend_architecture.test.ts`.
**Do this instead:** Keep product behavior in `frontend/hooks/use-task-workspace.ts`, `frontend/app/*` helpers, and `frontend/components/chat/`.

## Error Handling

**Strategy:** Convert transport and backend failures into user-facing message strings at the API/state boundary, then surface them through hook-owned notice messages.

**Patterns:**
- `requestTaskJson` wraps fetch failures with `formatRequestFailure` and non-OK responses with `formatHttpErrorMessage` (`frontend/lib/task-api.ts`, `frontend/app/task-state.ts`).
- `useTaskWorkspace` catches action failures, sets `errorLevel`, and exposes workspace notices through `buildWorkspaceNoticeMessages` (`frontend/hooks/use-task-workspace.ts`, `frontend/app/workspace-view.ts`).
- Backend task errors and `needs_input` data are projected as state notices through `buildStateNoticeMessages` (`frontend/app/workspace-view.ts:101`).
- SSE error payloads are parsed by `getSseErrorDetail` and followed by summary/event refresh (`frontend/hooks/use-task-workspace.ts`).
- Artifact URL validation throws the same user-facing blocked-url message before token-bearing fetches (`frontend/app/task-state.ts`).

## Cross-Cutting Concerns

**Logging:** The frontend does not maintain an application logger. It renders backend event logs and diagnostics through `ExecutionLog`, `buildLiveLogItems`, `buildRunDiagnosticsJson`, and copy-to-clipboard JSONL helpers in `frontend/app/workspace-view.ts`.

**Validation:** Validate backend JSON with `isRecord`, `readString`, bounded readers, and normalizers in `frontend/app/task-state.ts`. Validate upload filenames in `frontend/app/file-upload.ts`. Validate slash skill tokens in `frontend/app/skill-selection.ts`. Validate artifact URL trust in `frontend/app/task-state.ts`.

**Authentication:** Optional browser access tokens are read from `NEXT_PUBLIC_MYAGENT_TOKEN` or `NEXT_PUBLIC_AGENT_CHAT_TOKEN` in `frontend/lib/task-api.ts`. REST requests send `X-MyAgent-Token`; SSE uses a `token` query parameter because browser `EventSource` cannot set custom headers.

**Configuration:** `frontend/.env.example` documents public frontend variables. `frontend/.env.local` is present as ignored local configuration and must not be read or copied into documentation.

**Styling:** Keep global visual tokens and component class styling in `frontend/app/globals.css`; route files and components use class names rather than CSS modules.

---

*Architecture analysis: 2026-05-22*
