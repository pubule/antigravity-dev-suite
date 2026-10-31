# ==============================================================================
# Antigravity Legacy Plugins & Redundant Rules Cleaner (Windows PowerShell)
# ==============================================================================
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

# 2. Disable conflicting/redundant plugins in config.json
if (Test-Path $ConfigFile) {
    try {
        $json = Get-Content -Raw -Path $ConfigFile | ConvertFrom-Json
        if (-not $json.plugins) {
            $json | Add-Member -MemberType NoteProperty -Name "plugins" -Value ([PSCustomObject]@{})
        }
        $legacyPlugins = @("ponytail", "superpowers", "skill-anything", "opencode-agy")
        foreach ($legacy in $legacyPlugins) {
            if ($json.plugins.$legacy) {
                $json.plugins.$legacy.enabled = $false
            }
        }
        $json | ConvertTo-Json -Depth 10 | Set-Content -Path $ConfigFile -Encoding UTF8
        Write-Host "[+] Disabled conflicting plugins in config.json" -ForegroundColor Green
    } catch {
        Write-Host "  ⚠ Skipping config.json edit due to parse error" -ForegroundColor Gray
    }
}

# 3. Clean up conflicting plugin junctions
$pluginsToRemove = @("ponytail", "skill-anything", "opencode-agy")
foreach ($plugin in $pluginsToRemove) {
    $pluginPath = Join-Path $PluginsDir $plugin
    if (Test-Path $pluginPath) {
        cmd /c rmdir "$pluginPath" 2>$null
        Write-Host "[-] Removed legacy plugin junction: $pluginPath" -ForegroundColor Yellow
    }
}

# 4. Clean up legacy unbundled rule files
$rulesToClean = @("claude_discipline.md", "visual_qa_mandate.md")
foreach ($rule in $rulesToClean) {
    $rulePath = Join-Path $ConfigDir "rules\$rule"
    if (Test-Path $rulePath) {
        Remove-Item -Path $rulePath -Force
        Write-Host "[-] Removed legacy unbundled rule: $rulePath" -ForegroundColor Yellow
    }
}

Write-Host "=== [2/3] Windows Legacy Cleanup Completed Successfully ===" -ForegroundColor Green
