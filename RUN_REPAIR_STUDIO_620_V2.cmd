@echo off
setlocal EnableExtensions
title Ibn Al-Waqadi Studio 6.2 Repair V2

set "PS1=%TEMP%\REPAIR_PRESERVE_UI_SHILA_XTTS_620_V2.ps1"
set "URL=https://raw.githubusercontent.com/Agfsgsy/awesome-voice-ai-tools/249b6f94b2cbd0d3c505b061d7e7c6dd2ab6e098/REPAIR_PRESERVE_UI_SHILA_XTTS_620_V2.ps1"

echo Downloading repair script...
where curl.exe >nul 2>&1
if errorlevel 1 (
  echo ERROR: curl.exe was not found.
  pause
  exit /b 1
)

curl.exe -L --fail --silent --show-error "%URL%" -o "%PS1%"
if errorlevel 1 (
  echo ERROR: Download failed.
  pause
  exit /b 1
)
if not exist "%PS1%" (
  echo ERROR: Repair script was not created.
  pause
  exit /b 1
)

echo Starting repair...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PS1%"
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo.
  echo Repair exited with code %RC%.
  pause
  exit /b %RC%
)

echo.
echo Repair launcher completed.
pause
exit /b 0
