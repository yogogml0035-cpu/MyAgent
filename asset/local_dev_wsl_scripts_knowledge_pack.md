# Local Dev WSL Scripts Knowledge Pack

## Background And Scope

This package covers the WSL local development helper scripts for MyAgent. It applies when changing repository-level scripts that stop occupied frontend/backend ports or open WSL terminals for the FastAPI backend and Next.js frontend.

## Business Rules

- The default backend development port is `8001`.
- The default frontend development port is `3001`.
- `scripts/stop-dev-ports.sh` stops WSL processes listening on the configured backend and frontend ports.
- `scripts/start-dev-wsl.sh` runs from the repository root, stops the configured ports first, then opens two Windows Terminal WSL windows: one for the backend and one for the frontend.
- The backend starts with `uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8001` by default so both localhost and the machine IP can reach it.
- The frontend starts on host `0.0.0.0` and port `3001` by default so both localhost and the machine IP can reach it.
- The frontend helper uses `frontend/node_modules/.bin/next dev -p <port> -H <host>` when a host is configured; the `frontend/package.json` `dev` script remains the direct manual command for localhost-focused development.
- Port and host overrides must be explicit through script arguments or environment variables.
- If the backend port changes, `frontend/.env.local` must point `NEXT_PUBLIC_MYAGENT_API_BASE_URL` at the matching backend URL, or the frontend resolver and tests must be updated away from the default `8001`.
- Provider keys and task access tokens remain in the existing backend/frontend env files; startup scripts must not embed secrets.
- The startup script depends on WSL interop access to `wt.exe` and `wsl.exe`.
- `start-dev-wsl.sh` should pass only a short `bash -lc` launcher into Windows Terminal. Do not include semicolon-separated shell bodies in `wt.exe` arguments because Windows Terminal treats semicolons as command separators.

## Input And Output Examples

Start both services from WSL:

```bash
cd /mnt/d/AgentProject/MyAgent
./scripts/start-dev-wsl.sh
```

Stop default development ports:

```bash
cd /mnt/d/AgentProject/MyAgent
./scripts/stop-dev-ports.sh
```

Use non-default ports:

```bash
BACKEND_PORT=8002 FRONTEND_PORT=3002 ./scripts/start-dev-wsl.sh
./scripts/stop-dev-ports.sh --backend-port 8002 --frontend-port 3002
```

## Boundary Conditions

- The scripts are Bash scripts intended for WSL. `start-dev-wsl.sh` must run inside WSL because it opens Windows Terminal windows that launch WSL commands.
- `stop-dev-ports.sh` only targets listener processes visible inside the WSL environment through `lsof`, `fuser`, or `ss`.
- If a Windows-side process owns a port, close it from Windows instead of assuming the WSL script can terminate it.
- `start-dev-wsl.sh --no-stop` skips the pre-start port cleanup and lets service startup fail naturally if ports are occupied.
- Custom frontend hosts or ports use `frontend/node_modules/.bin/next`; if dependencies are missing, run `cd frontend && npm ci`.
- Ctrl+C should be sent in the individual backend or frontend terminal to stop that service. `scripts/stop-dev-ports.sh` can stop both by port.
- Under WSL NAT, binding inside WSL to `0.0.0.0` is not always enough for Windows LAN-IP URLs such as `10.11.148.97:3001`; Windows may need administrator `netsh interface portproxy` and firewall rules that forward ports `3001` and `8001` to the current WSL IP.

## Known Pitfalls

- Do not run parallel `next dev` processes in the same `frontend/` directory because they share `.next` output.
- Do not bind backend to non-loopback hosts without reviewing `MYAGENT_ACCESS_TOKEN` and CORS settings.
- With the default LAN-friendly bind host, local setups that use an IP URL must keep `MYAGENT_ACCESS_TOKEN`, `NEXT_PUBLIC_MYAGENT_TOKEN`, and exact `MYAGENT_CORS_ORIGINS` in sync.
- Windows portproxy rules can go stale when the WSL IP changes after restart; rerun the administrator PowerShell portproxy setup if localhost works but the Windows LAN IP stops connecting.
- Do not add secrets, access tokens, or private local paths to these scripts or docs.
- Do not change the frontend package script's default `3001` behavior without updating the startup script, README, and this package together.
- Do not regress `start-dev-wsl.sh` back to one-terminal background concurrency; the expected local path is two visible WSL terminals.

## Related Code Paths

- `scripts/start-dev-wsl.sh`
- `scripts/dev-terminal-runner.sh`
- `scripts/stop-dev-ports.sh`
- `backend/app/main.py`
- `frontend/package.json`
- `README.md`

## Related Test Paths

- `backend/tests/test_workflow.py`
- `frontend/tests/task-state.test.ts`

## Verification Commands

```bash
bash -n scripts/start-dev-wsl.sh
bash -n scripts/stop-dev-ports.sh
scripts/start-dev-wsl.sh --help
scripts/stop-dev-ports.sh --dry-run
git diff --check
```

## Regression Risks

- Leaving old dev processes alive and causing backend or frontend startup to bind the wrong port or fail.
- Accidentally killing unrelated non-development ports if defaults or overrides are parsed incorrectly.
- Starting frontend and backend with mismatched ports relative to frontend API configuration.
- Weakening local-first access boundaries when exposing backend beyond loopback.
