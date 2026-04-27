# MyAgent Frontend

Next.js app-router frontend for the local MyAgent application.

## Setup

```bash
npm install
npm run dev
```

The frontend reads `NEXT_PUBLIC_MYAGENT_API_BASE_URL` and defaults to `http://localhost:8000`
when it is not set. If the backend sets `MYAGENT_ACCESS_TOKEN`, set the same value as
`NEXT_PUBLIC_MYAGENT_TOKEN` for local development.

The legacy `NEXT_PUBLIC_API_BASE_URL` and `NEXT_PUBLIC_AGENT_CHAT_TOKEN` names are still
accepted for migrated local setups.

Expected backend endpoints:

- `POST /api/tasks` creates a task.
- `POST /api/tasks/{task_id}/files` uploads Markdown files as multipart form data.
- `POST /api/tasks/{task_id}/messages` sends a user message.
- `POST /api/tasks/{task_id}/cancel` stops a task.
- `GET /api/tasks/{task_id}` fetches task state, messages, logs, and artifacts.

The first exposed model option is `deepseek-reasoner`. Provider secrets must stay in the backend `.env`; this frontend only sends safe model IDs.
