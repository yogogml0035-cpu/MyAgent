#requires -Version 5.1
[CmdletBinding()]
param(
  [ValidateRange(1, 65535)]
  [int]$BackendPort = 8001,
  [ValidateRange(1, 65535)]
  [int]$FrontendPort = 3001,
  [ValidateRange(1, 65535)]
  [int[]]$Port = @(),
  [switch]$IncludeWslRelay,
  [switch]$DryRun,
  [switch]$Quiet,
  [switch]$Help
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Show-Usage {
  @"
Usage: scripts\stop-dev-ports-win.ps1 [options]

Stop Windows processes listening on the MyAgent backend/frontend ports.

Options:
  -BackendPort PORT   Backend port to stop. Default: 8001
  -FrontendPort PORT  Frontend port to stop. Default: 3001
  -Port PORT          Additional port to stop. Can be repeated.
  -IncludeWslRelay   Also stop WSL relay processes for WSL-hosted listeners.
  -DryRun             Show matching processes without stopping them.
  -Quiet              Print only errors.
  -Help               Show this help.
"@
}

function Write-Log {
  param([Parameter(Mandatory = $true)][string]$Message)
  if (-not $Quiet) {
    Write-Host $Message
  }
}

function Get-ListenersForPort {
  param([Parameter(Mandatory = $true)][int]$LocalPort)

  @(Get-NetTCPConnection -State Listen -LocalPort $LocalPort -ErrorAction SilentlyContinue |
    Where-Object { $_.OwningProcess -and $_.OwningProcess -gt 0 } |
    Select-Object -ExpandProperty OwningProcess -Unique)
}

if ($Help) {
  Show-Usage
  exit 0
}

$ports = @($BackendPort, $FrontendPort) + $Port
$exitCode = 0

foreach ($localPort in $ports) {
  $pids = @(Get-ListenersForPort -LocalPort $localPort)
  if ($pids.Count -eq 0) {
    Write-Log "[port:$localPort] no Windows listener found"
    continue
  }

  Write-Log "[port:$localPort] matching listener(s):"
  foreach ($processId in $pids) {
    $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
    if ($process) {
      Write-Log ("  {0,7} {1} {2}" -f $process.Id, $process.ProcessName, $process.Path)
    }
    else {
      Write-Log ("  {0,7} <process exited>" -f $processId)
    }
  }

  if ($DryRun) {
    continue
  }

  foreach ($processId in $pids) {
    $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
    if ($process -and $process.ProcessName -ieq "wslrelay" -and -not $IncludeWslRelay) {
      Write-Log "[port:$localPort] skipping wslrelay.exe; stop the WSL service with scripts/stop-dev-ports.sh or pass -IncludeWslRelay explicitly."
      continue
    }

    try {
      Stop-Process -Id $processId -Force -ErrorAction Stop
    }
    catch {
      Write-Error "[port:$localPort] failed to stop PID $processId`: $($_.Exception.Message)"
      $exitCode = 1
    }
  }
}

Start-Sleep -Milliseconds 200

foreach ($localPort in $ports) {
  $remaining = @(Get-ListenersForPort -LocalPort $localPort)
  if ($remaining.Count -gt 0 -and -not $DryRun) {
    Write-Error "[port:$localPort] still occupied after stop attempt"
    $exitCode = 1
  }
}

exit $exitCode
