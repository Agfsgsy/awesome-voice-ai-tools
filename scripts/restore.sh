#!/bin/bash
# Voice AI Studio Arabic - Restore
set -e
echo "=== Restore ==="

BACKUP_DIR="backups"
LATEST=$(ls -t "$BACKUP_DIR"/*.tar.gz 2>/dev/null | head -1)

if [ -z "$LATEST" ]; then
    echo "[ERROR] No backup found in $BACKUP_DIR/"
    exit 1
fi

echo "[INFO] Restoring from: $LATEST"
tar -xzf "$LATEST"

echo "[OK] Restore complete"
