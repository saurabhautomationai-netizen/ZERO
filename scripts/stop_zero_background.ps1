# ZERO & Trading Bot - Stop Background Services

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "  Stopping ZERO & Trading Bot Services.. " -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan

# Find and stop ZERO daemon, web app, telegram runner, and paper trading bot
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -like "*zero_core.daemon*" -or
    $_.CommandLine -like "*zero_core.interfaces.telegram.runner*" -or
    $_.CommandLine -like "*zero_core.interfaces.web.app:app*" -or
    $_.CommandLine -like "*paper_runner.py*"
} | ForEach-Object {
    Write-Host "[*] Stopping Process $($_.ProcessId) ($($_.Name))..." -ForegroundColor Yellow
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
}

Write-Host "[OK] All ZERO and Trading Bot background services stopped." -ForegroundColor Green
