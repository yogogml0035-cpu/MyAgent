param(
    [string]$RepoRoot = "."
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonScript = Join-Path $scriptDir "collect_map_sources.py"
$resolvedRepoRoot = (Resolve-Path -LiteralPath $RepoRoot).Path
$repoRootPath = [System.IO.Path]::GetFullPath($resolvedRepoRoot)

$candidates = New-Object System.Collections.Generic.List[object]

function Add-PythonCandidate {
    param(
        [string]$Label,
        [string]$Command,
        [string[]]$Arguments = @()
    )

    if (-not $Command) {
        return
    }

    $script:candidates.Add([pscustomobject]@{
        Label = $Label
        Command = $Command
        Arguments = $Arguments
    })
}

$windowsVenvPython = Join-Path $repoRootPath "backend\.venv\Scripts\python.exe"
if (Test-Path -LiteralPath $windowsVenvPython) {
    Add-PythonCandidate -Label "backend Windows venv" -Command $windowsVenvPython
}

$linuxVenvPython = Join-Path $repoRootPath "backend\.venv-linux\bin\python"
if (Test-Path -LiteralPath $linuxVenvPython) {
    Add-PythonCandidate -Label "backend Linux venv" -Command $linuxVenvPython
}

$pythonCommand = Get-Command python -ErrorAction SilentlyContinue | Select-Object -First 1
if ($pythonCommand) {
    Add-PythonCandidate -Label "python on PATH" -Command $pythonCommand.Source
}

$python3Command = Get-Command python3 -ErrorAction SilentlyContinue | Select-Object -First 1
if ($python3Command) {
    Add-PythonCandidate -Label "python3 on PATH" -Command $python3Command.Source
}

$pyCommand = Get-Command py -ErrorAction SilentlyContinue | Select-Object -First 1
if ($pyCommand) {
    Add-PythonCandidate -Label "py launcher" -Command $pyCommand.Source -Arguments @("-3")
}

if ($candidates.Count -eq 0) {
    Write-Error "No Python interpreter found. Create backend\.venv or install Python 3."
    exit 1
}

$errors = New-Object System.Collections.Generic.List[string]

foreach ($candidate in $candidates) {
    $args = @()
    $args += $candidate.Arguments
    $args += $pythonScript
    $args += $repoRootPath

    try {
        & $candidate.Command @args
        $exitCode = $LASTEXITCODE
    } catch {
        $errors.Add("$($candidate.Label): $($_.Exception.Message)")
        continue
    }

    if ($exitCode -eq 0) {
        exit 0
    }

    $errors.Add("$($candidate.Label): exited with code $exitCode")
}

Write-Error ("All Python candidates failed: " + ($errors -join "; "))
exit 1
