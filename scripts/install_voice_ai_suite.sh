#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m pip install -r requirements.txt
python3 -m pip install -r requirements-voice-ai.txt
python3 scripts/voice_ai_manager.py doctor || true
python3 scripts/voice_ai_manager.py write-env
echo "Install optional engines individually, for example:"
echo "python3 scripts/voice_ai_manager.py install xtts"
echo "python3 scripts/voice_ai_manager.py install openvoice"
echo "python3 scripts/voice_ai_manager.py install f5tts"
echo "python3 scripts/voice_ai_manager.py install gpt_sovits"
echo "python3 scripts/voice_ai_manager.py install cosyvoice"
echo "python3 scripts/voice_ai_manager.py install rvc"
echo "python3 scripts/voice_ai_manager.py install ace_step"
echo "python3 scripts/voice_ai_manager.py install yue"
