@echo off
REM سكريبت تثبيت لنظام Windows

echo 🎙️ تثبيت Voice AI Unified Launcher على Windows...

python -m venv venv
call venv\Scripts\activate

pip install --upgrade pip
pip install gradio soundfile numpy

echo.
echo اختر المحرك:
echo 1. pip install f5-tts torch torchaudio
echo 2. pip install TTS torch torchaudio
echo 3. pip install kokoro
echo 4. pip install -r requirements/requirements-all.txt
echo.
pause

echo ✅ بعد التثبيت، شغّل: python app.py
pause
