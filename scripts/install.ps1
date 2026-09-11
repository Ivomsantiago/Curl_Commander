<#
.SYNOPSIS
    Instalador remoto do CurlCommander (Windows, PowerShell 5.1+ / 7+).
.DESCRIPTION
    Uso (uma linha):
      irm https://raw.githubusercontent.com/Ivomsantiago/Curl_Commander/main/scripts/install.ps1 | iex

    Escolhe o melhor método disponível, nesta ordem:
      1. uv tool   (isolado, recomendado)
      2. pipx      (isolado)
      3. venv gerenciado em %LOCALAPPDATA%\CurlCommander\venv + atalho em ...\bin

    É idempotente e não assume nada em silêncio: avisa antes de baixar da rede e
    ao alterar o PATH. Todas as mensagens são em português.
.PARAMETER Yes
    Não perguntar nada (uso em scripts/CI).
.PARAMETER Help
    Mostrar esta ajuda.
.NOTES
    Variável de ambiente CURLCMD_SOURCE: instala desta origem em vez do PyPI
    (um caminho local ou especificação pip). A CI usa isso para instalar a
    partir do checkout: $env:CURLCMD_SOURCE='.'; .\scripts\install.ps1 -Yes
#>
[CmdletBinding()]
param(
    [switch]$Yes,
    [switch]$Help
)

$ErrorActionPreference = 'Stop'

$Package  = 'curlcommander'
$Source   = if ($env:CURLCMD_SOURCE) { $env:CURLCMD_SOURCE } else { $Package }
$VenvDir  = Join-Path $env:LOCALAPPDATA 'CurlCommander\venv'
$ShimDir  = Join-Path $env:LOCALAPPDATA 'CurlCommander\bin'

if ($Help) {
    Get-Help $PSCommandPath -Detailed
    Write-Host ''
    Write-Host 'Sem Python? Baixe um binário standalone na página de releases:'
    Write-Host '  https://github.com/Ivomsantiago/Curl_Commander/releases'
    exit 0
}

function Info($m) { Write-Host "[*] $m" }
function Ok($m)   { Write-Host "[OK] $m" }
function Warn($m) { Write-Warning $m }
function Have([string]$name) { [bool](Get-Command $name -ErrorAction SilentlyContinue) }

function Confirm([string]$question) {
    if ($Yes) { return $true }
    if (-not [Environment]::UserInteractive) {
        Warn 'Sem sessão interativa. Rode novamente com -Yes para prosseguir.'
        return $false
    }
    $reply = Read-Host "$question [s/N]"
    return $reply -match '^(s|sim|y|yes)$'
}

function Test-OnPath([string]$dir) {
    $parts = $env:PATH -split ';'
    return $parts -contains $dir
}

function Update-CurrentSessionPath {
    # A registry PATH change (ours, or uv/pipx's own) never propagates to a
    # process already running — child processes only inherit PATH at launch.
    # Rebuilding $env:Path from Machine+User here makes `curlcmd` work in the
    # SAME window that ran the installer, without needing a new terminal.
    $machine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $user    = [Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = @($machine, $user) -join ';'
}

function Confirm-Version([string]$exe) {
    try {
        $v = & $exe --version 2>$null
        if ($LASTEXITCODE -eq 0) { Ok "Instalado: $v"; return $true }
    } catch { }
    Warn "Instalado, mas '$exe --version' não respondeu. Verifique o PATH."
    return $false
}

function Invoke-Setup([string]$exe) {
    Write-Host ''
    if (Confirm "Rodar 'curlcmd setup' agora para conferir a base?") {
        if ($Yes) { & $exe setup --yes } else { & $exe setup }
    } else {
        Write-Host 'Depois, rode:  curlcmd setup        (conferir base)'
        Write-Host '              curlcmd setup --all   (recursos opcionais + payloads)'
        Write-Host '              curlcmd doctor        (diagnóstico)'
    }
}

function Update-ToolPath([string]$tool, [string[]]$arguments) {
    # Windows PowerShell 5.1 turns any native stderr output into a
    # NativeCommandError when the script uses ErrorActionPreference=Stop.
    # uv writes harmless status messages (including "already in PATH") to
    # stderr, so run only this best-effort shell integration with Continue and
    # decide from the native exit code instead. Do not let it abort an install
    # that has already succeeded.
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        & $tool @arguments 2>$null | Out-Null
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousPreference
    }

    if ($exitCode -ne 0) {
        Warn "Não foi possível atualizar o PATH automaticamente com '$tool'. Abra um novo terminal se curlcmd não for encontrado."
    }
}

function Install-WithUv {
    Info 'Instalando com uv tool (isolado)…'
    if (-not (Confirm 'Baixar/instalar o curlcmd via uv (usa a rede)?')) { throw 'Cancelado.' }
    if ($Source -eq $Package) { uv tool install --force $Package }
    else { uv tool install --force --from $Source $Package }
    Update-ToolPath 'uv' @('tool', 'update-shell')
    Ok 'Instalado via uv tool.'
    Update-CurrentSessionPath
    if (Have 'curlcmd') { [void](Confirm-Version 'curlcmd'); Invoke-Setup 'curlcmd' }
    else { Warn 'curlcmd ainda não está no PATH mesmo após atualizar a sessão atual. Abra um novo terminal.' }
}

function Install-WithPipx {
    Info 'Instalando com pipx (isolado)…'
    if (-not (Confirm 'Baixar/instalar o curlcmd via pipx (usa a rede)?')) { throw 'Cancelado.' }
    pipx install --force $Source
    Update-ToolPath 'pipx' @('ensurepath')
    Ok 'Instalado via pipx.'
    Update-CurrentSessionPath
    if (Have 'curlcmd') { [void](Confirm-Version 'curlcmd'); Invoke-Setup 'curlcmd' }
    else { Warn 'curlcmd ainda não está no PATH mesmo após atualizar a sessão atual. Abra um novo terminal.' }
}

function Install-WithVenv {
    Info "uv e pipx não encontrados — criando um venv gerenciado em $VenvDir…"
    if (-not (Confirm 'Criar o venv e baixar o curlcmd (usa a rede)?')) { throw 'Cancelado.' }
    $py = $null
    foreach ($cand in 'py', 'python', 'python3') { if (Have $cand) { $py = $cand; break } }
    if (-not $py) { throw 'Python 3.11+ não encontrado. Instale o Python ou use o binário standalone.' }

    & $py -m venv $VenvDir
    $venvPy = Join-Path $VenvDir 'Scripts\python.exe'
    & $venvPy -m pip install --upgrade pip | Out-Null
    & $venvPy -m pip install --upgrade $Source

    New-Item -ItemType Directory -Force -Path $ShimDir | Out-Null
    $venvExe = Join-Path $VenvDir 'Scripts\curlcmd.exe'
    $shim = Join-Path $ShimDir 'curlcmd.cmd'
    # Um .cmd de atalho é mais portável que um symlink no Windows.
    "@echo off`r`n`"$venvExe`" %*`r`n" | Set-Content -Path $shim -Encoding ASCII
    Ok "Instalado no venv, com atalho em $shim."

    [void](Confirm-Version $venvExe)
    if (-not (Test-OnPath $ShimDir)) {
        if (Confirm "Adicionar $ShimDir ao PATH do usuário (permanente)?") {
            $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
            $parts = @()
            if ($userPath) { $parts = $userPath -split ';' | Where-Object { $_ -ne '' } }
            if ($parts -notcontains $ShimDir) {
                # Idempotency: never append a duplicate entry on a repeat install/update.
                $newPath = if ($userPath) { "$userPath;$ShimDir" } else { $ShimDir }
                try {
                    [Environment]::SetEnvironmentVariable('Path', $newPath, 'User')
                    Ok 'PATH do usuário atualizado.'
                } catch {
                    Warn "Não foi possível gravar o PATH do usuário automaticamente: $_"
                    Write-Host "  Adicione manualmente: $ShimDir"
                }
            }
        } else {
            Warn "$ShimDir não está no seu PATH. Rode o instalador de novo para adicioná-lo, ou adicione manualmente."
        }
    }
    Update-CurrentSessionPath
    if (-not (Have 'curlcmd')) {
        Warn 'curlcmd ainda não está no PATH da sessão atual (PATH de usuário pode estar truncado). Abra um novo terminal.'
    }
    Invoke-Setup $venvExe
}

Info "CurlCommander — instalador (origem: $Source)"
if (Have 'uv') { Install-WithUv }
elseif (Have 'pipx') { Install-WithPipx }
else { Install-WithVenv }
