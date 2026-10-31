# ==============================================================================
# Antigravity Dev Suite — Uninstaller for Windows (PowerShell)
# ==============================================================================
$ErrorActionPreference = "SilentlyContinue"

$GeminiHome = Join-Path $env:USERPROFILE ".gemini"
$ConfigDir = Join-Path $GeminiHome "config"
$PluginsDir = Join-Path $ConfigDir "plugins"
$TargetPluginDir = Join-Path $PluginsDir "antigravity-dev-suite"
$ConfigFile = Join-Path $ConfigDir "config.json"

Write-Host "=== Uninstalling Antigravity Dev Suite on Windows ===" -ForegroundColor Yellow

# 1. Remove plugin junction
if (Test-Path $TargetPluginDir) {
    cmd /c rmdir "$TargetPluginDir" 2>$null
    if (Test-Path $TargetPluginDir) {
        Remove-Item -Path $TargetPluginDir -Recurse -Force
    }
    Write-Host "[-] Removed plugin junction: $TargetPluginDir" -ForegroundColor Green
}

# 2. Update config.json if needed
if (Test-Path $ConfigFile) {
    try {
        $json = Get-Content -Raw -Path $ConfigFile | ConvertFrom-Json
        if ($json.plugins."antigravity-dev-suite") {
            $json.plugins."antigravity-dev-suite".enabled = $false
            $json | ConvertTo-Json -Depth 10 | Set-Content -Path $ConfigFile -Encoding UTF8
            Write-Host "[-] Disabled plugin in config.json" -ForegroundColor Green
        }
    } catch {}
}

# 3. Clean global legacy rules if present
$rulesToClean = @("claude_discipline.md", "visual_qa_mandate.md", "AGENTS.md")
foreach ($rule in $rulesToClean) {
    $rulePath = Join-Path $ConfigDir "rules\$rule"
    if (Test-Path $rulePath) {
        Remove-Item -Path $rulePath -Force
    }
}

Write-Host "=== Antigravity Dev Suite uninstalled successfully. ===" -ForegroundColor Green
