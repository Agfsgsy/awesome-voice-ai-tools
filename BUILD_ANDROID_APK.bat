@echo off
setlocal
cd /d "%~dp0"
python scripts\build_android_app.py --apk %*
endlocal
