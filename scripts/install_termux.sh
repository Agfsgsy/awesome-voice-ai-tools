#!/bin/bash
# Voice AI Studio Arabic - Termux Installer
set -e
echo "=== Installing Voice AI Studio Arabic on Termux ==="

if [ ! -d "/data/data/com.termux/files/usr" ]; then
    echo "[ERROR] This script is for Termux only"
    exit 1
fi

pkg update -y
pkg install -y python git rust

if [ ! -d ".venv" ]; then
    python -m venv .venv
fi
source .venv/bin/activate

pip install --upgrade pip wheel setuptools
MATHLIB=m pip install -r requirements-termux.txt

for dir in uploads outputs cache logs models voices downloads config; do
    mkdir -p "$dir"
done

echo ""
echo "=== Installation Complete ==="
echo "Run: ./scripts/run.sh"
