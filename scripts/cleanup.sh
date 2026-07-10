#!/bin/bash
# Voice AI Studio Arabic - Cleanup
echo "=== Cleanup ==="

echo "[INFO] Removing __pycache__..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

echo "[INFO] Removing .pyc files..."
find . -name "*.pyc" -delete 2>/dev/null || true

echo "[INFO] Clearing cache..."
rm -rf cache/*
touch cache/.gitkeep

echo "[INFO] Removing temp files..."
rm -rf /tmp/voice_ai_* 2>/dev/null || true

echo "=== Cleanup Complete ==="
