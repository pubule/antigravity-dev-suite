# ==============================================================================
# Antigravity Dev Suite — Uninstaller for Windows (PowerShell)
# ==============================================================================
$ErrorActionPreference = "SilentlyContinue"

$GeminiHome = Join-Path $env:USERPROFILE ".gemini"
$ConfigDir = Join-Path $GeminiHome "config"
$PluginsDir = Join-Path $ConfigDir "plugins"
$TargetPluginDir = Join-Path $PluginsDir "antigravity-dev-suite"

Write-Host "=== Uninstalling Antigravity Dev Suite on Windows ===" -ForegroundColor Yellow

if (Test-Path $TargetPluginDir) {
    cmd /c rmdir "$TargetPluginDir" 2>$null
    if (Test-Path $TargetPluginDir) {
        Remove-Item -Path $TargetPluginDir -Recurse -Force
    }
    Write-Host "[-] Removed plugin junction: $TargetPluginDir" -ForegroundColor Green
}

Write-Host "=== Antigravity Dev Suite uninstalled successfully. ===" -ForegroundColor Green
