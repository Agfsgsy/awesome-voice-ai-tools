@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Ibn Al-Waqadi Studio - Unified Windows Setup Builder

echo =====================================================
echo   Ibn Al-Waqadi Studio 5.1 - Free First Builder
echo =====================================================
echo.

set "PY=py -3.11"
%PY% -V >nul 2>&1
if errorlevel 1 (
  where winget >nul 2>&1
  if errorlevel 1 (
    echo [ERROR] Python 3.11 is missing and Windows Package Manager was not found.
    echo Install Python 3.11, then run this file again.
    pause
    exit /b 1
  )
  echo Installing Python 3.11 automatically...
  winget install --id Python.Python.3.11 --exact --silent --accept-package-agreements --accept-source-agreements
  %PY% -V >nul 2>&1
  if errorlevel 1 (
    echo [ERROR] Python 3.11 installation did not complete. Restart Windows and try again.
    pause
    exit /b 1
  )
)

echo [1/5] Installing build dependencies...
%PY% -m pip install --upgrade pip wheel
if errorlevel 1 goto :failed
%PY% -m pip install -r requirements.txt -r requirements-desktop.txt
if errorlevel 1 goto :failed

echo [2/5] Compiling source files...
%PY% -m compileall -q main.py desktop_app.py backend scripts
if errorlevel 1 goto :failed

echo [3/5] Validating versions, free-first audio, and API contracts...
%PY% scripts\validate_unified_release.py
if errorlevel 1 goto :failed

echo [4/5] Building standalone desktop application...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
%PY% -m PyInstaller --noconfirm --clean VoiceAIStudio.spec
if errorlevel 1 goto :failed
if not exist "dist\VoiceAIStudioArabic\VoiceAIStudioArabic.exe" goto :failed

echo [5/5] Building Setup.exe...
call :find_iscc
if not defined ISCC (
  where winget >nul 2>&1
  if not errorlevel 1 (
    echo Installing Inno Setup automatically...
    winget install --id JRSoftware.InnoSetup --exact --silent --accept-package-agreements --accept-source-agreements
    timeout /t 5 /nobreak >nul
    call :find_iscc
  )
)
if not defined ISCC (
  echo [ERROR] Inno Setup 6 was installed but ISCC.exe could not be located.
  echo Close this window, open a new Command Prompt, and run the builder again.
  pause
  exit /b 1
)

if exist dist-installer rmdir /s /q dist-installer
echo Using Inno Setup: %ISCC%
"%ISCC%" "installer\VoiceAIStudio.iss"
if errorlevel 1 goto :failed
if not exist "dist-installer\VoiceAIStudioSetup.exe" goto :failed

echo.
echo [SUCCESS] Unified Studio 5.1 installer created:
echo %CD%\dist-installer\VoiceAIStudioSetup.exe
start "" explorer.exe "%CD%\dist-installer"
pause
exit /b 0

:find_iscc
set "ISCC="
for %%P in (
  "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
  "%ProgramFiles%\Inno Setup 6\ISCC.exe"
  "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
  "%USERPROFILE%\AppData\Local\Programs\Inno Setup 6\ISCC.exe"
) do if not defined ISCC if exist "%%~P" set "ISCC=%%~P"
if not defined ISCC for /f "delims=" %%P in ('where ISCC.exe 2^>nul') do if not defined ISCC set "ISCC=%%P"
if not defined ISCC for /f "delims=" %%P in ('where /r "%ProgramFiles%" ISCC.exe 2^>nul') do if not defined ISCC set "ISCC=%%P"
if not defined ISCC if defined ProgramFiles(x86) for /f "delims=" %%P in ('where /r "%ProgramFiles(x86)%" ISCC.exe 2^>nul') do if not defined ISCC set "ISCC=%%P"
if not defined ISCC for /f "delims=" %%P in ('where /r "%LOCALAPPDATA%" ISCC.exe 2^>nul') do if not defined ISCC set "ISCC=%%P"
exit /b 0

:failed
echo.
echo [ERROR] Unified build validation or packaging failed. Review the message above.
pause
exit /b 1
