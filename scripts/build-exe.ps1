$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$branch = & git branch --show-current
if ($LASTEXITCODE -ne 0) {
    throw "Could not read the current Git branch."
}
$isCi = $env:GITHUB_ACTIONS -eq "true"
if (-not $branch -and $isCi) {
    $branch = if ($env:GITHUB_HEAD_REF) { $env:GITHUB_HEAD_REF } else { $env:GITHUB_REF_NAME }
}
$branch = ([string]$branch).Trim()
if (-not $branch) {
    throw "Build from a named Git branch."
}
$commit = (& git rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) {
    throw "Could not read the source commit."
}

# Worktrees share one local dist directory. CI has an isolated checkout and
# keeps its original artifact path even for pull request builds.
$commonGitDir = (& git rev-parse --path-format=absolute --git-common-dir).Trim()
if ($LASTEXITCODE -ne 0) {
    throw "Could not locate the shared Git directory."
}
$sharedRoot = Split-Path -Parent $commonGitDir
$distRoot = Join-Path $sharedRoot "dist"
if ($branch -eq "master" -or $isCi) {
    $slotRoot = $distRoot
} else {
    $safeBranch = ($branch -replace '[^A-Za-z0-9._-]', '-').Trim('.-')
    if ($safeBranch.Length -gt 48) {
        $safeBranch = $safeBranch.Substring(0, 48)
    }
    $branchHash = [BitConverter]::ToString(
        [Security.Cryptography.SHA256]::HashData([Text.Encoding]::UTF8.GetBytes($branch))
    ).Replace("-", "").Substring(0, 8).ToLowerInvariant()
    $slotRoot = Join-Path (Join-Path $distRoot "branches") "$safeBranch-$branchHash"
}

$target = Join-Path $slotRoot "PokeTokenBar-Windows"
$stagingRoot = Join-Path $distRoot (".staging-{0}-{1}" -f $PID, [guid]::NewGuid().ToString("N"))
$stagedApp = Join-Path $stagingRoot "PokeTokenBar-Windows"
$backup = Join-Path $slotRoot (".previous-{0}" -f [guid]::NewGuid().ToString("N"))

$venv = Join-Path $root ".venv-build"
if (-not (Test-Path $venv)) {
    if ($env:PTB_BUILD_PYTHON) {
        & $env:PTB_BUILD_PYTHON -m venv $venv
    } else {
        $py = Get-Command py -ErrorAction SilentlyContinue
        if ($py) {
            & py -3 -c "import sys; print(sys.executable)" *> $null
        }
        if ($py -and $LASTEXITCODE -eq 0) {
            & py -3 -m venv $venv
        } else {
            & python -m venv $venv
        }
    }
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path (Join-Path $venv "Scripts\python.exe"))) {
        throw "Could not create .venv-build. Set PTB_BUILD_PYTHON to a Python 3.10+ executable."
    }
}

$python = Join-Path $venv "Scripts\python.exe"
& $python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) {
    throw "Failed to upgrade pip in .venv-build."
}
& $python -m pip install ".[build]"
if ($LASTEXITCODE -ne 0) {
    throw "Failed to install PokeTokenBar build dependencies."
}

Remove-Item -Recurse -Force -ErrorAction SilentlyContinue (Join-Path $root "build\PokeTokenBar-Windows")
New-Item -ItemType Directory -Path $stagingRoot -Force | Out-Null
try {
    $pyInstallerArgs = @(
        "--noconfirm", "--clean", "--windowed", "--onedir",
        "--name", "PokeTokenBar-Windows",
        "--distpath", $stagingRoot,
        "--paths", (Join-Path $root "src"),
        "--add-data", "$(Join-Path $root 'src\poketokenbar_windows\qml');poketokenbar_windows\qml",
        "--collect-all", "PySide6",
        (Join-Path $root "scripts\pyinstaller_entry.py")
    )
    & $python -m PyInstaller @pyInstallerArgs
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed to build PokeTokenBar-Windows."
    }

    $bundleInternal = Join-Path $stagedApp "_internal"
    # Codex can add its bundled Poppler runtime to PATH. PyInstaller then mistakes
    # Poppler's versioned ICU 78 for the unversioned Windows ICU used by Qt 6.
    foreach ($foreignIcu in @("icuuc.dll", "icudt78.dll")) {
        Remove-Item -LiteralPath (Join-Path $bundleInternal $foreignIcu) -Force -ErrorAction SilentlyContinue
    }

    $executable = Join-Path $stagedApp "PokeTokenBar-Windows.exe"
    if (-not (Test-Path -LiteralPath $executable -PathType Leaf)) {
        throw "PyInstaller completed without producing $executable."
    }
    Copy-Item -LiteralPath (Join-Path $root "scripts\Probar-en-paralelo.cmd") -Destination $stagedApp
    [ordered]@{
        branch = $branch
        commit = $commit
        built_utc = (Get-Date).ToUniversalTime().ToString("o")
    } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $stagedApp "build-info.json")

    New-Item -ItemType Directory -Path $slotRoot -Force | Out-Null
    if (Test-Path -LiteralPath $target) {
        Move-Item -LiteralPath $target -Destination $backup
    }
    try {
        Move-Item -LiteralPath $stagedApp -Destination $target
    } catch {
        if (Test-Path -LiteralPath $backup) {
            Move-Item -LiteralPath $backup -Destination $target
        }
        throw
    }
    if (Test-Path -LiteralPath $backup) {
        Remove-Item -LiteralPath $backup -Recurse -Force
    }
} finally {
    if (Test-Path -LiteralPath $stagingRoot) {
        Remove-Item -LiteralPath $stagingRoot -Recurse -Force
    }
}

Write-Host "Built $commit ($branch): $target"
if ($branch -eq "master" -and -not $isCi) {
    & (Join-Path $PSScriptRoot "prune-dist.ps1") -Apply
}
