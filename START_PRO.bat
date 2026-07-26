@echo off
cd /d "%~dp0"
title Voice AI Studio Pro
start "" cmd /c "timeout /t 4 /nobreak >nul & start "" http://localhost:8000/static/pro.html"
python main.py
if errorlevel 1 (
  echo.
  echo تعذر تشغيل البرنامج. شغّل INSTALL_WINDOWS_LITE.bat أولاً.
  pause
)
