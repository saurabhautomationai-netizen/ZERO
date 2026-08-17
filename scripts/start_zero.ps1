# PowerShell script to run ZERO FastAPI server locally
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "Starting ZERO Personal AI Operating System" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan

$VenvPython = Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"
if (-Not (Test-Path $VenvPython)) {
    Write-Error "Virtual environment not found at $VenvPython. Please run python -m venv .venv"
    exit 1
}

# Run Uvicorn server on localhost:8000
& $VenvPython -m uvicorn zero_core.interfaces.web.app:app --reload --host 127.0.0.1 --port 8000
