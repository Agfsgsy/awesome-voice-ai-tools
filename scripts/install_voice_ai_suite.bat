@echo off
setlocal
cd /d "%~dp0\.."
python -m pip install -r requirements.txt || exit /b 1
python -m pip install -r requirements-voice-ai.txt || exit /b 1
python scripts\voice_ai_manager.py doctor
python scripts\voice_ai_manager.py write-env
echo Install optional engines individually, for example:
echo python scripts\voice_ai_manager.py install xtts
echo python scripts\voice_ai_manager.py install openvoice
echo python scripts\voice_ai_manager.py install f5tts
echo python scripts\voice_ai_manager.py install gpt_sovits
echo python scripts\voice_ai_manager.py install cosyvoice
echo python scripts\voice_ai_manager.py install rvc
echo python scripts\voice_ai_manager.py install ace_step
echo python scripts\voice_ai_manager.py install yue
endlocal
