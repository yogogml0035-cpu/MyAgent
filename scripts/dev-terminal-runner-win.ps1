#requires -Version 5.1
[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)]
  [ValidateSet("backend", "frontend")]
  [string]$Service,
  [Parameter(Mandatory = $true)]
  [string]$RepoRoot,
  [string]$BackendHost = "127.0.0.1",
  [ValidateRange(1, 65535)]
  [int]$BackendPort = 8001,
  [string]$FrontendHost = "127.0.0.1",
  [ValidateRange(1, 65535)]
  [int]$FrontendPort = 3001,
  [switch]$ForcePolling
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Enable-PollingWatchers {
  if (-not $ForcePolling) {
    return
  }

  if (-not $env:WATCHFILES_FORCE_POLLING) {
    $env:WATCHFILES_FORCE_POLLING = "true"
  }
  if (-not $env:WATCHFILES_POLL_DELAY_MS) {
    $env:WATCHFILES_POLL_DELAY_MS = "300"
  }
  if (-not $env:WATCHPACK_POLLING) {
    $env:WATCHPACK_POLLING = "true"
  }
  if (-not $env:CHOKIDAR_USEPOLLING) {
    $env:CHOKIDAR_USEPOLLING = "true"
  }
  if (-not $env:CHOKIDAR_INTERVAL) {
    $env:CHOKIDAR_INTERVAL = "300"
  }
}

try {
  $resolvedRoot = (Resolve-Path -LiteralPath $RepoRoot).Path
  Enable-PollingWatchers

  switch ($Service) {
    "backend" {
      Set-Location -LiteralPath (Join-Path $resolvedRoot "backend")
      Write-Host "[dev] starting Windows backend on http://localhost:$BackendPort (bind $BackendHost)"
      Write-Host "[dev] backend reload polling: WATCHFILES_FORCE_POLLING=$($env:WATCHFILES_FORCE_POLLING)"
      Write-Host ""
      & uv run uvicorn app.main:app --reload --reload-delay 0.25 --host $BackendHost --port $BackendPort
      exit $LASTEXITCODE
    }
    "frontend" {
      Set-Location -LiteralPath (Join-Path $resolvedRoot "frontend")
      Write-Host "[dev] starting Windows frontend on http://localhost:$FrontendPort (bind $FrontendHost)"
      Write-Host "[dev] frontend hot reload polling: WATCHPACK_POLLING=$($env:WATCHPACK_POLLING) CHOKIDAR_USEPOLLING=$($env:CHOKIDAR_USEPOLLING)"
      Write-Host ""

      $nextCmd = Join-Path (Get-Location).Path "node_modules\.bin\next.cmd"
      if (-not (Test-Path -LiteralPath $nextCmd)) {
        throw "frontend\node_modules\.bin\next.cmd not found. Run scripts\setup-dev-win.ps1 first."
      }

      & $nextCmd dev -p $FrontendPort -H $FrontendHost
      exit $LASTEXITCODE
    }
  }
}
finally {
  Write-Host ""
  Write-Host "[dev] $Service exited."
  if ([Environment]::UserInteractive) {
    Read-Host "Press Enter to close this terminal" | Out-Null
  }
}
