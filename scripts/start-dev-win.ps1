#requires -Version 5.1
[CmdletBinding()]
param(
  [string]$BackendHost = "127.0.0.1",
  [ValidateRange(1, 65535)]
  [int]$BackendPort = 8001,
  [string]$FrontendHost = "127.0.0.1",
  [ValidateRange(1, 65535)]
  [int]$FrontendPort = 3001,
  [switch]$NoStop,
  [switch]$Install,
  [switch]$CleanInstall,
  [switch]$StopWslRelay,
  [switch]$ForcePolling,
  [switch]$DryRun,
  [switch]$Help
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Show-Usage {
  @"
Usage: scripts\start-dev-win.ps1 [options]

Open two Windows Terminal tabs for the MyAgent Windows-native backend and frontend.

Options:
  -BackendHost HOST    Backend bind host. Default: 127.0.0.1
  -BackendPort PORT    Backend port. Default: 8001
  -FrontendHost HOST   Next.js bind host. Default: 127.0.0.1
  -FrontendPort PORT   Frontend port. Default: 3001
  -NoStop              Do not stop existing Windows listeners before starting.
  -Install             Run scripts\setup-dev-win.ps1 before starting.
  -CleanInstall        Remove Windows dependency/build caches before installing.
  -StopWslRelay        Allow stopping wslrelay.exe when WSL services occupy the ports.
  -ForcePolling        Force polling watchers on Windows.
  -DryRun              Print actions without stopping or starting services.
  -Help                Show this help.

Examples:
  .\scripts\start-dev-win.ps1
  .\scripts\start-dev-win.ps1 -Install
  .\scripts\start-dev-win.ps1 -CleanInstall
"@
}

function Invoke-Checked {
  param(
    [Parameter(Mandatory = $true)][string]$FilePath,
    [Parameter(Mandatory = $true)][string[]]$ArgumentList
  )

  if ($DryRun) {
    Write-Host "[dry-run] $FilePath $($ArgumentList -join ' ')"
    return
  }

  & $FilePath @ArgumentList
  if ($LASTEXITCODE -ne 0) {
    throw "$FilePath exited with code $LASTEXITCODE"
  }
}

function Open-DevTab {
  param(
    [Parameter(Mandatory = $true)][string]$Title,
    [Parameter(Mandatory = $true)][string]$Service,
    [Parameter(Mandatory = $true)][string]$RepoRoot
  )

  $runner = Join-Path $RepoRoot "scripts\dev-terminal-runner-win.ps1"
  $command = @(
    "-NoExit",
    "-ExecutionPolicy", "Bypass",
    "-File", $runner,
    "-Service", $Service,
    "-RepoRoot", $RepoRoot,
    "-BackendHost", $BackendHost,
    "-BackendPort", $BackendPort,
    "-FrontendHost", $FrontendHost,
    "-FrontendPort", $FrontendPort
  )
  if ($ForcePolling) {
    $command += "-ForcePolling"
  }

  $args = @("-w", "new", "new-tab", "--title", $Title, "powershell.exe") + $command
  Invoke-Checked "wt.exe" $args
}

if ($Help) {
  Show-Usage
  exit 0
}

if (-not $DryRun -and -not (Get-Command wt.exe -ErrorAction SilentlyContinue)) {
  throw "wt.exe is required but was not found in PATH."
}
if (-not $DryRun -and -not (Get-Command uv -ErrorAction SilentlyContinue)) {
  throw "uv is required but was not found in PATH."
}
if (-not $DryRun -and -not (Get-Command npm -ErrorAction SilentlyContinue)) {
  throw "npm is required but was not found in PATH."
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

if ($CleanInstall) {
  $Install = $true
}

if ($Install) {
  $setupArgs = @("-ExecutionPolicy", "Bypass", "-File", (Join-Path $repoRoot "scripts\setup-dev-win.ps1"))
  if ($CleanInstall) {
    $setupArgs += "-Clean"
  }
  Invoke-Checked "powershell.exe" $setupArgs
}

if ($DryRun) {
  Write-Host "[dry-run] powershell.exe -ExecutionPolicy Bypass -File $repoRoot\scripts\set-frontend-deps-link-win.ps1 -Target win -RepoRoot $repoRoot"
}
else {
  & powershell.exe -ExecutionPolicy Bypass -File (Join-Path $repoRoot "scripts\set-frontend-deps-link-win.ps1") -Target win -RepoRoot $repoRoot
  if ($LASTEXITCODE -ne 0) {
    throw "Failed to point frontend dependencies at node_modules-win."
  }
}

if (-not $NoStop) {
  $stopArgs = @(
    "-ExecutionPolicy", "Bypass",
    "-File", (Join-Path $repoRoot "scripts\stop-dev-ports-win.ps1"),
    "-BackendPort", $BackendPort,
    "-FrontendPort", $FrontendPort
  )
  if ($StopWslRelay) {
    $stopArgs += "-IncludeWslRelay"
  }
  Invoke-Checked "powershell.exe" $stopArgs
}

Open-DevTab "MyAgent Backend :$BackendPort (Win)" "backend" $repoRoot
Open-DevTab "MyAgent Frontend :$FrontendPort (Win)" "frontend" $repoRoot

Write-Host "[dev] opened Windows backend terminal:  http://localhost:$BackendPort (bind $BackendHost)"
Write-Host "[dev] opened Windows frontend terminal: http://localhost:$FrontendPort (bind $FrontendHost)"
Write-Host "[dev] stop each service with Ctrl+C in its terminal, or run .\scripts\stop-dev-ports-win.ps1."
