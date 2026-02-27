#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# run.sh — Launch the Remittance Reconciliation Tool
# Activates the virtual environment and starts Flask.
# The default browser opens automatically at http://localhost:5000
# ---------------------------------------------------------------------------
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -d "venv" ]; then
    echo "Virtual environment not found. Please run setup.sh first."
    exit 1
fi

source venv/bin/activate

echo "Starting Remittance Reconciliation Tool..."
echo "Browser will open at http://localhost:5000"
echo "Press Ctrl+C to stop."
echo ""

python app/main.py
