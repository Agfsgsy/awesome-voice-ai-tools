#!/bin/bash
# Voice AI Studio Arabic - Health Check
echo "=== Health Check ==="

PORT=${APP_PORT:-8000}

# Check if process is running
if pgrep -f "python main.py" > /dev/null; then
    echo "[OK] Process running"
else
    echo "[FAIL] Process not running"
    exit 1
fi

# Check HTTP endpoint
if command -v curl &> /dev/null; then
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:$PORT/health" 2>/dev/null || echo "000")
    if [ "$HTTP_CODE" = "200" ]; then
        echo "[OK] HTTP endpoint responding (200)"
    else
        echo "[FAIL] HTTP endpoint returned: $HTTP_CODE"
        exit 1
    fi
fi

echo "=== All checks passed ==="
