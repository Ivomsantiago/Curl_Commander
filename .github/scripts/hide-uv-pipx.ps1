# Dot-source this at the very top of every step in install-smoke-venv-windows
# that needs uv/pipx unreachable. It must be redone in-process in EVERY such
# step, not once and propagated via $GITHUB_ENV: GitHub Actions re-prepends
# every GITHUB_PATH addition (actions/setup-python registers its own Scripts
# directory that way) to the Path handed to each new step process, for the
# rest of the job, unconditionally -- silently undoing any "Path=" override
# written to $GITHUB_ENV by an earlier step. Confirmed via the real runner
# log: Get-Command kept resolving pipx.exe from the exact hostedtoolcache
# Scripts directory a prior step's $GITHUB_ENV override had already removed.
#
# Resolution is also done by direct filesystem Test-Path, not Get-Command:
# Get-Command -All was previously seen to under-report matches on this
# runner image, so this checks every Path directory against every
# $env:PATHEXT extension itself.
$targets = 'uv', 'pipx'
$exts = ($env:PATHEXT -split ';') + ''
$exclude = [System.Collections.Generic.List[string]]::new()
foreach ($dir in ($env:Path -split ';')) {
    $trimmed = $dir.TrimEnd('\')
    if (-not $trimmed) { continue }
    foreach ($name in $targets) {
        foreach ($ext in $exts) {
            if (Test-Path -LiteralPath (Join-Path $trimmed "$name$ext") -PathType Leaf) {
                $exclude.Add($dir)
                break
            }
        }
        if ($exclude.Contains($dir)) { break }
    }
}
if ($exclude.Count -gt 0) {
    Write-Host "Excluding from this process's PATH: $exclude"
    $env:Path = ($env:Path -split ';' | Where-Object { -not $exclude.Contains($_) }) -join ';'
}
