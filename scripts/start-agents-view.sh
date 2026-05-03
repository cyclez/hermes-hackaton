#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

RUN_COUNT=""

usage() {
  cat <<'EOF'
Usage:
  ./scripts/start-agents-view.sh
  ./scripts/start-agents-view.sh --run <count>

Options:
  --run <count>   Automatically restart after training completes, until <count>
                  total games have finished learning. Leaves server and UI running.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --run)
      if [ "$#" -lt 2 ]; then
        echo "[start-agents-view] ERROR: --run requires a positive integer."
        usage
        exit 1
      fi
      RUN_COUNT="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "[start-agents-view] ERROR: unknown argument: $1"
      usage
      exit 1
      ;;
  esac
done

if [ -n "$RUN_COUNT" ] && ! [[ "$RUN_COUNT" =~ ^[1-9][0-9]*$ ]]; then
  echo "[start-agents-view] ERROR: --run must be a positive integer."
  exit 1
fi

# Load env files (local overrides example)
if [ -f .env.example ]; then set -a; source .env.example; set +a; fi
if [ -f .env ]; then set -a; source .env; set +a; fi
if [ -f .env.local ]; then set -a; source .env.local; set +a; fi

UVICORN="$REPO_ROOT/.venv/bin/uvicorn"
if [ ! -x "$UVICORN" ]; then
  echo "[start-agents-view] ERROR: $UVICORN not found. Run: uv pip install -e . first."
  exit 1
fi

PYTHON_BIN="$REPO_ROOT/.venv/bin/python"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="$(command -v python3 || true)"
fi
if [ -z "$PYTHON_BIN" ]; then
  echo "[start-agents-view] ERROR: no Python interpreter found for local API polling."
  exit 1
fi

wait_for_backend() {
  local attempts=0
  until curl -fsS http://localhost:8000/api/health >/dev/null 2>&1; do
    attempts=$((attempts + 1))
    if [ "$attempts" -ge 60 ]; then
      echo "[start-agents-view] ERROR: backend did not become ready on :8000."
      return 1
    fi
    sleep 1
  done
}

read_state_fields() {
  "$PYTHON_BIN" -c '
import json, sys
data = json.load(sys.stdin)
training = data.get("training") or {}
values = [
    str(data.get("game_id") or ""),
    "1" if data.get("is_finished") else "0",
    str(training.get("status") or ""),
    str(training.get("error") or ""),
]
print("\t".join(v.replace("\t", " ").replace("\n", " ") for v in values))
'
}

run_restart_loop() {
  local target_count="$1"
  local completed_runs=0
  local last_completed_game=""
  local game_id=""
  local is_finished=""
  local training_status=""
  local training_error=""

  echo "[start-agents-view] Auto-restart loop armed for $target_count runs."
  wait_for_backend || return 1

  while kill -0 "$SERVER_PID" >/dev/null 2>&1 && kill -0 "$UI_PID" >/dev/null 2>&1; do
    local state_json=""
    state_json="$(curl -fsS http://localhost:8000/api/state 2>/dev/null || true)"
    if [ -z "$state_json" ]; then
      sleep 2
      continue
    fi

    IFS=$'\t' read -r game_id is_finished training_status training_error < <(
      printf '%s' "$state_json" | read_state_fields
    )

    if [ "$is_finished" = "1" ]; then
      if [ "$training_status" = "failed" ]; then
        echo "[start-agents-view] Auto-run halted: training failed for game $game_id."
        if [ -n "$training_error" ]; then
          echo "[start-agents-view] Training error: $training_error"
        fi
        return 1
      fi

      if [ "$training_status" = "completed" ] && [ "$game_id" != "$last_completed_game" ]; then
        completed_runs=$((completed_runs + 1))
        last_completed_game="$game_id"
        echo "[start-agents-view] Completed run $completed_runs/$target_count (game $game_id)."

        if [ "$completed_runs" -lt "$target_count" ]; then
          echo "[start-agents-view] Restarting next game…"
          if ! curl -fsS -X POST http://localhost:8000/api/server/restart >/dev/null 2>&1; then
            echo "[start-agents-view] Auto-run halted: restart request failed."
            return 1
          fi
        else
          echo "[start-agents-view] Run target reached. Leaving server and UI running."
          return 0
        fi
      fi
    fi

    sleep 3
  done

  return 0
}

echo "[start-agents-view] Launching OptimiCity with agent-focused backend logs…"

PYTHONUNBUFFERED=1 "$UVICORN" src.server.app:app --host 0.0.0.0 --port 8000 --no-access-log &
SERVER_PID=$!
echo "[start-agents-view] Server PID=$SERVER_PID on :8000 (access logs disabled)"

cd "$REPO_ROOT/src/ui" && npm run dev &
UI_PID=$!
echo "[start-agents-view] UI PID=$UI_PID on :5173"

LOOP_PID=""
if [ -n "$RUN_COUNT" ]; then
  run_restart_loop "$RUN_COUNT" &
  LOOP_PID=$!
fi

sleep 2
open http://localhost:5173 2>/dev/null || xdg-open http://localhost:5173 2>/dev/null || true

echo "[start-agents-view] Ctrl+C to stop both processes."

cleanup() {
  echo ""
  echo "[start-agents-view] Shutting down…"
  if [ -n "$LOOP_PID" ]; then
    kill "$LOOP_PID" 2>/dev/null || true
  fi
  kill "$SERVER_PID" "$UI_PID" 2>/dev/null || true
}
trap cleanup INT TERM

wait
