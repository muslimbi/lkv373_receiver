@echo off
setlocal enabledelayedexpansion
title LKV373 HDMI-over-IP MJPEG Receiver

echo ==================================================
echo   LKV373 HDMI-over-IP MJPEG Receiver Launcher
echo ==================================================
echo.

:: Check Python availability
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python is not installed or not in PATH!
    echo Please install Python 3.10 or higher and add it to your system PATH.
    pause
    exit /b 1
)

:: Run main.py with passed arguments
python "%~dp0main.py" %*

if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Application exited with error code %ERRORLEVEL%
    pause
)
