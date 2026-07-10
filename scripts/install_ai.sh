#!/bin/bash
# Voice AI Studio Arabic - AI Engines Installer
set -e
echo "=== Installing AI TTS Engines ==="

PYTHON=${PYTHON:-python3}

echo "[1/5] Installing Piper TTS..."
pip install -q piper-tts && echo "  [OK]" || echo "  [SKIP] Failed"

echo "[2/5] Installing Kokoro TTS..."
pip install -q kokoro && echo "  [OK]" || echo "  [SKIP] Failed"

echo "[3/5] Installing Coqui TTS + torch..."
pip install -q TTS torch torchaudio && echo "  [OK]" || echo "  [SKIP] Failed"

echo "[4/5] Installing MeloTTS..."
pip install -q git+https://github.com/myshell-ai/MeloTTS.git && echo "  [OK]" || echo "  [SKIP] Failed"

echo "[5/5] Installing StyleTTS2..."
pip install -q git+https://github.com/yl4579/StyleTTS2.git && echo "  [OK]" || echo "  [SKIP] Failed"

echo ""
echo "=== AI Engines Installation Complete ==="
echo "Run: python download_models.py --engine all"
echo "Check: ./scripts/doctor_ai.sh"
