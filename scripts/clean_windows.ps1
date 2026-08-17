param(
    [switch]$All  # also remove .venv (forces a fresh `pip install ".[dev]"` on next build/run)
)

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

foreach ($target in @("build", "dist", ".pytest_cache")) {
    if (Test-Path $target) {
        Write-Host "Removing $target"
        Remove-Item -Recurse -Force $target
    }
}

# PyInstaller regenerates this from scratch on every build (see
# scripts/build_windows.ps1) -- it's a byproduct, not hand-maintained.
Get-ChildItem -Path . -File -Filter "*.spec" | ForEach-Object {
    Write-Host "Removing $($_.Name)"
    Remove-Item -Force $_.FullName
}

foreach ($root in @("src", "tests")) {
    Get-ChildItem -Path $root -Recurse -Directory -Filter "__pycache__" | ForEach-Object {
        Write-Host "Removing $($_.FullName)"
        Remove-Item -Recurse -Force $_.FullName
    }
    Get-ChildItem -Path $root -Recurse -File -Filter "*.pyc" | Remove-Item -Force
    # editable installs (`pip install -e .`) leave an egg-info dir under src/
    Get-ChildItem -Path $root -Recurse -Directory -Filter "*.egg-info" | ForEach-Object {
        Write-Host "Removing $($_.FullName)"
        Remove-Item -Recurse -Force $_.FullName
    }
}

# ...and some pip versions leave one at the repo root instead
Get-ChildItem -Path . -Directory -Filter "*.egg-info" | ForEach-Object {
    Write-Host "Removing $($_.FullName)"
    Remove-Item -Recurse -Force $_.FullName
}

if ($All -and (Test-Path ".venv")) {
    Write-Host "Removing .venv"
    Remove-Item -Recurse -Force ".venv"
}

Write-Host "Clean complete."
