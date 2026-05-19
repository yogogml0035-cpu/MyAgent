# Codebase Structure

**Analysis Date:** 2026-05-19

## Directory Layout

```text
frontend/
├── app/                         # App router entry, global CSS, pure state/view helpers
│   ├── page.tsx                 # Home route delegates to TaskWorkspace
│   ├── layout.tsx               # Root layout and metadata
│   ├── globals.css              # Design tokens and all UI styles
│   ├── task-state.ts            # Backend payload normalization and security helpers
│   ├── workspace-view.ts        # Pure view projection and labels
│   ├── file-upload.ts           # Upload extension filtering
│   └── model-ui.ts              # Model presentation metadata
├── components/
│   └── chat/                    # Workspace presentation components
├── hooks/                       # React orchestration hooks
├── lib/                         # Browser API adapter
├── tests/                       # Node test suites grouped by concern
├── e2e-playwright/              # Playwright specs and ignored evidence folders
├── package.json                 # npm scripts and dependency constraints
├── package-lock.json            # Exact npm package resolution
├── tsconfig.json                # Strict TypeScript config
├── eslint.config.mjs            # Next ESLint config
├── next.config.mjs              # Next distDir and watch config
└── .env.example                 # Browser-safe env template
```

## Directory Purposes

**`frontend/app/`:**
- Purpose: Next app entry files plus pure state/projection utilities.
- Key files: `page.tsx`, `layout.tsx`, `globals.css`, `task-state.ts`, `workspace-view.ts`, `file-upload.ts`, `model-ui.ts`.
- Add pure frontend helpers here when they are not React hooks or visual components.

**`frontend/components/chat/`:**
- Purpose: Chat workspace presentation.
- Key files: `TaskWorkspace.tsx`, `ChatSidebar.tsx`, `TaskConversation.tsx`, `ChatComposer.tsx`, `TypewriterText.tsx`, `RobotAvatar.tsx`.
- Components receive props/callbacks from the hook and should not call backend APIs directly.

**`frontend/hooks/`:**
- Purpose: React side effects and workflow state.
- Key file: `use-task-workspace.ts`.
- Add new task workflow side effects here before passing plain props to components.

**`frontend/lib/`:**
- Purpose: Browser I/O adapter.
- Key file: `task-api.ts`.
- Add backend REST/SSE/blob calls here and normalize responses at the boundary.

**`frontend/tests/`:**
- Purpose: Node unit/source tests.
- Groups: `state/`, `workspace/`, `upload/`, and `model/`.

**`frontend/e2e-playwright/`:**
- Purpose: Browser acceptance specs and local screenshot evidence.
- Commit specs and README; do not commit `e2e-YYYYMMDDHHMMSS/` evidence folders.

## Key File Locations

**Entry Points:**
- `frontend/app/page.tsx` - Home route.
- `frontend/components/chat/TaskWorkspace.tsx` - Main workspace composition.
- `frontend/hooks/use-task-workspace.ts` - Workflow orchestration.

**Configuration:**
- `frontend/package.json` - Scripts and dependencies.
- `frontend/tsconfig.json` - Strict TypeScript config.
- `frontend/eslint.config.mjs` - Lint config.
- `frontend/next.config.mjs` - Next build/dev output and watcher config.
- `frontend/.env.example` - Public env template.

**Core Logic:**
- `frontend/lib/task-api.ts` - API calls, SSE, artifact blob fetch.
- `frontend/app/task-state.ts` - Wire normalization and artifact URL trust checks.
- `frontend/app/workspace-view.ts` - Conversation/log projection.
- `frontend/app/file-upload.ts` - Supported upload extension filter.
- `frontend/app/model-ui.ts` - Model display copy and badges.

**Testing:**
- `frontend/tests/state/test_task_state.test.ts` - State normalization and artifact security.
- `frontend/tests/workspace/test_workspace_view.test.ts` - Log/progress/conversation projection.
- `frontend/tests/workspace/test_frontend_architecture.test.ts` - Boundary/source invariants.
- `frontend/e2e-playwright/test_*.spec.mjs` - Browser acceptance specs.

**Documentation:**
- `frontend/e2e-playwright/README.md` - E2E evidence conventions and commands.
- `frontend/.planning/codebase/` - Frontend codebase map.

## Naming Conventions

**Files:**
- `kebab-case.ts` for app/helpers: `task-state.ts`, `workspace-view.ts`, `file-upload.ts`.
- `PascalCase.tsx` for React components: `TaskWorkspace.tsx`, `ChatComposer.tsx`.
- `use-*.ts` for hooks: `use-task-workspace.ts`.
- `test_*.test.ts` for Node tests.
- `test_*.spec.mjs` for Playwright specs.

**Directories:**
- Lowercase concern directories: `app/`, `components/chat/`, `hooks/`, `lib/`, `tests/state/`.

**Special Patterns:**
- No TypeScript path alias is configured; imports are relative.
- App router files (`page.tsx`, `layout.tsx`) stay under `frontend/app/`.
- Run-specific Playwright folders use `e2e-YYYYMMDDHHMMSS/`.

## Where to Add New Code

**New backend API call:**
- Add wrapper: `frontend/lib/task-api.ts`.
- Add normalization/type support: `frontend/app/task-state.ts`.
- Add tests: `frontend/tests/state/` or `frontend/tests/workspace/`.

**New workflow behavior:**
- Hook orchestration: `frontend/hooks/use-task-workspace.ts`.
- Presentation props: `frontend/components/chat/TaskWorkspace.tsx`.
- UI rendering: relevant component in `frontend/components/chat/`.

**New event/log type:**
- Normalize: `frontend/app/task-state.ts`.
- Project/display: `frontend/app/workspace-view.ts`.
- Tests: `frontend/tests/state/test_task_state.test.ts` and `frontend/tests/workspace/test_workspace_view.test.ts`.
- Browser E2E: add or update `frontend/e2e-playwright/test_*.spec.mjs` if user-visible.

**New visual style:**
- Read `DESIGN.md` first.
- Add CSS in `frontend/app/globals.css`.
- Add component markup in `frontend/components/chat/`.
- Add source/unit tests and Playwright screenshot evidence when behavior or visuals change.

**New Playwright scenario:**
- Spec: `frontend/e2e-playwright/test_<scenario>.spec.mjs`.
- Evidence: `frontend/e2e-playwright/e2e-YYYYMMDDHHMMSS/<scenario>/`.
- README: update `frontend/e2e-playwright/README.md` if it becomes a stable acceptance entry.

## Special Directories

**`.next/`, `.next-dev/`, `.next-dev-e2e/`:**
- Purpose: Generated Next build/dev output.
- Committed: No.

**`node_modules/`:**
- Purpose: npm dependencies.
- Committed: No.

**`frontend/e2e-playwright/e2e-*/`:**
- Purpose: Local screenshot/download/trace evidence from Playwright runs.
- Committed: No.

**`frontend/test-results/`, `frontend/e2e-playwright/test-results/`, `frontend/e2e-playwright/playwright-report/`:**
- Purpose: Generated test artifacts.
- Committed: No.

---

*Structure analysis: 2026-05-19*
*Update when frontend directories, entry points, or placement rules change*
