#!/bin/bash
# Voice AI Studio Arabic - Backup
set -e
echo "=== Backup ==="

BACKUP_DIR="backups"
BACKUP_NAME="voice-ai-backup-$(date +%Y%m%d-%H%M%S).tar.gz"

mkdir -p "$BACKUP_DIR"

echo "[INFO] Creating backup: $BACKUP_NAME"
tar -czf "$BACKUP_DIR/$BACKUP_NAME" \
    --exclude='.venv' \
    --exclude='__pycache__' \
    --exclude='.git' \
    --exclude='backups' \
    --exclude='node_modules' \
    backend/ frontend/ plugins/ config/ scripts/ main.py requirements*.txt Dockerfile docker-compose.yml .env.example README.md

echo "[OK] Backup saved: $BACKUP_DIR/$BACKUP_NAME"
