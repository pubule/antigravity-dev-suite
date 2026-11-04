# PowerShell Uninstall Script for /dev SDLC Pipeline Suite
# Usage: powershell -ExecutionPolicy Bypass -File .\uninstall.ps1

$ErrorActionPreference = "SilentlyContinue"

Write-Host "=== Uninstall /dev SDLC Pipeline Suite (Windows) ===" -ForegroundColor Cyan
Write-Host ""

Write-Host "Uninstalling dev plugin..." -ForegroundColor Yellow
& claude plugin uninstall dev --scope user

$claudeHome = Join-Path $env:USERPROFILE ".claude"
$devSkillTarget = Join-Path $claudeHome "skills\dev"

if (Test-Path $devSkillTarget) {
    Write-Host "Removing $devSkillTarget fallback folder..." -ForegroundColor Yellow
    Remove-Item -Path $devSkillTarget -Recurse -Force
}

Write-Host ""
Write-Host "dev plugin uninstalled." -ForegroundColor Green
Write-Host "Note: dependencies 'superpowers' and 'llm-council' were left intact." -ForegroundColor Yellow
