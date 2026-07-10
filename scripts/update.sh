#!/bin/bash
# Voice AI Studio Arabic - Update Script
set -e
echo "=== Updating Voice AI Studio Arabic ==="

# Pull latest changes
if [ -d ".git" ]; then
    echo "[INFO] Pulling latest changes..."
    git pull origin main
fi

# Update dependencies
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

REQ_FILE="requirements.txt"
if [ -d "/data/data/com.termux/files/usr" ]; then
    REQ_FILE="requirements-termux.txt"
fi

echo "[INFO] Updating dependencies..."
pip install --upgrade -r "$REQ_FILE"

echo "=== Update Complete ==="
