#!/usr/bin/env bash
set -Eeuo pipefail

BACKEND_PORT="${BACKEND_PORT:-8001}"
FRONTEND_PORT="${FRONTEND_PORT:-3001}"
DRY_RUN=0
QUIET=0
EXTRA_PORTS=()

usage() {
  cat <<'EOF'
Usage: scripts/stop-dev-ports.sh [options]

Stop every WSL process listening on the MyAgent backend/frontend ports.

Options:
  --backend-port PORT    Backend port to stop. Default: 8001
  --frontend-port PORT   Frontend port to stop. Default: 3001
  --port PORT            Additional port to stop. Can be repeated.
  --dry-run              Show matching processes without killing them.
  -q, --quiet            Print only errors.
  -h, --help             Show this help.

Environment:
  BACKEND_PORT           Backend port override.
  FRONTEND_PORT          Frontend port override.
EOF
}

log() {
  if [[ "$QUIET" -eq 0 ]]; then
    printf '%s\n' "$*"
  fi
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

collect_pids_for_port() {
  local port="$1"

  {
    if command -v lsof >/dev/null 2>&1; then
      lsof -nP -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true
      printf '\n'
    fi

    if command -v fuser >/dev/null 2>&1; then
      fuser -n tcp "$port" 2>/dev/null | tr ' ' '\n' || true
      printf '\n'
    fi

    if command -v ss >/dev/null 2>&1; then
      ss -H -ltnp "sport = :$port" 2>/dev/null \
        | grep -oE 'pid=[0-9]+' \
        | cut -d= -f2 || true
      printf '\n'
    fi
  } | awk '/^[0-9]+$/ { print }' | sort -u
}

describe_pid() {
  local pid="$1"
  ps -p "$pid" -o pid=,comm=,args= 2>/dev/null | sed 's/^/  /' || true
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --backend-port)
      [[ $# -ge 2 ]] || die "--backend-port requires a value"
      BACKEND_PORT="$2"
      shift 2
      ;;
    --frontend-port)
      [[ $# -ge 2 ]] || die "--frontend-port requires a value"
      FRONTEND_PORT="$2"
      shift 2
      ;;
    --port)
      [[ $# -ge 2 ]] || die "--port requires a value"
      EXTRA_PORTS+=("$2")
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    -q|--quiet)
      QUIET=1
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

PORTS=("$BACKEND_PORT" "$FRONTEND_PORT" "${EXTRA_PORTS[@]}")
for port in "${PORTS[@]}"; do
  require_port "$port"
done

FOUND=0
STOPPED_PORTS=()
for port in "${PORTS[@]}"; do
  mapfile -t pids < <(collect_pids_for_port "$port")

  if [[ "${#pids[@]}" -eq 0 ]]; then
    log "[port:$port] no WSL listener found"
    continue
  fi

  FOUND=1
  STOPPED_PORTS+=("$port")
  log "[port:$port] matching listener(s):"
  for pid in "${pids[@]}"; do
    describe_pid "$pid"
  done

  if [[ "$DRY_RUN" -eq 1 ]]; then
    continue
  fi

  if ! kill -TERM "${pids[@]}" 2>/dev/null; then
    printf '[port:%s] failed to send SIGTERM to one or more processes; try running with sudo if they are not yours\n' "$port" >&2
  fi
done

if [[ "$DRY_RUN" -eq 1 || "$FOUND" -eq 0 ]]; then
  exit 0
fi

sleep 1

EXIT_CODE=0
for port in "${STOPPED_PORTS[@]}"; do
  mapfile -t remaining < <(collect_pids_for_port "$port")
  if [[ "${#remaining[@]}" -eq 0 ]]; then
    log "[port:$port] stopped"
    continue
  fi

  log "[port:$port] still listening after SIGTERM, sending SIGKILL:"
  for pid in "${remaining[@]}"; do
    describe_pid "$pid"
  done

  if ! kill -KILL "${remaining[@]}" 2>/dev/null; then
    printf '[port:%s] failed to send SIGKILL to one or more processes\n' "$port" >&2
    EXIT_CODE=1
  fi
done

sleep 0.2

for port in "${STOPPED_PORTS[@]}"; do
  mapfile -t remaining < <(collect_pids_for_port "$port")
  if [[ "${#remaining[@]}" -gt 0 ]]; then
    printf '[port:%s] still occupied after stop attempt\n' "$port" >&2
    EXIT_CODE=1
  fi
done

exit "$EXIT_CODE"
