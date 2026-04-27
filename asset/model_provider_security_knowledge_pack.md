# Model Provider Security Knowledge Pack

## Background And Scope

This package covers MyAgent environment variables, model-provider secrets, browser-visible frontend configuration, access-token behavior, CORS/local-first boundaries, and request-size safety limits.

It applies when editing:

- `backend/.env.example`
- `frontend/.env.example`
- `.env.example`
- `backend/app/settings.py`
- `backend/app/main.py`
- `backend/app/model_provider.py`
- frontend code that sends API base URLs, model IDs, or access tokens

## Business Rules

- Provider keys such as `DEEPSEEK_API_KEY` and `TAVILY_API_KEY` are backend-only.
- Frontend `NEXT_PUBLIC_*` values are browser-visible and must not contain provider secrets, customer source text, or private credentials.
- `MYAGENT_ACCESS_TOKEN` is optional for local loopback use, but required when task APIs are exposed beyond loopback.
- If `MYAGENT_ACCESS_TOKEN` is set, task APIs accept either `Authorization: Bearer <token>` or `X-MyAgent-Token`.
- The frontend sends `NEXT_PUBLIC_MYAGENT_TOKEN` as `X-MyAgent-Token` for local protected task access.
- Backend CORS is controlled by comma-separated `MYAGENT_CORS_ORIGINS`, defaulting to `http://localhost:3001,http://127.0.0.1:3001`.
- LAN frontend access requires an exact backend CORS origin such as `http://10.11.148.97:3001`. The frontend API base URL should usually be `auto`, which derives `http://<current page hostname>:8001`; explicit URLs such as `http://10.11.148.97:8001` remain supported.
- New configuration should use `MYAGENT_*`; legacy `AGENT_CHAT_*` names remain compatibility fallbacks.
- The backend is single-process oriented because task runners and JSON task storage are in-process/local.

## Input And Output Examples

Backend `.env` example:

```env
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
TAVILY_API_KEY=
MYAGENT_ACCESS_TOKEN=
MYAGENT_CORS_ORIGINS=http://localhost:3001,http://127.0.0.1:3001
MYAGENT_TASK_ROOT=
MYAGENT_MAX_UPLOAD_FILES=10
MYAGENT_MAX_UPLOAD_FILE_BYTES=10485760
MYAGENT_MAX_UPLOAD_REQUEST_BYTES=105906176
MYAGENT_MAX_JSON_REQUEST_BYTES=65536
DEEPSEEK_TIMEOUT_SECONDS=15
```

Frontend `.env.local` example:

```env
NEXT_PUBLIC_MYAGENT_API_BASE_URL=auto
NEXT_PUBLIC_MYAGENT_TOKEN=
```

LAN frontend `.env.local` example for host `10.11.148.97`:

```env
NEXT_PUBLIC_MYAGENT_API_BASE_URL=auto
NEXT_PUBLIC_MYAGENT_TOKEN=<same value as MYAGENT_ACCESS_TOKEN>
```

Protected task request example:

```http
Authorization: Bearer <token>
```

or:

```http
X-MyAgent-Token: <token>
```

## Boundary Conditions

- Task APIs are loopback-only when no access token is configured.
- Non-loopback task access without a configured token returns `403`.
- Missing or wrong token when a token is configured returns `401`.
- Browser origins not listed in `MYAGENT_CORS_ORIGINS` fail CORS preflight and are blocked by the browser.
- `MYAGENT_CORS_ORIGINS` entries must match the browser origin by scheme, host, and port; path components are not origins.
- `NEXT_PUBLIC_MYAGENT_API_BASE_URL=auto` follows the browser page hostname and assumes backend port `8001`; non-default backend ports require an explicit API base URL or a frontend resolver change.
- Upload request limits and JSON body limits are enforced before task mutation.
- Multi-worker deployment is blocked by `WEB_CONCURRENCY`, `UVICORN_WORKERS`, and `GUNICORN_WORKERS` checks.
- Root `.env.example` is a reference file; the current runtime loads `backend/.env` for backend settings and frontend env values through the frontend toolchain.

## Known Pitfalls

- Never copy `DEEPSEEK_API_KEY` or `TAVILY_API_KEY` into `NEXT_PUBLIC_*`.
- Do not assume root `.env` is automatically loaded by the backend.
- Do not expose the backend on LAN or the internet without setting `MYAGENT_ACCESS_TOKEN`.
- Do not use wildcard CORS with browser-visible task tokens; list the expected frontend origins explicitly.
- Do not configure multiple backend workers without redesigning task ownership and storage.
- Keep `.env.example` files empty of real secrets, customer data, and private local paths.

## Related Code Paths

- `backend/app/settings.py`
- `backend/app/main.py`
- `backend/app/model_provider.py`
- `frontend/app/page.tsx`
- `.env.example`
- `backend/.env.example`
- `frontend/.env.example`

## Related Test Paths

- `backend/tests/test_workflow.py`
- `frontend/tests/task-state.test.ts`

## Verification Commands

```bash
git diff --check
cd backend && uv run pytest
cd frontend && npm test
```

For documentation-only env example edits, `git diff --check` is the minimum check.

## Regression Risks

- Leaking provider credentials into browser-visible frontend bundles.
- Breaking local development by documenting an env file path the runtime does not read.
- Weakening task API access boundaries for non-loopback clients.
- Reintroducing multi-worker deployment assumptions that split in-process task state.
