@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
title Ibn Al-Waqadi Studio 6.2 - XTTS 98 Percent Import V2

set "SOURCE_COMMIT=971ffffa846d4f7be5c802a1061073f9b97788fa"
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

set "TEMPROOT=%TEMP%\IbnWaqadiXTTS98V2-%RANDOM%%RANDOM%"
set "BACKUP=%PROJECT%\Backups\XTTS98ImportV2-620-%RANDOM%%RANDOM%"
set "EXISTING=%BACKUP%\existing.txt"
set "NEWFILES=%BACKUP%\new.txt"
set "ENTERFILE=%TEMP%\ibn_waqadi_xtts_98_v2_enter.txt"
set "UNLOCKER=%TEMPROOT%\INSTALL_BUILT_SETUP_UNLOCKED_620.cmd"
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
echo  Ibn Al-Waqadi Studio 6.2 - XTTS 98 Percent Import Repair V2
echo ========================================================================
echo Project: %PROJECT%
echo.
echo This repair changes only XTTS runtime/finalization source files and main.py.
echo It preserves the downloaded 1992.6 MB model, keys, profiles, samples,
echo consent records, generated audio, shila projects and the complete interface.
echo Backup: %BACKUP%
echo.

echo [1/8] Closing only Studio and XTTS workers...
taskkill /f /t /im VoiceAIStudioArabic.exe >nul 2>&1
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
  "$root=Join-Path $env:LOCALAPPDATA 'VoiceAIStudioArabic\voice_clones\local_engine';" ^
  "Get-CimInstance Win32_Process | Where-Object {" ^
  "  (([string]$_.ExecutablePath).StartsWith($root,[StringComparison]::OrdinalIgnoreCase)) -or" ^
  "  (([string]$_.CommandLine).IndexOf($root,[StringComparison]::OrdinalIgnoreCase) -ge 0)" ^
  "} | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1
timeout /t 3 /nobreak >nul

echo [2/8] Backing up and installing the consistent XTTS files...
call :apply "backend\api\voice_clone_repair_runtime.py" "backend/api/voice_clone_repair_runtime.py"
if errorlevel 1 goto :rollback
call :apply "backend\api\voice_clone_xtts_runtime.py" "backend/api/voice_clone_xtts_runtime.py"
if errorlevel 1 goto :rollback
call :apply "backend\api\voice_clone_download_resume_patch.py" "backend/api/voice_clone_download_resume_patch.py"
if errorlevel 1 goto :rollback
call :apply "backend\api\voice_clone_download_source_fix.py" "backend/api/voice_clone_download_source_fix.py"
if errorlevel 1 goto :rollback
call :apply "backend\api\voice_clone_98_finalize_patch.py" "backend/api/voice_clone_98_finalize_patch.py"
if errorlevel 1 goto :rollback
call :apply "backend\api\voice_clone_auto_finalize_patch.py" "backend/api/voice_clone_auto_finalize_patch.py"
if errorlevel 1 goto :rollback
call :apply "main.py" "main.py"
if errorlevel 1 goto :rollback

echo [3/8] Checking direct imports and finalizing the existing XTTS model...
pushd "%PROJECT%"
py -3.11 -m py_compile ^
  "backend\api\voice_clone_repair_runtime.py" ^
  "backend\api\voice_clone_xtts_runtime.py" ^
  "backend\api\voice_clone_download_resume_patch.py" ^
  "backend\api\voice_clone_download_source_fix.py" ^
  "backend\api\voice_clone_98_finalize_patch.py" ^
  "backend\api\voice_clone_auto_finalize_patch.py" ^
  "main.py"
set "COMPILE_RESULT=%ERRORLEVEL%"
if "%COMPILE_RESULT%"=="0" (
  py -3.11 -c "import importlib; import main; r=importlib.import_module('backend.api.voice_clone_download_resume_patch'); p=importlib.import_module('backend.api.voice_clone_repair_runtime'); f=importlib.import_module('backend.api.voice_clone_98_finalize_patch'); d=r._model_dir(); print('XTTS_DIRECT_IMPORT_OK'); print('XTTS_MODEL_MB=',round(r._directory_bytes(d)/1048576,1)); print('XTTS_MARKER=',p.MODEL_MARKER.exists()); assert callable(f._validate_downloaded_model); assert p.MODEL_MARKER.exists(), 'Downloaded XTTS files were not finalized'"
  set "IMPORT_RESULT=!ERRORLEVEL!"
) else (
  set "IMPORT_RESULT=1"
)
popd
if not "%COMPILE_RESULT%"=="0" goto :rollback
if not "%IMPORT_RESULT%"=="0" goto :rollback

echo [4/8] Building the same Studio version 6.2.0...
if exist "%PROJECT%\build" rmdir /s /q "%PROJECT%\build"
if exist "%PROJECT%\dist" rmdir /s /q "%PROJECT%\dist"
if exist "%PROJECT%\dist-installer" rmdir /s /q "%PROJECT%\dist-installer"
echo.>"%ENTERFILE%"
call "%PROJECT%\BUILD_WINDOWS_INSTALLER.bat" < "%ENTERFILE%"
if errorlevel 1 goto :rollback
if not exist "%PROJECT%\dist-installer\VoiceAIStudioSetup.exe" goto :rollback

echo [5/8] Downloading the safe unlocked installer helper...
curl.exe -L --fail --silent --show-error "%RAW%/INSTALL_BUILT_SETUP_UNLOCKED_620.cmd" -o "%UNLOCKER%"
if errorlevel 1 goto :rollback
if not exist "%UNLOCKER%" goto :rollback

echo [6/8] Installing the corrected build without touching user data...
call "%UNLOCKER%"
if errorlevel 1 goto :rollback

echo [7/8] Verifying the installed application exists...
if not exist "%LOCALAPPDATA%\Programs\Voice AI Studio Arabic Pro\VoiceAIStudioArabic.exe" goto :rollback

echo [8/8] Repair completed.
del /q "%ENTERFILE%" >nul 2>&1
rmdir /s /q "%TEMPROOT%" >nul 2>&1

echo.
echo ========================================================================
echo SUCCESS: XTTS 98-percent Import V2 repair was installed.
echo The existing model is finalized at 100 percent and remains preserved.
echo Open Voice Clone Pro and select Local XTTS or Automatic Fast.
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
echo ERROR: XTTS 98-percent Import V2 did not complete.
echo Restoring only source files changed by this repair...
if exist "%EXISTING%" for /f "usebackq delims=" %%R in ("%EXISTING%") do (
  if exist "%BACKUP%\%%R" copy /y "%BACKUP%\%%R" "%PROJECT%\%%R" >nul
)
if exist "%NEWFILES%" for /f "usebackq delims=" %%R in ("%NEWFILES%") do (
  if exist "%PROJECT%\%%R" del /q "%PROJECT%\%%R" >nul 2>&1
)
if exist "%ENTERFILE%" del /q "%ENTERFILE%" >nul 2>&1
if exist "%TEMPROOT%" rmdir /s /q "%TEMPROOT%" >nul 2>&1
echo No user key, profile, sample, model download, audio, project or UI file was deleted.
echo Backup: %BACKUP%
pause
exit /b 1

:failed_no_rollback
echo.
echo ERROR: The repair could not start.
echo No project or user file was changed.
pause
exit /b 1
