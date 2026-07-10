#!/bin/bash
# Voice AI Studio Arabic - Installation Script
set -e

echo "=== Voice AI Studio Arabic - Installation ==="

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python 3 not found"
    exit 1
fi

PYTHON=python3
echo "[OK] Python: $($PYTHON --version)"

# Check if Termux
IS_TERMUX=false
if [ -d "/data/data/com.termux/files/usr" ]; then
    IS_TERMUX=true
    echo "[INFO] Termux detected"
    REQ_FILE="requirements-termux.txt"
else
    REQ_FILE="requirements.txt"
fi

# Create venv
if [ ! -d ".venv" ]; then
    echo "[INFO] Creating virtual environment..."
    $PYTHON -m venv .venv
fi

# Activate venv
if [ "$IS_TERMUX" = true ]; then
    source .venv/bin/activate
else
    source .venv/bin/activate
fi

# Upgrade pip
echo "[INFO] Upgrading pip..."
pip install --upgrade pip wheel setuptools

# Install requirements
echo "[INFO] Installing requirements from $REQ_FILE..."
pip install -r "$REQ_FILE"

# Create directories
for dir in uploads outputs cache logs models voices downloads config; do
    mkdir -p "$dir"
done

echo ""
echo "=== Installation Complete ==="
echo "Run: ./scripts/run.sh"
echo "URL: http://localhost:8000"
