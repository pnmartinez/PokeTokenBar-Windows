param([switch]$Apply)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$branch = [string](& git -C $root branch --show-current)
if ($LASTEXITCODE -ne 0 -or $branch.Trim() -ne "master") {
    throw "Prune branch builds only from master."
}
$commonGitDir = (& git -C $root rev-parse --path-format=absolute --git-common-dir).Trim()
if ($LASTEXITCODE -ne 0) {
    throw "Could not locate the shared Git directory."
}
$sharedRoot = Split-Path -Parent $commonGitDir
$previewRoot = Join-Path (Join-Path $sharedRoot "dist") "branches"
if (-not (Test-Path -LiteralPath $previewRoot -PathType Container)) {
    return
}
$previewRoot = (Resolve-Path -LiteralPath $previewRoot).Path

foreach ($preview in Get-ChildItem -LiteralPath $previewRoot -Directory) {
    if ($preview.Attributes -band [IO.FileAttributes]::ReparsePoint) {
        continue
    }
    if ($preview.Parent.FullName -ne $previewRoot) {
        continue
    }
    $manifestPath = Join-Path (Join-Path $preview.FullName "PokeTokenBar-Windows") "build-info.json"
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        continue
    }
    try {
        $info = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    } catch {
        continue
    }
    $previewBranch = [string]$info.branch
    $previewCommit = [string]$info.commit
    if (-not $previewBranch -or -not $previewCommit -or $previewBranch -eq "master") {
        continue
    }
    & git -C $root check-ref-format --branch $previewBranch *> $null
    if ($LASTEXITCODE -ne 0) {
        continue
    }
    $safeBranch = ($previewBranch -replace '[^A-Za-z0-9._-]', '-').Trim('.-')
    if ($safeBranch.Length -gt 48) {
        $safeBranch = $safeBranch.Substring(0, 48)
    }
    $branchHash = [BitConverter]::ToString(
        [Security.Cryptography.SHA256]::HashData([Text.Encoding]::UTF8.GetBytes($previewBranch))
    ).Replace("-", "").Substring(0, 8).ToLowerInvariant()
    if ($preview.Name -ne "$safeBranch-$branchHash") {
        continue
    }

    $remoteRef = "refs/remotes/origin/$previewBranch"
    & git -C $root show-ref --verify --quiet $remoteRef
    if ($LASTEXITCODE -eq 0) {
        $candidate = $remoteRef
    } else {
        $candidate = $previewCommit
    }
    & git -C $root merge-base --is-ancestor $candidate HEAD
    if ($LASTEXITCODE -ne 0) {
        continue
    }
    if ($Apply) {
        Remove-Item -LiteralPath $preview.FullName -Recurse -Force
        Write-Host "Removed merged branch build: $previewBranch"
    } else {
        Write-Host "Would remove merged branch build: $previewBranch"
    }
}
