#!/usr/bin/env bash
# Start the local development environment (backend API + frontend dev server).
# Usage: ./dev.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

cleanup() {
  echo ""
  echo "Shutting down..."
  kill $BACKEND_PID $FRONTEND_PID 2>/dev/null
  wait $BACKEND_PID $FRONTEND_PID 2>/dev/null
  echo "Done."
}
trap cleanup EXIT INT TERM

# --- Backend (Flask on :8000) ---
echo "Starting backend API on http://localhost:8000 ..."
AUTH_ENABLED=false USE_MOTO=true python3 "$SCRIPT_DIR/lambda/local_api.py" &
BACKEND_PID=$!

# Give the backend a moment to bind
sleep 1

# --- Frontend (Vite on :5173) ---
echo "Starting frontend on http://localhost:5173 ..."
cd "$SCRIPT_DIR/frontend"
npx vite --host &
FRONTEND_PID=$!

echo ""
echo "  Backend API:  http://localhost:8000"
echo "  Frontend:     http://localhost:5173"
echo ""
echo "Press Ctrl+C to stop both."

wait
