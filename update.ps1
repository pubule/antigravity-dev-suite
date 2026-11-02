# Update the Antigravity Dev Suite in place (git pull) and re-register the hooks.
$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (Test-Path (Join-Path $ScriptDir ".git")) {
    git -C $ScriptDir pull --ff-only
    if ($LASTEXITCODE -ne 0) { Write-Host "git pull failed" -ForegroundColor Red; exit 1 }
}
& (Join-Path $ScriptDir "install.ps1")
