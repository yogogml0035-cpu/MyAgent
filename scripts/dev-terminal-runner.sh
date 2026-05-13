#!/usr/bin/env bash
set -Eeuo pipefail

SERVICE="${1:-}"
ROOT_DIR="${MYAGENT_DEV_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-8001}"
FRONTEND_HOST="${FRONTEND_HOST:-127.0.0.1}"
FRONTEND_PORT="${FRONTEND_PORT:-3001}"

enable_polling_watchers() {
  local force_polling="${MYAGENT_DEV_FORCE_POLLING:-1}"
  case "$force_polling" in
    0|false|False|FALSE|no|No|NO)
      return
      ;;
  esac

  export WATCHFILES_FORCE_POLLING="${WATCHFILES_FORCE_POLLING:-true}"
  export WATCHFILES_POLL_DELAY_MS="${WATCHFILES_POLL_DELAY_MS:-300}"
  export WATCHPACK_POLLING="${WATCHPACK_POLLING:-true}"
  export CHOKIDAR_USEPOLLING="${CHOKIDAR_USEPOLLING:-true}"
  export CHOKIDAR_INTERVAL="${CHOKIDAR_INTERVAL:-300}"
}

finish() {
  local status=$?
  trap - EXIT INT TERM

  printf '\n[dev] %s exited with status %s.\n' "${SERVICE:-service}" "$status"
  if [[ -t 0 ]]; then
    read -r -p 'Press Enter to close this terminal...' || true
  fi

  exit "$status"
}

trap finish EXIT

case "$SERVICE" in
  backend)
    cd "$ROOT_DIR/backend"
    printf '[dev] starting backend on http://localhost:%s (bind %s)\n\n' "$BACKEND_PORT" "$BACKEND_HOST"
    enable_polling_watchers
    printf '[dev] backend reload polling: WATCHFILES_FORCE_POLLING=%s WATCHFILES_POLL_DELAY_MS=%s\n\n' \
      "${WATCHFILES_FORCE_POLLING:-false}" "${WATCHFILES_POLL_DELAY_MS:-default}"
    uv run uvicorn app.main:app --reload --reload-delay 0.25 --host "$BACKEND_HOST" --port "$BACKEND_PORT"
    ;;
  frontend)
    cd "$ROOT_DIR/frontend"
    printf '[dev] starting frontend on http://localhost:%s (bind %s)\n\n' "$FRONTEND_PORT" "$FRONTEND_HOST"

    enable_polling_watchers
    export NEXT_DIST_DIR="${NEXT_DIST_DIR:-.next-dev}"
    printf '[dev] frontend hot reload polling: WATCHPACK_POLLING=%s CHOKIDAR_USEPOLLING=%s CHOKIDAR_INTERVAL=%s\n\n' \
      "${WATCHPACK_POLLING:-false}" "${CHOKIDAR_USEPOLLING:-false}" "${CHOKIDAR_INTERVAL:-default}"
    if [[ "$FRONTEND_PORT" == "3001" && -z "$FRONTEND_HOST" ]]; then
      npm run dev
    else
      if [[ ! -x node_modules/.bin/next ]]; then
        printf 'Error: frontend/node_modules/.bin/next not found. Run "cd frontend && npm ci" first.\n' >&2
        exit 127
      fi

      args=(dev -p "$FRONTEND_PORT")
      if [[ -n "$FRONTEND_HOST" ]]; then
        args+=(-H "$FRONTEND_HOST")
      fi
      ./node_modules/.bin/next "${args[@]}"
    fi
    ;;
  *)
    printf 'Error: unknown service "%s"; expected backend or frontend.\n' "$SERVICE" >&2
    exit 2
    ;;
esac
