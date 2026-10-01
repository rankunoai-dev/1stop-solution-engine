<#
.SYNOPSIS
    Create the local Python environment and install the development tooling.

.EXAMPLE
    .\scripts\bootstrap.ps1
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$version = & python -c "import sys; print('%d.%d' % sys.version_info[:2])"
if ([version]$version -lt [version]'3.11') {
    Write-Error "Python 3.11+ is required; 'python' is $version."
    exit 1
}

if (-not (Test-Path '.venv')) {
    python -m venv .venv
}

$python = Join-Path $RepoRoot '.venv\Scripts\python.exe'
& $python -m pip install --upgrade pip
& $python -m pip install -e '.[dev]'
& $python -m pre_commit install

Write-Host 'Environment ready. Run .\scripts\verify.ps1 to check everything.' -ForegroundColor Green
