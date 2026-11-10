#!/bin/bash
# setup_and_seed.sh — Single command to set up AURORA from a clean checkout
# Usage: bash scripts/setup_and_seed.sh [--skip-frontend] [--skip-evals]
# 
# This script:
# 1. Creates a Python venv and installs backend dependencies
# 2. Seeds the demo database
# 3. Loads all four tenant packs
# 4. Runs the eval suite (optional, pass --skip-evals to skip)
# 5. Installs frontend dependencies
# 6. Runs a quick TypeScript check

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BACKEND="$PROJECT_ROOT/backend"
FRONTEND="$PROJECT_ROOT/frontend"

# Parse flags
SKIP_FRONTEND=0
SKIP_EVALS=0
for arg in "$@"; do
    case $arg in
        --skip-frontend) SKIP_FRONTEND=1 ;;
        --skip-evals)    SKIP_EVALS=1 ;;
    esac
done

echo "=== AURORA Setup and Seed ==="
echo "Project root: $PROJECT_ROOT"
echo ""

# ── Backend ────────────────────────────────────────────────────────────────────

echo "--- Backend: creating virtual environment ---"
cd "$BACKEND"

if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate

echo "--- Backend: installing dependencies ---"
pip install -e ".[dev]" -q

echo "--- Backend: seeding demo data ---"
python scripts/seed_demo_data.py

echo "--- Backend: loading all four tenant packs ---"
python -m app.cli tenant load \
    ../sample-data/tenants/sbu_demo.pack.json \
    ../sample-data/tenants/northbridge_demo.pack.json \
    ../sample-data/tenants/pacific_demo.pack.json \
    ../sample-data/tenants/rhine_demo.pack.json

echo "--- Backend: verifying tenant list ---"
python -m app.cli tenant list

if [ $SKIP_EVALS -eq 0 ]; then
    echo "--- Backend: running eval suite ---"
    python -m evals.run --all
    echo ""
fi

echo "--- Backend: running test suite (quick check) ---"
pytest -q --tb=short 2>&1 | tail -4

cd "$PROJECT_ROOT"

# ── Frontend ───────────────────────────────────────────────────────────────────

if [ $SKIP_FRONTEND -eq 0 ]; then
    echo ""
    echo "--- Frontend: installing dependencies ---"
    cd "$FRONTEND"
    npm install --silent

    echo "--- Frontend: TypeScript check ---"
    npm run type-check

    echo "--- Frontend: production build ---"
    npm run build 2>&1 | tail -3

    cd "$PROJECT_ROOT"
fi

echo ""
echo "=== Setup complete ==="
echo ""
echo "To start the backend:"
echo "  cd backend && source .venv/bin/activate && uvicorn app.main:app --reload --port 8000"
echo ""
echo "To start the frontend:"
echo "  cd frontend && npm run dev"
echo ""
echo "Then open http://localhost:5173"
