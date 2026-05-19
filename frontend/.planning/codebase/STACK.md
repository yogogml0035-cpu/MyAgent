# Technology Stack

**Analysis Date:** 2026-05-19

## Languages

**Primary:**
- TypeScript/TSX - Next.js app router UI, React components, workspace hook, API adapter, state normalization, and unit tests under `frontend/app/`, `frontend/components/`, `frontend/hooks/`, `frontend/lib/`, and `frontend/tests/`.

**Secondary:**
- JavaScript ES modules - Playwright browser E2E specs in `frontend/e2e-playwright/*.mjs`.
- CSS - Global design system and application styling in `frontend/app/globals.css`.
- JSON - `frontend/package.json`, `frontend/package-lock.json`, and `frontend/tsconfig.json`.

## Runtime

**Environment:**
- Node.js target is 20 from root `.nvmrc` and project CI assumptions.
- Next.js app router runs on port 3001 by default.
- Browser runtime uses `fetch`, `EventSource`, `FormData`, `Blob`, object URLs, and `window.open()` for artifacts.

**Package Manager:**
- npm with lockfile `frontend/package-lock.json`.
- Exact package versions are resolved in `frontend/package-lock.json`; dependency constraints are in `frontend/package.json`.

## Frameworks

**Core:**
- Next.js 15.5.18 - App router application mounted by `frontend/app/page.tsx`.
- React 19.2.5 and React DOM 19.2.5 - Chat workspace components in `frontend/components/chat/`.
- TypeScript 5.9.3 - Strict mode source and test typing through `frontend/tsconfig.json`.

**Rendering:**
- `react-markdown` 10.1.0 - Markdown rendering in conversation components.
- `remark-gfm` 4.0.1 - GitHub-flavored Markdown support.

**Testing:**
- Node built-in `node:test` with `tsx` 4.21.0 - Unit/source tests under `frontend/tests/`.
- Playwright 1.60.0 - Browser E2E specs under `frontend/e2e-playwright/`.

**Build/Dev:**
- ESLint 9.39.4 with `eslint-config-next` 15.5.15 - Linting through `frontend/eslint.config.mjs`.
- Next typegen plus `tsc --noEmit` - Typecheck command in `frontend/package.json`.
- Next dev output is isolated with `NEXT_DIST_DIR=.next-dev`; E2E dev output is expected under `.next-dev-e2e`.

## Key Dependencies

**Critical:**
- `next` - App routing, build/dev server, typegen, and production build.
- `react` / `react-dom` - UI component runtime.
- `react-markdown` and `remark-gfm` - Assistant Markdown and artifact text rendering.
- `@playwright/test` - Browser E2E runner and screenshot evidence.
- `tsx` - Runs TypeScript test files with Node's test runner.

**Infrastructure:**
- FastAPI backend - Browser calls task, model, upload, artifact, cancel, events, and SSE endpoints through `frontend/lib/task-api.ts`.
- Browser EventSource - Streaming connection from `createTaskEventSource()` in `frontend/lib/task-api.ts`.
- Local evidence folders - Playwright screenshots and downloaded artifacts under ignored `frontend/e2e-playwright/e2e-YYYYMMDDHHMMSS/`.

## Configuration

**Environment:**
- `NEXT_PUBLIC_MYAGENT_API_BASE_URL` or legacy `NEXT_PUBLIC_API_BASE_URL` configures backend origin; `auto` resolves to the current browser hostname on port 8001 in `frontend/app/task-state.ts`.
- `NEXT_PUBLIC_MYAGENT_TOKEN` or legacy `NEXT_PUBLIC_AGENT_CHAT_TOKEN` attaches browser-visible token credentials in `frontend/lib/task-api.ts`.
- `MYAGENT_E2E_*` variables configure Playwright specs; examples are documented in `frontend/e2e-playwright/README.md`.
- `frontend/.env.local` is ignored and must contain only browser-safe `NEXT_PUBLIC_*` values.

**Build:**
- `frontend/package.json` scripts:
  - `npm run dev` - Next dev on port 3001 with polling and `.next-dev`.
  - `npm run typecheck` - `next typegen && tsc --noEmit`.
  - `npm test` - `node --test --import tsx tests/*/test_*.test.ts`.
  - `npm run lint` - ESLint with `--max-warnings=0`.
  - `npm run build` - Production Next build.
- `frontend/next.config.mjs` uses `NEXT_DIST_DIR` and polling watch options.
- `frontend/eslint.config.mjs` ignores `.next/`, `.next-dev/`, `.next-dev-e2e/`, `node_modules/`, and generated Next env types.

## Platform Requirements

**Development:**
- Install with `cd frontend && npm ci`.
- Run with `cd frontend && npm run dev`.
- Backend is expected on `http://127.0.0.1:8001` or a configured API base.
- For WSL/mounted drives, polling watchers are enabled by default.

**Production:**
- Built with `npm run build`; served with `npm run start` on port 3001.
- Browser-facing env values must remain safe because `NEXT_PUBLIC_*` is exposed to users.
- The frontend has no server-side API routes of its own; backend availability is required for task workflows.

---

*Stack analysis: 2026-05-19*
*Update after major dependency, runtime, build, or browser support changes*
