# MyAgent Frontend

Next.js app-router frontend for the local MyAgent application.

## Setup

Use the WSL path consistently when developing from WSL:

```bash
cd /mnt/d/AgentProject/MyAgent/frontend
```

Do not install dependencies or build Next output from Windows `D:\AgentProject\MyAgent\frontend`
and then run the dev server from WSL `/mnt/d/AgentProject/MyAgent/frontend`. Mixing the two
path styles can make Next.js generate a React Client Manifest with Windows paths while the
server resolves WSL paths. The dev server and production builds both write `.next`.
Keep both directories environment-local and do not reuse them across Windows and WSL.

Type checking runs `next typegen && tsc --noEmit`. The generated `next-env.d.ts` file is
ignored and should not be committed.

If that has happened, clean and reinstall from WSL:

```bash
rm -rf .next node_modules
npm ci
npm run dev
```

The frontend reads `NEXT_PUBLIC_MYAGENT_API_BASE_URL`. When it is unset or set to `auto`,
the browser derives the backend URL from the current page host as
`http://<hostname>:8001`, so `http://localhost:3001` maps to `http://localhost:8001`
and `http://127.0.0.1:3001` maps to `http://127.0.0.1:8001`. Explicit backend URLs such
as `http://localhost:8001` are still supported. If you change the frontend origin or
backend port, update `NEXT_PUBLIC_MYAGENT_API_BASE_URL` and backend
`MYAGENT_CORS_ORIGINS` accordingly.

The legacy `NEXT_PUBLIC_API_BASE_URL` name is still accepted for migrated local setups.

## E2E Acceptance

For every bug fix, feature, or other behavior change, run browser-side E2E against the live app and save screenshot evidence under `frontend/e2e-playwright/`.

- Keep `frontend/e2e-playwright/README.md` in place as the directory comment.
- Create subdirectories per scenario or task when storing screenshots.
- Do not store screenshots that expose customer-sensitive documents, tokens, or secrets.

Expected backend endpoints:

- `POST /api/tasks` creates a task.
- `POST /api/tasks/{task_id}/files` uploads Markdown or JSON files as multipart form data.
- `POST /api/tasks/{task_id}/messages` sends a user message.
- `POST /api/tasks/{task_id}/cancel` stops a task.
- `GET /api/tasks/{task_id}` fetches task state, messages, logs, and artifacts.

The frontend exposes a model picker button, but the menu is intentionally restricted to the two DeepSeek V4 Flash options: `deepseek-v4-flash` and `deepseek-v4-flash-thinking`. Provider secrets must stay in the backend `.env`; the browser only sends these safe backend-registered model IDs.
