<#
==============================================================================
Antigravity Dev Suite — Multi-Iteration Autonomous Audit & Self-Healing Loop (PowerShell)
Executes /antigravity-dev-suite:opus-dev audit & fix prompt iteratively.
==============================================================================
#>
[CmdletBinding()]
param (
    [Alias("n")][int]$Iterations = 10,
    [Alias("d")][int]$DelaySeconds = 3,
    [Alias("w")][string]$WorkspaceDir = "$PSScriptRoot/..",
    [Alias("l")][string]$LogFile = "",
    [Alias("m")][string]$Model = "",
    [Alias("p")][string]$Prompt = "/antigravity-dev-suite:opus-dev esegui un audit fortemente critico sulla plugin antigravity-dev-suite per trovare inefficienze, lacune, punti di miglioramento, controindicazioni o errori rispetto all'obiettivo che la plugin si pone. poi esegui un loop in cui implementi tutte le fix, riesegui l'audit lanciato poco fa e se serve implementi le nuove fix. Continua a loopare finchè non ci sono più fix da fare. Se ti aiuta usa /goal."
)

$ErrorActionPreference = "Stop"

if (-not $LogFile) {
    $LogFile = Join-Path (Resolve-Path $WorkspaceDir).Path "agy_audit_current.log"
}

# Resolve AGY Executable
$AgyCmd = Get-Command "agy" -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -First 1

if (-not $AgyCmd) {
    $CommonPaths = @(
        "$env:LOCALAPPDATA\Programs\Antigravity\bin\agy.exe",
        "$env:USERPROFILE\.gemini\antigravity-cli\bin\agy.exe",
        "/opt/homebrew/bin/agy",
        "/usr/local/bin/agy"
    )
    foreach ($p in $CommonPaths) {
        if (Test-Path $p) {
            $AgyCmd = $p
            break
        }
    }
}

if (-not $AgyCmd) {
    Write-Error "❌ Error: 'agy' CLI executable was not found in PATH or standard installation locations."
    exit 1
}

function Write-Log {
    param ([string]$Message, [string]$Color = "White")
    Write-Host $Message -ForegroundColor $Color
    if ($LogFile) {
        $logDir = Split-Path $LogFile -Parent
        if ($logDir -and (-not (Test-Path $logDir))) {
            New-Item -ItemType Directory -Path $logDir -Force | Out-Null
        }
        Add-Content -Path $LogFile -Value $Message -Encoding utf8
    }
}

Write-Log "================================================================================" "Cyan"
Write-Log "🚀 Antigravity Autonomous Audit Loop Engine (PowerShell)" "Cyan"
Write-Log "Binary:        $AgyCmd" "White"
Write-Log "Workspace:     $WorkspaceDir" "White"
Write-Log "Iterations:    $Iterations" "White"
Write-Log "Delay:         $DelaySeconds s between iterations" "White"
if ($Model) { Write-Log "Model:         $Model" "White" }
Write-Log "Live Log:      $LogFile" "White"
Write-Log "================================================================================" "Cyan"
Write-Log "" "White"

if (Test-Path $WorkspaceDir) {
    Set-Location $WorkspaceDir
}

$AgyArgs = @("--dangerously-skip-permissions")
if ($Model) {
    $AgyArgs += @("--model", $Model)
}
$AgyArgs += @("-p", $Prompt)

for ($i = 1; $i -le $Iterations; $i++) {
    $StartTime = Get-Date
    $Timestamp = $StartTime.ToString("yyyy-MM-dd HH:mm:ss")

    Write-Log "--------------------------------------------------------------------------------" "Yellow"
    Write-Log "🔄 [Iteration $i/$Iterations] Started at $Timestamp" "Yellow"
    Write-Log "Prompt: $Prompt" "White"
    Write-Log "--------------------------------------------------------------------------------" "Yellow"

    $output = & $AgyCmd @AgyArgs 2>&1
    $ExitCode = $LASTEXITCODE

    foreach ($line in $output) {
        Write-Log "$line" "White"
    }

    $EndTime = Get-Date
    $Duration = [math]::Round(($EndTime - $StartTime).TotalSeconds)

    if ($ExitCode -eq 0) {
        Write-Log "✅ [Iteration $i/$Iterations] Completed successfully (Duration: ${Duration}s)" "Green"
    } else {
        Write-Log "⚠️  [Iteration $i/$Iterations] Finished with exit code $ExitCode (Duration: ${Duration}s)" "DarkYellow"
    }

    if ($i -lt $Iterations) {
        Write-Log "⏳ Waiting $DelaySeconds s before launching next iteration..." "Gray"
        Start-Sleep -Seconds $DelaySeconds
        Write-Log "" "White"
    }
}

Write-Log "================================================================================" "Cyan"
Write-Log "🎉 All $Iterations iterations finished." "Cyan"
Write-Log "================================================================================" "Cyan"
