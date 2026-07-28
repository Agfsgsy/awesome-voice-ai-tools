@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
title Ibn Al-Waqadi Studio 6.2 - XTTS Auto Resume

set "SCRIPT_URL=https://raw.githubusercontent.com/Agfsgsy/awesome-voice-ai-tools/cda6fb7014c2f2a154427ba8506ed3be7c04c09c/FIX_XTTS_FIND_OR_RESUME_620.ps1"
set "SCRIPT=%TEMP%\FIX_XTTS_FIND_OR_RESUME_620.ps1"
set "MAX_ATTEMPTS=15"

where curl.exe >nul 2>&1
if errorlevel 1 (
  echo ERROR: curl.exe was not found.
  pause
  exit /b 1
)

curl.exe -L --fail --silent --show-error "%SCRIPT_URL%" -o "%SCRIPT%"
if errorlevel 1 (
  echo ERROR: Could not download the XTTS resume script.
  pause
  exit /b 1
)
if not exist "%SCRIPT%" (
  echo ERROR: XTTS resume script is missing.
  pause
  exit /b 1
)

for /L %%A in (1,1,%MAX_ATTEMPTS%) do (
  cls
  echo ========================================================================
  echo  Ibn Al-Waqadi Studio 6.2 - XTTS Automatic Resume
  echo ========================================================================
  echo Attempt %%A of %MAX_ATTEMPTS%
  echo.
  echo Existing downloaded pieces are preserved and reused.
  echo Do not close this window while the download is active.
  echo.

  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%"
  set "RESULT=!ERRORLEVEL!"
  if "!RESULT!"=="0" (
    echo.
    echo SUCCESS: XTTS completed and the Studio was started.
    pause
    exit /b 0
  )

  if %%A LSS %MAX_ATTEMPTS% (
    echo.
    echo The internet connection interrupted this attempt.
    echo Saved files were kept. Retrying automatically in 30 seconds...
    timeout /t 30 /nobreak >nul
  )
)

echo.
echo ERROR: XTTS did not finish after %MAX_ATTEMPTS% attempts.
echo No downloaded piece or user file was deleted.
echo Connect to a more stable network and run this same command again.
pause
exit /b 1
