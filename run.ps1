<#
.SYNOPSIS
    LKV373 HDMI-over-IP MJPEG Receiver PowerShell Launcher
.DESCRIPTION
    Launches the LKV373 HDMI-over-IP Receiver Python application.
.EXAMPLE
    .\run.ps1
    .\run.ps1 --group 226.2.2.2 --port 2068
    .\run.ps1 --pcap sample_capture.bin
    .\run.ps1 --fullscreen --monitor 0
#>

[CmdletBinding()]
param(
    [ValueFromRemainingArguments($true)]
    [string[]]$AppArgs
)

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  LKV373 HDMI-over-IP MJPEG Receiver Launcher" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host ""

# Verify Python installation
$PythonCmd = Get-Command python -ErrorAction SilentlyContinue

if (-not $PythonCmd) {
    Write-Host "[ERROR] Python is not installed or not found in system PATH!" -ForegroundColor Red
    Write-Host "Please install Python 3.10+ and ensure 'python' is accessible." -ForegroundColor Yellow
    Pause
    exit 1
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$MainScript = Join-Path $ScriptDir "main.py"

Write-Host "Launching LKV373 Receiver..." -ForegroundColor Green
if ($AppArgs) {
    Write-Host "Arguments: $AppArgs" -ForegroundColor Yellow
    & python $MainScript @AppArgs
} else {
    & python $MainScript
}

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "[ERROR] Application exited with code $LASTEXITCODE" -ForegroundColor Red
    Pause
}
