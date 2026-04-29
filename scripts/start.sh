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
  echo "[start] ERROR: $UVICORN not found. Run: uv pip install -e . first."
  exit 1
fi

echo "[start] Launching OptimiCity…"

PYTHONUNBUFFERED=1 "$UVICORN" src.server.app:app --host 0.0.0.0 --port 8000 &
SERVER_PID=$!
echo "[start] Server PID=$SERVER_PID on :8000"

cd "$REPO_ROOT/src/ui" && npm run dev &
UI_PID=$!
echo "[start] UI PID=$UI_PID on :5173"

sleep 2
open http://localhost:5173 2>/dev/null || xdg-open http://localhost:5173 2>/dev/null || true

echo "[start] Ctrl+C to stop both processes."

cleanup() {
  echo ""
  echo "[start] Shutting down…"
  kill "$SERVER_PID" "$UI_PID" 2>/dev/null
}
trap cleanup INT TERM

wait
