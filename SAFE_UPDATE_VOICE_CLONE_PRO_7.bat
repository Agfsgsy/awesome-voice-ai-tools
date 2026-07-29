@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

set "ROOT=%~1"
if not defined ROOT set "ROOT=C:\awesome-voice-ai-tools"

cd /d "%ROOT%" || (
  echo [ERROR] Project folder was not found: %ROOT%
  pause
  exit /b 1
)

echo =============================================================
echo   Voice Clone Multi-Engine Pro 7.0 - Safe Overlay Update
echo   No reset, no clean, no purge, and no file deletion.
echo =============================================================
echo.

where git >nul 2>nul || (
  echo [ERROR] Git is not installed.
  pause
  exit /b 1
)

where py >nul 2>nul || (
  echo [ERROR] Python launcher is not installed.
  pause
  exit /b 1
)

py -3.11 -c "import sys; assert sys.version_info[:2] == (3,11)" >nul 2>nul || (
  echo [ERROR] Python 3.11 is required.
  pause
  exit /b 1
)

if not exist "safe_backups" mkdir "safe_backups"
for /f "delims=" %%D in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmmss"') do set "STAMP=%%D"

git diff > "safe_backups\before-v7-!STAMP!.patch"
git diff --cached > "safe_backups\before-v7-staged-!STAMP!.patch"
git status --porcelain > "safe_backups\before-v7-status-!STAMP!.txt"

echo [1/7] Fetching Voice Clone Pro 7.0...
git fetch origin agent/voice-clone-pro-v7 || (
  echo [ERROR] Could not fetch the update branch.
  pause
  exit /b 1
)

set "ZIP=%TEMP%\VoiceClonePro7_!RANDOM!_!RANDOM!.zip"
set "EXTRACT=%TEMP%\VoiceClonePro7_!RANDOM!_!RANDOM!"

echo [2/7] Creating a non-destructive update package...
git archive --format=zip --output="!ZIP!" origin/agent/voice-clone-pro-v7 || (
  echo [ERROR] Could not create the update package.
  pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -LiteralPath '!ZIP!' -DestinationPath '!EXTRACT!' -Force" || (
  echo [ERROR] Could not extract the update package.
  pause
  exit /b 1
)

echo [3/7] Overlaying new and updated files without deleting any existing file...
robocopy "!EXTRACT!" "%ROOT%" /E /COPY:DAT /R:2 /W:1 /NFL /NDL /NJH /NJS /NP
set "ROBOCOPY_CODE=!ERRORLEVEL!"
if !ROBOCOPY_CODE! GEQ 8 (
  echo [ERROR] The safe overlay copy failed with code !ROBOCOPY_CODE!.
  pause
  exit /b 1
)

echo [4/7] Preparing the isolated Python 3.11 environment...
if not exist ".venv-v7\Scripts\python.exe" py -3.11 -m venv .venv-v7
if not exist ".venv-v7\Scripts\python.exe" (
  echo [ERROR] Could not create .venv-v7.
  pause
  exit /b 1
)

".venv-v7\Scripts\python.exe" -m pip install --upgrade pip setuptools wheel || (
  echo [ERROR] Could not update pip tools.
  pause
  exit /b 1
)

if exist "requirements.txt" (
  echo [5/7] Updating the studio requirements...
  ".venv-v7\Scripts\python.exe" -m pip install -r requirements.txt || (
    echo [ERROR] Could not install the studio requirements.
    pause
    exit /b 1
  )
)

echo [6/7] Updating XTTS and the isolated engine pack...
".venv-v7\Scripts\python.exe" scripts\install_voice_clone_engine_pack.py --all --include-music --accept-licenses
if errorlevel 1 echo [WARNING] One or more optional engine installations need manual review.

echo [7/7] Verifying Voice Clone Pro 7.0...
".venv-v7\Scripts\python.exe" scripts\verify_voice_clone_v7.py || (
  echo [ERROR] Voice Clone Pro 7.0 verification failed.
  pause
  exit /b 1
)

echo.
echo [SUCCESS] Voice Clone Pro 7.0 was updated without deleting existing files.
echo Backups of local Git changes are in: %ROOT%\safe_backups

if exist "desktop_app.py" (
  start "Ibn Al-Waqadi Studio" ".venv-v7\Scripts\python.exe" desktop_app.py
) else (
  start "Ibn Al-Waqadi Studio" ".venv-v7\Scripts\python.exe" main.py
)

exit /b 0
