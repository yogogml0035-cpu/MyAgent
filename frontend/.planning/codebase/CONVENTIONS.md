# Coding Conventions

**Analysis Date:** 2026-05-22

## Naming Patterns

**Files:**
- Use kebab-case for reusable TypeScript modules in `frontend/app/`, `frontend/hooks/`, and `frontend/lib/`: `frontend/app/task-state.ts`, `frontend/app/workspace-view.ts`, `frontend/hooks/use-task-workspace.ts`, `frontend/lib/task-api.ts`.
- Use PascalCase component filenames under `frontend/components/chat/`: `frontend/components/chat/TaskWorkspace.tsx`, `frontend/components/chat/ChatComposer.tsx`, `frontend/components/chat/TaskConversation.tsx`, `frontend/components/chat/ChatSidebar.tsx`.
- Use snake_case test filenames under `frontend/tests/<area>/`: `frontend/tests/workspace/test_workspace_view.test.ts`, `frontend/tests/state/test_task_state.test.ts`, `frontend/tests/upload/test_file_upload.test.ts`.
- Use Playwright spec names prefixed with `test_` under `frontend/e2e-playwright/`: `frontend/e2e-playwright/test_runtime_contracts.spec.mjs`, `frontend/e2e-playwright/test_skill_selector.spec.mjs`.

**Functions:**
- Use camelCase for functions and helpers: `normalizeTaskState` in `frontend/app/task-state.ts`, `buildConversationStreamItems` in `frontend/app/workspace-view.ts`, `requestTaskJson` in `frontend/lib/task-api.ts`.
- Prefix pure transformation helpers by intent: `normalize*`, `format*`, `build*`, `read*`, `is*`, `merge*`, and `partition*`. Follow examples in `frontend/app/task-state.ts`, `frontend/app/workspace-view.ts`, and `frontend/app/file-upload.ts`.
- Use `handle*` for component/hook event handlers: `handleSubmit`, `handleFileSelection`, `handleSelectConversation`, and `handleOpenArtifact` in `frontend/hooks/use-task-workspace.ts`; `handleComposerKeyDown` in `frontend/components/chat/ChatComposer.tsx`.
- Use React hook names with `use` prefix and keep the hook file kebab-case: `useTaskWorkspace` in `frontend/hooks/use-task-workspace.ts`.

**Variables:**
- Use camelCase for state and derived values: `selectedModelRunnable`, `conversationStreamItems`, `runActivityGroups`, and `noticeMessages` in `frontend/hooks/use-task-workspace.ts`.
- Use uppercase `const` names for module-level constants: `DEFAULT_MODEL_ID`, `ALLOWED_MODEL_IDS`, `MAX_SSE_RETRIES`, and `TASK_WORKSPACE_STREAM_EVENT_TYPES` in `frontend/hooks/use-task-workspace.ts`; `SUPPORTED_UPLOAD_EXTENSIONS` in `frontend/app/file-upload.ts`.
- Use `*Ref` suffix for React refs: `fileInputRef`, `dismissedSkillSlashTokenRef`, `modelPickerRef`, and `textareaRef` in `frontend/components/chat/ChatComposer.tsx`.
- Use explicit "busy" booleans for interaction locks: `isSubmittingTask`, `isSwitchingConversation`, `isMutatingConversation`, `isStoppingTask`, `isComposerBusy`, and `isHistoryBusy` in `frontend/hooks/use-task-workspace.ts`.

**Types:**
- Use `type` aliases for object shapes and unions instead of interfaces: `TaskStatus`, `ChatMessage`, `ExecutionLog`, `TaskState`, and `MessageRequestPayload` in `frontend/app/task-state.ts`.
- Export shared domain types from pure modules and import them with `import type`: `ModelOption`, `TaskState`, `TaskSummary`, and `SkillOption` from `frontend/app/task-state.ts`.
- Define component props as local `type <ComponentName>Props` near the component: `ChatComposerProps` in `frontend/components/chat/ChatComposer.tsx`, `TaskConversationProps` in `frontend/components/chat/TaskConversation.tsx`, `ChatSidebarProps` in `frontend/components/chat/ChatSidebar.tsx`.
- Use discriminated unions for rendered stream items: `ConversationStreamItem` in `frontend/app/workspace-view.ts` uses `kind: "message" | "run" | "artifact"`.

## Code Style

**Formatting:**
- No Prettier or Biome config is detected in `frontend/`; format manually to match the existing TypeScript style.
- Use two-space indentation in TypeScript, TSX, CSS, JSON, and MJS files: `frontend/app/task-state.ts`, `frontend/components/chat/ChatComposer.tsx`, `frontend/app/globals.css`, and `frontend/package.json`.
- Prefer trailing commas for multiline objects, arrays, function arguments, JSX props, and imports, as used in `frontend/hooks/use-task-workspace.ts` and `frontend/components/chat/TaskConversation.tsx`.
- Keep long boolean conditions and JSX class composition split across lines, following `frontend/components/chat/ChatComposer.tsx` and `frontend/hooks/use-task-workspace.ts`.
- Use double quotes for strings in TypeScript, TSX, MJS, CSS string values, and JSON.

**Linting:**
- Use ESLint flat config from `frontend/eslint.config.mjs`.
- `frontend/eslint.config.mjs` extends `next/core-web-vitals` and `next/typescript` through `FlatCompat`.
- Ignored lint paths are `.next/**`, `.next-dev*/**`, `node_modules/**`, and `next-env.d.ts` in `frontend/eslint.config.mjs`.
- The lint command is `npm run lint`, which runs `eslint . --max-warnings=0` from `frontend/package.json`.

**TypeScript:**
- `frontend/tsconfig.json` has `strict: true`, `allowJs: false`, `isolatedModules: true`, `moduleResolution: "bundler"`, and `jsx: "preserve"`.
- Keep browser/backend payloads as `unknown` at the boundary and normalize them through explicit readers in `frontend/app/task-state.ts` and `frontend/app/skill-selection.ts`.
- Avoid widening with `any`; use `unknown`, `Record<string, unknown>`, type guards such as `isRecord`, and narrowing helpers such as `readString`.
- Do not commit generated `frontend/next-env.d.ts`; it is ignored by `frontend/.gitignore` and regenerated by Next.

## Import Organization

**Order:**
1. React, Next, and third-party imports, including type imports: `frontend/components/chat/TaskConversation.tsx`, `frontend/components/chat/ChatComposer.tsx`.
2. Pure app/domain module imports from `frontend/app/`: `frontend/hooks/use-task-workspace.ts`, `frontend/lib/task-api.ts`.
3. Local component imports from `frontend/components/chat/`: `frontend/components/chat/TaskWorkspace.tsx`, `frontend/components/chat/TaskConversation.tsx`.

**Path Aliases:**
- No path aliases are configured in `frontend/tsconfig.json`; use relative imports.
- Use repo-local relative paths from component files, such as `../../app/task-state` in `frontend/components/chat/TaskConversation.tsx`.
- Use `../app/...` and `../lib/...` from `frontend/hooks/use-task-workspace.ts`.

**Type Imports:**
- Use `import type` for type-only imports: `import type { Metadata } from "next"` in `frontend/app/layout.tsx`, `import type { ModelDisplayOption }` in `frontend/components/chat/ChatComposer.tsx`.
- Combine React value and type imports when the file needs both, as in `frontend/components/chat/ChatComposer.tsx` and `frontend/components/chat/TaskConversation.tsx`.

## Error Handling

**Patterns:**
- Centralize HTTP request failures in `frontend/lib/task-api.ts` using `requestTaskJson`, `formatHttpErrorMessage`, and `formatRequestFailure`.
- Throw `Error` objects with user-facing Chinese messages at API and validation boundaries: `requestTaskJson` in `frontend/lib/task-api.ts`, `buildArtifactRequest` in `frontend/app/task-state.ts`.
- Convert caught errors into display strings through `formatTaskApiFailure` in `frontend/lib/task-api.ts` and store them in `error` plus `errorLevel` in `frontend/hooks/use-task-workspace.ts`.
- Keep backend task errors separate from local workspace errors: `backendError` comes from normalized task state, while `error` and `errorLevel` represent frontend interaction failures in `frontend/hooks/use-task-workspace.ts`.
- Use `try` / `catch` / `finally` around async mutations and always release busy flags in `finally`: `handleSubmit`, `handleStop`, `handleRenameConversation`, `handleDeleteConversation`, and `handleOpenArtifact` in `frontend/hooks/use-task-workspace.ts`.
- For optional startup data, degrade gracefully: `fetchModelOptions` falls back to `DEFAULT_MODEL_OPTIONS`, and `fetchSkillOptions` sets a warning without blocking workspace initialization in `frontend/hooks/use-task-workspace.ts`.
- For SSE, parse each message defensively, merge normalized events, refresh task summary on malformed payloads, and bound reconnect attempts with `MAX_SSE_RETRIES` in `frontend/hooks/use-task-workspace.ts`.
- For unsafe artifact URLs, validate API origin, route shape, task id, run id, file name, query, hash, and path traversal before sending tokens in `frontend/app/task-state.ts`.

## Logging

**Framework:** Browser console is not used by application code.

**Patterns:**
- Do not add `console.log` or `console.error` to application modules; no application logging calls are present in `frontend/app/`, `frontend/components/`, `frontend/hooks/`, or `frontend/lib/`.
- Use task event logs and diagnostics as the user-visible logging surface: `ExecutionLog` in `frontend/app/task-state.ts`, `buildLiveLogItems` and `buildLogClipboardText` in `frontend/app/workspace-view.ts`, rendered by `frontend/components/chat/TaskConversation.tsx`.
- Preserve raw diagnostic JSONL when copying logs: `buildLogClipboardText` in `frontend/app/workspace-view.ts` and copy buttons in `frontend/components/chat/TaskConversation.tsx`.
- E2E specs may collect browser console errors as assertions, as in `frontend/e2e-playwright/test_skill_selector.spec.mjs` and `frontend/e2e-playwright/test_skill_selector_full_loop.spec.mjs`.

## Comments

**When to Comment:**
- Add comments only for non-obvious behavioral constraints or security boundaries. Existing examples include the sandboxed artifact preview CSP in `frontend/hooks/use-task-workspace.ts` and the disabled intermediate streaming answer explanation in `frontend/app/workspace-view.ts`.
- Avoid comments that restate assignments, prop names, or JSX structure.
- Keep config comments short and operational, as in `frontend/next.config.mjs`.

**JSDoc/TSDoc:**
- JSDoc/TSDoc is not used in `frontend/app/`, `frontend/components/`, `frontend/hooks/`, or `frontend/lib/`.
- Prefer explicit exported type names and focused tests over doc comments for behavior documentation.

## Function Design

**Size:** Pure helper modules contain many small exported functions; stateful React orchestration is concentrated in `frontend/hooks/use-task-workspace.ts`.

**Parameters:** Prefer structured option objects when a function has optional or mode-like parameters, as in `buildMessageRequestPayload(message, model, { mode, skills })` in `frontend/app/task-state.ts` and `fetchTask(id, { includeEvents })` in `frontend/lib/task-api.ts`.

**Return Values:** Return normalized, UI-ready objects from pure modules. Examples include `normalizeTaskState` in `frontend/app/task-state.ts`, `buildRunActivityGroups` in `frontend/app/workspace-view.ts`, and `buildModelDisplayOptions` in `frontend/app/model-ui.ts`.

**Pure Logic:**
- Place pure data normalization, formatting, sorting, filtering, and request-building logic in `frontend/app/*.ts` or `frontend/lib/*.ts`.
- Keep pure helpers exported when they are part of a tested behavior contract: `shouldSubmitComposerKey`, `buildConversationStreamItems`, `buildArtifactRequest`, and `partitionSupportedUploadFiles`.

**React Logic:**
- Use `useMemo` for derived arrays and display values that depend on state: `historyItems`, `modelDisplayOptions`, `selectedSkillNames`, `runActivityGroups`, and `conversationStreamItems` in `frontend/hooks/use-task-workspace.ts`.
- Use `useCallback` for handlers returned from hooks or passed through component boundaries: `handleSubmit`, `handleCopyText`, `handleDeleteConversation`, and `handleOpenArtifact` in `frontend/hooks/use-task-workspace.ts`.
- Use cleanup functions for document listeners, timers, SSE connections, and animation frames: `frontend/components/chat/ChatComposer.tsx`, `frontend/components/chat/ChatSidebar.tsx`, `frontend/components/chat/TaskConversation.tsx`, and `frontend/hooks/use-task-workspace.ts`.

## Module Design

**Exports:**
- Export pure helpers and types from `frontend/app/*.ts` when tests or other modules need a stable contract.
- Keep component exports named: `TaskWorkspace`, `ChatComposer`, `TaskConversation`, `ChatSidebar`, `RobotAvatar`, and `TypewriterText` in `frontend/components/chat/`.
- Keep the route component as a default export only at `frontend/app/page.tsx` and `frontend/app/layout.tsx`.

**Barrel Files:**
- No barrel files are used. Import directly from the module that owns the type or function.
- `frontend/app/task-state.ts` re-exports skill selection helpers from `frontend/app/skill-selection.ts`; use this only for state-bound consumers that already depend on task-state exports.

**Layer Boundaries:**
- `frontend/app/page.tsx` only delegates to `frontend/components/chat/TaskWorkspace.tsx`.
- `frontend/components/chat/TaskWorkspace.tsx` wires hook state and handlers into presentational chat components.
- `frontend/hooks/use-task-workspace.ts` owns browser state, task lifecycle orchestration, SSE, uploads, artifact open/download, history mutation, and model/skill selection state.
- `frontend/lib/task-api.ts` owns REST, SSE URL construction, auth header/query-token injection, and request response parsing.
- `frontend/app/task-state.ts`, `frontend/app/workspace-view.ts`, `frontend/app/model-ui.ts`, `frontend/app/file-upload.ts`, and `frontend/app/skill-selection.ts` own pure transformations.

## React Component Patterns

**Client Components:**
- Add `"use client";` only to components or hooks that use browser APIs, React state, effects, refs, or event handlers: `frontend/components/chat/TaskWorkspace.tsx`, `frontend/components/chat/TaskConversation.tsx`, `frontend/components/chat/ChatComposer.tsx`, `frontend/components/chat/TypewriterText.tsx`, and `frontend/hooks/use-task-workspace.ts`.
- Leave pure modules and server-compatible route/layout files without `"use client";`: `frontend/app/page.tsx`, `frontend/app/layout.tsx`, `frontend/app/task-state.ts`, `frontend/app/workspace-view.ts`.

**Props and Handlers:**
- Keep components controlled by props from `useTaskWorkspace`; do not fetch directly inside `frontend/components/chat/TaskWorkspace.tsx`, `frontend/components/chat/ChatComposer.tsx`, `frontend/components/chat/TaskConversation.tsx`, or `frontend/components/chat/ChatSidebar.tsx`.
- Name handler props with `on*` and implementation functions with `handle*`.
- For async handler props used in JSX, wrap calls with `void` to avoid unhandled promise lint noise: `onClick={() => void onStop()}` in `frontend/components/chat/ChatComposer.tsx`, `onClick={() => void handleDelete(item.id)}` in `frontend/components/chat/ChatSidebar.tsx`.

**Accessibility:**
- Add explicit `aria-label`, `aria-expanded`, `aria-haspopup`, `aria-selected`, and `aria-current` where controls are icon-only, menu-driven, or stateful: `frontend/components/chat/ChatComposer.tsx`, `frontend/components/chat/ChatSidebar.tsx`, `frontend/components/chat/TaskConversation.tsx`.
- Use semantic containers for major regions: `<main className="agentShell">` in `frontend/components/chat/TaskWorkspace.tsx`, `<aside aria-label="历史会话">` in `frontend/components/chat/ChatSidebar.tsx`, `<section aria-label="任务对话">` in `frontend/components/chat/TaskConversation.tsx`.
- Use `role="listbox"` and `role="option"` for model and skill pickers in `frontend/components/chat/ChatComposer.tsx`.

**UX Conventions:**
- Preserve the warm-canvas design tokens in `frontend/app/globals.css`: `--canvas`, `--workspace`, `--surface-card`, `--primary`, `--primary-active`, `--hairline`, `--ink`, and radius variables.
- Prefer global CSS class names in camelCase/Pascal-like CSS casing such as `agentShell`, `chatWorkspace`, `filePreviewShelf`, `skillPickerMenu`, and `traceLogToggleButton`; do not introduce CSS modules unless the layout architecture changes.
- Keep icon-only controls visually drawn with CSS or inline SVG and name them with accessible labels and titles, as in `frontend/components/chat/ChatComposer.tsx` and `frontend/components/chat/TaskConversation.tsx`.
- Keep destructive actions confirmed before mutation: delete and clear-history flows use `window.confirm` in `frontend/components/chat/ChatSidebar.tsx` and `frontend/hooks/use-task-workspace.ts`.
- Preserve responsive behavior in `frontend/app/globals.css` media queries for `max-width: 980px`, `760px`, and `520px`.
- Keep selected file, selected skill, model picker, log detail, history menu, and artifact controls covered by test IDs or accessible queries that match `frontend/tests/` and `frontend/e2e-playwright/`.

---

*Convention analysis: 2026-05-22*
