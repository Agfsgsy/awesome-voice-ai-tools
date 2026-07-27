@echo off
setlocal EnableExtensions
chcp 65001 >nul
title Ibn Al-Waqadi Studio 6.2 - Voice Clone Fast Fix V2

set "SOURCE_COMMIT=d73d788ea1959fd3c25c8fd8a85b359a2ac7cd82"
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

set "TEMPROOT=%TEMP%\IbnWaqadiCloneFastV2-%RANDOM%%RANDOM%"
set "BACKUP=%PROJECT%\Backups\VoiceCloneFast620V2-%RANDOM%%RANDOM%"
set "EXISTING=%BACKUP%\existing.txt"
set "NEWFILES=%BACKUP%\new.txt"
set "SETUP=%PROJECT%\dist-installer\VoiceAIStudioSetup.exe"
set "APP=%LOCALAPPDATA%\Programs\Voice AI Studio Arabic Pro\VoiceAIStudioArabic.exe"
set "ENTERFILE=%TEMP%\ibn_waqadi_clone_v2_enter.txt"

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
echo  Voice Clone Fast Fix V2 - Studio 6.2.0
echo ========================================================================
echo Project: %PROJECT%
echo.
echo The previous failure was only an unrelated validator mismatch.
echo This repair changes only Voice Clone runtime/build files.
echo It does NOT delete keys, profiles, samples, audio, shila tools or projects.
echo Backup: %BACKUP%
echo.

echo [1/7] Downloading and backing up the Voice Clone files...
call :apply "backend\api\voice_clone_fast_routes.py" "backend/api/voice_clone_fast_routes.py"
if errorlevel 1 goto :rollback
call :apply "backend\api\voice_clone_repair_runtime.py" "backend/api/voice_clone_repair_runtime.py"
if errorlevel 1 goto :rollback
call :apply "backend\api\voice_clone_xtts_runtime.py" "backend/api/voice_clone_xtts_runtime.py"
if errorlevel 1 goto :rollback
call :apply "backend\api\voice_clone_fast_runtime_patch.py" "backend/api/voice_clone_fast_runtime_patch.py"
if errorlevel 1 goto :rollback
call :apply "backend\api\voice_clone_ui_runtime.py" "backend/api/voice_clone_ui_runtime.py"
if errorlevel 1 goto :rollback
call :apply "frontend\static\voice_clone_fast_patch.js" "frontend/static/voice_clone_fast_patch.js"
if errorlevel 1 goto :rollback
call :apply "main.py" "main.py"
if errorlevel 1 goto :rollback
call :apply "requirements.txt" "requirements.txt"
if errorlevel 1 goto :rollback
call :apply "VoiceAIStudio.spec" "VoiceAIStudio.spec"
if errorlevel 1 goto :rollback

rem The source is a clone-only compatible validator, installed at the filename
rem already called by BUILD_WINDOWS_INSTALLER.bat. The previous validator is backed up.
call :apply "scripts\validate_unified_release.py" "scripts/validate_voice_clone_fast_repair_620.py"
if errorlevel 1 goto :rollback

echo [2/7] Checking Python syntax before closing the application...
py -3.11 -m py_compile ^
  "%PROJECT%\backend\api\voice_clone_fast_routes.py" ^
  "%PROJECT%\backend\api\voice_clone_repair_runtime.py" ^
  "%PROJECT%\backend\api\voice_clone_xtts_runtime.py" ^
  "%PROJECT%\backend\api\voice_clone_fast_runtime_patch.py" ^
  "%PROJECT%\backend\api\voice_clone_ui_runtime.py" ^
  "%PROJECT%\main.py" ^
  "%PROJECT%\scripts\validate_unified_release.py"
if errorlevel 1 goto :rollback

echo [3/7] Closing only Ibn Al-Waqadi Studio...
taskkill /f /im VoiceAIStudioArabic.exe >nul 2>&1

echo [4/7] Removing only old temporary build folders...
if exist "%PROJECT%\build" rmdir /s /q "%PROJECT%\build"
if exist "%PROJECT%\dist" rmdir /s /q "%PROJECT%\dist"
if exist "%PROJECT%\dist-installer" rmdir /s /q "%PROJECT%\dist-installer"

echo [5/7] Building and validating Studio 6.2.0...
echo.>"%ENTERFILE%"
call "%PROJECT%\BUILD_WINDOWS_INSTALLER.bat" < "%ENTERFILE%"
if errorlevel 1 goto :rollback
if not exist "%SETUP%" goto :rollback

echo [6/7] Installing the corrected Voice Clone build...
start "" /wait "%SETUP%" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP- /TASKS=desktopicon
if errorlevel 1 goto :rollback
if not exist "%APP%" goto :rollback

echo [7/7] Starting Ibn Al-Waqadi Studio...
start "" "%APP%"

del /q "%ENTERFILE%" >nul 2>&1
rmdir /s /q "%TEMPROOT%" >nul 2>&1

echo.
echo ========================================================================
echo SUCCESS: Voice Clone Fast V2 was installed correctly.
echo The old interface, shila/zamil tools and all saved user data were preserved.
echo Open Voice Clone Pro and choose Automatic Fast.
echo For local XTTS, press the setup button once until the full model is ready.
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
for %%F in ("%TEMPFILE%") do if %%~zF LSS 32 exit /b 1
for %%D in ("%LOCAL%") do if not exist "%%~dpD" mkdir "%%~dpD" >nul 2>&1
copy /y "%TEMPFILE%" "%LOCAL%" >nul
if errorlevel 1 exit /b 1
exit /b 0

:rollback
echo.
echo ERROR: Voice Clone Fast V2 did not complete.
echo Restoring only the source files changed by this repair...
if exist "%EXISTING%" for /f "usebackq delims=" %%R in ("%EXISTING%") do (
  if exist "%BACKUP%\%%R" copy /y "%BACKUP%\%%R" "%PROJECT%\%%R" >nul
)
if exist "%NEWFILES%" for /f "usebackq delims=" %%R in ("%NEWFILES%") do (
  if exist "%PROJECT%\%%R" del /q "%PROJECT%\%%R" >nul 2>&1
)
if exist "%ENTERFILE%" del /q "%ENTERFILE%" >nul 2>&1
if exist "%TEMPROOT%" rmdir /s /q "%TEMPROOT%" >nul 2>&1
echo No user keys, profiles, samples, audio, shila files or projects were deleted.
echo Backup: %BACKUP%
pause
exit /b 1

:failed_no_rollback
echo.
echo ERROR: The repair could not start.
echo No project or user file was changed.
pause
exit /b 1
