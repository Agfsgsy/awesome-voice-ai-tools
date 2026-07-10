#!/bin/bash
# Voice AI Studio Arabic - Doctor (Self-Diagnostic)
echo "=== Voice AI Studio Arabic - Doctor ==="
echo ""

echo "--- Python ---"
python3 --version 2>/dev/null && echo "[OK]" || echo "[FAIL]"

echo "--- pip ---"
pip --version 2>/dev/null && echo "[OK]" || echo "[FAIL]"

echo "--- Git ---"
git --version 2>/dev/null && echo "[OK]" || echo "[FAIL]"

echo "--- Internet ---"
if ping -c 1 -W 5 huggingface.co &> /dev/null 2>&1 || curl -s -o /dev/null huggingface.co 2>/dev/null; then
    echo "[OK] Internet available"
else
    echo "[WARN] Internet check failed"
fi

echo "--- Disk Space ---"
FREE_MB=$(df -m . | tail -1 | awk '{print $4}')
echo "Free: ${FREE_MB} MB"
[ "$FREE_MB" -gt 500 ] && echo "[OK]" || echo "[WARN] Low disk space"

echo "--- RAM ---"
if [ -f "/proc/meminfo" ]; then
    RAM_FREE=$(grep MemAvailable /proc/meminfo | awk '{print int($2/1024)}')
    echo "Available: ${RAM_FREE} MB"
else
    echo "[INFO] RAM info not available"
fi

echo "--- Port ${APP_PORT:-8000} ---"
if ss -tlnp 2>/dev/null | grep -q ":${APP_PORT:-8000}" || netstat -tlnp 2>/dev/null | grep -q ":${APP_PORT:-8000}"; then
    echo "[WARN] Port in use"
else
    echo "[OK] Port available"
fi

echo "--- FastAPI ---"
python3 -c "import fastapi; print(fastapi.__version__)" 2>/dev/null && echo "[OK]" || echo "[FAIL]"

echo "--- Uvicorn ---"
python3 -c "import uvicorn; print(uvicorn.__version__)" 2>/dev/null && echo "[OK]" || echo "[FAIL]"

echo "--- Venv ---"
[ -d ".venv" ] && echo "[OK] .venv exists" || echo "[WARN] No venv"

echo ""
echo "=== Doctor Complete ==="
