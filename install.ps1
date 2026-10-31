# ==============================================================================
# Antigravity Dev Suite — 1-Click Installer for Windows (PowerShell)
# Claude Opus 5.5 Coding Standard & Cross-Platform Engine
# ==============================================================================
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$GeminiHome = Join-Path $env:USERPROFILE ".gemini"
$ConfigDir = Join-Path $GeminiHome "config"
$PluginsDir = Join-Path $ConfigDir "plugins"
$RulesDir = Join-Path $ConfigDir "rules"
$AgentsDir = Join-Path $ConfigDir "agents"
$TargetPluginDir = Join-Path $PluginsDir "antigravity-dev-suite"
$ConfigFile = Join-Path $ConfigDir "config.json"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "🚀 Installing Antigravity Dev Suite on Windows (AGY Standard)" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Clean legacy / conflicting plugins
Write-Host "[1/6] Running legacy plugins cleanup & backup on Windows..." -ForegroundColor Yellow
$CleanerScript = Join-Path $ScriptDir "scripts\clean_legacy_plugins.ps1"
if (Test-Path $CleanerScript) {
    & powershell.exe -ExecutionPolicy Bypass -File $CleanerScript
}

# 2. Ensure Antigravity directory structure exists
Write-Host "[2/6] Setting up Antigravity directory structure..." -ForegroundColor Yellow
$dirsToCreate = @($PluginsDir, $RulesDir, $AgentsDir, (Join-Path $ConfigDir "scripts"))
foreach ($dir in $dirsToCreate) {
    if (!(Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
}

# 3. Setup Python dependencies & Playwright Chromium
Write-Host "[3/6] Verifying Playwright & Python environment..." -ForegroundColor Yellow
$PythonCmd = if (Get-Command python -ErrorAction SilentlyContinue) { "python" } elseif (Get-Command py -ErrorAction SilentlyContinue) { "py" } elseif (Get-Command python3 -ErrorAction SilentlyContinue) { "python3" } else { "" }

if ($PythonCmd) {
    & $PythonCmd -c "import playwright" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  ⏳ Installing Playwright python module..." -ForegroundColor Gray
        & $PythonCmd -m pip install --quiet playwright
    } else {
        Write-Host "  ✔ Playwright python module is already installed." -ForegroundColor Green
    }
    
    # Try playwright install chromium
    & $PythonCmd -m playwright install chromium 2>$null
} else {
    Write-Host "  ⚠ Python not found in PATH. Please install Python 3.10+." -ForegroundColor Red
}

# 4. Create Plugin Junction / Link
Write-Host "[4/6] Linking Antigravity Dev Suite plugin..." -ForegroundColor Yellow
if (Test-Path $TargetPluginDir) {
    cmd /c rmdir "$TargetPluginDir" 2>$null
    if (Test-Path $TargetPluginDir) {
        Remove-Item -Path $TargetPluginDir -Recurse -Force
    }
}

# Create directory junction (does not require admin or Developer Mode)
New-Item -ItemType Junction -Path $TargetPluginDir -Target $ScriptDir -Force | Out-Null
Write-Host "  ✔ Linked plugin -> $TargetPluginDir" -ForegroundColor Green

# 5. Enable plugin in config.json
Write-Host "[5/6] Registering plugin in config.json..." -ForegroundColor Yellow
try {
    if (Test-Path $ConfigFile) {
        $json = Get-Content -Raw -Path $ConfigFile | ConvertFrom-Json
    } else {
        $json = [PSCustomObject]@{}
    }
    if (-not $json.plugins) {
        $json | Add-Member -MemberType NoteProperty -Name "plugins" -Value ([PSCustomObject]@{} )
    }
    if (-not $json.plugins."antigravity-dev-suite") {
        $json.plugins | Add-Member -MemberType NoteProperty -Name "antigravity-dev-suite" -Value ([PSCustomObject]@{ enabled = $true })
    } else {
        $json.plugins."antigravity-dev-suite".enabled = $true
    }
    $json | ConvertTo-Json -Depth 10 | Set-Content -Path $ConfigFile -Encoding UTF8
    Write-Host "  ✔ Plugin enabled in config.json" -ForegroundColor Green
} catch {
    Write-Host "  ⚠ Could not parse config.json. Antigravity will load plugin by default." -ForegroundColor Gray
}

# 6. Run Self-Test
Write-Host "[6/6] Running Self-Verification Test..." -ForegroundColor Yellow
if ($PythonCmd) {
    & $PythonCmd (Join-Path $ScriptDir "scripts\visual_qa.py") --test-mode
}

Write-Host ""
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "✅ Antigravity Dev Suite successfully installed on Windows!" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Cyan
