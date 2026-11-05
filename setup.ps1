# PowerShell Setup Script for /dev SDLC Pipeline Suite
# Usage: powershell -ExecutionPolicy Bypass -File .\setup.ps1

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$claudeHome = Join-Path $env:USERPROFILE ".claude"

Write-Host "=== Setup /dev SDLC Pipeline Suite (Windows) ===" -ForegroundColor Cyan
Write-Host ""

# 1. Check prerequisites
Write-Host "[1/4] Checking prerequisites..." -ForegroundColor Yellow

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Error "ERROR: 'git' is not installed or not in PATH."
    exit 1
}

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Write-Error "ERROR: 'node' is not installed or not in PATH. Required for hooks and Claude Code."
    exit 1
}

if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
    Write-Error "ERROR: 'claude' CLI is not installed or not in PATH. Install with: npm install -g @anthropic-ai/claude-code"
    exit 1
}

Write-Host "  ✓ git detected" -ForegroundColor Green
Write-Host "  ✓ node detected" -ForegroundColor Green
Write-Host "  ✓ claude CLI detected" -ForegroundColor Green
Write-Host ""

# 2. Install superpowers plugin
Write-Host "[2/4] Installing dependency: superpowers plugin..." -ForegroundColor Yellow
try {
    & claude plugin install superpowers@claude-plugins-official --scope user
    Write-Host "  ✓ superpowers plugin installed" -ForegroundColor Green
} catch {
    Write-Warning "Could not install superpowers automatically. Verify marketplace access."
}
Write-Host ""

# 3. Install llm-council skill
Write-Host "[3/4] Installing dependency: llm-council skill..." -ForegroundColor Yellow
$skillsDir = Join-Path $claudeHome "skills"
$llmCouncilDir = Join-Path $skillsDir "llm-council"

if (-not (Test-Path $skillsDir)) {
    New-Item -ItemType Directory -Path $skillsDir -Force | Out-Null
}

if (Test-Path (Join-Path $llmCouncilDir ".git")) {
    Write-Host "  Updating existing llm-council repository..."
    git -C $llmCouncilDir pull --ff-only
    Write-Host "  ✓ llm-council updated" -ForegroundColor Green
} elseif (Test-Path $llmCouncilDir) {
    Write-Host "  ✓ llm-council folder already exists at $llmCouncilDir" -ForegroundColor Green
} else {
    Write-Host "  Cloning llm-council into $llmCouncilDir..."
    git clone https://github.com/tenfoldmarc/llm-council-skill.git $llmCouncilDir
    Write-Host "  ✓ llm-council cloned" -ForegroundColor Green
}
Write-Host ""

# 4. Install dev plugin
Write-Host "[4/4] Installing dev plugin..." -ForegroundColor Yellow
$installSuccess = $false
try {
    & claude plugin install $scriptDir --scope user
    $installSuccess = $true
    Write-Host "  ✓ dev plugin installed from $scriptDir" -ForegroundColor Green
} catch {
    Write-Host "  ! Plugin install failed, falling back to direct copy..." -ForegroundColor Yellow
}

if (-not $installSuccess) {
    $devSkillTarget = Join-Path $skillsDir "dev"
    if (-not (Test-Path $devSkillTarget)) {
        New-Item -ItemType Directory -Path $devSkillTarget -Force | Out-Null
    }
    Copy-Item -Path (Join-Path $scriptDir "skills\dev\SKILL.md") -Destination $devSkillTarget -Force
    Copy-Item -Path (Join-Path $scriptDir "skills\dev\implement-and-review.js") -Destination $devSkillTarget -Force
    Copy-Item -Path (Join-Path $scriptDir "skills\dev\dev-trace.js") -Destination $devSkillTarget -Force
    Write-Warning "The bare-skill fallback has no hooks, so production tracing (dev-trace) will NOT record. /dev will flag this at gate GT."
    Write-Host "  ✓ Copied skill directly to $devSkillTarget" -ForegroundColor Green
}
Write-Host ""

# Default AI observability choice for tools that call an AI (asked/confirmed by /dev, gate GA)
$defaultsFile = Join-Path $HOME ".claude\dev-pipeline.json"
if (-not (Test-Path $defaultsFile)) {
    Set-Content -Path $defaultsFile -Value "{`n  `"agentObservabilityDefault`": `"A`"`n}" -Encoding UTF8
    Write-Host "  ✓ AI observability default set to A (full) in $defaultsFile" -ForegroundColor Green
}
Write-Host ""

Write-Host "=== Installation complete ===" -ForegroundColor Cyan
Write-Host "You can now run /dev inside any Claude Code session." -ForegroundColor Green
