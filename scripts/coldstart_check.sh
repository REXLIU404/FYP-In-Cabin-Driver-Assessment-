#!/usr/bin/env bash
# ST-COLDSTART-01 (sprint plan v3, W5 / G-W5-A): from a fresh checkout to a green gate run and a
# serving backend, borrowing nothing from a developer's environment except
#   - the three trained model files, which are not in git (linked read-only from COLDSTART_MODEL_ROOT),
#   - the pip / npm download caches and the Playwright browser cache (machine-wide, not the project).
#
#   scripts/coldstart_check.sh [COMMIT]          # default: HEAD of this checkout
#
# Steps, each timed and logged: clone + checkout -> python venv + pip install -r
# backend/requirements.lock.txt -> npm ci -> link the models -> scripts/run_gates.py with
# DRA_REQUIRE_MODELS=1 (build, full pytest incl. the browser tests, vitest, tsc, eslint) -> start
# uvicorn from the clean checkout on a free port with a throw-away database and check /api/health,
# /api/models (hashes) and / (the built dashboard).
#
# Env: PYTHON (interpreter for the venv, default python3), COLDSTART_MODEL_ROOT (default
# <this checkout>/ml/outputs), COLDSTART_OUT (default docs/evidence/<UTC date>/coldstart).
# The scratch checkout is left under $TMPDIR for inspection; nothing in this checkout is changed
# except the evidence directory.
set -uo pipefail

SRC="$(cd "$(dirname "$0")/.." && pwd)"
COMMIT="$(git -C "$SRC" rev-parse "${1:-HEAD}")"
PYTHON="${PYTHON:-python3}"
MODELS="${COLDSTART_MODEL_ROOT:-$SRC/ml/outputs}"
OUT="${COLDSTART_OUT:-$SRC/docs/evidence/$(date -u +%F)/coldstart}"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/coldstart.XXXXXX")"
REPO="$WORK/repo"
LOG="$OUT/coldstart.log"
mkdir -p "$OUT"
: >"$LOG"
STEPS=()

note() { echo "$*" | tee -a "$LOG"; }
step() {  # step NAME CMD... : run, time, log; stop the script on failure
  local name="$1"; shift
  local t0=$SECONDS
  note ""
  note "== $name: $*"
  "$@" >>"$LOG" 2>&1
  local rc=$?
  STEPS+=("| $name | $([ $rc -eq 0 ] && echo PASS || echo FAIL) | $rc | $((SECONDS - t0)) |")
  note "-> exit $rc in $((SECONDS - t0)) s"
  if [ $rc -ne 0 ]; then summary FAIL; exit 1; fi
}
summary() {
  {
    echo "# ST-COLDSTART-01 - $1"
    echo
    echo "- Commit: \`$COMMIT\`"
    echo "- Scratch checkout: \`$REPO\`"
    echo "- Python: \`$("$PYTHON" --version 2>&1)\` ($PYTHON); node \`$(node --version)\`; npm \`$(npm --version)\`"
    echo "- Models linked from: \`$MODELS\`"
    echo
    echo "| Step | Result | Exit | Seconds |"
    echo "|---|---|---|---|"
    printf '%s\n' "${STEPS[@]}"
    echo
    echo "Full output: \`coldstart.log\`; gate logs: \`gates/\`."
  } >"$OUT/SUMMARY.md"
  note ""
  note "ST-COLDSTART-01: $1 (summary in $OUT/SUMMARY.md)"
}

link_models() {
  local f
  for f in vision/mobilenetv3_large_vision.onnx vision/mobilenetv3_large_vision.pt telemetry/xgb_telemetry.json; do
    [ -f "$MODELS/$f" ] || { echo "missing model file $MODELS/$f"; return 1; }
    mkdir -p "$REPO/ml/outputs/$(dirname "$f")"
    ln -s "$MODELS/$f" "$REPO/ml/outputs/$f"
    shasum -a 256 "$REPO/ml/outputs/$f"
  done
}
SERVE_PID=""
stop_server() { if [ -n "$SERVE_PID" ]; then kill "$SERVE_PID" 2>/dev/null; wait "$SERVE_PID" 2>/dev/null; SERVE_PID=""; fi; }
trap stop_server EXIT

serve_check() {
  local port db ok=1
  port="$("$REPO/.venv/bin/python" -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1])')"
  db="$WORK/serve.db"
  # exec: the background job IS uvicorn, so $! is its PID and stop_server really stops it (without
  # exec, $! is the subshell's PID and killing it leaves uvicorn running under macOS bash 3.2).
  ( cd "$WORK" && exec env -u DRA_MODEL_ROOT DRA_DATABASE_URL="sqlite:///$db" PYTHONDONTWRITEBYTECODE=1 \
      "$REPO/.venv/bin/python" -m uvicorn app.main:app --app-dir "$REPO/backend" --host 127.0.0.1 --port "$port" ) >"$WORK/serve.log" 2>&1 &
  SERVE_PID=$!
  for _ in $(seq 1 60); do curl -s -m 1 "http://127.0.0.1:$port/api/health" >/dev/null 2>&1 && break; sleep 0.5; done
  echo "health: $(curl -s -m 5 -o /dev/null -w '%{http_code}' "http://127.0.0.1:$port/api/health")"
  echo "models: $(curl -s -m 10 "http://127.0.0.1:$port/api/models")"
  echo "dashboard: $(curl -s -m 5 -o /dev/null -w '%{http_code}' "http://127.0.0.1:$port/")"
  [ "$(curl -s -m 5 -o /dev/null -w '%{http_code}' "http://127.0.0.1:$port/api/health")" = 200 ] || ok=0
  curl -s -m 10 "http://127.0.0.1:$port/api/models" | grep -q b3a42e8dd4553355b1fd7d9e7fe3d28e318decb894e76eb029489b7ff2e90bcf || ok=0
  curl -s -m 10 "http://127.0.0.1:$port/api/models" | grep -q 9802cb06ca98f0c1befaf851fa7668cfec70e005cf8bb3884e49d7d45d7aec07 || ok=0
  [ "$(curl -s -m 5 -o /dev/null -w '%{http_code}' "http://127.0.0.1:$port/")" = 200 ] || ok=0
  stop_server
  if ps -axo command= | grep -F -- "--app-dir $REPO/backend" | grep -v grep >/dev/null; then
    echo "a server from this checkout is still running after stop"; ok=0
  fi
  [ "$ok" = 1 ]
}

note "ST-COLDSTART-01 commit $COMMIT -> $REPO"
step "clone" bash -c "git clone --quiet --no-checkout '$SRC' '$REPO' && git -C '$REPO' checkout --quiet '$COMMIT' && git -C '$REPO' log --oneline -1"
step "python venv" "$PYTHON" -m venv "$REPO/.venv"
step "pip install (requirements.lock.txt)" "$REPO/.venv/bin/python" -m pip install --disable-pip-version-check -q -r "$REPO/backend/requirements.lock.txt"
step "pip freeze" "$REPO/.venv/bin/python" -m pip freeze
step "npm ci" bash -c "cd '$REPO' && npm ci --prefer-offline --no-audit --no-fund"
step "link models (read-only)" link_models
step "gates (run_gates.py, DRA_REQUIRE_MODELS=1)" env DRA_REQUIRE_MODELS=1 PYTHONDONTWRITEBYTECODE=1 "$REPO/.venv/bin/python" "$REPO/scripts/run_gates.py" --out "$OUT/gates"
step "serve from the clean checkout" serve_check
summary PASS
