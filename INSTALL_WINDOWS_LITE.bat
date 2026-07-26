@echo off
cd /d "%~dp0"
title Voice AI Studio - Windows Lite Installer
python --version >nul 2>&1
if errorlevel 1 (
  echo Python غير مثبت أو غير مضاف إلى PATH.
  pause
  exit /b 1
)
python -m pip install --upgrade pip
python -m pip install fastapi==0.115.6 "uvicorn[standard]==0.34.0" pydantic==2.10.4 python-multipart==0.0.20 httpx==0.28.1 aiofiles==24.1.0 requests edge-tts pydub soundfile imageio-ffmpeg
if errorlevel 1 (
  echo فشل التثبيت. صوّر الخطأ وأرسله.
  pause
  exit /b 1
)
echo.
echo تم التثبيت بنجاح. شغّل START_PRO.bat
pause
