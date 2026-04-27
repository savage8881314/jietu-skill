$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$source = Join-Path $repoRoot "skill"
$targetRoot = Join-Path $HOME ".codex\skills"
$target = Join-Path $targetRoot "web-capture-layout"

if (-not (Test-Path $source)) {
    throw "Skill source folder not found: $source"
}

New-Item -ItemType Directory -Path $targetRoot -Force | Out-Null
New-Item -ItemType Directory -Path $target -Force | Out-Null

Copy-Item -Path (Join-Path $source "*") -Destination $target -Recurse -Force

Write-Host "Installed web-capture-layout to $target"
