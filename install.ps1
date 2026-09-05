<#
.SYNOPSIS
    CurlCommander installer for Windows (PowerShell).
.DESCRIPTION
    Prefers isolated installs (uv tool, then pipx), falls back to a local .venv,
    and only touches the system Python with -System (after confirmation).
.PARAMETER System
    Install into the system Python instead of an isolated environment.
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File install.ps1
    powershell -ExecutionPolicy Bypass -File install.ps1 -System
#>
[CmdletBinding()]
param(
    [switch]$System,
    [switch]$Help
)

$ErrorActionPreference = 'Stop'
Set-Location -Path $PSScriptRoot

if ($Help) {
    Write-Host "Usage: install.ps1 [-System]"
    Write-Host "  (default) install with uv tool / pipx, or a local .venv"
    Write-Host "  -System   install into the system Python"
    exit 0
}

function Test-Cmd([string]$name) {
    return [bool](Get-Command $name -ErrorAction SilentlyContinue)
}

if (Test-Cmd 'uv') {
    Write-Host '[*] Installing with uv tool...'
    uv tool install --from . curlcommander
    Write-Host '[OK] Installed. Run: curlcmd --version'
    exit 0
}

if (Test-Cmd 'pipx') {
    Write-Host '[*] Installing with pipx...'
    pipx install .
    Write-Host '[OK] Installed. Run: curlcmd --version'
    exit 0
}

if ($System) {
    Write-Host '[!] -System requested: installing into the system Python.'
    $reply = Read-Host '    This affects your global Python. Continue? [y/N]'
    if ($reply -notmatch '^(y|yes)$') { Write-Host 'Aborted.'; exit 1 }
    python -m pip install -e ".[dev]"
    Write-Host '[OK] Installed. Run: curlcmd --version'
    exit 0
}

Write-Host '[*] uv and pipx not found - creating a local virtual environment (.venv)...'
python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install --upgrade pip | Out-Null
& .\.venv\Scripts\python.exe -m pip install -e ".[dev]"
Write-Host '[OK] Installed in .venv.'
Write-Host '    Activate it with:  .\.venv\Scripts\Activate.ps1'
Write-Host '    Then run:          curlcmd --version'
