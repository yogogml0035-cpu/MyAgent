# Technology Stack

**Analysis Date:** 2026-05-22

## Languages

**Primary:**
- TypeScript 5.9.3 - App logic, React components, hooks, API adapters, and unit tests under `frontend/app/`, `frontend/components/`, `frontend/hooks/`, `frontend/lib/`, and `frontend/tests/`.
- TSX / React JSX - Client UI components in `frontend/components/chat/*.tsx` and the App Router entrypoint in `frontend/app/page.tsx`.

**Secondary:**
- JavaScript / ESM - Next, ESLint, and Playwright configuration/spec files in `frontend/next.config.mjs`, `frontend/eslint.config.mjs`, and `frontend/e2e-playwright/*.mjs`.
- CSS - Global styling and design tokens in `frontend/app/globals.css`.
- SVG - App icon in `frontend/app/icon.svg` and inline icon geometry in components such as `frontend/components/chat/RobotAvatar.tsx`.

## Runtime

**Environment:**
- Browser runtime - The production UI runs in the browser, using DOM APIs declared by `frontend/tsconfig.json` (`dom`, `dom.iterable`, `esnext`).
- Node.js - Required for Next.js, unit tests, linting, builds, and Playwright. `frontend/package-lock.json` resolves `next@15.5.18`, whose engine range is `^18.18.0 || ^19.8.0 || >= 20.0.0`.
- Local observed tool runtime - `node v24.14.1` and `npm 11.11.0` are available in this workspace.

**Package Manager:**
- npm 11.11.0 - Use npm scripts from `frontend/package.json`.
- Lockfile: present at `frontend/package-lock.json` with lockfile version 3.
- No `packageManager` or `engines` field is declared in `frontend/package.json`; rely on the Next.js engine range from `frontend/package-lock.json`.

## Frameworks

**Core:**
- Next.js 15.5.18 - App Router application shell, metadata, build, dev server, and production server. Entry files are `frontend/app/layout.tsx` and `frontend/app/page.tsx`.
- React 19.2.5 - Client component state, effects, and rendering in `frontend/components/chat/*.tsx` and `frontend/hooks/use-task-workspace.ts`.
- React DOM 19.2.5 - Browser rendering through Next.js.

**Testing:**
- Node `node:test` - Unit tests run through `node --test --import tsx tests/*/test_*.test.ts` from `frontend/package.json`.
- `tsx` 4.21.0 - TypeScript loader for Node test files in `frontend/tests/`.
- Playwright 1.60.0 / `@playwright/test` 1.60.0 - Browser E2E specs under `frontend/e2e-playwright/`, including `frontend/e2e-playwright/test_runtime_contracts.spec.mjs`.

**Build/Dev:**
- Next build/dev/start - Scripts in `frontend/package.json` run `next dev -p 3001`, `next build`, and `next start -p 3001`.
- TypeScript compiler 5.9.3 - `frontend/package.json` runs `next typegen && tsc --noEmit`; strict type checking is configured in `frontend/tsconfig.json`.
- ESLint 9.39.4 with `eslint-config-next` 15.5.15 - Flat config in `frontend/eslint.config.mjs` extends `next/core-web-vitals` and `next/typescript`.
- PostCSS 8.5.11 - Forced through the `overrides` section in `frontend/package.json`.

## Key Dependencies

**Critical:**
- `next` 15.5.18 - Owns routing, build output, dev server, and production serving for `frontend/app/`.
- `react` 19.2.5 and `react-dom` 19.2.5 - Own the interactive task workspace in `frontend/components/chat/TaskWorkspace.tsx`.
- `react-markdown` 10.1.0 - Renders assistant Markdown messages in `frontend/components/chat/TaskConversation.tsx` and `frontend/components/chat/TypewriterText.tsx`.
- `remark-gfm` 4.0.1 - Enables GitHub-flavored Markdown rendering in `frontend/components/chat/TaskConversation.tsx` and `frontend/components/chat/TypewriterText.tsx`.

**Infrastructure:**
- `@playwright/test` 1.60.0 - Runtime browser acceptance tests under `frontend/e2e-playwright/`.
- `typescript` 5.9.3 - Strict type validation for `frontend/app/`, `frontend/components/`, `frontend/hooks/`, `frontend/lib/`, and `frontend/tests/`.
- `tsx` 4.21.0 - Loads TypeScript tests for the Node test runner.
- `eslint` 9.39.4 and `eslint-config-next` 15.5.15 - Lint rules for Next.js and TypeScript in `frontend/eslint.config.mjs`.
- `@types/node` 22.19.17, `@types/react` 19.2.14, and `@types/react-dom` 19.2.3 - Type declarations resolved in `frontend/package-lock.json`.

## Configuration

**Environment:**
- Browser-facing runtime configuration is documented in `frontend/.env.example`.
- `NEXT_PUBLIC_MYAGENT_API_BASE_URL` controls the backend base URL. `auto` or an unset value derives `http://<current page hostname>:8001` in `frontend/app/task-state.ts`.
- `NEXT_PUBLIC_API_BASE_URL` is a legacy fallback read by `frontend/lib/task-api.ts`.
- `NEXT_PUBLIC_MYAGENT_TOKEN` is an optional browser-exposed access token read by `frontend/lib/task-api.ts`.
- `NEXT_PUBLIC_AGENT_CHAT_TOKEN` is a legacy browser-exposed token fallback read by `frontend/lib/task-api.ts`.
- `NEXT_WATCH_POLL_INTERVAL_MS` controls Next watch polling in `frontend/next.config.mjs`; the default is `300`.
- `.env.local` exists under `frontend/.env.local` and is ignored by `frontend/.gitignore`; do not read or document its values.

**Build:**
- `frontend/package.json` scripts:
  - `npm run dev` starts Next on port `3001` with polling env vars for Windows/WSL-friendly file watching.
  - `npm run build` runs `next build`.
  - `npm run start` runs `next start -p 3001`.
  - `npm run typecheck` runs `next typegen && tsc --noEmit`.
  - `npm test` runs Node unit tests through `tsx`.
  - `npm run lint` runs `eslint . --max-warnings=0`.
  - `npm run e2e:runtime-contracts` runs `frontend/e2e-playwright/test_runtime_contracts.spec.mjs`.
- `frontend/next.config.mjs` sets `distDir` to `.next-dev` for development and `.next` for production builds.
- `frontend/next.config.mjs` disables dev indicators and configures `watchOptions.pollIntervalMs`.
- `frontend/tsconfig.json` uses `target: ES2017`, `module: esnext`, `moduleResolution: bundler`, `strict: true`, `jsx: preserve`, and includes generated Next types from `.next/types/**/*.ts` and `.next-dev/types/**/*.ts`.
- `frontend/eslint.config.mjs` ignores `.next/**`, `.next-dev*/**`, `node_modules/**`, and `next-env.d.ts`.
- `frontend/.gitignore` excludes `node_modules/`, `.next/`, `.next-dev*/`, `coverage/`, `*.tsbuildinfo`, `next-env.d.ts`, `.env`, and `.env*.local`.

## Platform Requirements

**Development:**
- Work from a consistent path style. `frontend/README.md` directs WSL development through `/mnt/d/AgentProject/MyAgent/frontend` and warns against mixing Windows `D:\AgentProject\MyAgent\frontend` build artifacts with WSL dev-server execution.
- Backend availability is expected at port `8001` when `NEXT_PUBLIC_MYAGENT_API_BASE_URL` is unset or set to `auto`; frontend dev/start uses port `3001`.
- Backend CORS must allow the frontend origin. `frontend/README.md` pairs `NEXT_PUBLIC_MYAGENT_API_BASE_URL` changes with backend `MYAGENT_CORS_ORIGINS` changes.
- Provider secrets stay in the backend environment. `frontend/README.md` states the browser only sends backend-registered model IDs such as `deepseek-v4-flash` and `deepseek-v4-flash-thinking`.

**Production:**
- Production serving uses Next.js through `npm run build` followed by `npm run start` from `frontend/package.json`.
- The default production port is `3001` through `next start -p 3001`.
- No hosting provider, deployment adapter, or CI deployment workflow is detected inside `frontend/`.

---

*Stack analysis: 2026-05-22*
