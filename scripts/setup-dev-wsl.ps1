#requires -Version 5.1
[CmdletBinding()]
param(
  [string]$Distribution = "",
  [switch]$Clean,
  [switch]$SkipBackend,
  [switch]$SkipFrontend,
  [switch]$Help
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Show-Usage {
  @"
Usage: scripts\setup-dev-wsl.ps1 [options]

Install WSL-native MyAgent development dependencies.

Options:
  -Distribution NAME  WSL distribution name. Default: current/default WSL distro.
  -Clean             Remove backend\.venv-wsl and frontend\node_modules-wsl/.next caches first.
  -SkipBackend       Do not run backend uv sync.
  -SkipFrontend      Do not run frontend npm ci.
  -Help              Show this help.
"@
}

function ConvertTo-WslPath {
  param([Parameter(Mandatory = $true)][string]$Path)

  $resolved = (Resolve-Path $Path).Path
  if ($resolved -match '^([A-Za-z]):\\(.*)$') {
    $drive = $matches[1].ToLowerInvariant()
    $rest = $matches[2] -replace '\\', '/'
    return "/mnt/$drive/$rest"
  }

  if ($resolved -match '^/') {
    return $resolved
  }

  throw "Cannot convert path to WSL form: $resolved"
}

function Quote-Bash {
  param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$Value)
  return "'" + ($Value -replace "'", "'`"`"'") + "'"
}

function Invoke-WslBash {
  param([Parameter(Mandatory = $true)][string]$Command)

  $args = @()
  if ($Distribution) {
    $args += @("-d", $Distribution)
  }
  $args += @("--", "bash", "-lc", $Command)

  & wsl.exe @args
  if ($LASTEXITCODE -ne 0) {
    throw "wsl.exe exited with code $LASTEXITCODE"
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

if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) {
  throw "wsl.exe is required but was not found in PATH."
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$repoRootWsl = ConvertTo-WslPath $repoRoot

if ($Clean) {
  if (-not $SkipBackend) {
    Invoke-WslBash "rm -rf $(Quote-Bash "$repoRootWsl/backend/.venv-wsl")"
  }
  if (-not $SkipFrontend) {
    Invoke-WslBash "rm -rf $(Quote-Bash "$repoRootWsl/frontend/node_modules-wsl") $(Quote-Bash "$repoRootWsl/frontend/.next") $(Quote-Bash "$repoRootWsl/frontend/.next-dev")"
  }
}

if (-not $SkipBackend) {
  Write-Host "[setup] installing backend dependencies for WSL into backend/.venv-wsl"
  Invoke-WslBash "cd $(Quote-Bash "$repoRootWsl/backend") && UV_PROJECT_ENVIRONMENT=.venv-wsl uv sync"
}

if (-not $SkipFrontend) {
  Write-Host "[setup] installing frontend dependencies for WSL into frontend/node_modules-wsl"
  Remove-NodeModulesPath
  Invoke-WslBash "cd $(Quote-Bash "$repoRootWsl/frontend") && npm ci && rm -rf node_modules-wsl && mv node_modules node_modules-wsl"

  & powershell.exe -ExecutionPolicy Bypass -File (Join-Path $repoRoot "scripts\set-frontend-deps-link-win.ps1") -Target wsl -RepoRoot $repoRoot
  if ($LASTEXITCODE -ne 0) {
    throw "Failed to point frontend dependencies at node_modules-wsl."
  }
}

Write-Host "[setup] WSL development dependencies are ready."
