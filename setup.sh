#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# setup.sh — First-time setup for Remittance Reconciliation Tool
# Creates a virtual environment and installs all Python dependencies.
# No administrator privileges required.
# ---------------------------------------------------------------------------
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "======================================================="
echo "  Remittance Reconciliation Tool — Setup"
echo "======================================================="
echo ""

# ------------------------------------------------------------------
# Check Python version
# ------------------------------------------------------------------
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        VERSION=$("$cmd" -c "import sys; print(sys.version_info[:2])" 2>/dev/null)
        MAJOR=$("$cmd" -c "import sys; print(sys.version_info.major)")
        MINOR=$("$cmd" -c "import sys; print(sys.version_info.minor)")
        if [ "$MAJOR" -ge 3 ] && [ "$MINOR" -ge 9 ]; then
            PYTHON="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo "ERROR: Python 3.9 or later is required but was not found."
    echo "Please install Python from https://www.python.org/downloads/"
    exit 1
fi

echo "Using Python: $($PYTHON --version)"
echo ""

# ------------------------------------------------------------------
# Create virtual environment
# ------------------------------------------------------------------
if [ ! -d "venv" ]; then
    echo "Creating virtual environment in ./venv ..."
    "$PYTHON" -m venv venv
    echo "Virtual environment created."
else
    echo "Virtual environment already exists. Skipping creation."
fi
echo ""

# ------------------------------------------------------------------
# Activate and install dependencies
# ------------------------------------------------------------------
echo "Installing Python dependencies from requirements.txt ..."
echo "(This may take a few minutes on first run.)"
echo ""

source venv/bin/activate
pip install --upgrade pip --quiet
pip install -r requirements.txt

# ------------------------------------------------------------------
# Create runtime data directories
# ------------------------------------------------------------------
echo ""
echo "Creating data directories ..."
mkdir -p data/tokens data/watch data/remittances data/attachments
echo "Data directories ready."

# ------------------------------------------------------------------
# Check for optional system dependencies
# ------------------------------------------------------------------
echo ""
echo "Checking optional system dependencies ..."

if command -v tesseract &>/dev/null; then
    echo "  [OK] Tesseract OCR found: $(tesseract --version 2>&1 | head -1)"
else
    echo "  [WARN] Tesseract OCR not found."
    echo "         OCR fallback will be unavailable."
    echo "         Install via: sudo apt install tesseract-ocr  (Ubuntu/Debian)"
    echo "                   or: brew install tesseract  (macOS)"
    echo "         Most PDFs are processed without OCR — this is optional."
fi

# ------------------------------------------------------------------
# Done
# ------------------------------------------------------------------
echo ""
echo "======================================================="
echo "  Setup complete!"
echo ""
echo "  To launch the application:"
echo "    ./run.sh"
echo ""
echo "  The browser will open automatically at http://localhost:5000"
echo "======================================================="
echo ""
