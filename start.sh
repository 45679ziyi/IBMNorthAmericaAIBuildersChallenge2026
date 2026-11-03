#!/usr/bin/env bash
# AURORA — start.sh
# Self-locating startup script. Run from any directory:
#   bash /path/to/aurora-campus-intelligence/start.sh

set -e

# Resolve the directory this script lives in
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BACKEND="$SCRIPT_DIR/backend"
FRONTEND="$SCRIPT_DIR/frontend"

echo "=== AURORA Campus Intelligence ==="
echo "Project root: $SCRIPT_DIR"
echo ""

# ── Backend setup ─────────────────────────────────────────────────────────────
echo "[1/4] Setting up Python virtual environment..."
cd "$BACKEND"

if ! [ -d ".venv" ]; then
  if command -v uv &>/dev/null; then
    uv venv --python python3
  else
    python3 -m venv .venv
  fi
fi

# Activate
source "$BACKEND/.venv/bin/activate"

echo "[2/4] Installing Python dependencies..."
if command -v uv &>/dev/null; then
  uv pip install -e ".[dev]" --quiet
else
  pip install -e ".[dev]" --quiet
fi

echo "[3/4] Seeding demo data..."
python -m scripts.seed_demo_data

echo "[4/4] Starting backend on http://localhost:8000 ..."
echo "      Press Ctrl+C to stop. Open a second terminal for the frontend."
echo ""
uvicorn app.main:app --reload --port 8000 --host 127.0.0.1
