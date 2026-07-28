@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
title Ibn Al-Waqadi Studio 6.2 - Safe Installer Unlock

set "PROJECT="
if exist "%USERPROFILE%\Desktop\VoiceAIStudio-Pro-Latest\dist-installer\VoiceAIStudioSetup.exe" set "PROJECT=%USERPROFILE%\Desktop\VoiceAIStudio-Pro-Latest"
if not defined PROJECT if exist "%USERPROFILE%\OneDrive\Desktop\VoiceAIStudio-Pro-Latest\dist-installer\VoiceAIStudioSetup.exe" set "PROJECT=%USERPROFILE%\OneDrive\Desktop\VoiceAIStudio-Pro-Latest"
if not defined PROJECT if exist "%USERPROFILE%\Downloads\VoiceAIStudio-Pro-Latest\dist-installer\VoiceAIStudioSetup.exe" set "PROJECT=%USERPROFILE%\Downloads\VoiceAIStudio-Pro-Latest"
if not defined PROJECT if exist "%USERPROFILE%\Desktop\awesome-voice-ai-tools-agent-professional-tts-engine\dist-installer\VoiceAIStudioSetup.exe" set "PROJECT=%USERPROFILE%\Desktop\awesome-voice-ai-tools-agent-professional-tts-engine"
if not defined PROJECT if exist "%USERPROFILE%\Downloads\awesome-voice-ai-tools-agent-professional-tts-engine\dist-installer\VoiceAIStudioSetup.exe" set "PROJECT=%USERPROFILE%\Downloads\awesome-voice-ai-tools-agent-professional-tts-engine"

if not defined PROJECT (
  echo ERROR: The completed VoiceAIStudioSetup.exe was not found.
  echo Expected folder: Desktop\VoiceAIStudio-Pro-Latest\dist-installer
  pause
  exit /b 1
)

set "SETUP=%PROJECT%\dist-installer\VoiceAIStudioSetup.exe"
set "INSTALLDIR=%LOCALAPPDATA%\Programs\Voice AI Studio Arabic Pro"
set "APP=%INSTALLDIR%\VoiceAIStudioArabic.exe"
set "DATA=%LOCALAPPDATA%\VoiceAIStudioArabic"

cls
echo ========================================================================
echo  Ibn Al-Waqadi Studio 6.2 - Safe Installation Retry
echo ========================================================================
echo.
echo The Windows build already succeeded. This tool only unlocks the old install
echo and installs the completed Setup file. It does not rebuild or edit source.
echo.
echo Preserved:
echo   - %DATA%
echo   - keys, profiles, consent records and voice samples
echo   - partial XTTS model downloads
 echo  - generated audio, shila projects and Desktop exports
echo   - the entire old program folder as a backup
 echo.

if not exist "%SETUP%" (
  echo ERROR: Setup file is missing: %SETUP%
  pause
  exit /b 1
)

for %%F in ("%SETUP%") do echo Setup: %%~fF  ^(%%~zF bytes^)
echo.

echo [1/6] Closing Ibn Al-Waqadi Studio and its child processes...
taskkill /f /t /im VoiceAIStudioArabic.exe >nul 2>&1

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
  "$install=[IO.Path]::GetFullPath('%INSTALLDIR%').TrimEnd('\')+'\';" ^
  "$data=[IO.Path]::GetFullPath('%DATA%').TrimEnd('\')+'\';" ^
  "$clone=Join-Path $env:LOCALAPPDATA 'VoiceAIStudioArabic\voice_clones\local_engine';" ^
  "$self=$PID;" ^
  "Get-CimInstance Win32_Process | ForEach-Object {" ^
  "  $p=$_; $exe=[string]$p.ExecutablePath; $cmd=[string]$p.CommandLine;" ^
  "  $owned=($exe -and ($exe.StartsWith($install,[StringComparison]::OrdinalIgnoreCase) -or $exe.StartsWith($clone,[StringComparison]::OrdinalIgnoreCase))) -or" ^
  "         ($cmd -and ($cmd.IndexOf('VoiceAIStudioArabic',[StringComparison]::OrdinalIgnoreCase) -ge 0 -or $cmd.IndexOf($data,[StringComparison]::OrdinalIgnoreCase) -ge 0));" ^
  "  if($owned -and $p.ProcessId -ne $self){ Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue }" ^
  "}" >nul 2>&1

timeout /t 4 /nobreak >nul

echo [2/6] Confirming no studio process is still using the old files...
set "LEFTOVER=0"
for /f %%C in ('powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$install=[IO.Path]::GetFullPath('%INSTALLDIR%').TrimEnd('\')+'\'; @(Get-CimInstance Win32_Process ^| Where-Object { ([string]$_.ExecutablePath).StartsWith($install,[StringComparison]::OrdinalIgnoreCase) }).Count"') do set "LEFTOVER=%%C"
if not "%LEFTOVER%"=="0" (
  echo ERROR: %LEFTOVER% studio process^(es^) still hold the installation folder.
  echo Restart Windows, do not open the studio, then run this same command again.
  pause
  exit /b 1
)

echo [3/6] Preserving the complete old installed program folder...
set "OLD_BACKUP="
if exist "%INSTALLDIR%" (
  for /f "usebackq delims=" %%B in (`powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$src='%INSTALLDIR%'; $stamp=Get-Date -Format 'yyyyMMdd-HHmmss'; $dst=$src+'.backup-'+$stamp; Move-Item -LiteralPath $src -Destination $dst -Force; Write-Output $dst"`) do set "OLD_BACKUP=%%B"
  if exist "%INSTALLDIR%" (
    echo ERROR: Windows still has a file locked inside:
    echo %INSTALLDIR%
    echo.
    echo Restart Windows, do not open the studio, then run this command again.
    pause
    exit /b 1
  )
  if not defined OLD_BACKUP (
    echo ERROR: The old install folder could not be preserved.
    pause
    exit /b 1
  )
  echo Old program backup: !OLD_BACKUP!
) else (
  echo No complete old program folder was present. User data remains untouched.
)

echo [4/6] Installing the already-built corrected Studio 6.2.0...
start "" /wait "%SETUP%" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP- /CLOSEAPPLICATIONS /FORCECLOSEAPPLICATIONS /TASKS=desktopicon
set "INSTALL_RESULT=%ERRORLEVEL%"
if not "%INSTALL_RESULT%"=="0" goto :restore
if not exist "%APP%" goto :restore

echo [5/6] Verifying the installed executable...
for %%F in ("%APP%") do if %%~zF LSS 100000 goto :restore

echo [6/6] Starting Ibn Al-Waqadi Studio...
start "" "%APP%"

echo.
echo ========================================================================
echo SUCCESS: The corrected build was installed without deleting user data.
if defined OLD_BACKUP echo Old program backup: !OLD_BACKUP!
echo User data remains at: %DATA%
echo ========================================================================
pause
exit /b 0

:restore
echo.
echo ERROR: Installation did not complete. Code: %INSTALL_RESULT%
echo The user data folder was never changed.
if defined OLD_BACKUP if exist "!OLD_BACKUP!" if not exist "%INSTALLDIR%" (
  echo Restoring the complete old installed program folder...
  move "!OLD_BACKUP!" "%INSTALLDIR%" >nul
)
echo No keys, profiles, samples, XTTS downloads, audio or projects were deleted.
pause
exit /b 1
