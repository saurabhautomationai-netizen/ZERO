# ZERO - Register Windows Auto-Start
# Automatically launches start_zero_background.ps1 whenever you log into Windows

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$ScriptPath = Join-Path $RepoRoot "scripts\start_zero_background.ps1"
$StartupFolder = [Environment]::GetFolderPath("Startup")
$ShortcutPath = Join-Path $StartupFolder "ZERO_AutoStart.vbs"

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "  Register ZERO Windows Auto-Start       " -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan

try {
    # Create silent VBS launcher in User Startup folder (No admin rights required)
    $VbsContent = @"
Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "powershell.exe -ExecutionPolicy Bypass -WindowStyle Hidden -File ""$ScriptPath""", 0, False
"@
    Set-Content -Path $ShortcutPath -Value $VbsContent -Encoding ASCII
    Write-Host "[OK] Auto-Start successfully configured in Startup folder!" -ForegroundColor Green
    Write-Host "     Location: $ShortcutPath" -ForegroundColor Gray
    Write-Host "     ZERO will now start silently in the background on every Windows login." -ForegroundColor White
} catch {
    Write-Host "[!] Could not configure startup: $_" -ForegroundColor Red
}
