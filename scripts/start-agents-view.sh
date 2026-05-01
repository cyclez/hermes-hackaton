#!/usr/bin/env bash
set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

# Load env files (local overrides example)
if [ -f .env.example ]; then set -a; source .env.example; set +a; fi
if [ -f .env ]; then set -a; source .env; set +a; fi
if [ -f .env.local ]; then set -a; source .env.local; set +a; fi

UVICORN="$REPO_ROOT/.venv/bin/uvicorn"
if [ ! -x "$UVICORN" ]; then
  echo "[start-agents-view] ERROR: $UVICORN not found. Run: uv pip install -e . first."
  exit 1
fi

echo "[start-agents-view] Launching OptimiCity with agent-focused backend logs…"

PYTHONUNBUFFERED=1 "$UVICORN" src.server.app:app --host 0.0.0.0 --port 8000 --no-access-log &
SERVER_PID=$!
echo "[start-agents-view] Server PID=$SERVER_PID on :8000 (access logs disabled)"

cd "$REPO_ROOT/src/ui" && npm run dev &
UI_PID=$!
echo "[start-agents-view] UI PID=$UI_PID on :5173"

sleep 2
open http://localhost:5173 2>/dev/null || xdg-open http://localhost:5173 2>/dev/null || true

echo "[start-agents-view] Ctrl+C to stop both processes."

cleanup() {
  echo ""
  echo "[start-agents-view] Shutting down…"
  kill "$SERVER_PID" "$UI_PID" 2>/dev/null
}
trap cleanup INT TERM

wait
