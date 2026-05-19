# Coding Conventions

**Analysis Date:** 2026-05-19

## Naming Patterns

**Files:**
- `kebab-case.ts` for non-component modules: `frontend/app/task-state.ts`, `frontend/app/workspace-view.ts`, `frontend/lib/task-api.ts`.
- `PascalCase.tsx` for React component files: `ChatComposer.tsx`, `TaskConversation.tsx`.
- `test_*.test.ts` for Node tests under `frontend/tests/`.
- `test_*.spec.mjs` for Playwright specs under `frontend/e2e-playwright/`.

**Functions:**
- Use `camelCase` for functions and helpers: `requestTaskJson()`, `normalizeTaskState()`, `buildRunActivityGroups()`.
- Use `handle*` for component/hook event handlers: `handleSubmit()`, `handleFileSelection()`.
- Use `use*` for hooks: `useTaskWorkspace()`.

**Variables:**
- Use `UPPER_SNAKE_CASE` for module constants: `MAX_SSE_RETRIES`, `DEFAULT_MODEL_ID`, `TASK_API_BASE_URL`.
- Use `camelCase` for frontend state fields after normalization: `createdAt`, `runId`, `uploadCount`, `needsInput`.
- Keep backend field names only inside normalization/API boundary code.

**Types:**
- Use `PascalCase` for type aliases: `TaskState`, `ExecutionLog`, `RunActivityGroup`, `ModelOption`.
- Prefer exported type aliases for shared UI/view models in `frontend/app/task-state.ts` and `frontend/app/workspace-view.ts`.

## Code Style

**Formatting:**
- TypeScript strict mode is enabled in `frontend/tsconfig.json`.
- No Prettier or Biome config is present; keep formatting consistent with existing source.
- Keep display text sized to component context and style through CSS classes, not inline styles, except generated artifact preview document string.

**Linting:**
- Run `npm run lint` from `frontend/`; ESLint warnings fail because the script uses `--max-warnings=0`.
- Next generated directories are ignored by `frontend/eslint.config.mjs`.

## Import Organization

**Order:**
1. React and Node/package imports.
2. Type imports when practical.
3. Relative app/helper/component imports.

**Grouping:**
- Components import types and helpers from `frontend/app/` through relative paths.
- Hook imports API functions from `../lib/task-api` and projection helpers from `../app/workspace-view`.

**Path Aliases:**
- No `@/` or other TypeScript path alias is configured.
- Do not introduce aliases without updating `frontend/tsconfig.json`, lint/test tooling, and imports.

## Error Handling

**Patterns:**
- `requestTaskJson()` centralizes network, status, JSON parsing, and token attachment for JSON requests.
- `formatHttpErrorMessage()` extracts backend `detail` messages and hides verbose 422 payloads.
- `formatRequestFailure()` turns network `TypeError` into backend-down guidance.
- Hook handlers catch errors, set user-visible notices, and refresh task state when possible.
- Unknown backend statuses normalize to `unknown`, not `running`.
- SSE parse or connection problems trigger summary/event refresh and bounded retry.

**Error Types:**
- User-facing frontend errors are regular `Error` instances with localized messages.
- Trusted artifact validation throws before token attachment.

## Logging

**Framework:**
- No frontend logging framework is used.
- Avoid `console.log` in committed app code; use React state, notices, and copied diagnostics.

**Patterns:**
- Backend event diagnostics stay in `ExecutionLog.rawRecord` as a non-enumerable property.
- Clipboard logs use raw JSONL through `buildLogClipboardText()`.

## Comments

**When to Comment:**
- Use comments only around non-obvious protocol or security choices.
- Existing examples include the disabled streamed-answer card explanation in `frontend/app/workspace-view.ts`.

**JSDoc/TSDoc:**
- Not a dominant pattern. Prefer expressive names, strict types, and focused tests.

## Function Design

**Size:**
- Keep React components mostly presentational.
- Keep backend I/O in `frontend/lib/task-api.ts`.
- Keep side effects in `frontend/hooks/use-task-workspace.ts`.
- Keep pure projections in `frontend/app/task-state.ts` and `frontend/app/workspace-view.ts`.

**Parameters:**
- Use options objects for optional behavior, such as `buildMessageRequestPayload()` and `fetchTask()`.
- Use typed event-intent objects for keyboard behavior, such as `shouldSubmitComposerKey()`.

**Return Values:**
- Return typed normalized records from API/state helpers.
- Return view model arrays from projection helpers.
- Return callback props from `useTaskWorkspace()` for components to wire.

## Module Design

**Exports:**
- Prefer named exports for components, hooks, helpers, and types.
- `frontend/app/page.tsx` uses the default export required by Next app router.

**Boundary Rules:**
- Components should not call backend APIs directly.
- API adapter should not render UI.
- State normalization should not create React state.
- View projection helpers should remain pure enough to test with Node.

**CSS:**
- Global CSS is centralized in `frontend/app/globals.css`.
- Reuse existing tokens such as `--canvas`, `--surface-card`, `--primary`, `--radius-md`, and font variables.
- Visual changes must align with `DESIGN.md`.

---

*Convention analysis: 2026-05-19*
*Update when frontend style, naming, imports, or boundary conventions change*
