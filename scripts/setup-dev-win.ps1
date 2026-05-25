#requires -Version 5.1
[CmdletBinding()]
param(
  [switch]$Clean,
  [switch]$SkipBackend,
  [switch]$SkipFrontend,
  [switch]$Help
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Show-Usage {
  @"
Usage: scripts\setup-dev-win.ps1 [options]

Install Windows-native MyAgent development dependencies.

Options:
  -Clean          Remove backend\.venv and frontend\node_modules-win/.next caches first.
  -SkipBackend   Do not run backend uv sync.
  -SkipFrontend  Do not run frontend npm ci.
  -Help          Show this help.
"@
}

function Remove-PathIfPresent {
  param([Parameter(Mandatory = $true)][string]$Path)

  $resolved = Join-Path $repoRoot $Path
  if (Test-Path -LiteralPath $resolved) {
    Write-Host "[setup] removing $Path"
    Remove-Item -LiteralPath $resolved -Recurse -Force
  }
}

function Remove-NodeModulesPath {
  $path = Join-Path $repoRoot "frontend\node_modules"
  if (-not (Test-Path -LiteralPath $path)) {
    return
  }

  $item = Get-Item -LiteralPath $path -Force
  if ($item.LinkType -in @("Junction", "SymbolicLink")) {
    & cmd.exe /c "rmdir `"$path`""
    if ($LASTEXITCODE -ne 0) {
      throw "Failed to remove frontend\node_modules junction."
    }
  }
  else {
    Remove-Item -LiteralPath $path -Recurse -Force
  }
}

if ($Help) {
  Show-Usage
  exit 0
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
  throw "uv is required but was not found in PATH."
}
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
  throw "npm is required but was not found in PATH."
}

if ($Clean) {
  if (-not $SkipBackend) {
    Remove-PathIfPresent "backend\.venv"
  }
  if (-not $SkipFrontend) {
    Remove-NodeModulesPath
    Remove-PathIfPresent "frontend\node_modules-win"
    Remove-PathIfPresent "frontend\.next"
    Remove-PathIfPresent "frontend\.next-dev"
  }
}

if (-not $SkipBackend) {
  Write-Host "[setup] installing backend dependencies for Windows"
  Push-Location (Join-Path $repoRoot "backend")
  try {
    & uv sync
    if ($LASTEXITCODE -ne 0) {
      throw "uv sync failed with exit code $LASTEXITCODE"
    }
  }
  finally {
    Pop-Location
  }
}

if (-not $SkipFrontend) {
  Write-Host "[setup] installing frontend dependencies for Windows"
  Push-Location (Join-Path $repoRoot "frontend")
  try {
    Remove-NodeModulesPath
    & npm ci
    if ($LASTEXITCODE -ne 0) {
      throw "npm ci failed with exit code $LASTEXITCODE"
    }

    $target = Join-Path (Get-Location).Path "node_modules-win"
    if (Test-Path -LiteralPath $target) {
      Remove-Item -LiteralPath $target -Recurse -Force
    }
    Rename-Item -LiteralPath (Join-Path (Get-Location).Path "node_modules") -NewName "node_modules-win"
  }
  finally {
    Pop-Location
  }

  & powershell.exe -ExecutionPolicy Bypass -File (Join-Path $repoRoot "scripts\set-frontend-deps-link-win.ps1") -Target win -RepoRoot $repoRoot
  if ($LASTEXITCODE -ne 0) {
    throw "Failed to point frontend dependencies at node_modules-win."
  }
}

Write-Host "[setup] Windows development dependencies are ready."
