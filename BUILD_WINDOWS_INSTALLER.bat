@echo off
setlocal
cd /d "%~dp0"
title Voice AI Studio - Build Installer

echo Voice AI Studio Arabic - Windows Installer Builder
echo.

where py >nul 2>&1
if errorlevel 1 (
  echo Python Launcher is not installed.
  pause
  exit /b 1
)

py -m pip install --upgrade pip
if errorlevel 1 goto failed
py -m pip install -r requirements.txt -r requirements-desktop.txt
if errorlevel 1 goto failed

py -m PyInstaller --noconfirm --clean VoiceAIStudio.spec
if errorlevel 1 goto failed

set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" (
  echo The desktop program was built successfully.
  echo Run dist\VoiceAIStudio\VoiceAIStudio.exe
  echo Install Inno Setup 6 to create the Setup file.
  pause
  exit /b 0
)

"%ISCC%" installer\VoiceAIStudio.iss
if errorlevel 1 goto failed

echo.
echo Installer created in the dist_installer folder.
pause
exit /b 0

:failed
echo Build failed. Review the messages above.
pause
exit /b 1
