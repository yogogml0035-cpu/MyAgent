# Architecture

**Analysis Date:** 2026-05-19

## Pattern Overview

**Overall:** Next.js app-router single-page task workspace with a typed boundary layer, React hook orchestration, and pure projection helpers for backend events.

**Key Characteristics:**
- `frontend/app/page.tsx` is intentionally thin and delegates to `TaskWorkspace`.
- API calls are centralized in `frontend/lib/task-api.ts`.
- Backend wire data is normalized in `frontend/app/task-state.ts`.
- React side effects and workflow state live in `frontend/hooks/use-task-workspace.ts`.
- Display grouping, progress rows, conversation ordering, and labels live in `frontend/app/workspace-view.ts`.
- Components under `frontend/components/chat/` render UI from hook outputs and callbacks.

## Layers

**App Router Entry:**
- Purpose: Mount the application workspace.
- Contains: `Home()` in `frontend/app/page.tsx`, root metadata/layout in `frontend/app/layout.tsx`.
- Depends on: `frontend/components/chat/TaskWorkspace.tsx`.
- Used by: Next.js route `/`.

**API Adapter:**
- Purpose: Encapsulate backend origin resolution, token attachment, HTTP errors, JSON parsing, SSE construction, and artifact blob fetching.
- Contains: `frontend/lib/task-api.ts`.
- Depends on: `frontend/app/task-state.ts`, browser `fetch`, browser `EventSource`.
- Used by: `frontend/hooks/use-task-workspace.ts`.

**State Normalization:**
- Purpose: Convert untrusted backend payloads into typed frontend records.
- Contains: `frontend/app/task-state.ts`.
- Depends on: browser `URL`, known backend field names, bounded readers, and internal type guards.
- Used by: API adapter, workspace hook, and unit tests.

**Workspace Orchestration Hook:**
- Purpose: Coordinate user workflows: model load, task history, task creation, upload, message send, SSE retry, polling recovery, cancel, rename/delete, artifact open/download, and notices.
- Contains: `frontend/hooks/use-task-workspace.ts`.
- Depends on: API adapter, state normalization, model/file helpers, workspace projection helpers.
- Used by: `TaskWorkspace`.

**View Projection Helpers:**
- Purpose: Build conversation stream items, run groups, log rows, diagnostics JSON, visible partitions, labels, timestamps, and clipboard text.
- Contains: `frontend/app/workspace-view.ts`.
- Depends on: normalized `TaskState`, `ExecutionLog`, runs, messages, and artifacts.
- Used by: components and tests.

**Presentation Components:**
- Purpose: Render sidebar/history, conversation/progress/artifacts, composer/file preview/model picker, typewriter text, and avatar.
- Contains: `frontend/components/chat/TaskWorkspace.tsx`, `ChatSidebar.tsx`, `TaskConversation.tsx`, `ChatComposer.tsx`, `TypewriterText.tsx`, and `RobotAvatar.tsx`.
- Depends on: hook return values and global CSS classes.
- Used by: browser and Playwright specs.

**Design System Surface:**
- Purpose: Global tokens, layout, responsive behavior, and component styling.
- Contains: `frontend/app/globals.css`; external visual reference is `DESIGN.md`.
- Depends on: class names emitted by chat components.

## Data Flow

**Initial Page Load:**
1. Next renders `frontend/app/page.tsx`.
2. `TaskWorkspace` calls `useTaskWorkspace()`.
3. Hook fetches `/api/models` and `/api/tasks` through `frontend/lib/task-api.ts`.
4. Responses are normalized by `normalizeModelOption()` and `normalizeTaskSummaries()`.
5. Sidebar renders history and composer renders model availability.

**Send Message With Optional Uploads:**
1. `ChatComposer` calls `handleSubmit()` from the hook.
2. Hook ensures a task exists with `createTask()`.
3. Hook uploads selected files through `uploadTaskFiles()` if any.
4. Hook posts the message with `postTaskMessage()` and `buildMessageRequestPayload()`.
5. Hook refreshes task state and history.
6. Active `running` status starts the SSE effect.

**Live Event Flow:**
1. `createTaskEventSource()` opens `/api/tasks/{task_id}/stream`.
2. SSE messages are JSON-parsed in `useTaskWorkspace()`.
3. Allowed event types are normalized by `normalizeEventRecords()`.
4. Logs merge by event ID through `mergeExecutionLogs()`.
5. `buildRunActivityGroups()` associates logs and artifacts with runs.
6. `buildConversationStreamItems()` interleaves messages, run progress groups, and artifacts.

**SSE Recovery Flow:**
1. On SSE error, the hook closes the current `EventSource`.
2. It refreshes task summary and fetches incremental events after the last known log ID.
3. It retries with `calculateSseRetryDelay()` up to `MAX_SSE_RETRIES`.
4. After repeated failure it renders a workspace error notice.

**Artifact Flow:**
1. User opens or downloads an artifact in `TaskConversation`.
2. Hook calls `fetchArtifactBlob()`.
3. `buildArtifactRequest()` validates origin, task ID, run ID, and artifact name before attaching token.
4. Download uses a temporary anchor; HTML open writes a wrapper page with a sandboxed iframe.

**State Management:**
- Backend task state is authoritative.
- React local state is the UI projection and is refreshed after write operations.
- Incremental event state is merged by log ID to handle SSE replay/reconnect.

## Key Abstractions

**TaskState:**
- Purpose: UI-normalized task record with `camelCase` fields.
- Example: `frontend/app/task-state.ts`.
- Pattern: Type alias plus `normalizeTaskState()`.

**ExecutionLog:**
- Purpose: Normalized event record with optional live metadata, reasoning, search, memory, orchestration, stream, and raw diagnostics.
- Example: `normalizeLog()` in `frontend/app/task-state.ts`.
- Pattern: Bounded extraction from untrusted backend payloads.

**RunActivityGroup:**
- Purpose: Group a run's logs, artifacts, status, and optional streamed-answer diagnostics.
- Example: `buildRunActivityGroups()` in `frontend/app/workspace-view.ts`.
- Pattern: Pure derived view model.

**useTaskWorkspace:**
- Purpose: Own side effects and workflow state.
- Example: `frontend/hooks/use-task-workspace.ts`.
- Pattern: React hook returns plain props/callbacks to presentation components.

**ArtifactRequest:**
- Purpose: Safe URL and header pair for artifact fetches.
- Example: `buildArtifactRequest()` in `frontend/app/task-state.ts`.
- Pattern: Trust check before token attachment.

## Entry Points

**Next Route `/`:**
- Location: `frontend/app/page.tsx`.
- Triggers: Browser navigation to the app.
- Responsibilities: Render `TaskWorkspace`.

**Workspace Component:**
- Location: `frontend/components/chat/TaskWorkspace.tsx`.
- Triggers: React render.
- Responsibilities: Compose sidebar, conversation, and composer.

**Workspace Hook:**
- Location: `frontend/hooks/use-task-workspace.ts`.
- Triggers: Component lifecycle and user events.
- Responsibilities: All backend calls and browser side effects.

**API Adapter:**
- Location: `frontend/lib/task-api.ts`.
- Triggers: Hook callbacks and effects.
- Responsibilities: REST/SSE/blob I/O.

## Error Handling

**Strategy:** Convert backend/network failures into user-facing notices while preserving backend state as source of truth.

**Patterns:**
- `requestTaskJson()` wraps network failures and non-OK responses.
- `formatHttpErrorMessage()` extracts stable backend `detail` messages.
- `formatRequestFailure()` turns `TypeError` into backend-down guidance.
- Hook write operations catch errors, set notice level, and refresh task state when possible.
- Unknown backend statuses normalize to `unknown` rather than `running`.
- SSE parser failures trigger task summary refresh instead of crashing UI.

## Cross-Cutting Concerns

**Validation:**
- All untrusted backend payloads pass through type guards and bounded readers in `frontend/app/task-state.ts`.
- Artifact URLs are validated before tokens are attached.
- Upload support is filtered by extension in `frontend/app/file-upload.ts`.

**Accessibility:**
- Components use aria labels, `aria-expanded`, `aria-haspopup`, `role="menu"`, `role="listbox"`, and keyboard Escape/outside-click handling for menus.

**Design:**
- Visual work must read `DESIGN.md` and reuse tokens in `frontend/app/globals.css`.
- Current style uses warm canvas, coral primary color, restrained card radius, and dense workspace layout.

**Logging:**
- Browser app code avoids console logging; diagnostics are UI state and copied raw JSONL.

---

*Architecture analysis: 2026-05-19*
*Update when frontend boundaries, task flow, SSE recovery, or rendering architecture changes*
