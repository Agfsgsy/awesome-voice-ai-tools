@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  python scripts\setup_mobile_backend.py
  if errorlevel 1 exit /b 1
)
".venv\Scripts\python.exe" scripts\run_mobile_backend.py %*
endlocal
