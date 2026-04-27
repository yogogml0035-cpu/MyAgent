#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_PORT="${BACKEND_PORT:-8001}"
FRONTEND_PORT="${FRONTEND_PORT:-3001}"
BACKEND_HOST="${BACKEND_HOST:-0.0.0.0}"
FRONTEND_HOST="${FRONTEND_HOST:-0.0.0.0}"
STOP_PORTS_FIRST=1

usage() {
  cat <<'EOF'
Usage: scripts/start-dev-wsl.sh [options]

Open two WSL terminals for the MyAgent FastAPI backend and Next.js frontend.

Options:
  --backend-host HOST    Backend bind host. Default: 0.0.0.0
  --backend-port PORT    Backend port. Default: 8001
  --frontend-host HOST   Next.js bind host. Default: 0.0.0.0
  --frontend-port PORT   Frontend port. Default: 3001
  --no-stop              Do not stop existing listeners before starting.
  -h, --help             Show this help.

Environment:
  BACKEND_HOST           Backend bind host override.
  BACKEND_PORT           Backend port override.
  FRONTEND_HOST          Next.js bind host override.
  FRONTEND_PORT          Frontend port override.
EOF
}

die() {
  printf 'Error: %s\n' "$*" >&2
  exit 2
}

require_port() {
  local port="$1"
  [[ "$port" =~ ^[0-9]+$ ]] || die "invalid port: $port"
  ((port > 0 && port <= 65535)) || die "port out of range: $port"
}

is_wsl() {
  [[ -n "${WSL_DISTRO_NAME:-}" ]] && return 0
  grep -qiE '(microsoft|wsl)' /proc/version 2>/dev/null
}

shell_quote() {
  printf '%q' "$1"
}

open_wsl_terminal() {
  local title="$1"
  local service="$2"
  local wsl_args=()
  local launcher

  if [[ -n "${WSL_DISTRO_NAME:-}" ]]; then
    wsl_args=(-d "$WSL_DISTRO_NAME")
  fi

  launcher=$(printf 'MYAGENT_DEV_ROOT=%s BACKEND_HOST=%s BACKEND_PORT=%s FRONTEND_HOST=%s FRONTEND_PORT=%s exec bash %s %s' \
    "$(shell_quote "$ROOT_DIR")" \
    "$(shell_quote "$BACKEND_HOST")" \
    "$(shell_quote "$BACKEND_PORT")" \
    "$(shell_quote "$FRONTEND_HOST")" \
    "$(shell_quote "$FRONTEND_PORT")" \
    "$(shell_quote "$ROOT_DIR/scripts/dev-terminal-runner.sh")" \
    "$(shell_quote "$service")")

  wt.exe -w new new-tab --title "$title" \
    wsl.exe "${wsl_args[@]}" -- bash -lc "$launcher" >/dev/null 2>&1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --backend-host)
      [[ $# -ge 2 ]] || die "--backend-host requires a value"
      BACKEND_HOST="$2"
      shift 2
      ;;
    --backend-port)
      [[ $# -ge 2 ]] || die "--backend-port requires a value"
      BACKEND_PORT="$2"
      shift 2
      ;;
    --frontend-host)
      [[ $# -ge 2 ]] || die "--frontend-host requires a value"
      FRONTEND_HOST="$2"
      shift 2
      ;;
    --frontend-port)
      [[ $# -ge 2 ]] || die "--frontend-port requires a value"
      FRONTEND_PORT="$2"
      shift 2
      ;;
    --no-stop)
      STOP_PORTS_FIRST=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "unknown option: $1"
      ;;
  esac
done

require_port "$BACKEND_PORT"
require_port "$FRONTEND_PORT"

is_wsl || die 'this script must be run from WSL so it can open WSL terminal windows'

command -v uv >/dev/null 2>&1 || die 'uv is required for the backend but was not found in PATH'
command -v npm >/dev/null 2>&1 || die 'npm is required for the frontend but was not found in PATH'
command -v wt.exe >/dev/null 2>&1 || die 'wt.exe is required to open two Windows Terminal windows from WSL'
command -v wsl.exe >/dev/null 2>&1 || die 'wsl.exe is required to open WSL terminal windows'

if [[ "$STOP_PORTS_FIRST" -eq 1 ]]; then
  "$ROOT_DIR/scripts/stop-dev-ports.sh" \
    --backend-port "$BACKEND_PORT" \
    --frontend-port "$FRONTEND_PORT"
fi

open_wsl_terminal "MyAgent Backend :$BACKEND_PORT" "backend"
open_wsl_terminal "MyAgent Frontend :$FRONTEND_PORT" "frontend"

printf '[dev] opened backend terminal:  http://localhost:%s (bind %s)\n' "$BACKEND_PORT" "$BACKEND_HOST"
printf '[dev] opened frontend terminal: http://localhost:%s (bind %s)\n' "$FRONTEND_PORT" "$FRONTEND_HOST"
printf '[dev] stop each service with Ctrl+C in its terminal, or run ./scripts/stop-dev-ports.sh\n'
