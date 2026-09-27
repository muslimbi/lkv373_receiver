@echo off
setlocal
title LKV373 PCAP Playback Launcher

echo ==================================================
echo   LKV373 PCAP Capture File Playback Launcher
echo ==================================================
echo.

set "PCAP_FILE=%~1"

if "%PCAP_FILE%"=="" (
    if exist "sample_capture.bin" (
        set "PCAP_FILE=sample_capture.bin"
    ) else (
        set /p "PCAP_FILE=Enter path to PCAP/PCAPNG/BIN file: "
    )
)

if not exist "%PCAP_FILE%" (
    echo [ERROR] File not found: %PCAP_FILE%
    pause
    exit /b 1
)

echo Playing back capture file: %PCAP_FILE% ...
python "%~dp0main.py" --pcap "%PCAP_FILE%"

if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Application exited with error code %ERRORLEVEL%
    pause
)
