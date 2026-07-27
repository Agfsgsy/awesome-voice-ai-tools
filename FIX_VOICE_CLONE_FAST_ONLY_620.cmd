@echo off
setlocal EnableExtensions
chcp 65001 >nul
title Ibn Al-Waqadi Studio 6.2 - Voice Clone Fast Fix Only

set "SOURCE_COMMIT=e9544c294d7be46df1b1ec6121ca4a18ecda144f"
set "RAW=https://raw.githubusercontent.com/Agfsgsy/awesome-voice-ai-tools/%SOURCE_COMMIT%"
set "PROJECT="
if exist "%USERPROFILE%\Desktop\VoiceAIStudio-Pro-Latest\BUILD_WINDOWS_INSTALLER.bat" set "PROJECT=%USERPROFILE%\Desktop\VoiceAIStudio-Pro-Latest"
if not defined PROJECT if exist "%USERPROFILE%\OneDrive\Desktop\VoiceAIStudio-Pro-Latest\BUILD_WINDOWS_INSTALLER.bat" set "PROJECT=%USERPROFILE%\OneDrive\Desktop\VoiceAIStudio-Pro-Latest"
if not defined PROJECT if exist "%USERPROFILE%\Downloads\VoiceAIStudio-Pro-Latest\BUILD_WINDOWS_INSTALLER.bat" set "PROJECT=%USERPROFILE%\Downloads\VoiceAIStudio-Pro-Latest"
if not defined PROJECT if exist "%USERPROFILE%\Desktop\awesome-voice-ai-tools-agent-professional-tts-engine\BUILD_WINDOWS_INSTALLER.bat" set "PROJECT=%USERPROFILE%\Desktop\awesome-voice-ai-tools-agent-professional-tts-engine"
if not defined PROJECT if exist "%USERPROFILE%\Downloads\awesome-voice-ai-tools-agent-professional-tts-engine\BUILD_WINDOWS_INSTALLER.bat" set "PROJECT=%USERPROFILE%\Downloads\awesome-voice-ai-tools-agent-professional-tts-engine"

if not defined PROJECT (
  echo ERROR: Project folder was not found.
  echo Put VoiceAIStudio-Pro-Latest on Desktop and run this repair again.
  pause
  exit /b 1
)

set "TEMPROOT=%TEMP%\IbnWaqadiCloneFast%RANDOM%%RANDOM%"
set "BACKUP=%PROJECT%\Backups\VoiceCloneFast620-%RANDOM%%RANDOM%"
set "EXISTING=%BACKUP%\existing.txt"
set "NEWFILES=%BACKUP%\new.txt"
set "SETUP=%PROJECT%\dist-installer\VoiceAIStudioSetup.exe"
set "APP=%LOCALAPPDATA%\Programs\Voice AI Studio Arabic Pro\VoiceAIStudioArabic.exe"
set "ENTERFILE=%TEMP%\ibn_waqadi_clone_enter.txt"

mkdir "%TEMPROOT%" >nul 2>&1
mkdir "%BACKUP%" >nul 2>&1
if not exist "%TEMPROOT%" goto :failed_no_rollback
if not exist "%BACKUP%" goto :failed_no_rollback

where curl.exe >nul 2>&1
if errorlevel 1 (
  echo ERROR: curl.exe is not available on this Windows installation.
  goto :failed_no_rollback
)

echo.
echo ========================================================================
echo  Voice Clone Fast Fix Only - Studio 6.2.0
echo ========================================================================
echo Project: %PROJECT%
echo.
echo This repair changes only voice-clone runtime source files.
echo It does NOT delete keys, profiles, samples, consent records, audio or projects.
echo Backup: %BACKUP%
echo.

echo [1/6] Downloading and backing up the voice-clone repair files...
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
call :apply "scripts\validate_unified_release.py" "scripts/validate_unified_release.py"
if errorlevel 1 goto :rollback
call :apply "VoiceAIStudio.spec" "VoiceAIStudio.spec"
if errorlevel 1 goto :rollback

echo [2/6] Checking Python syntax before building...
py -3.11 -m py_compile ^
  "%PROJECT%\backend\api\voice_clone_fast_routes.py" ^
  "%PROJECT%\backend\api\voice_clone_repair_runtime.py" ^
  "%PROJECT%\backend\api\voice_clone_xtts_runtime.py" ^
  "%PROJECT%\backend\api\voice_clone_fast_runtime_patch.py" ^
  "%PROJECT%\backend\api\voice_clone_ui_runtime.py" ^
  "%PROJECT%\main.py" ^
  "%PROJECT%\scripts\validate_unified_release.py"
if errorlevel 1 goto :rollback

echo [3/6] Closing only the running Studio application...
taskkill /f /im VoiceAIStudioArabic.exe >nul 2>&1

echo [4/6] Building and validating the same Studio 6.2.0...
echo.>"%ENTERFILE%"
call "%PROJECT%\BUILD_WINDOWS_INSTALLER.bat" < "%ENTERFILE%"
if errorlevel 1 goto :rollback
if not exist "%SETUP%" goto :rollback

echo [5/6] Installing the voice-clone repair...
start "" /wait "%SETUP%" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP- /TASKS=desktopicon
if errorlevel 1 goto :rollback
if not exist "%APP%" goto :rollback

echo [6/6] Starting Ibn Al-Waqadi Studio...
start "" "%APP%"

del /q "%ENTERFILE%" >nul 2>&1
rmdir /s /q "%TEMPROOT%" >nul 2>&1

echo.
echo SUCCESS: Voice Clone Fast repair was installed.
echo The designed interface and all saved data were preserved.
echo Open Voice Clone Pro and use Automatic Fast mode.
echo For local XTTS, click the setup button once if the page says the full model is required.
echo Backup: %BACKUP%
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
echo ERROR: The voice-clone repair did not complete.
echo Restoring the project source files from the backup...
if exist "%EXISTING%" for /f "usebackq delims=" %%R in ("%EXISTING%") do (
  if exist "%BACKUP%\%%R" copy /y "%BACKUP%\%%R" "%PROJECT%\%%R" >nul
)
if exist "%NEWFILES%" for /f "usebackq delims=" %%R in ("%NEWFILES%") do (
  if exist "%PROJECT%\%%R" del /q "%PROJECT%\%%R" >nul 2>&1
)
if exist "%ENTERFILE%" del /q "%ENTERFILE%" >nul 2>&1
if exist "%TEMPROOT%" rmdir /s /q "%TEMPROOT%" >nul 2>&1
echo No user keys, profiles, samples, audio or projects were deleted.
echo Backup: %BACKUP%
pause
exit /b 1

:failed_no_rollback
echo.
echo ERROR: The repair could not start.
echo No project or user file was changed.
pause
exit /b 1
