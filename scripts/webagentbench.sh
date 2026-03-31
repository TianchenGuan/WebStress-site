#!/usr/bin/env bash
set -eo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_DIR="$ROOT/webagentbench/environments"
BACKEND_PORT=8080
OPEN_BROWSER=true
MODE="dev"
PIDS=()
SELECTED_ENVS=()

usage() {
  cat <<'EOF'
Usage:
  ./scripts/webagentbench.sh dev [--env ENV_ID] [--no-open]
  ./scripts/webagentbench.sh build

Modes:
  dev     Start the FastAPI backend and frontend dev servers, then open /launch
  build   Build the static frontend bundles under webagentbench/static/envs/

Options:
  --env ENV_ID   Start only the specified frontend in dev mode. Repeatable.
  --no-open      Do not open the browser automatically.

If no subcommand is provided, the script defaults to dev mode.
EOF
}

all_dev_envs() {
  echo "gmail"
}

env_port() {
  case "$1" in
    gmail) echo "4173" ;;
    *) return 1 ;;
  esac
}

env_base_url() {
  local port
  port="$(env_port "$1")"
  case "$1" in
    gmail) echo "http://localhost:${port}/env/gmail" ;;
    *) return 1 ;;
  esac
}

start_env_dev_server() {
  case "$1" in
    gmail)
      (
        cd "$ENV_DIR"
        pnpm dev:gmail 2>&1 | sed 's/^/  [frontend:gmail] /'
      ) &
      PIDS+=($!)
      ;;
    *)
      echo "ERROR: unsupported dev frontend: $1" >&2
      exit 1
      ;;
  esac
}

if [ $# -gt 0 ]; then
  case "$1" in
    dev|build)
      MODE="$1"
      shift
      ;;
    help|-h|--help)
      usage
      exit 0
      ;;
  esac
fi

while [ $# -gt 0 ]; do
  case "$1" in
    --env)
      if [ $# -lt 2 ]; then
        echo "ERROR: --env requires a value" >&2
        usage
        exit 1
      fi
      SELECTED_ENVS+=("$2")
      shift 2
      ;;
    --no-open)
      OPEN_BROWSER=false
      shift
      ;;
    help|-h|--help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

for candidate in \
  "$ROOT/.tools/node-v24.14.1-darwin-arm64/bin" \
  "$HOME/Library/pnpm" \
  "$HOME/.local/share/pnpm"
do
  if [ -d "$candidate" ]; then
    export PATH="$candidate:$PATH"
  fi
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

require_pnpm() {
  if ! command -v pnpm &>/dev/null; then
    echo "ERROR: pnpm is required for the WebAgentBench frontend workflow."
    echo "Install pnpm or expose it on PATH, then rerun this script."
    exit 1
  fi
}

ensure_uv() {
  if command -v uv &>/dev/null; then
    return
  fi

  echo "[0/3] Installing uv (Python package manager)..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
  if ! command -v uv &>/dev/null; then
    echo "ERROR: uv install failed. Install manually: https://docs.astral.sh/uv/"
    exit 1
  fi
  echo "  uv installed: $(uv --version)"
}

ensure_python_deps() {
  if [ ! -f "$ROOT/tinker-cookbook/pyproject.toml" ]; then
    mkdir -p "$ROOT/tinker-cookbook"
    cat > "$ROOT/tinker-cookbook/pyproject.toml" <<'STUB'
[project]
name = "tinker-cookbook"
version = "0.0.0"
requires-python = ">=3.10"
STUB
    echo "  Created tinker-cookbook stub (submodule not cloned)"
  fi

  if ! "$ROOT/.venv/bin/python" -c "import uvicorn" 2>/dev/null; then
    echo "[1/3] Installing Python dependencies..."
    (cd "$ROOT" && uv sync)
  else
    echo "[1/3] Python deps OK"
  fi
}

ensure_node_modules() {
  require_pnpm

  if [ ! -d "$ENV_DIR/node_modules" ]; then
    echo "[2/3] Installing Node dependencies..."
    (cd "$ENV_DIR" && pnpm install --frozen-lockfile 2>/dev/null || pnpm install)
  else
    echo "[2/3] Node modules OK"
  fi
}

wait_for_url() {
  local url="$1"
  local label="$2"

  for _ in $(seq 1 60); do
    if curl -sf "$url" > /dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done

  echo "ERROR: timed out waiting for $label at $url" >&2
  exit 1
}

open_url() {
  local url="$1"

  if command -v open &>/dev/null; then
    if open "$url" >/dev/null 2>&1; then
      return 0
    fi
  fi

  if command -v xdg-open &>/dev/null; then
    if xdg-open "$url" >/dev/null 2>&1; then
      return 0
    fi
  fi

  if command -v python3 &>/dev/null; then
    if python3 -m webbrowser "$url" >/dev/null 2>&1; then
      return 0
    fi
  fi

  echo "WARNING: failed to auto-open $url" >&2
  return 1
}

build_frontends() {
  ensure_node_modules
  echo "[frontend] Building workspace frontends..."
  (cd "$ENV_DIR" && pnpm build)
  echo "[frontend] Build complete."
}

selected_envs_or_default() {
  if [ ${#SELECTED_ENVS[@]} -gt 0 ]; then
    printf '%s\n' "${SELECTED_ENVS[@]}"
    return
  fi
  all_dev_envs
}

validate_selected_envs() {
  local env_id
  while IFS= read -r env_id; do
    [ -n "$env_id" ] || continue
    env_base_url "$env_id" > /dev/null
  done < <(selected_envs_or_default)
}

dev_frontend_env_var() {
  local mappings=()
  local env_id
  while IFS= read -r env_id; do
    [ -n "$env_id" ] || continue
    mappings+=("${env_id}=$(env_base_url "$env_id")")
  done < <(selected_envs_or_default)

  local joined=""
  local mapping
  for mapping in "${mappings[@]}"; do
    if [ -n "$joined" ]; then
      joined="${joined},"
    fi
    joined="${joined}${mapping}"
  done
  printf '%s' "$joined"
}

start_dev() {
  trap cleanup EXIT INT TERM

  validate_selected_envs
  ensure_uv
  ensure_python_deps
  ensure_node_modules

  local dev_frontends
  dev_frontends="$(dev_frontend_env_var)"

  echo "[3/3] Starting servers..."
  echo ""

  if [ -f "$ROOT/.env" ]; then
    set -a
    source "$ROOT/.env"
    set +a
  fi

  echo "  Backend  → http://localhost:$BACKEND_PORT"
  (
    cd "$ROOT"
    export WEBAGENTBENCH_DEV_FRONTENDS="$dev_frontends"
    source .venv/bin/activate
    python -m uvicorn webagentbench.app:app \
      --host 127.0.0.1 --port "$BACKEND_PORT" --reload \
      --log-level info 2>&1 | sed 's/^/  [backend] /'
  ) &
  PIDS+=($!)

  wait_for_url "http://127.0.0.1:$BACKEND_PORT/health" "backend"

  local env_id
  while IFS= read -r env_id; do
    [ -n "$env_id" ] || continue
    echo "  Frontend $env_id → $(env_base_url "$env_id")/"
    start_env_dev_server "$env_id"
  done < <(selected_envs_or_default)

  while IFS= read -r env_id; do
    [ -n "$env_id" ] || continue
    wait_for_url "$(env_base_url "$env_id")/" "frontend $env_id"
  done < <(selected_envs_or_default)

  if [ "$OPEN_BROWSER" = true ]; then
    local url="http://localhost:$BACKEND_PORT/launch"
    echo ""
    echo "  Opening $url"
    open_url "$url" || true
  fi

  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "  WebAgentBench is running!"
  echo ""
  echo "  Launcher:  http://localhost:$BACKEND_PORT/launch"
  echo "  Backend:   http://localhost:$BACKEND_PORT/"
  while IFS= read -r env_id; do
    [ -n "$env_id" ] || continue
    echo "  Dev UI:    $(env_base_url "$env_id")/"
  done < <(selected_envs_or_default)
  echo ""
  echo "  Press Ctrl+C to stop all servers."
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo ""

  wait
}

case "$MODE" in
  build)
    build_frontends
    ;;
  dev)
    start_dev
    ;;
  *)
    echo "ERROR: unsupported mode: $MODE" >&2
    usage
    exit 1
    ;;
esac
