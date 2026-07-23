@echo off
echo ==================================================
echo Voice AI Studio Arabic - Windows Installer
echo ==================================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python 3.10+ from https://www.python.org/downloads/
    pause
    goto :EOF
)

REM Check if PowerShell is available
powershell -Command "Write-Host 'Check'" >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo [ERROR] PowerShell is not available. Please ensure it is installed and in your PATH.
    pause
    goto :EOF
)

echo Starting PowerShell installer...
powershell -ExecutionPolicy Bypass -File "%~dp0install_ai.ps1"

IF %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Installation failed.
) ELSE (
    echo [SUCCESS] Installation completed successfully.
)

pause
