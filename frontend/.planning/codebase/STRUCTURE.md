# Codebase Structure

**Analysis Date:** 2026-05-22

## Directory Layout

```text
frontend/
├── app/                         # Next app route files, global CSS, pure frontend domain/view helpers
│   ├── layout.tsx               # Root app shell and metadata
│   ├── page.tsx                 # Root route delegating to TaskWorkspace
│   ├── globals.css              # Global design tokens and chat workspace styles
│   ├── task-state.ts            # Backend payload normalization and frontend state contracts
│   ├── workspace-view.ts        # View-model builders for conversation/history/progress logs
│   ├── file-upload.ts           # Supported upload file rules
│   ├── model-ui.ts              # Model display metadata
│   └── skill-selection.ts       # Browser-safe skill normalization and slash picker helpers
├── components/
│   └── chat/                    # Client chat workspace components
├── hooks/                       # React controller hooks
├── lib/                         # Browser transport/API adapters
├── tests/                       # Node test runner unit and boundary tests
├── e2e-playwright/              # Reusable Playwright specs plus ignored evidence folders
├── .planning/codebase/          # Generated frontend codebase maps
├── package.json                 # Scripts and dependency manifest
├── package-lock.json            # npm lockfile
├── next.config.mjs              # Next dev/build configuration
├── tsconfig.json                # TypeScript configuration
├── eslint.config.mjs            # ESLint flat config
├── .env.example                 # Public frontend env example
└── README.md                    # Frontend setup and E2E instructions
```

## Directory Purposes

**`frontend/app/`:**
- Purpose: Own the Next app shell, root route, global stylesheet, and pure frontend domain/view helper modules.
- Contains: `frontend/app/layout.tsx`, `frontend/app/page.tsx`, `frontend/app/globals.css`, `frontend/app/task-state.ts`, `frontend/app/workspace-view.ts`, `frontend/app/file-upload.ts`, `frontend/app/model-ui.ts`, `frontend/app/skill-selection.ts`, `frontend/app/icon.svg`.
- Key files: `frontend/app/page.tsx`, `frontend/app/task-state.ts`, `frontend/app/workspace-view.ts`.

**`frontend/components/chat/`:**
- Purpose: Own all chat workspace React components.
- Contains: `frontend/components/chat/TaskWorkspace.tsx`, `frontend/components/chat/ChatSidebar.tsx`, `frontend/components/chat/TaskConversation.tsx`, `frontend/components/chat/ChatComposer.tsx`, `frontend/components/chat/RobotAvatar.tsx`, `frontend/components/chat/TypewriterText.tsx`.
- Key files: `frontend/components/chat/TaskWorkspace.tsx`, `frontend/components/chat/TaskConversation.tsx`, `frontend/components/chat/ChatComposer.tsx`, `frontend/components/chat/ChatSidebar.tsx`.

**`frontend/hooks/`:**
- Purpose: Own React hook state machines and browser effects that coordinate multiple components.
- Contains: `frontend/hooks/use-task-workspace.ts`.
- Key files: `frontend/hooks/use-task-workspace.ts`.

**`frontend/lib/`:**
- Purpose: Own browser transport adapters and shared clients.
- Contains: `frontend/lib/task-api.ts`.
- Key files: `frontend/lib/task-api.ts`.

**`frontend/tests/`:**
- Purpose: Own Node test-runner unit and architecture tests for pure helpers, transport adapters, and source boundaries.
- Contains: `frontend/tests/workspace/`, `frontend/tests/state/`, `frontend/tests/model/`, `frontend/tests/upload/`.
- Key files: `frontend/tests/workspace/test_frontend_architecture.test.ts`, `frontend/tests/workspace/test_task_workspace.test.ts`, `frontend/tests/state/test_task_state.test.ts`, `frontend/tests/workspace/test_workspace_view.test.ts`.

**`frontend/e2e-playwright/`:**
- Purpose: Own browser acceptance specs and local screenshot/evidence output.
- Contains: committed specs such as `frontend/e2e-playwright/test_runtime_contracts.spec.mjs`, `frontend/e2e-playwright/test_progress_log_disclosure.spec.mjs`, `frontend/e2e-playwright/test_multi_session_thinking_audit.spec.mjs`, `frontend/e2e-playwright/test_skill_selector_full_loop.spec.mjs`, plus ignored `e2e-YYYYMMDDHHMMSS/` evidence directories.
- Key files: `frontend/e2e-playwright/README.md`, `frontend/e2e-playwright/test_runtime_contracts.spec.mjs`.

**`frontend/.planning/codebase/`:**
- Purpose: Store generated frontend codebase reference documents for GSD planning and execution.
- Contains: `frontend/.planning/codebase/ARCHITECTURE.md`, `frontend/.planning/codebase/STRUCTURE.md`.
- Key files: `frontend/.planning/codebase/ARCHITECTURE.md`, `frontend/.planning/codebase/STRUCTURE.md`.

**Root config files:**
- Purpose: Define package scripts, Next output directories, TypeScript checking, linting, public env examples, ignored artifacts, and frontend developer instructions.
- Contains: `frontend/package.json`, `frontend/package-lock.json`, `frontend/next.config.mjs`, `frontend/tsconfig.json`, `frontend/eslint.config.mjs`, `frontend/.env.example`, `frontend/.gitignore`, `frontend/README.md`.
- Key files: `frontend/package.json`, `frontend/next.config.mjs`, `frontend/tsconfig.json`, `frontend/eslint.config.mjs`.

## Key File Locations

**Entry Points:**
- `frontend/app/layout.tsx`: Root layout, metadata, icon registration, global CSS import.
- `frontend/app/page.tsx`: Root `/` route; renders `TaskWorkspace`.
- `frontend/components/chat/TaskWorkspace.tsx`: Client workspace composition boundary.
- `frontend/hooks/use-task-workspace.ts`: Runtime state/action boundary for the workspace.
- `frontend/lib/task-api.ts`: Backend REST/SSE/blob transport boundary.

**Configuration:**
- `frontend/package.json`: npm scripts for dev, build, start, typecheck, test, E2E runtime contracts, and lint.
- `frontend/next.config.mjs`: Disables dev indicators, uses `.next-dev` for dev output and `.next` for production output, configures polling watch interval.
- `frontend/tsconfig.json`: Strict TypeScript config with Next typegen outputs from `.next/types` and `.next-dev/types`.
- `frontend/eslint.config.mjs`: Next core web vitals and TypeScript lint config with generated directories ignored.
- `frontend/.env.example`: Documents public browser env variables; use it instead of reading `frontend/.env.local`.
- `frontend/README.md`: Setup, WSL/Windows path warning, public API base URL behavior, endpoint summary, and E2E acceptance guidance.

**Core Logic:**
- `frontend/app/task-state.ts`: Types, backend normalization, event/log normalization, artifact URL validation, error formatting.
- `frontend/app/workspace-view.ts`: Conversation stream ordering, run grouping, progress log rendering models, diagnostic JSON formatting, status labels.
- `frontend/hooks/use-task-workspace.ts`: Task creation, upload, message send, cancellation, SSE retries, event cursor recovery, conversation history mutations, artifact open/download.
- `frontend/lib/task-api.ts`: HTTP methods and endpoint paths for tasks, models, skills, events, files, messages, cancel, artifacts.
- `frontend/app/file-upload.ts`: Upload extension rules shared by hook, composer, and tests.
- `frontend/app/model-ui.ts`: Model presentation metadata for the composer picker.
- `frontend/app/skill-selection.ts`: Skill option normalization and slash-token picker behavior.

**UI Components:**
- `frontend/components/chat/TaskWorkspace.tsx`: Pass hook state into sidebar, conversation, and composer.
- `frontend/components/chat/ChatSidebar.tsx`: History list, rename/delete menu, clear history.
- `frontend/components/chat/TaskConversation.tsx`: Transcript, markdown messages, live progress logs, diagnostics panels, artifact actions.
- `frontend/components/chat/ChatComposer.tsx`: Textarea, file input, upload preview, model picker, skill picker, send/stop controls.
- `frontend/components/chat/RobotAvatar.tsx`: Shared assistant avatar.
- `frontend/components/chat/TypewriterText.tsx`: Client-side markdown typewriter effect.

**Styling:**
- `frontend/app/globals.css`: All global CSS variables and workspace styles.
- `frontend/app/icon.svg`: App icon used by `frontend/app/layout.tsx`.

**Testing:**
- `frontend/tests/workspace/test_frontend_architecture.test.ts`: Source-boundary tests for route/component/hook/API layering and config expectations.
- `frontend/tests/workspace/test_task_workspace.test.ts`: Hook behavior, SSE helpers, artifact preview, model gating, skill wiring, busy-state behavior.
- `frontend/tests/workspace/test_task_api.test.ts`: API adapter exports, skill normalization through the adapter, message payload structure.
- `frontend/tests/workspace/test_workspace_view.test.ts`: Conversation, log, diagnostics, ordering, and display helper tests.
- `frontend/tests/state/test_task_state.test.ts`: Task state normalization, artifact request security, message payloads, event translation.
- `frontend/tests/state/test_skill_selection.test.ts`: Slash skill selection helpers.
- `frontend/tests/model/test_model_ui.test.ts`: Model picker display helpers.
- `frontend/tests/upload/test_file_upload.test.ts`: Supported upload file rules.
- `frontend/e2e-playwright/test_runtime_contracts.spec.mjs`: Browser runtime contract acceptance against real frontend/backend services.
- `frontend/e2e-playwright/README.md`: Scenario-specific Playwright command matrix and screenshot evidence rules.

## Naming Conventions

**Files:**
- Next app route files use framework names: `frontend/app/layout.tsx`, `frontend/app/page.tsx`.
- Pure helper modules under `frontend/app/` use kebab-case: `frontend/app/task-state.ts`, `frontend/app/workspace-view.ts`, `frontend/app/file-upload.ts`, `frontend/app/model-ui.ts`, `frontend/app/skill-selection.ts`.
- React component files use PascalCase: `frontend/components/chat/TaskWorkspace.tsx`, `frontend/components/chat/ChatComposer.tsx`.
- Hook files use `use-*.ts`: `frontend/hooks/use-task-workspace.ts`.
- Browser API adapters use domain names under `frontend/lib/`: `frontend/lib/task-api.ts`.
- Node tests use `test_*.test.ts`: `frontend/tests/workspace/test_task_workspace.test.ts`.
- Playwright specs use `test_*.spec.mjs`: `frontend/e2e-playwright/test_skill_selector.spec.mjs`.

**Directories:**
- Product source directories are lowercase by responsibility: `frontend/app/`, `frontend/components/`, `frontend/hooks/`, `frontend/lib/`, `frontend/tests/`, `frontend/e2e-playwright/`.
- Component subdirectories are domain-oriented lowercase: `frontend/components/chat/`.
- Test subdirectories group by surface: `frontend/tests/workspace/`, `frontend/tests/state/`, `frontend/tests/model/`, `frontend/tests/upload/`.
- E2E evidence directories use timestamped `e2e-YYYYMMDDHHMMSS/` names under `frontend/e2e-playwright/`.

**Exports:**
- React components use PascalCase named exports: `TaskWorkspace`, `TaskConversation`, `ChatComposer`, `ChatSidebar`.
- React hooks use camelCase `use*` exports: `useTaskWorkspace`.
- Pure functions and helpers use camelCase named exports: `normalizeTaskState`, `buildRunActivityGroups`, `fetchTaskSummaries`.
- Types use PascalCase named exports: `TaskState`, `ExecutionLog`, `ConversationStreamItem`, `ModelDisplayOption`.

## Where to Add New Code

**New Route:**
- Primary code: add a route directory/file under `frontend/app/`.
- Shared workspace code: keep reusable UI in `frontend/components/chat/` or a new domain component folder under `frontend/components/`.
- Tests: add source-boundary or behavior tests under `frontend/tests/workspace/`; add browser specs under `frontend/e2e-playwright/` when user-visible behavior changes.

**New Workspace Behavior:**
- State and side effects: `frontend/hooks/use-task-workspace.ts`.
- Pure state normalization or backend field mapping: `frontend/app/task-state.ts`.
- Render ordering, grouping, labels, diagnostics, or copy text: `frontend/app/workspace-view.ts`.
- UI controls or layout: `frontend/components/chat/` and `frontend/app/globals.css`.
- Tests: `frontend/tests/workspace/` plus relevant `frontend/e2e-playwright/test_*.spec.mjs`.

**New Backend Endpoint or API Operation:**
- Transport function: `frontend/lib/task-api.ts`.
- Request/response types and normalizers: `frontend/app/task-state.ts`.
- Hook integration: `frontend/hooks/use-task-workspace.ts`.
- Tests: `frontend/tests/workspace/test_task_api.test.ts`, `frontend/tests/state/test_task_state.test.ts`, and browser E2E when behavior is visible.

**New Conversation Rendering Rule:**
- Pure projection: `frontend/app/workspace-view.ts`.
- JSX renderer: `frontend/components/chat/TaskConversation.tsx`.
- Styles: `frontend/app/globals.css`.
- Tests: `frontend/tests/workspace/test_workspace_view.test.ts` and progress-related Playwright specs in `frontend/e2e-playwright/`.

**New Composer Control:**
- UI state and DOM events: `frontend/components/chat/ChatComposer.tsx`.
- Workspace-owned state or backend action: `frontend/hooks/use-task-workspace.ts`.
- Pure helper rules: add to `frontend/app/` as a focused kebab-case module when rules are reusable and testable.
- Styles: `frontend/app/globals.css`.
- Tests: `frontend/tests/workspace/test_task_workspace.test.ts` or a new focused test under `frontend/tests/`.

**New Upload Format:**
- Extension support and labels: `frontend/app/file-upload.ts`.
- Composer behavior: `frontend/components/chat/ChatComposer.tsx` only if UI changes are required.
- Tests: `frontend/tests/upload/test_file_upload.test.ts`, `frontend/e2e-playwright/test_resource_upload_harness.spec.mjs`, and `frontend/e2e-playwright/test_upload_preview_design.spec.mjs` when file picker or preview UI changes.

**New Model UI Behavior:**
- Display metadata: `frontend/app/model-ui.ts`.
- Availability gating and allowed model list: `frontend/hooks/use-task-workspace.ts`.
- Picker rendering: `frontend/components/chat/ChatComposer.tsx`.
- Tests: `frontend/tests/model/test_model_ui.test.ts`, `frontend/tests/workspace/test_task_workspace.test.ts`.

**New Skill Selection Behavior:**
- Skill normalization/filtering/token logic: `frontend/app/skill-selection.ts`.
- Picker/chip rendering: `frontend/components/chat/ChatComposer.tsx`.
- API loading: `frontend/lib/task-api.ts` and `frontend/hooks/use-task-workspace.ts`.
- Tests: `frontend/tests/state/test_skill_selection.test.ts`, `frontend/tests/workspace/test_task_api.test.ts`, `frontend/e2e-playwright/test_skill_selector.spec.mjs`, `frontend/e2e-playwright/test_skill_selector_full_loop.spec.mjs`.

**Utilities:**
- Shared frontend domain helpers: put focused modules in `frontend/app/` when they are pure and app-specific.
- Browser transport helpers: put them in `frontend/lib/`.
- React stateful helpers: put hooks in `frontend/hooks/`.
- Avoid creating broad `utils` modules unless a repeated pattern has a clear domain and tests.

## Special Directories

**`frontend/.planning/codebase/`:**
- Purpose: Generated codebase maps consumed by planning/execution agents.
- Generated: Yes
- Committed: Yes, when codebase documentation is refreshed.

**`frontend/.next/`:**
- Purpose: Next production build output and generated type files.
- Generated: Yes
- Committed: No; ignored by `frontend/.gitignore`.

**`frontend/.next-dev/`:**
- Purpose: Next dev server output selected by `frontend/next.config.mjs`.
- Generated: Yes
- Committed: No; ignored by `frontend/.gitignore`.

**`frontend/node_modules/`:**
- Purpose: npm dependency installation.
- Generated: Yes
- Committed: No; ignored by `frontend/.gitignore`.

**`frontend/test-results/`:**
- Purpose: Playwright and local test output.
- Generated: Yes
- Committed: No; ignored by `frontend/.gitignore`.

**`frontend/e2e-playwright/e2e-YYYYMMDDHHMMSS/`:**
- Purpose: Local browser acceptance screenshots, fixtures, downloads, and evidence.
- Generated: Yes
- Committed: No; keep evidence local and reference it in delivery notes.

**`frontend/next-env.d.ts`:**
- Purpose: Next.js generated TypeScript environment declarations.
- Generated: Yes
- Committed: No; ignored by `frontend/.gitignore`.

**`frontend/tsconfig.tsbuildinfo`:**
- Purpose: TypeScript incremental build cache.
- Generated: Yes
- Committed: No; ignored by `frontend/.gitignore`.

**`frontend/.env.local`:**
- Purpose: Local browser-exposed frontend environment overrides.
- Generated: Local configuration
- Committed: No; ignored by `frontend/.gitignore` and not safe to read or quote.

---

*Structure analysis: 2026-05-22*
