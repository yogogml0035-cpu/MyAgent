# MyAgent Frontend

Next.js app-router frontend for the local MyAgent application.

## Setup

Use the WSL path consistently when developing from WSL:

```bash
cd /mnt/d/AgentProject/MyAgent/frontend
```

Do not install dependencies or build `.next` from Windows `D:\AgentProject\MyAgent\frontend`
and then run the dev server from WSL `/mnt/d/AgentProject/MyAgent/frontend`. Mixing the two
path styles can make Next.js generate a React Client Manifest with Windows paths while the
server resolves WSL paths.

If that has happened, clean and reinstall from WSL:

```bash
rm -rf .next node_modules
npm ci
npm run dev
```

The frontend reads `NEXT_PUBLIC_MYAGENT_API_BASE_URL`. When it is unset or set to `auto`,
the browser derives the backend URL from the current page host as
`http://<hostname>:8001`, so both `http://localhost:3001` and a LAN URL such as
`http://10.11.148.97:3001` target the matching backend host. Explicit backend URLs such
as `http://localhost:8001` are still supported. If the backend sets
`MYAGENT_ACCESS_TOKEN`, set the same value as `NEXT_PUBLIC_MYAGENT_TOKEN` for local
development. When opening the UI through a LAN address, include the frontend origin such
as `http://10.11.148.97:3001` in backend `MYAGENT_CORS_ORIGINS`.

The legacy `NEXT_PUBLIC_API_BASE_URL` and `NEXT_PUBLIC_AGENT_CHAT_TOKEN` names are still
accepted for migrated local setups.

Expected backend endpoints:

- `POST /api/tasks` creates a task.
- `POST /api/tasks/{task_id}/files` uploads Markdown files as multipart form data.
- `POST /api/tasks/{task_id}/messages` sends a user message.
- `POST /api/tasks/{task_id}/cancel` stops a task.
- `GET /api/tasks/{task_id}` fetches task state, messages, logs, and artifacts.

The first exposed model option is `deepseek-reasoner`. Provider secrets must stay in the backend `.env`; this frontend only sends safe model IDs.
