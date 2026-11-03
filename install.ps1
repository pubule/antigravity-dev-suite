# ==============================================================================
# Antigravity Dev Suite — 1-Click Installer for Windows (PowerShell)
# Claude Opus 5.5 Coding Standard & Cross-Platform Engine
# ==============================================================================
param([switch]$WithBrowsers, [switch]$NoBrowsers)
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$GeminiHome = Join-Path $env:USERPROFILE ".gemini"
$ConfigDir = Join-Path $GeminiHome "config"
$PluginsDir = Join-Path $ConfigDir "plugins"
$TargetPluginDir = Join-Path $PluginsDir "antigravity-dev-suite"
$ConfigFile = Join-Path $ConfigDir "config.json"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "🚀 Installing Antigravity Dev Suite on Windows (AGY Standard)" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Clean legacy / conflicting plugin stubs
Write-Host "[1/5] Running legacy plugins cleanup & backup on Windows..." -ForegroundColor Yellow
$CleanerScript = Join-Path $ScriptDir "scripts\clean_legacy_plugins.ps1"
if (Test-Path $CleanerScript) {
    & $CleanerScript
}

# 2. Ensure Antigravity directory structure exists
Write-Host "[2/5] Setting up Antigravity directory structure..." -ForegroundColor Yellow
$dirsToCreate = @($PluginsDir, (Join-Path $ConfigDir "rules"), (Join-Path $ConfigDir "agents"))
foreach ($dir in $dirsToCreate) {
    if (!(Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
}

# 3. Setup Python dependencies & Playwright Chromium
Write-Host "[3/5] Verifying Playwright & Python environment..." -ForegroundColor Yellow
# Find a real Python 3.9+ (skip the Microsoft Store "python" alias, which does not run)
$PythonCmd = $null
$PythonArgs = @()
foreach ($cand in @("py -3", "python", "python3")) {
    $parts = $cand.Split(" ")
    if (-not (Get-Command $parts[0] -ErrorAction SilentlyContinue)) { continue }
    $extra = @($parts | Select-Object -Skip 1)
    try {
        & $parts[0] @extra -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" *> $null
        if ($LASTEXITCODE -eq 0) { $PythonCmd = $parts[0]; $PythonArgs = $extra; break }
    } catch { }
}
if (-not $PythonCmd) {
    Write-Host "  ❌ Python 3.9+ not found. Install it from https://www.python.org/downloads/ and run this script again." -ForegroundColor Red
    exit 1
}

# Playwright is optional (visual QA only): never let it abort the install.
try {
    & $PythonCmd @PythonArgs -c "import playwright" *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  ⏳ Installing Playwright python module..." -ForegroundColor Gray
        & $PythonCmd @PythonArgs -m pip install --quiet --timeout 20 --retries 1 playwright
    } else {
        Write-Host "  ✔ Playwright python module is already installed." -ForegroundColor Green
    }
    # Chromium for the visual QA step of the Stop gate (about 150 MB, once).
    # Skip with -NoBrowsers or AGY_INSTALL_BROWSERS=0. -WithBrowsers is kept for compatibility.
    if (-not $NoBrowsers -and $env:AGY_INSTALL_BROWSERS -ne "0") {
        Write-Host "  ⏳ Installing Playwright Chromium (bounded to 10 minutes)..." -ForegroundColor Gray
        & $PythonCmd @PythonArgs -c "import subprocess, sys; sys.exit(subprocess.run([sys.executable, '-m', 'playwright', 'install', 'chromium'], timeout=600).returncode)" *> $null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  ✔ Chromium ready for visual QA." -ForegroundColor Green
        } else {
            Write-Host "  ℹ Chromium could not be installed now. Run later: py -3 -m playwright install chromium" -ForegroundColor Gray
        }
    }
} catch {
    Write-Host "  ℹ Playwright could not be installed. Visual QA will run in fallback mode." -ForegroundColor Gray
}

# 4. Create Plugin Junction / Link
Write-Host "[4/5] Linking Antigravity Dev Suite plugin..." -ForegroundColor Yellow
if (Test-Path $TargetPluginDir) {
    cmd /c rmdir "$TargetPluginDir" 2>$null
    if (Test-Path $TargetPluginDir) {
        Remove-Item -Path $TargetPluginDir -Recurse -Force
    }
}

# Create directory junction (does not require admin or Developer Mode)
New-Item -ItemType Junction -Path $TargetPluginDir -Target $ScriptDir -Force | Out-Null
Write-Host "  ✔ Linked plugin -> $TargetPluginDir" -ForegroundColor Green

# Enable plugin in config.json using BOM-less UTF-8 encoding
Write-Host "  Registering plugin in config.json..." -ForegroundColor Yellow
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
    $utf8NoBom = [System.Text.UTF8Encoding]::new($false)
    [System.IO.File]::WriteAllText($ConfigFile, ($json | ConvertTo-Json -Depth 10), $utf8NoBom)
    Write-Host "  ✔ Plugin enabled in config.json (BOM-less UTF-8)" -ForegroundColor Green
} catch {
    Write-Host "  ⚠ Could not parse config.json. Antigravity will load plugin by default." -ForegroundColor Gray
}

# 5. Register hooks globally (IDE + CLI) and run the doctor
Write-Host "[5/5] Registering hooks and running the installation doctor..." -ForegroundColor Yellow
& $PythonCmd @PythonArgs (Join-Path $ScriptDir "scripts\setup_hooks.py") install
& $PythonCmd @PythonArgs (Join-Path $ScriptDir "scripts\agy_hook.py") doctor
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ The doctor found problems (see FAIL lines above)." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "✅ Antigravity Dev Suite successfully installed on Windows!" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Cyan
