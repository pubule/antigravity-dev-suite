# ==============================================================================
# Antigravity Legacy Plugins & Redundant Rules Cleaner (Windows PowerShell)
# Safe, idempotent cleaner with automatic backup.
# ==============================================================================
param (
    [switch]$CleanAll = $false
)
$ErrorActionPreference = "SilentlyContinue"

$GeminiHome = Join-Path $env:USERPROFILE ".gemini"
$ConfigDir = Join-Path $GeminiHome "config"
$PluginsDir = Join-Path $ConfigDir "plugins"
$ConfigFile = Join-Path $ConfigDir "config.json"
$BackupTimestamp = Get-Date -Format "yyyyMMdd_HHmmss"

Write-Host "=== [1/3] Starting Antigravity Legacy Cleanup on Windows ===" -ForegroundColor Cyan

# 1. Backup config.json if present
if (Test-Path $ConfigFile) {
    Copy-Item -Path $ConfigFile -Destination "$ConfigFile.bak-$BackupTimestamp" -Force
    Write-Host "[+] Backed up config.json -> $ConfigFile.bak-$BackupTimestamp" -ForegroundColor Gray
}

# 2. Clean up legacy unbundled rule stubs if they exist
$rulesToClean = @("claude_discipline.md", "visual_qa_mandate.md")
foreach ($rule in $rulesToClean) {
    $rulePath = Join-Path $ConfigDir "rules\$rule"
    if (Test-Path $rulePath) {
        Remove-Item -Path $rulePath -Force
        Write-Host "[-] Cleaned legacy unbundled rule: $rulePath" -ForegroundColor Yellow
    }
}

# 3. Clean legacy dangling junctions if requested
if ($CleanAll) {
    $pluginsToRemove = @("ponytail", "skill-anything", "opencode-agy")
    foreach ($plugin in $pluginsToRemove) {
        $pluginPath = Join-Path $PluginsDir $plugin
        if (Test-Path $pluginPath) {
            cmd /c rmdir "$pluginPath" 2>$null
            Write-Host "[-] Removed legacy plugin junction: $pluginPath" -ForegroundColor Yellow
        }
    }
}

Write-Host "=== [2/3] Windows Legacy Cleanup Completed Successfully ===" -ForegroundColor Green
