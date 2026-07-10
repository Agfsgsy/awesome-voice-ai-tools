#!/bin/bash
# Voice AI Studio Arabic - Restart Script
echo "=== Restarting Voice AI Studio Arabic ==="

# Stop existing
./scripts/stop.sh 2>/dev/null || true
sleep 2

# Start again
./scripts/run.sh
