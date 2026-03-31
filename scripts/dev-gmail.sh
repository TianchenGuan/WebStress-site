#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────
# dev-gmail.sh — One-command launcher for the Gmail environment
#
# Starts both the FastAPI backend (port 8080) and Vite dev
# server (port 4173), installs deps if needed, and opens
# the browser once everything is ready.
#
# Usage:
#   ./scripts/dev-gmail.sh            # default ports
#   ./scripts/dev-gmail.sh --no-open  # skip browser open
# ──────────────────────────────────────────────────────────
set -eo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_DIR="$ROOT/webagentbench/environments"
BACKEND_PORT=8080
FRONTEND_PORT=4173
OPEN_BROWSER=true
PIDS=()

for arg in "$@"; do
  case "$arg" in
    --no-open) OPEN_BROWSER=false ;;
  esac
done

cleanup() {
  echo ""
  echo "Shutting down..."
  for pid in "${PIDS[@]+"${PIDS[@]}"}"; do
    kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null
  echo "Done."
}
trap cleanup EXIT INT TERM

# ── 0. Ensure uv is available ────────────────────────────
if ! command -v uv &>/dev/null; then
  echo "[0/3] Installing uv (Python package manager)..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  # The installer puts uv in ~/.local/bin — add it to PATH for this session
  export PATH="$HOME/.local/bin:$PATH"
  if ! command -v uv &>/dev/null; then
    echo "ERROR: uv install failed. Install manually: https://docs.astral.sh/uv/"
    exit 1
  fi
  echo "  uv installed: $(uv --version)"
fi

# ── 1. Python environment ──────────────────────────────────
# tinker-cookbook is a workspace member that may not be cloned (it's for training,
# not needed for the Gmail env). Create a stub so uv sync doesn't fail.
if [ ! -f "$ROOT/tinker-cookbook/pyproject.toml" ]; then
  mkdir -p "$ROOT/tinker-cookbook"
  cat > "$ROOT/tinker-cookbook/pyproject.toml" << 'STUB'
[project]
name = "tinker-cookbook"
version = "0.0.0"
requires-python = ">=3.10"
STUB
  echo "  Created tinker-cookbook stub (submodule not cloned)"
fi

# Check that uvicorn is actually importable, not just that .venv exists
if ! "$ROOT/.venv/bin/python" -c "import uvicorn" 2>/dev/null; then
  echo "[1/3] Installing Python dependencies..."
  (cd "$ROOT" && uv sync)
else
  echo "[1/3] Python deps OK"
fi

# ── 2. Node dependencies ──────────────────────────────────
if [ ! -d "$ENV_DIR/node_modules" ]; then
  echo "[2/3] Installing Node dependencies..."
  (cd "$ENV_DIR" && pnpm install --frozen-lockfile 2>/dev/null || pnpm install)
else
  echo "[2/3] Node modules OK"
fi

# ── 3. Start servers ──────────────────────────────────────
echo "[3/3] Starting servers..."
echo ""

# Load .env if present (for OPENAI_API_KEY etc.)
if [ -f "$ROOT/.env" ]; then
  set -a; source "$ROOT/.env"; set +a
fi

# Backend (FastAPI)
echo "  Backend  → http://localhost:$BACKEND_PORT"
(
  cd "$ROOT"
  source .venv/bin/activate
  python -m uvicorn webagentbench.app:app \
    --host 127.0.0.1 --port "$BACKEND_PORT" --reload \
    --log-level info 2>&1 | sed 's/^/  [backend] /'
) &
PIDS+=($!)

# Wait for backend to be ready before starting frontend
echo "  Waiting for backend..."
for i in $(seq 1 30); do
  if curl -sf "http://127.0.0.1:$BACKEND_PORT/health" > /dev/null 2>&1; then
    break
  fi
  sleep 1
done

# Frontend (Vite)
echo "  Frontend → http://localhost:$FRONTEND_PORT/env/gmail/"
(
  cd "$ENV_DIR"
  pnpm dev:gmail 2>&1 | sed 's/^/  [frontend] /'
) &
PIDS+=($!)

# Wait for Vite to be ready
sleep 2

# ── Open browser ──────────────────────────────────────────
if [ "$OPEN_BROWSER" = true ]; then
  URL="http://localhost:$BACKEND_PORT/launch"
  echo ""
  echo "  Opening $URL"
  if command -v open &>/dev/null; then
    open "$URL"
  elif command -v xdg-open &>/dev/null; then
    xdg-open "$URL"
  fi
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Gmail environment is running!"
echo ""
echo "  Launcher:  http://localhost:$FRONTEND_PORT/env/gmail/"
echo "  Backend:   http://localhost:$BACKEND_PORT/"
echo "  Health:    http://localhost:$BACKEND_PORT/health"
echo ""
echo "  Press Ctrl+C to stop both servers."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Keep script alive until Ctrl+C
wait
