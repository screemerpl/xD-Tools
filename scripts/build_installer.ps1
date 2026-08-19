# Builds the Windows installer: dist/xD-Tools-<version>-setup.exe
#
# Runs the PyInstaller build first unless -SkipBuild is given, then wraps
# its onedir output with NSIS. The version is read from the package itself,
# so there is one place it is stated and the installer cannot claim a
# different one than Help > About.
#
# NSIS is not bundled -- install it once with:
#     winget install NSIS.NSIS
# (open source, zlib licence). Everything else this script needs is already
# in the repo.

param(
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

function Find-MakeNsis {
    $command = Get-Command makensis.exe -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    foreach ($candidate in @(
            "$env:ProgramFiles\NSIS\makensis.exe",
            "${env:ProgramFiles(x86)}\NSIS\makensis.exe")) {
        if (Test-Path $candidate) { return $candidate }
    }
    throw "makensis.exe not found. Install NSIS first: winget install NSIS.NSIS"
}

if (-not $SkipBuild) {
    Write-Host "Building the application..."
    & powershell -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "build_windows.ps1")
    if ($LASTEXITCODE -ne 0) { throw "the application build failed" }
}

$source = Join-Path (Get-Location) "dist\MDTools"
if (-not (Test-Path (Join-Path $source "MDTools.exe"))) {
    throw "dist\MDTools\MDTools.exe is missing -- run without -SkipBuild, or build first."
}

# Read the version out of the package rather than restating it here.
$versionLine = Select-String -Path "src\mdtools\__init__.py" -Pattern '__version__\s*=\s*"([^"]+)"'
if (-not $versionLine) { throw "could not read __version__ from src\mdtools\__init__.py" }
$version = $versionLine.Matches[0].Groups[1].Value
# NSIS's VIProductVersion wants four numeric parts, so a version like
# "0.3.0-rc2" has to be reduced to the numbers before it is handed over.
$numeric = ($version -replace '[^0-9.].*$', '').TrimEnd('.')
while (($numeric -split '\.').Count -lt 3) { $numeric = "$numeric.0" }

$outFile = Join-Path (Get-Location) "dist\xD-Tools-$version-setup.exe"
$icon = Join-Path (Get-Location) "assets\img\xdtools.ico"
$script = Join-Path $PSScriptRoot "installer\mdtools.nsi"

$makensis = Find-MakeNsis
Write-Host "NSIS:    $makensis"
Write-Host "Version: $version (file version $numeric)"
Write-Host "Source:  $source"
Write-Host "Output:  $outFile"

$arguments = @(
    "/V2",
    "/DVERSION=$numeric",
    "/DDISPLAY_VERSION=$version",
    "/DSOURCE_DIR=$source",
    "/DOUT_FILE=$outFile"
)
if (Test-Path $icon) { $arguments += "/DAPP_ICON=$icon" }
$arguments += $script

& $makensis @arguments
if ($LASTEXITCODE -ne 0) { throw "makensis failed with exit code $LASTEXITCODE" }

$size = [math]::Round((Get-Item $outFile).Length / 1MB, 1)
Write-Host "Installer written: $outFile ($size MB)"
