$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

if (-not (Test-Path ".venv")) {
    python -m venv .venv
}
& ".venv/Scripts/python.exe" -m pip install -e ".[dev]"

# Qt's own standard-button strings ("Close", "Cancel", "OK", ...) live in
# Qt's own qtbase_<code>.qm, not this app's mdtools_<code>.qm -- see
# i18n/__init__.py's install_translator() docstring. Located dynamically
# (not a hardcoded .venv path) since PySide6's own install layout can
# shift between versions/platforms.
$qtTranslations = & ".venv/Scripts/python.exe" -c "from PySide6.QtCore import QLibraryInfo; print(QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath))"

& ".venv/Scripts/pyinstaller.exe" --noconfirm --windowed --name MDTools --paths src `
    --icon "assets/img/mdlogo.ico" `
    --add-data "src/mdtools/templates/defaults.json;mdtools/templates" `
    --add-data "src/mdtools/i18n/mdtools_pl.qm;mdtools/i18n" `
    --add-data "src/mdtools/i18n/mdtools_ja.qm;mdtools/i18n" `
    --add-data "$qtTranslations/qtbase_pl.qm;PySide6/translations" `
    --add-data "$qtTranslations/qtbase_ja.qm;PySide6/translations" `
    --add-data "assets/img;assets/img" `
    --add-data "assets/icons;assets/icons" `
    src/mdtools/main.py

Write-Host "Build output: dist/MDTools/MDTools.exe"
