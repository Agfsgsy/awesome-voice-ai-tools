@echo off
setlocal EnableExtensions
chcp 65001 >nul
title Ibn Al-Waqadi Studio 6.2 - XTTS Resume Fix

set "SOURCE_COMMIT=600591233459024826ff7ff47acc0852d5bcd171"
set "RAW=https://raw.githubusercontent.com/Agfsgsy/awesome-voice-ai-tools/%SOURCE_COMMIT%"
set "PROJECT="
if exist "%USERPROFILE%\Desktop\VoiceAIStudio-Pro-Latest\BUILD_WINDOWS_INSTALLER.bat" set "PROJECT=%USERPROFILE%\Desktop\VoiceAIStudio-Pro-Latest"
if not defined PROJECT if exist "%USERPROFILE%\OneDrive\Desktop\VoiceAIStudio-Pro-Latest\BUILD_WINDOWS_INSTALLER.bat" set "PROJECT=%USERPROFILE%\OneDrive\Desktop\VoiceAIStudio-Pro-Latest"
if not defined PROJECT if exist "%USERPROFILE%\Downloads\VoiceAIStudio-Pro-Latest\BUILD_WINDOWS_INSTALLER.bat" set "PROJECT=%USERPROFILE%\Downloads\VoiceAIStudio-Pro-Latest"
if not defined PROJECT if exist "%USERPROFILE%\Desktop\awesome-voice-ai-tools-agent-professional-tts-engine\BUILD_WINDOWS_INSTALLER.bat" set "PROJECT=%USERPROFILE%\Desktop\awesome-voice-ai-tools-agent-professional-tts-engine"
if not defined PROJECT if exist "%USERPROFILE%\Downloads\awesome-voice-ai-tools-agent-professional-tts-engine\BUILD_WINDOWS_INSTALLER.bat" set "PROJECT=%USERPROFILE%\Downloads\awesome-voice-ai-tools-agent-professional-tts-engine"

if not defined PROJECT (
  echo ERROR: Project folder was not found.
  echo Put VoiceAIStudio-Pro-Latest on Desktop and run this command again.
  pause
  exit /b 1
)

set "TEMPROOT=%TEMP%\IbnWaqadiXTTSResume-%RANDOM%%RANDOM%"
set "BACKUP=%PROJECT%\Backups\XTTSResume620-%RANDOM%%RANDOM%"
set "EXISTING=%BACKUP%\existing.txt"
set "NEWFILES=%BACKUP%\new.txt"
set "SETUP=%PROJECT%\dist-installer\VoiceAIStudioSetup.exe"
set "APP=%LOCALAPPDATA%\Programs\Voice AI Studio Arabic Pro\VoiceAIStudioArabic.exe"
set "ENTERFILE=%TEMP%\ibn_waqadi_xtts_resume_enter.txt"

mkdir "%TEMPROOT%" >nul 2>&1
mkdir "%BACKUP%" >nul 2>&1
if not exist "%TEMPROOT%" goto :failed_no_rollback
if not exist "%BACKUP%" goto :failed_no_rollback

where curl.exe >nul 2>&1
if errorlevel 1 (
  echo ERROR: curl.exe is unavailable.
  goto :failed_no_rollback
)
where py.exe >nul 2>&1
if errorlevel 1 (
  echo ERROR: Python launcher py.exe is unavailable.
  goto :failed_no_rollback
)

cls
echo ========================================================================
echo  XTTS Resume and Shila Error Fix - Studio 6.2.0
echo ========================================================================
echo Project: %PROJECT%
echo.
echo This repair does not delete profiles, samples, keys, generated audio,
echo shila projects, the preserved interface, or the partial XTTS model cache.
echo Backup: %BACKUP%
echo.

echo [1/8] Downloading and backing up only the repair files...
call :apply "backend\api\voice_clone_download_resume_patch.py" "backend/api/voice_clone_download_resume_patch.py"
if errorlevel 1 goto :rollback
call :apply "backend\api\voice_clone_download_source_fix.py" "backend/api/voice_clone_download_source_fix.py"
if errorlevel 1 goto :rollback
call :apply "backend\api\voice_clone_ui_runtime.py" "backend/api/voice_clone_ui_runtime.py"
if errorlevel 1 goto :rollback
call :apply "backend\api\yemeni_ui_runtime.py" "backend/api/yemeni_ui_runtime.py"
if errorlevel 1 goto :rollback
call :apply "frontend\static\response_body_guard.js" "frontend/static/response_body_guard.js"
if errorlevel 1 goto :rollback
call :apply "main.py" "main.py"
if errorlevel 1 goto :rollback
call :apply "scripts\validate_unified_release.py" "scripts/validate_xtts_resume_and_response_fix_620.py"
if errorlevel 1 goto :rollback

echo [2/8] Checking Python syntax...
py -3.11 -m py_compile ^
  "%PROJECT%\backend\api\voice_clone_download_resume_patch.py" ^
  "%PROJECT%\backend\api\voice_clone_download_source_fix.py" ^
  "%PROJECT%\backend\api\voice_clone_ui_runtime.py" ^
  "%PROJECT%\backend\api\yemeni_ui_runtime.py" ^
  "%PROJECT%\main.py" ^
  "%PROJECT%\scripts\validate_unified_release.py"
if errorlevel 1 goto :rollback

echo [3/8] Closing only Ibn Al-Waqadi Studio...
taskkill /f /im VoiceAIStudioArabic.exe >nul 2>&1

echo [4/8] Stopping only the old XTTS download worker and preserving its files...
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$target=Join-Path $env:LOCALAPPDATA 'VoiceAIStudioArabic\voice_clones\local_engine\venv\Scripts\python.exe'; Get-CimInstance Win32_Process ^| Where-Object { $_.ExecutablePath -eq $target } ^| ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1

echo [5/8] Removing only temporary application build folders...
if exist "%PROJECT%\build" rmdir /s /q "%PROJECT%\build"
if exist "%PROJECT%\dist" rmdir /s /q "%PROJECT%\dist"
if exist "%PROJECT%\dist-installer" rmdir /s /q "%PROJECT%\dist-installer"

echo [6/8] Validating and building Studio 6.2.0...
echo.>"%ENTERFILE%"
call "%PROJECT%\BUILD_WINDOWS_INSTALLER.bat" < "%ENTERFILE%"
if errorlevel 1 goto :rollback
if not exist "%SETUP%" goto :rollback

echo [7/8] Installing the corrected build...
start "" /wait "%SETUP%" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP- /TASKS=desktopicon
if errorlevel 1 goto :rollback
if not exist "%APP%" goto :rollback

echo [8/8] Starting Ibn Al-Waqadi Studio...
start "" "%APP%"

del /q "%ENTERFILE%" >nul 2>&1
rmdir /s /q "%TEMPROOT%" >nul 2>&1

echo.
echo ========================================================================
echo SUCCESS: XTTS resumable download repair was installed.
echo Open Voice Clone Pro, accept the license, and press the setup button again.
echo The program will reuse partial files and show downloaded MB plus elapsed time.
echo The shila page will now show the real server error instead of body stream read.
echo Backup: %BACKUP%
echo ========================================================================
pause
exit /b 0

:apply
set "RELWIN=%~1"
set "RELURL=%~2"
set "LOCAL=%PROJECT%\%RELWIN%"
set "TEMPFILE=%TEMPROOT%\%RELWIN%"
set "BACKUPFILE=%BACKUP%\%RELWIN%"
for %%D in ("%TEMPFILE%") do if not exist "%%~dpD" mkdir "%%~dpD" >nul 2>&1
for %%D in ("%BACKUPFILE%") do if not exist "%%~dpD" mkdir "%%~dpD" >nul 2>&1
if exist "%LOCAL%" (
  copy /y "%LOCAL%" "%BACKUPFILE%" >nul
  if errorlevel 1 exit /b 1
  echo %RELWIN%>>"%EXISTING%"
) else (
  echo %RELWIN%>>"%NEWFILES%"
)
curl.exe -L --fail --silent --show-error "%RAW%/%RELURL%" -o "%TEMPFILE%"
if errorlevel 1 exit /b 1
if not exist "%TEMPFILE%" exit /b 1
for %%F in ("%TEMPFILE%") do if %%~zF LSS 24 exit /b 1
for %%D in ("%LOCAL%") do if not exist "%%~dpD" mkdir "%%~dpD" >nul 2>&1
copy /y "%TEMPFILE%" "%LOCAL%" >nul
if errorlevel 1 exit /b 1
exit /b 0

:rollback
echo.
echo ERROR: The XTTS resume repair did not complete.
echo Restoring only the source files changed by this repair...
if exist "%EXISTING%" for /f "usebackq delims=" %%R in ("%EXISTING%") do (
  if exist "%BACKUP%\%%R" copy /y "%BACKUP%\%%R" "%PROJECT%\%%R" >nul
)
if exist "%NEWFILES%" for /f "usebackq delims=" %%R in ("%NEWFILES%") do (
  if exist "%PROJECT%\%%R" del /q "%PROJECT%\%%R" >nul 2>&1
)
if exist "%ENTERFILE%" del /q "%ENTERFILE%" >nul 2>&1
if exist "%TEMPROOT%" rmdir /s /q "%TEMPROOT%" >nul 2>&1
echo No keys, profiles, samples, partial model files, audio or projects were deleted.
echo Backup: %BACKUP%
pause
exit /b 1

:failed_no_rollback
echo.
echo ERROR: The repair could not start.
echo No project or user file was changed.
pause
exit /b 1
