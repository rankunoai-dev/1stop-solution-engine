<#
.SYNOPSIS
    SDLC Step 7 - Automated Verification.

.DESCRIPTION
    Runs the full quality gate: format check, lint, dependency-layer check,
    strict type check, tests with coverage. CI runs the same checks, so a green
    run here means a green run there.

    No slice may be reported as complete until this script exits zero.

.EXAMPLE
    .\scripts\verify.ps1
    .\scripts\verify.ps1 -Fix    # auto-fix formatting and lint issues first
#>
[CmdletBinding()]
param(
    [switch]$Fix
)

$ErrorActionPreference = 'Continue'
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$python = Join-Path $RepoRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
    Write-Error 'No .venv found. Run .\scripts\bootstrap.ps1 first.'
    exit 1
}
$lintImports = Join-Path $RepoRoot '.venv\Scripts\lint-imports.exe'

$failures = @()

function Invoke-Gate {
    param([string]$Name, [string]$Exe, [string[]]$Arguments)

    Write-Host ''
    Write-Host "=== $Name ===" -ForegroundColor Cyan
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) {
        $script:failures += $Name
        Write-Host "FAILED: $Name" -ForegroundColor Red
    } else {
        Write-Host "PASSED: $Name" -ForegroundColor Green
    }
}

if ($Fix) {
    Write-Host 'Applying automatic fixes...' -ForegroundColor Yellow
    & $python -m ruff format .
    & $python -m ruff check . --fix
}

Invoke-Gate 'Format'       $python      @('-m', 'ruff', 'format', '--check', '.')
Invoke-Gate 'Lint'         $python      @('-m', 'ruff', 'check', '.')
Invoke-Gate 'Layers'       $lintImports @()
Invoke-Gate 'Type check'   $python      @('-m', 'mypy', 'src')
Invoke-Gate 'Tests'        $python      @('-m', 'pytest', '--cov=src', '--cov-report=term-missing', '-m', 'not integration')

Write-Host ''
if ($failures.Count -gt 0) {
    Write-Host ('VERIFICATION FAILED: ' + ($failures -join ', ')) -ForegroundColor Red
    Write-Host 'Do not report this slice as complete.' -ForegroundColor Red
    exit 1
}

Write-Host 'ALL GATES PASSED.' -ForegroundColor Green
Write-Host 'Next: SDLC Step 8 - README & architecture drift audit.' -ForegroundColor Cyan
exit 0
