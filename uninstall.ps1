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

# 0. Remove hooks from %USERPROFILE%\.gemini\config\hooks.json (other hooks are kept)
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
foreach ($cand in @("py -3", "python", "python3")) {
    $parts = $cand.Split(" ")
    if (-not (Get-Command $parts[0] -ErrorAction SilentlyContinue)) { continue }
    $extra = @($parts | Select-Object -Skip 1)
    & $parts[0] @extra (Join-Path $ScriptDir "scripts\setup_hooks.py") uninstall
    if ($LASTEXITCODE -eq 0) { break }
}

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
            $utf8NoBom = [System.Text.UTF8Encoding]::new($false)
            [System.IO.File]::WriteAllText($ConfigFile, ($json | ConvertTo-Json -Depth 10), $utf8NoBom)
            Write-Host "[-] Disabled plugin in config.json (BOM-less UTF-8)" -ForegroundColor Green
        }
    } catch {}
}

# 3. Clean legacy rule stubs if any
$rulesToClean = @("claude_discipline.md", "visual_qa_mandate.md")
foreach ($rule in $rulesToClean) {
    $rulePath = Join-Path $ConfigDir "rules\$rule"
    if (Test-Path $rulePath) {
        Remove-Item -Path $rulePath -Force
    }
}

Write-Host "=== Antigravity Dev Suite uninstalled successfully. ===" -ForegroundColor Green
