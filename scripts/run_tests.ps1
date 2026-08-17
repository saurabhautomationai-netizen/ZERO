# PowerShell script to execute ZERO unit and integration test suite
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "Running ZERO Automated Test Suite" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan

$VenvPytest = Join-Path $PSScriptRoot "..\.venv\Scripts\pytest.exe"
if (-Not (Test-Path $VenvPytest)) {
    Write-Error "Pytest executable not found at $VenvPytest."
    exit 1
}

& $VenvPytest -q $args
