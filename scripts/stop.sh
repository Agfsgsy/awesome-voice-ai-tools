#!/bin/bash
# Voice AI Studio Arabic - Stop Script
echo "=== Stopping Voice AI Studio Arabic ==="

# Find and kill the process
PID_FILE="logs/app.pid"
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        kill "$PID"
        echo "[OK] Stopped process $PID"
    else
        echo "[INFO] Process $PID not running"
    fi
    rm -f "$PID_FILE"
else
    # Try pkill
    pkill -f "python main.py" 2>/dev/null && echo "[OK] Stopped via pkill" || echo "[INFO] No process found"
fi
