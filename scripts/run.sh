#!/bin/bash
# Voice AI Studio Arabic - Run Script
set -e

echo "=== Starting Voice AI Studio Arabic ==="

# Activate venv
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Set defaults
export APP_HOST=${APP_HOST:-0.0.0.0}
export APP_PORT=${APP_PORT:-8000}

echo "[INFO] Starting server on $APP_HOST:$APP_PORT"
python main.py
