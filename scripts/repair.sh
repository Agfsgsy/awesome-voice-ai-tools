#!/bin/bash
# Voice AI Studio Arabic - Repair Script
set -e
echo "=== Repairing Voice AI Studio Arabic ==="

# Recreate directories
for dir in uploads outputs cache logs models voices downloads config; do
    mkdir -p "$dir"
    touch "$dir/.gitkeep"
done

# Reinstall dependencies
if [ -d ".venv" ]; then
    source .venv/bin/activate
    REQ_FILE="requirements.txt"
    if [ -d "/data/data/com.termux/files/usr" ]; then
        REQ_FILE="requirements-termux.txt"
    fi
    echo "[INFO] Reinstalling dependencies..."
    pip install --force-reinstall -r "$REQ_FILE"
else
    echo "[WARN] No venv found. Run install.sh first."
fi

# Clear cache
echo "[INFO] Clearing cache..."
rm -rf cache/*
touch cache/.gitkeep

echo "=== Repair Complete ==="
