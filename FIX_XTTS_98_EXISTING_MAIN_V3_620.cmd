@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
title Ibn Al-Waqadi Studio 6.2 - XTTS 98 Existing Main V3

set "SOURCE_COMMIT=0543290b36fdb4f318b63312784fb6b18205f559"
set "RAW=https://raw.githubusercontent.com/Agfsgsy/awesome-voice-ai-tools/%SOURCE_COMMIT%"
set "PROJECT="
if exist "%USERPROFILE%\Desktop\VoiceAIStudio-Pro-Latest\VoiceAIStudio.spec" set "PROJECT=%USERPROFILE%\Desktop\VoiceAIStudio-Pro-Latest"
if not defined PROJECT if exist "%USERPROFILE%\OneDrive\Desktop\VoiceAIStudio-Pro-Latest\VoiceAIStudio.spec" set "PROJECT=%USERPROFILE%\OneDrive\Desktop\VoiceAIStudio-Pro-Latest"
if not defined PROJECT if exist "%USERPROFILE%\Downloads\VoiceAIStudio-Pro-Latest\VoiceAIStudio.spec" set "PROJECT=%USERPROFILE%\Downloads\VoiceAIStudio-Pro-Latest"
if not defined PROJECT if exist "%USERPROFILE%\Desktop\awesome-voice-ai-tools-agent-professional-tts-engine\VoiceAIStudio.spec" set "PROJECT=%USERPROFILE%\Desktop\awesome-voice-ai-tools-agent-professional-tts-engine"
if not defined PROJECT if exist "%USERPROFILE%\Downloads\awesome-voice-ai-tools-agent-professional-tts-engine\VoiceAIStudio.spec" set "PROJECT=%USERPROFILE%\Downloads\awesome-voice-ai-tools-agent-professional-tts-engine"

if not defined PROJECT (
  echo ERROR: Project folder was not found.
  echo Expected VoiceAIStudio-Pro-Latest on Desktop or Downloads.
  pause
  exit /b 1
)

set "STAMP=%RANDOM%%RANDOM%"
set "TEMPROOT=%TEMP%\IbnWaqadiXTTS98V3-%STAMP%"
set "BACKUP=%PROJECT%\Backups\XTTS98ExistingMainV3-620-%STAMP%"
set "EXISTING=%BACKUP%\existing.txt"
set "NEWFILES=%BACKUP%\new.txt"
set "PATCHER=%TEMPROOT%\patch_xtts_98_existing_main.py"
set "SETUP=%PROJECT%\dist-installer\VoiceAIStudioSetup.exe"
set "INSTALLDIR=%LOCALAPPDATA%\Programs\Voice AI Studio Arabic Pro"
set "APP=%INSTALLDIR%\VoiceAIStudioArabic.exe"
set "DATA=%LOCALAPPDATA%\VoiceAIStudioArabic"
set "OLDINSTALL="
set "OLD_BUILD="
set "OLD_DIST="
set "OLD_INSTALLER="

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
echo  Ibn Al-Waqadi Studio 6.2 - XTTS 98 Percent Repair V3
echo ========================================================================
echo Project: %PROJECT%
echo.
echo This repair DOES NOT replace main.py or any HTML interface.
echo It patches only the existing Voice Clone import block and XTTS runtime files.
echo It preserves the downloaded model, keys, profiles, samples, consent records,
echo generated audio, shila projects, Gemini settings and the complete current UI.
echo Backup: %BACKUP%
echo.

echo [1/9] Closing Studio and local XTTS workers only...
taskkill /f /t /im VoiceAIStudioArabic.exe >nul 2>&1
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
  "$root=Join-Path $env:LOCALAPPDATA 'VoiceAIStudioArabic\voice_clones\local_engine';" ^
  "Get-CimInstance Win32_Process | Where-Object {" ^
  "  (([string]$_.ExecutablePath).StartsWith($root,[StringComparison]::OrdinalIgnoreCase)) -or" ^
  "  (([string]$_.CommandLine).IndexOf($root,[StringComparison]::OrdinalIgnoreCase) -ge 0)" ^
  "} | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1
timeout /t 3 /nobreak >nul

echo [2/9] Backing up only the source files touched by this repair...
call :apply "backend\api\voice_clone_repair_runtime.py" "backend/api/voice_clone_repair_runtime.py"
if errorlevel 1 goto :rollback
call :apply "backend\api\voice_clone_routes.py" "backend/api/voice_clone_routes.py"
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
call :apply "backend\api\voice_clone_fast_runtime_patch.py" "backend/api/voice_clone_fast_runtime_patch.py"
if errorlevel 1 goto :rollback

if exist "%PROJECT%\main.py" (
  copy /y "%PROJECT%\main.py" "%BACKUP%\main.py" >nul
  if errorlevel 1 goto :rollback
  echo main.py>>"%EXISTING%"
) else (
  echo ERROR: Existing main.py was not found.
  goto :rollback
)

curl.exe -L --fail --silent --show-error "%RAW%/scripts/patch_xtts_98_existing_main.py" -o "%PATCHER%"
if errorlevel 1 goto :rollback
if not exist "%PATCHER%" goto :rollback

echo [3/9] Patching the existing main.py without changing its UI imports...
pushd "%PROJECT%"
py -3.11 "%PATCHER%" "%PROJECT%\main.py"
set "PATCH_RESULT=%ERRORLEVEL%"
popd
if not "%PATCH_RESULT%"=="0" goto :rollback

echo [4/9] Compiling XTTS files and finalizing the existing downloaded model...
pushd "%PROJECT%"
py -3.11 -m py_compile ^
  "backend\api\voice_clone_repair_runtime.py" ^
  "backend\api\voice_clone_routes.py" ^
  "backend\api\voice_clone_xtts_runtime.py" ^
  "backend\api\voice_clone_download_resume_patch.py" ^
  "backend\api\voice_clone_download_source_fix.py" ^
  "backend\api\voice_clone_98_finalize_patch.py" ^
  "backend\api\voice_clone_auto_finalize_patch.py" ^
  "backend\api\voice_clone_fast_runtime_patch.py" ^
  "main.py"
set "COMPILE_RESULT=%ERRORLEVEL%"
if "%COMPILE_RESULT%"=="0" (
  py -3.11 -c "import importlib; r=importlib.import_module('backend.api.voice_clone_download_resume_patch'); p=importlib.import_module('backend.api.voice_clone_repair_runtime'); importlib.import_module('backend.api.voice_clone_download_source_fix'); importlib.import_module('backend.api.voice_clone_auto_finalize_patch'); d=r._model_dir(); print('XTTS_MODULES_OK'); print('XTTS_MODEL_MB=',round(r._directory_bytes(d)/1048576,1)); print('XTTS_MARKER=',p.MODEL_MARKER.exists()); assert r._model_complete(d), 'XTTS model files are incomplete'; assert p.MODEL_MARKER.exists(), 'XTTS ready marker was not created'"
  set "IMPORT_RESULT=!ERRORLEVEL!"
) else (
  set "IMPORT_RESULT=1"
)
popd
if not "%COMPILE_RESULT%"=="0" goto :rollback
if not "%IMPORT_RESULT%"=="0" goto :rollback

echo [5/9] Preserving previous build folders instead of deleting them...
if exist "%PROJECT%\build" (
  set "OLD_BUILD=%BACKUP%\old-build"
  move "%PROJECT%\build" "!OLD_BUILD!" >nul
)
if exist "%PROJECT%\dist" (
  set "OLD_DIST=%BACKUP%\old-dist"
  move "%PROJECT%\dist" "!OLD_DIST!" >nul
)
if exist "%PROJECT%\dist-installer" (
  set "OLD_INSTALLER=%BACKUP%\old-dist-installer"
  move "%PROJECT%\dist-installer" "!OLD_INSTALLER!" >nul
)

echo [6/9] Building the desktop application directly, without old validators...
pushd "%PROJECT%"
py -3.11 -m PyInstaller --noconfirm --clean VoiceAIStudio.spec
set "BUILD_RESULT=%ERRORLEVEL%"
popd
if not "%BUILD_RESULT%"=="0" goto :rollback
if not exist "%PROJECT%\dist\VoiceAIStudioArabic\VoiceAIStudioArabic.exe" goto :rollback

echo [7/9] Building VoiceAIStudioSetup.exe directly...
call :find_iscc
if not defined ISCC (
  echo ERROR: Inno Setup 6 was not found.
  goto :rollback
)
if not exist "%PROJECT%\dist-installer" mkdir "%PROJECT%\dist-installer" >nul 2>&1
"%ISCC%" "%PROJECT%\installer\VoiceAIStudio.iss"
if errorlevel 1 goto :rollback
if not exist "%SETUP%" goto :rollback

echo [8/9] Unlocking and preserving the old installed program folder...
taskkill /f /t /im VoiceAIStudioArabic.exe >nul 2>&1
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
  "$install=[IO.Path]::GetFullPath('%INSTALLDIR%').TrimEnd('\')+'\';" ^
  "$clone=Join-Path $env:LOCALAPPDATA 'VoiceAIStudioArabic\voice_clones\local_engine';" ^
  "Get-CimInstance Win32_Process | ForEach-Object {" ^
  " $e=[string]$_.ExecutablePath; $c=[string]$_.CommandLine;" ^
  " if(($e -and ($e.StartsWith($install,[StringComparison]::OrdinalIgnoreCase) -or $e.StartsWith($clone,[StringComparison]::OrdinalIgnoreCase))) -or ($c -and $c.IndexOf($install,[StringComparison]::OrdinalIgnoreCase) -ge 0)){ Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" ^
  "}" >nul 2>&1
timeout /t 4 /nobreak >nul

if exist "%INSTALLDIR%" (
  for /f "usebackq delims=" %%B in (`powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$src='%INSTALLDIR%';$dst=$src+'.backup-'+(Get-Date -Format 'yyyyMMdd-HHmmss');Move-Item -LiteralPath $src -Destination $dst -Force;Write-Output $dst"`) do set "OLDINSTALL=%%B"
  if exist "%INSTALLDIR%" (
    echo ERROR: Windows still locks a file in the old install.
    echo Restart Windows, do not open Studio, then run this same V3 command again.
    goto :rollback
  )
)

echo [9/9] Installing and starting Studio 6.2.0...
start "" /wait "%SETUP%" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP- /CLOSEAPPLICATIONS /FORCECLOSEAPPLICATIONS /TASKS=desktopicon
set "INSTALL_RESULT=%ERRORLEVEL%"
if not "%INSTALL_RESULT%"=="0" goto :restore_install
if not exist "%APP%" goto :restore_install
start "" "%APP%"
rmdir /s /q "%TEMPROOT%" >nul 2>&1

echo.
echo ========================================================================
echo SUCCESS: XTTS 98 Percent V3 was installed.
echo XTTS existing model is finalized at 100 percent without redownloading.
echo The existing main.py and complete UI were preserved and patched in place.
echo User data remains at: %DATA%
echo Source backup: %BACKUP%
if defined OLDINSTALL echo Old installed program backup: !OLDINSTALL!
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

:find_iscc
set "ISCC="
for %%P in (
  "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
  "%ProgramFiles%\Inno Setup 6\ISCC.exe"
  "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
) do if not defined ISCC if exist "%%~P" set "ISCC=%%~P"
if not defined ISCC for /f "delims=" %%P in ('where ISCC.exe 2^>nul') do if not defined ISCC set "ISCC=%%P"
exit /b 0

:restore_install
echo ERROR: Installation failed. Restoring the previous installed program folder...
if defined OLDINSTALL if exist "!OLDINSTALL!" if not exist "%INSTALLDIR%" move "!OLDINSTALL!" "%INSTALLDIR%" >nul
goto :rollback

:rollback
echo.
echo ERROR: XTTS 98 Percent V3 did not complete.
echo Restoring only source files changed by this repair...
if exist "%EXISTING%" for /f "usebackq delims=" %%R in ("%EXISTING%") do (
  if exist "%BACKUP%\%%R" copy /y "%BACKUP%\%%R" "%PROJECT%\%%R" >nul
)
if exist "%NEWFILES%" for /f "usebackq delims=" %%R in ("%NEWFILES%") do (
  if exist "%PROJECT%\%%R" del /q "%PROJECT%\%%R" >nul 2>&1
)
if defined OLD_BUILD if exist "!OLD_BUILD!" if not exist "%PROJECT%\build" move "!OLD_BUILD!" "%PROJECT%\build" >nul
if defined OLD_DIST if exist "!OLD_DIST!" if not exist "%PROJECT%\dist" move "!OLD_DIST!" "%PROJECT%\dist" >nul
if defined OLD_INSTALLER if exist "!OLD_INSTALLER!" if not exist "%PROJECT%\dist-installer" move "!OLD_INSTALLER!" "%PROJECT%\dist-installer" >nul
if exist "%TEMPROOT%" rmdir /s /q "%TEMPROOT%" >nul 2>&1
echo No key, profile, sample, XTTS model, audio, shila project or UI file was deleted.
echo Backup: %BACKUP%
pause
exit /b 1

:failed_no_rollback
echo ERROR: Repair could not start. No project or user file was changed.
pause
exit /b 1
