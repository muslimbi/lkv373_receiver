<#
.SYNOPSIS
    LKV373 PCAP Playback PowerShell Launcher
.DESCRIPTION
    Launches PCAP/PCAPNG capture file playback mode.
.EXAMPLE
    .\run_pcap.ps1 sample_capture.bin
#>

[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$PcapFile
)

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  LKV373 PCAP Capture File Playback Launcher" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host ""

if (-not $PcapFile) {
    if (Test-Path "sample_capture.bin") {
        $PcapFile = "sample_capture.bin"
    }
    else {
        $PcapFile = Read-Host "Enter path to PCAP/PCAPNG/BIN file"
    }
}

if (-not (Test-Path $PcapFile)) {
    Write-Host "[ERROR] File not found: $PcapFile" -ForegroundColor Red
    Pause
    exit 1
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$MainScript = Join-Path $ScriptDir "main.py"

Write-Host "Playing back capture file: $PcapFile ..." -ForegroundColor Green
& python $MainScript --pcap $PcapFile

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "[ERROR] Application exited with code $LASTEXITCODE" -ForegroundColor Red
    Pause
}
