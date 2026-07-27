@echo off
setlocal EnableExtensions
chcp 65001 >nul
title Ibn Al-Waqadi Studio 6.2 - Shila Zamil Music Fix Only

set "PROJECT="
if exist "%USERPROFILE%\Desktop\VoiceAIStudio-Pro-Latest\BUILD_WINDOWS_INSTALLER.bat" set "PROJECT=%USERPROFILE%\Desktop\VoiceAIStudio-Pro-Latest"
if not defined PROJECT if exist "%USERPROFILE%\OneDrive\Desktop\VoiceAIStudio-Pro-Latest\BUILD_WINDOWS_INSTALLER.bat" set "PROJECT=%USERPROFILE%\OneDrive\Desktop\VoiceAIStudio-Pro-Latest"
if not defined PROJECT if exist "%USERPROFILE%\Downloads\VoiceAIStudio-Pro-Latest\BUILD_WINDOWS_INSTALLER.bat" set "PROJECT=%USERPROFILE%\Downloads\VoiceAIStudio-Pro-Latest"
if not defined PROJECT if exist "%USERPROFILE%\Desktop\awesome-voice-ai-tools-agent-professional-tts-engine\BUILD_WINDOWS_INSTALLER.bat" set "PROJECT=%USERPROFILE%\Desktop\awesome-voice-ai-tools-agent-professional-tts-engine"
if not defined PROJECT if exist "%USERPROFILE%\Downloads\awesome-voice-ai-tools-agent-professional-tts-engine\BUILD_WINDOWS_INSTALLER.bat" set "PROJECT=%USERPROFILE%\Downloads\awesome-voice-ai-tools-agent-professional-tts-engine"

if not defined PROJECT (
  echo ERROR: Project folder was not found.
  echo Put VoiceAIStudio-Pro-Latest on Desktop and run this file again.
  pause
  exit /b 1
)

set "TARGET=%PROJECT%\backend\api\yemeni_creative_hotfix.py"
set "BACKUP=%TARGET%.before_music_fix_620.bak"
set "NEWFILE=%TEMP%\yemeni_creative_hotfix_music_620.py"
set "URL=https://raw.githubusercontent.com/Agfsgsy/awesome-voice-ai-tools/c35529935721a80ab413175284dd62d491332d11/backend/api/yemeni_creative_hotfix.py"
set "SETUP=%PROJECT%\dist-installer\VoiceAIStudioSetup.exe"
set "APP=%LOCALAPPDATA%\Programs\Voice AI Studio Arabic Pro\VoiceAIStudioArabic.exe"
set "ENTERFILE=%TEMP%\ibn_waqadi_enter.txt"

 echo.
echo ================================================================
echo  Shila and Zamil Music Fix Only - Studio 6.2.0
echo ================================================================
echo Project: %PROJECT%
echo Only the Yemeni music production backend will be updated.
echo No keys, sessions, samples, audio, projects or UI files will be deleted.
echo.

if not exist "%TARGET%" (
  echo ERROR: Target backend file was not found.
  pause
  exit /b 1
)

copy /y "%TARGET%" "%BACKUP%" >nul
if errorlevel 1 (
  echo ERROR: Could not create the source backup.
  pause
  exit /b 1
)

echo [1/5] Downloading the fixed music backend...
where curl.exe >nul 2>&1
if errorlevel 1 (
  echo ERROR: curl.exe is not available on this Windows installation.
  goto :rollback
)
curl.exe -L --fail --silent --show-error "%URL%" -o "%NEWFILE%"
if errorlevel 1 goto :rollback
if not exist "%NEWFILE%" goto :rollback
for %%F in ("%NEWFILE%") do if %%~zF LSS 4096 goto :rollback

echo [2/5] Checking Python syntax...
py -3.11 -m py_compile "%NEWFILE%"
if errorlevel 1 goto :rollback

copy /y "%NEWFILE%" "%TARGET%" >nul
if errorlevel 1 goto :rollback

taskkill /f /im VoiceAIStudioArabic.exe >nul 2>&1

echo [3/5] Building the same Studio 6.2.0 installer...
echo.>"%ENTERFILE%"
call "%PROJECT%\BUILD_WINDOWS_INSTALLER.bat" < "%ENTERFILE%"
if errorlevel 1 goto :rollback

if not exist "%SETUP%" (
  echo ERROR: Installer was not created.
  goto :rollback
)

echo [4/5] Installing the music fix...
start "" /wait "%SETUP%" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP- /TASKS=desktopicon
if errorlevel 1 goto :rollback

if not exist "%APP%" (
  echo ERROR: Installed application was not found.
  goto :rollback
)

echo [5/5] Starting the repaired studio...
start "" "%APP%"

del /q "%NEWFILE%" "%ENTERFILE%" >nul 2>&1

echo.
echo SUCCESS: Shila and zamil music production was repaired.
echo The final shila/zamil now requires audible Yemeni music.
echo Backup: %BACKUP%
pause
exit /b 0

:rollback
echo.
echo ERROR: The music-only repair did not complete.
echo Restoring the previous backend file...
if exist "%BACKUP%" copy /y "%BACKUP%" "%TARGET%" >nul
if exist "%NEWFILE%" del /q "%NEWFILE%" >nul 2>&1
if exist "%ENTERFILE%" del /q "%ENTERFILE%" >nul 2>&1
echo No user data was deleted or changed.
pause
exit /b 1
