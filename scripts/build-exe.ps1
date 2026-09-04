$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

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
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue (Join-Path $root "dist\PokeTokenBar-Windows")

& $python -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --onedir `
    --name "PokeTokenBar-Windows" `
    --paths (Join-Path $root "src") `
    --add-data "$(Join-Path $root 'src\poketokenbar_windows\qml');poketokenbar_windows\qml" `
    --collect-all PySide6 `
    (Join-Path $root "scripts\pyinstaller_entry.py")
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed to build PokeTokenBar-Windows."
}

$bundleInternal = Join-Path $root "dist\PokeTokenBar-Windows\_internal"
# Codex can add its bundled Poppler runtime to PATH. PyInstaller then mistakes
# Poppler's versioned ICU 78 for the unversioned Windows ICU used by Qt 6.
foreach ($foreignIcu in @("icuuc.dll", "icudt78.dll")) {
    Remove-Item -LiteralPath (Join-Path $bundleInternal $foreignIcu) -Force -ErrorAction SilentlyContinue
}

$executable = Join-Path $root "dist\PokeTokenBar-Windows\PokeTokenBar-Windows.exe"
if (-not (Test-Path -LiteralPath $executable -PathType Leaf)) {
    throw "PyInstaller completed without producing $executable."
}

Write-Host "Built: dist\PokeTokenBar-Windows\PokeTokenBar-Windows.exe"
