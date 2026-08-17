# ZERO & Trading Bot - Start Background Services
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$PythonExe = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    $PythonExe = "python.exe"
}

# 1. Setup Logs Directory for ZERO
$LogsDir = Join-Path $RepoRoot "logs"
if (-not (Test-Path $LogsDir)) {
    New-Item -ItemType Directory -Path $LogsDir -Force | Out-Null
}

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "  ZERO & Trading Bot Background Launcher " -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan

# 2. Launch Unified ZERO Daemon (FastAPI + Telegram Runner)
$pZero = Start-Process -FilePath $PythonExe -ArgumentList @("-u", "-m", "zero_core.daemon") -WorkingDirectory $RepoRoot -WindowStyle Hidden -PassThru

# 3. Launch Paper Trading Bot
$TradingBotDir = "F:\AI Automation\Projects\Trading bot"
$TradingScript = Join-Path $TradingBotDir "paper_runner.py"

if (Test-Path $TradingScript) {
    $pTrading = Start-Process -FilePath $PythonExe -ArgumentList @("-u", "paper_runner.py") -WorkingDirectory $TradingBotDir -WindowStyle Hidden -PassThru
    $tradingStatus = "PID: $($pTrading.Id) -> Logs in trading_bot.log"
} else {
    $tradingStatus = "Script not found at $TradingScript"
}

Start-Sleep -Seconds 2

Write-Host "`n[OK] All Services Successfully Started in Background!" -ForegroundColor Green
Write-Host "  - ZERO Operating System: PID: $($pZero.Id) -> http://127.0.0.1:8000/" -ForegroundColor White
Write-Host "  - ZERO Telegram Daemon:  Active" -ForegroundColor White
Write-Host "  - Paper Trading Bot:     $tradingStatus" -ForegroundColor White
Write-Host "`nTo stop all services anytime, run: .\stop_zero_background.ps1" -ForegroundColor Gray
