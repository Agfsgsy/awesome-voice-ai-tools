@echo off
setlocal EnableExtensions
chcp 65001 >nul
title Ibn Al-Waqadi Studio 6.2 - XTTS Import and Resume Fix

set "SOURCE_COMMIT=bd63c77f11beab3342e983a2fb32a8a19f1dfadb"
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

set "TEMPROOT=%TEMP%\IbnWaqadiXTTSImport-%RANDOM%%RANDOM%"
set "BACKUP=%PROJECT%\Backups\XTTSImport620-%RANDOM%%RANDOM%"
set "EXISTING=%BACKUP%\existing.txt"
set "NEWFILES=%BACKUP%\new.txt"
set "SETUP=%PROJECT%\dist-installer\VoiceAIStudioSetup.exe"
set "APP=%LOCALAPPDATA%\Programs\Voice AI Studio Arabic Pro\VoiceAIStudioArabic.exe"
set "ENTERFILE=%TEMP%\ibn_waqadi_xtts_import_enter.txt"

mkdir "%TEMPROOT%" >nul 2>&1
mkdir "%BACKUP%" >nul 2>&1
if not exist "%TEMPROOT%" goto :failed_no_rollback
if not exist "%BACKUP%" goto :failed_no_rollback

where curl.exe >nul 2>&1
if errorlevel 1 goto :failed_no_rollback
where py.exe >nul 2>&1
if errorlevel 1 goto :failed_no_rollback

cls
echo ========================================================================
echo  XTTS Runtime Import and Resume Fix - Studio 6.2.0
echo ========================================================================
echo Project: %PROJECT%
echo.
echo This repair preserves profiles, samples, keys, partial XTTS downloads,
echo generated audio, shila projects and the preserved interface.
echo Backup: %BACKUP%
echo.

echo [1/8] Downloading and backing up only XTTS repair files...
call :apply "backend\api\voice_clone_routes.py" "backend/api/voice_clone_routes.py"
if errorlevel 1 goto :rollback
call :apply "backend\api\voice_clone_repair_runtime.py" "backend/api/voice_clone_repair_runtime.py"
if errorlevel 1 goto :rollback
call :apply "backend\api\voice_clone_fast_routes.py" "backend/api/voice_clone_fast_routes.py"
if errorlevel 1 goto :rollback
call :apply "backend\api\voice_clone_xtts_runtime.py" "backend/api/voice_clone_xtts_runtime.py"
if errorlevel 1 goto :rollback
call :apply "backend\api\voice_clone_fast_runtime_patch.py" "backend/api/voice_clone_fast_runtime_patch.py"
if errorlevel 1 goto :rollback
call :apply "backend\api\voice_clone_download_resume_patch.py" "backend/api/voice_clone_download_resume_patch.py"
if errorlevel 1 goto :rollback
call :apply "backend\api\voice_clone_download_source_fix.py" "backend/api/voice_clone_download_source_fix.py"
if errorlevel 1 goto :rollback
call :apply "backend\api\voice_clone_ui_runtime.py" "backend/api/voice_clone_ui_runtime.py"
if errorlevel 1 goto :rollback
call :apply "backend\api\yemeni_ui_runtime.py" "backend/api/yemeni_ui_runtime.py"
if errorlevel 1 goto :rollback
call :apply "frontend\static\voice_clone_fast_patch.js" "frontend/static/voice_clone_fast_patch.js"
if errorlevel 1 goto :rollback
call :apply "frontend\static\response_body_guard.js" "frontend/static/response_body_guard.js"
if errorlevel 1 goto :rollback
call :apply "main.py" "main.py"
if errorlevel 1 goto :rollback
call :apply "scripts\validate_unified_release.py" "scripts/validate_xtts_resume_import_fix_620.py"
if errorlevel 1 goto :rollback

echo [2/8] Verifying the missing XTTS runtime module directly...
pushd "%PROJECT%"
py -3.11 -c "import importlib; m=importlib.import_module('backend.api.voice_clone_xtts_runtime'); assert hasattr(m,'router'); importlib.import_module('backend.api.voice_clone_download_resume_patch'); print('XTTS_IMPORT_OK')"
set "IMPORT_RESULT=%ERRORLEVEL%"
popd
if not "%IMPORT_RESULT%"=="0" goto :rollback

echo [3/8] Checking Python syntax and generated XTTS workers...
pushd "%PROJECT%"
py -3.11 -m py_compile ^
  "backend\api\voice_clone_routes.py" ^
  "backend\api\voice_clone_repair_runtime.py" ^
  "backend\api\voice_clone_fast_routes.py" ^
  "backend\api\voice_clone_xtts_runtime.py" ^
  "backend\api\voice_clone_fast_runtime_patch.py" ^
  "backend\api\voice_clone_download_resume_patch.py" ^
  "backend\api\voice_clone_download_source_fix.py" ^
  "backend\api\voice_clone_ui_runtime.py" ^
  "backend\api\yemeni_ui_runtime.py" ^
  "main.py" ^
  "scripts\validate_unified_release.py"
set "COMPILE_RESULT=%ERRORLEVEL%"
popd
if not "%COMPILE_RESULT%"=="0" goto :rollback

echo [4/8] Closing only Ibn Al-Waqadi Studio...
taskkill /f /im VoiceAIStudioArabic.exe >nul 2>&1

echo [5/8] Stopping only old XTTS Python workers; downloaded files remain...
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$target=Join-Path $env:LOCALAPPDATA 'VoiceAIStudioArabic\voice_clones\local_engine\venv\Scripts\python.exe'; Get-CimInstance Win32_Process ^| Where-Object { $_.ExecutablePath -eq $target } ^| ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1

echo [6/8] Building Studio 6.2.0...
if exist "%PROJECT%\build" rmdir /s /q "%PROJECT%\build"
if exist "%PROJECT%\dist" rmdir /s /q "%PROJECT%\dist"
if exist "%PROJECT%\dist-installer" rmdir /s /q "%PROJECT%\dist-installer"
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
echo SUCCESS: XTTS runtime import and resumable download fix was installed.
echo Open Voice Clone Pro, accept the license, then press Setup again.
echo Existing partial XTTS files will be reused.
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
echo ERROR: The XTTS import repair did not complete.
echo Restoring only source files changed by this repair...
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
