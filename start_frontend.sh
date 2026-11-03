#!/usr/bin/env bash
# AURORA — start_frontend.sh
# Run from any directory:
#   bash /path/to/aurora-campus-intelligence/start_frontend.sh

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
FRONTEND="$SCRIPT_DIR/frontend"

echo "=== AURORA Frontend ==="
echo "Frontend root: $FRONTEND"
echo ""

cd "$FRONTEND"

if ! [ -d "node_modules" ]; then
  echo "Installing npm dependencies..."
  npm install
fi

echo "Starting frontend on http://localhost:5173 ..."
npm run dev
