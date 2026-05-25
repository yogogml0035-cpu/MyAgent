#requires -Version 5.1
[CmdletBinding()]
param(
  [ValidateSet("win", "wsl")]
  [string]$Target = "",
  [string]$RepoRoot = "",
  [switch]$Help
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Show-Usage {
  @"
Usage: scripts\set-frontend-deps-link-win.ps1 -Target win|wsl

Point frontend\node_modules at the dependency directory for a runtime mode.

Targets:
  win  -> frontend\node_modules-win
  wsl  -> frontend\node_modules-wsl
"@
}

if ($Help) {
  Show-Usage
  exit 0
}

if (-not $Target) {
  throw "Target is required. Use -Target win or -Target wsl."
}

if (-not $RepoRoot) {
  $RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}
else {
  $RepoRoot = (Resolve-Path -LiteralPath $RepoRoot).Path
}

$frontendRoot = Join-Path $RepoRoot "frontend"
$linkPath = Join-Path $frontendRoot "node_modules"
$targetName = if ($Target -eq "win") { "node_modules-win" } else { "node_modules-wsl" }
$targetPath = Join-Path $frontendRoot $targetName

if (Test-Path -LiteralPath $linkPath) {
  $item = Get-Item -LiteralPath $linkPath -Force
  if ($item.LinkType -in @("Junction", "SymbolicLink")) {
    & cmd.exe /c "rmdir `"$linkPath`""
    if ($LASTEXITCODE -ne 0) {
      throw "Failed to remove existing frontend\node_modules junction."
    }
  }
  else {
    $winPath = Join-Path $frontendRoot "node_modules-win"
    if (-not (Test-Path -LiteralPath $winPath)) {
      Rename-Item -LiteralPath $linkPath -NewName "node_modules-win"
    }
    else {
      throw "frontend\node_modules is a real directory and frontend\node_modules-win already exists. Move or remove one before switching dependency modes."
    }
  }
}

if (-not (Test-Path -LiteralPath $targetPath)) {
  New-Item -ItemType Directory -Path $targetPath | Out-Null
}

$cmd = "mklink /J `"$linkPath`" `"$targetPath`""
& cmd.exe /c $cmd | Out-Host
if ($LASTEXITCODE -ne 0) {
  throw "Failed to create junction frontend\node_modules -> $targetName"
}

Write-Host "[deps] frontend\node_modules -> $targetName"
