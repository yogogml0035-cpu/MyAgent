#requires -Version 5.1
[CmdletBinding()]
param(
  [string]$Distribution = "",
  [string]$BackendHost = "0.0.0.0",
  [ValidateRange(1, 65535)]
  [int]$BackendPort = 8001,
  [string]$FrontendHost = "0.0.0.0",
  [ValidateRange(1, 65535)]
  [int]$FrontendPort = 3001,
  [switch]$NoStop,
  [switch]$NoProxyRepair,
  [switch]$DryRun,
  [switch]$Help
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Show-Usage {
  @"
Usage: scripts\start-dev-wsl.ps1 [options]

Open two Windows Terminal tabs for the MyAgent WSL backend and frontend.

Options:
  -Distribution NAME    WSL distribution name. Default: current/default WSL distro.
  -BackendHost HOST     Backend bind host. Default: 0.0.0.0
  -BackendPort PORT     Backend port. Default: 8001
  -FrontendHost HOST    Next.js bind host. Default: 0.0.0.0
  -FrontendPort PORT    Frontend port. Default: 3001
  -NoStop               Do not stop existing WSL listeners before starting.
  -NoProxyRepair        Do not update .wslconfig for Windows localhost proxy issues.
  -DryRun               Print the actions without stopping or starting services.
  -Help                 Show this help.

Examples:
  .\scripts\start-dev-wsl.ps1
  .\scripts\start-dev-wsl.ps1 -BackendPort 8002 -FrontendPort 3002
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

  throw "Cannot convert path to WSL form: $resolved"
}

function Quote-Bash {
  param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$Value)

  return "'" + ($Value -replace "'", "'`"`"'") + "'"
}

function Get-WslConfigPath {
  return (Join-Path $env:USERPROFILE ".wslconfig")
}

function Get-Wsl2Setting {
  param([Parameter(Mandatory = $true)][string]$Name)

  $path = Get-WslConfigPath
  if (-not (Test-Path $path)) {
    return $null
  }

  $inWsl2 = $false
  $pattern = '^\s*' + [regex]::Escape($Name) + '\s*=(.*)$'
  foreach ($line in Get-Content -Path $path) {
    if ($line -match '^\s*\[(.+)\]\s*$') {
      $inWsl2 = ($matches[1].Trim() -ieq "wsl2")
      continue
    }

    if ($inWsl2 -and $line -match $pattern) {
      return $matches[1].Trim()
    }
  }

  return $null
}

function Set-Wsl2Setting {
  param(
    [Parameter(Mandatory = $true)][string]$Name,
    [Parameter(Mandatory = $true)][string]$Value
  )

  $path = Get-WslConfigPath
  $lines = [System.Collections.Generic.List[string]]::new()
  if (Test-Path $path) {
    foreach ($line in Get-Content -Path $path) {
      [void]$lines.Add($line)
    }
  }

  $sectionIndex = -1
  for ($i = 0; $i -lt $lines.Count; $i++) {
    if ($lines[$i] -match '^\s*\[(.+)\]\s*$' -and $matches[1].Trim() -ieq "wsl2") {
      $sectionIndex = $i
      break
    }
  }

  if ($sectionIndex -lt 0) {
    if ($lines.Count -gt 0 -and $lines[$lines.Count - 1].Trim() -ne "") {
      [void]$lines.Add("")
    }
    [void]$lines.Add("[wsl2]")
    [void]$lines.Add("$Name=$Value")
  }
  else {
    $keyPattern = '^\s*' + [regex]::Escape($Name) + '\s*='
    $insertIndex = $lines.Count
    $updated = $false

    for ($i = $sectionIndex + 1; $i -lt $lines.Count; $i++) {
      if ($lines[$i] -match '^\s*\[.+\]\s*$') {
        $insertIndex = $i
        break
      }
      if ($lines[$i] -match $keyPattern) {
        $lines[$i] = "$Name=$Value"
        $updated = $true
        break
      }
    }

    if (-not $updated) {
      $lines.Insert($insertIndex, "$Name=$Value")
    }
  }

  $text = [string]::Join([Environment]::NewLine, $lines)
  if ($text.Length -gt 0) {
    $text += [Environment]::NewLine
  }

  $utf8NoBom = New-Object System.Text.UTF8Encoding $false
  [System.IO.File]::WriteAllText($path, $text, $utf8NoBom)
}

function Get-WindowsProxyServer {
  $settings = Get-ItemProperty "HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings"
  if ($settings.ProxyEnable -ne 1) {
    return ""
  }
  return [string]$settings.ProxyServer
}

function Test-LocalhostProxyServer {
  param([AllowEmptyString()][string]$ProxyServer)

  return ($ProxyServer -match '(^|[=;\s])(localhost|127\.0\.0\.1|\[::1\]|::1)(:|;|$)')
}

function Ensure-WslProxyCompatibility {
  $proxyServer = Get-WindowsProxyServer
  if (-not (Test-LocalhostProxyServer $proxyServer)) {
    return
  }

  $networkingMode = Get-Wsl2Setting "networkingMode"
  $autoProxy = Get-Wsl2Setting "autoProxy"
  if ($networkingMode -ieq "mirrored" -or $autoProxy -ieq "false") {
    return
  }

  if ($NoProxyRepair) {
    throw "Windows proxy points to '$proxyServer'. WSL NAT cannot use a localhost proxy. Run without -NoProxyRepair or set [wsl2] autoProxy=false in $((Get-WslConfigPath))."
  }

  Write-Host "[dev] Windows localhost proxy detected: $proxyServer"
  Write-Host "[dev] Updating $((Get-WslConfigPath)) with [wsl2] autoProxy=false."
  if (-not $DryRun) {
    Set-Wsl2Setting "autoProxy" "false"
    Write-Host "[dev] Restarting WSL so the .wslconfig change takes effect."
    & wsl.exe --shutdown
    if ($LASTEXITCODE -ne 0) {
      throw "wsl.exe --shutdown failed with exit code $LASTEXITCODE"
    }
    Start-Sleep -Seconds 2
  }
}

function Invoke-WslBash {
  param([Parameter(Mandatory = $true)][string]$Command)

  $args = @()
  if ($Distribution) {
    $args += @("-d", $Distribution)
  }
  $args += @("--", "bash", "-lc", $Command)

  if ($DryRun) {
    Write-Host "[dry-run] wsl.exe $($args -join ' ')"
    return
  }

  & wsl.exe @args
  if ($LASTEXITCODE -ne 0) {
    throw "wsl.exe exited with code $LASTEXITCODE"
  }
}

function Open-WslTab {
  param(
    [Parameter(Mandatory = $true)][string]$Title,
    [Parameter(Mandatory = $true)][string]$Service,
    [Parameter(Mandatory = $true)][string]$RepoRootWsl
  )

  $launcher = "MYAGENT_DEV_ROOT=$(Quote-Bash $RepoRootWsl) BACKEND_HOST=$(Quote-Bash $BackendHost) BACKEND_PORT=$(Quote-Bash ([string]$BackendPort)) FRONTEND_HOST=$(Quote-Bash $FrontendHost) FRONTEND_PORT=$(Quote-Bash ([string]$FrontendPort)) exec bash $(Quote-Bash "$RepoRootWsl/scripts/dev-terminal-runner.sh") $(Quote-Bash $Service)"
  $args = @("-w", "new", "new-tab", "--title", $Title, "wsl.exe")
  if ($Distribution) {
    $args += @("-d", $Distribution)
  }
  $args += @("--", "bash", "-lc", $launcher)

  if ($DryRun) {
    Write-Host "[dry-run] wt.exe $($args -join ' ')"
    return
  }

  & wt.exe @args
  if ($LASTEXITCODE -ne 0) {
    throw "wt.exe exited with code $LASTEXITCODE"
  }
}

if ($Help) {
  Show-Usage
  exit 0
}

if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) {
  throw "wsl.exe is required but was not found in PATH."
}
if (-not (Get-Command wt.exe -ErrorAction SilentlyContinue)) {
  throw "wt.exe is required but was not found in PATH."
}

$repoRootWindows = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$repoRootWsl = ConvertTo-WslPath $repoRootWindows

Ensure-WslProxyCompatibility

$preflight = "command -v uv >/dev/null && command -v npm >/dev/null"
Invoke-WslBash $preflight

if (-not $NoStop) {
  $stopCommand = "cd $(Quote-Bash $repoRootWsl) && ./scripts/stop-dev-ports.sh --backend-port $(Quote-Bash ([string]$BackendPort)) --frontend-port $(Quote-Bash ([string]$FrontendPort))"
  Invoke-WslBash $stopCommand
}

Open-WslTab "MyAgent Backend :$BackendPort" "backend" $repoRootWsl
Open-WslTab "MyAgent Frontend :$FrontendPort" "frontend" $repoRootWsl

Write-Host "[dev] opened backend terminal:  http://localhost:$BackendPort (bind $BackendHost)"
Write-Host "[dev] opened frontend terminal: http://localhost:$FrontendPort (bind $FrontendHost)"
Write-Host "[dev] stop each service with Ctrl+C in its terminal, or run ./scripts/stop-dev-ports.sh inside WSL."
