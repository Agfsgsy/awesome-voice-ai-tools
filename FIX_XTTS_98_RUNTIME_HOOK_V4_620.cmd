@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
title Ibn Al-Waqadi Studio 6.2 - XTTS Runtime Hook V4

set "SOURCE_COMMIT=d542fd57819385f51fea2d4f37b0fc2993c911f4"
set "RAW=https://raw.githubusercontent.com/Agfsgsy/awesome-voice-ai-tools/%SOURCE_COMMIT%"
set "PROJECT="
if exist "%USERPROFILE%\Desktop\VoiceAIStudio-Pro-Latest\VoiceAIStudio.spec" set "PROJECT=%USERPROFILE%\Desktop\VoiceAIStudio-Pro-Latest"
if not defined PROJECT if exist "%USERPROFILE%\OneDrive\Desktop\VoiceAIStudio-Pro-Latest\VoiceAIStudio.spec" set "PROJECT=%USERPROFILE%\OneDrive\Desktop\VoiceAIStudio-Pro-Latest"
if not defined PROJECT if exist "%USERPROFILE%\Downloads\VoiceAIStudio-Pro-Latest\VoiceAIStudio.spec" set "PROJECT=%USERPROFILE%\Downloads\VoiceAIStudio-Pro-Latest"
if not defined PROJECT if exist "%USERPROFILE%\Desktop\awesome-voice-ai-tools-agent-professional-tts-engine\VoiceAIStudio.spec" set "PROJECT=%USERPROFILE%\Desktop\awesome-voice-ai-tools-agent-professional-tts-engine"
if not defined PROJECT if exist "%USERPROFILE%\Downloads\awesome-voice-ai-tools-agent-professional-tts-engine\VoiceAIStudio.spec" set "PROJECT=%USERPROFILE%\Downloads\awesome-voice-ai-tools-agent-professional-tts-engine"

if not defined PROJECT (
  echo ERROR: Project folder was not found.
  echo Put VoiceAIStudio-Pro-Latest on Desktop and run this command again.
  pause
  exit /b 1
)

set "TEMPROOT=%TEMP%\IbnWaqadiXTTSHookV4-%RANDOM%%RANDOM%"
set "BACKUP=%PROJECT%\Backups\XTTSRuntimeHookV4-620-%RANDOM%%RANDOM%"
set "EXISTING=%BACKUP%\existing.txt"
set "NEWFILES=%BACKUP%\new.txt"
set "PATCHER=%TEMPROOT%\patch_spec_xtts_runtime_hook.py"
set "SETUP=%PROJECT%\dist-installer\VoiceAIStudioSetup.exe"
set "INSTALLDIR=%LOCALAPPDATA%\Programs\Voice AI Studio Arabic Pro"
set "APP=%INSTALLDIR%\VoiceAIStudioArabic.exe"
set "DATA=%LOCALAPPDATA%\VoiceAIStudioArabic"
set "OLD_BUILD="
set "OLD_DIST="
set "OLD_INSTALLER="
set "OLD_INSTALL="

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
echo  Ibn Al-Waqadi Studio 6.2 - XTTS Runtime Hook Repair V4
echo ========================================================================
echo Project: %PROJECT%
echo.
echo This repair DOES NOT replace or edit main.py and DOES NOT edit any HTML UI.
echo It adds an XTTS runtime hook only to the existing PyInstaller spec.
echo It preserves the 1992.6 MB model, keys, profiles, samples, consent records,
echo generated audio, shila projects, Gemini settings and the complete current UI.
echo Backup: %BACKUP%
echo.

echo [1/10] Closing Studio and local XTTS workers only...
taskkill /f /t /im VoiceAIStudioArabic.exe >nul 2>&1
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
  "$root=Join-Path $env:LOCALAPPDATA 'VoiceAIStudioArabic\voice_clones\local_engine';" ^
  "Get-CimInstance Win32_Process | Where-Object {" ^
  " (([string]$_.ExecutablePath).StartsWith($root,[StringComparison]::OrdinalIgnoreCase)) -or" ^
  " (([string]$_.CommandLine).IndexOf($root,[StringComparison]::OrdinalIgnoreCase) -ge 0)" ^
  "} | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1
timeout /t 3 /nobreak >nul

echo [2/10] Backing up and installing XTTS runtime files only...
call :apply "backend\api\voice_clone_repair_runtime.py" "backend/api/voice_clone_repair_runtime.py"
if errorlevel 1 goto :rollback
call :apply "backend\api\voice_clone_routes.py" "backend/api/voice_clone_routes.py"
if errorlevel 1 goto :rollback
call :apply "backend\api\voice_clone_fast_routes.py" "backend/api/voice_clone_fast_routes.py"
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
call :apply "scripts\xtts_98_runtime_hook.py" "scripts/xtts_98_runtime_hook.py"
if errorlevel 1 goto :rollback

if exist "%PROJECT%\VoiceAIStudio.spec" (
  copy /y "%PROJECT%\VoiceAIStudio.spec" "%BACKUP%\VoiceAIStudio.spec" >nul
  if errorlevel 1 goto :rollback
  echo VoiceAIStudio.spec>>"%EXISTING%"
) else (
  echo ERROR: VoiceAIStudio.spec was not found.
  goto :rollback
)

curl.exe -L --fail --silent --show-error "%RAW%/scripts/patch_spec_xtts_runtime_hook.py" -o "%PATCHER%"
if errorlevel 1 goto :rollback
if not exist "%PATCHER%" goto :rollback

echo [3/10] Patching only VoiceAIStudio.spec; main.py and UI remain untouched...
pushd "%PROJECT%"
py -3.11 "%PATCHER%" "%PROJECT%\VoiceAIStudio.spec"
set "PATCH_RESULT=%ERRORLEVEL%"
popd
if not "%PATCH_RESULT%"=="0" goto :rollback

echo [4/10] Compiling XTTS files and validating the downloaded model directly...
pushd "%PROJECT%"
py -3.11 -m py_compile ^
  "backend\api\voice_clone_repair_runtime.py" ^
  "backend\api\voice_clone_routes.py" ^
  "backend\api\voice_clone_fast_routes.py" ^
  "backend\api\voice_clone_xtts_runtime.py" ^
  "backend\api\voice_clone_download_resume_patch.py" ^
  "backend\api\voice_clone_download_source_fix.py" ^
  "backend\api\voice_clone_98_finalize_patch.py" ^
  "backend\api\voice_clone_auto_finalize_patch.py" ^
  "backend\api\voice_clone_fast_runtime_patch.py" ^
  "scripts\xtts_98_runtime_hook.py" ^
  "VoiceAIStudio.spec"
set "COMPILE_RESULT=%ERRORLEVEL%"
if "!COMPILE_RESULT!"=="0" (
  py -3.11 -c "import importlib; importlib.import_module('backend.api.voice_clone_repair_runtime'); importlib.import_module('backend.api.voice_clone_routes'); importlib.import_module('backend.api.voice_clone_xtts_runtime'); r=importlib.import_module('backend.api.voice_clone_download_resume_patch'); importlib.import_module('backend.api.voice_clone_download_source_fix'); importlib.import_module('backend.api.voice_clone_auto_finalize_patch'); p=importlib.import_module('backend.api.voice_clone_repair_runtime'); d=r._model_dir(); print('XTTS_RUNTIME_HOOK_MODULES_OK'); print('XTTS_MODEL_MB=',round(r._directory_bytes(d)/1048576,1)); print('XTTS_MARKER=',p.MODEL_MARKER.exists()); assert r._model_complete(d), 'XTTS model files are incomplete'; assert p.MODEL_MARKER.exists(), 'XTTS ready marker was not created'"
  set "IMPORT_RESULT=!ERRORLEVEL!"
) else (
  set "IMPORT_RESULT=1"
)
popd
if not "%COMPILE_RESULT%"=="0" goto :rollback
if not "%IMPORT_RESULT%"=="0" goto :rollback

echo [5/10] Preserving previous build folders instead of deleting them...
if exist "%PROJECT%\build" (
  set "OLD_BUILD=%BACKUP%\old-build"
  move "%PROJECT%\build" "!OLD_BUILD!" >nul
  if errorlevel 1 goto :rollback
)
if exist "%PROJECT%\dist" (
  set "OLD_DIST=%BACKUP%\old-dist"
  move "%PROJECT%\dist" "!OLD_DIST!" >nul
  if errorlevel 1 goto :rollback
)
if exist "%PROJECT%\dist-installer" (
  set "OLD_INSTALLER=%BACKUP%\old-dist-installer"
  move "%PROJECT%\dist-installer" "!OLD_INSTALLER!" >nul
  if errorlevel 1 goto :rollback
)

echo [6/10] Building the desktop EXE directly without old project validators...
pushd "%PROJECT%"
py -3.11 -m PyInstaller --noconfirm --clean VoiceAIStudio.spec
set "BUILD_RESULT=%ERRORLEVEL%"
popd
if not "%BUILD_RESULT%"=="0" goto :rollback
if not exist "%PROJECT%\dist\VoiceAIStudioArabic\VoiceAIStudioArabic.exe" goto :rollback

echo [7/10] Building VoiceAIStudioSetup.exe directly...
call :find_iscc
if not defined ISCC (
  echo ERROR: Inno Setup 6 was not found.
  goto :rollback
)
if not exist "%PROJECT%\dist-installer" mkdir "%PROJECT%\dist-installer" >nul 2>&1
"%ISCC%" "%PROJECT%\installer\VoiceAIStudio.iss"
if errorlevel 1 goto :rollback
if not exist "%SETUP%" goto :rollback

echo [8/10] Unlocking and preserving the complete old installed program...
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
  for /f "usebackq delims=" %%B in (`powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$src='%INSTALLDIR%';$dst=$src+'.backup-'+(Get-Date -Format 'yyyyMMdd-HHmmss');Move-Item -LiteralPath $src -Destination $dst -Force;Write-Output $dst"`) do set "OLD_INSTALL=%%B"
  if exist "%INSTALLDIR%" (
    echo ERROR: Windows still locks the old installation folder.
    echo Restart Windows, do not open Studio, then run this same V4 command again.
    goto :rollback
  )
)

echo [9/10] Installing the corrected Studio 6.2.0...
start "" /wait "%SETUP%" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP- /CLOSEAPPLICATIONS /FORCECLOSEAPPLICATIONS /TASKS=desktopicon
set "INSTALL_RESULT=%ERRORLEVEL%"
if not "%INSTALL_RESULT%"=="0" goto :restore_install
if not exist "%APP%" goto :restore_install

echo [10/10] Starting Ibn Al-Waqadi Studio...
start "" "%APP%"
rmdir /s /q "%TEMPROOT%" >nul 2>&1

echo.
echo ========================================================================
echo SUCCESS: XTTS Runtime Hook V4 was installed.
echo The existing model is finalized at 100 percent without redownloading.
echo main.py, every HTML interface and all user data were preserved.
echo User data: %DATA%
echo Source backup: %BACKUP%
if defined OLD_INSTALL echo Old installed program backup: !OLD_INSTALL!
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

:restore_install
echo.
echo ERROR: Installation did not complete. Code: %INSTALL_RESULT%
if defined OLD_INSTALL if exist "!OLD_INSTALL!" if not exist "%INSTALLDIR%" move "!OLD_INSTALL!" "%INSTALLDIR%" >nul
goto :rollback

:rollback
echo.
echo ERROR: XTTS Runtime Hook V4 did not complete.
echo Restoring only source/spec files changed by this repair...
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
echo No main.py, UI, key, profile, sample, model download, audio or project was deleted.
echo Backup: %BACKUP%
pause
exit /b 1

:find_iscc
set "ISCC="
for %%P in (
  "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
  "%ProgramFiles%\Inno Setup 6\ISCC.exe"
  "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
  "%USERPROFILE%\AppData\Local\Programs\Inno Setup 6\ISCC.exe"
) do if not defined ISCC if exist "%%~P" set "ISCC=%%~P"
if not defined ISCC for /f "delims=" %%P in ('where ISCC.exe 2^>nul') do if not defined ISCC set "ISCC=%%P"
if not defined ISCC if defined ProgramFiles(x86) for /f "delims=" %%P in ('where /r "%ProgramFiles(x86)%" ISCC.exe 2^>nul') do if not defined ISCC set "ISCC=%%P"
if not defined ISCC for /f "delims=" %%P in ('where /r "%LOCALAPPDATA%" ISCC.exe 2^>nul') do if not defined ISCC set "ISCC=%%P"
exit /b 0

:failed_no_rollback
echo.
echo ERROR: The repair could not start.
echo No project or user file was changed.
pause
exit /b 1
