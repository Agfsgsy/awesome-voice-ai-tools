#!/bin/bash
# Voice AI Studio Arabic - Linux Installer
set -e
echo "=== Installing Voice AI Studio Arabic on Linux ==="

PYTHON=python3
if ! command -v $PYTHON &> /dev/null; then
    echo "[ERROR] Python 3 not found"
    exit 1
fi

echo "[OK] Python: $($PYTHON --version)"

if [ ! -d ".venv" ]; then
    $PYTHON -m venv .venv
fi
source .venv/bin/activate

pip install --upgrade pip wheel setuptools
pip install -r requirements-linux.txt

for dir in uploads outputs cache logs models voices downloads config; do
    mkdir -p "$dir"
done

echo ""
echo "=== Installation Complete ==="
echo "Run: ./scripts/run.sh"
