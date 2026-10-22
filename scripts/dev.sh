#!/usr/bin/env bash
# Development: the backend and the vite dev server with one command (`npm run dev:all`).
#
#   1. If this project's backend already answers on the port (it marks every response with
#      `X-DRA-Backend: 1`), it is reused and left running afterwards.
#   2. Otherwise the port must be free: the backend is started from backend/ (its own database,
#      backend/driver_risk.db, unless DRA_DATABASE_URL says otherwise), logged to
#      backend/logs/uvicorn-dev.log, and the script waits until /api/health answers.
#   3. Then vite runs in the foreground with /api forwarded to that backend.
#
# One Ctrl-C stops vite and, if this script started it, the backend.
#
# DRA_DEV_BACKEND_PORT  backend port (default 8000)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${DRA_DEV_BACKEND_PORT:-8000}"
URL="http://127.0.0.1:${PORT}"
PYTHON="$ROOT/.venv/bin/python"
LOG="$ROOT/backend/logs/uvicorn-dev.log"
started=""

ours() { curl -s -m 2 -D - -o /dev/null "$URL/api/health" 2>/dev/null | tr -d '\r' | grep -qi '^x-dra-backend: 1$'; }
busy() { lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; }
stop_backend() {
  if [ -n "$started" ] && kill -0 "$started" 2>/dev/null; then
    kill "$started" 2>/dev/null || true
    wait "$started" 2>/dev/null || true
    echo "backend: stopped (pid $started)"
  fi
  started=""
}
trap stop_backend EXIT
trap 'exit 130' INT TERM

if ours; then
  echo "backend: already running on $URL, reused (it keeps running after this script)"
elif busy; then
  echo "dev.sh: port $PORT is taken by something that is not this backend; free it or set DRA_DEV_BACKEND_PORT" >&2
  exit 1
else
  [ -x "$PYTHON" ] || { echo "dev.sh: $PYTHON not found (create the .venv first)" >&2; exit 1; }
  mkdir -p "$ROOT/backend/logs"
  (cd "$ROOT/backend" && PYTHONDONTWRITEBYTECODE=1 exec "$PYTHON" -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT") >>"$LOG" 2>&1 &
  started=$!
  for _ in $(seq 1 60); do
    ours && break
    if ! kill -0 "$started" 2>/dev/null; then
      started=""
      echo "dev.sh: the backend exited during start-up; last lines of $LOG:" >&2
      tail -n 20 "$LOG" >&2
      exit 1
    fi
    sleep 0.5
  done
  ours || { echo "dev.sh: the backend did not answer $URL/api/health within 30 s; see $LOG" >&2; exit 1; }
  echo "backend: started on $URL (pid $started, log backend/logs/uvicorn-dev.log)"
fi

cd "$ROOT"
DRA_DEV_BACKEND_URL="$URL" "$ROOT/node_modules/.bin/vite" --host 127.0.0.1
