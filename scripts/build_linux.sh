#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -d .venv ]; then
    python3 -m venv .venv
fi
.venv/bin/pip install -e ".[dev]"

# Qt's own standard-button strings ("Close", "Cancel", "OK", ...) live in
# Qt's own qtbase_<code>.qm, not this app's mdtools_<code>.qm -- see
# i18n/__init__.py's install_translator() docstring. Located dynamically
# (not a hardcoded .venv path) since PySide6's own install layout can
# shift between versions/platforms.
QT_TRANSLATIONS=$(.venv/bin/python -c "from PySide6.QtCore import QLibraryInfo; print(QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath))")

# No bin/ is bundled here, unlike the Windows build: cdparanoia and flac
# are packaged by every distribution, so cdrip.find_tool() picks them up
# from PATH instead of a bundled copy.
.venv/bin/pyinstaller --noconfirm --windowed --name MDTools --paths src \
    --add-data "src/mdtools/templates/defaults.json:mdtools/templates" \
    --add-data "src/mdtools/i18n/mdtools_pl.qm:mdtools/i18n" \
    --add-data "src/mdtools/i18n/mdtools_ja.qm:mdtools/i18n" \
    --add-data "$QT_TRANSLATIONS/qtbase_pl.qm:PySide6/translations" \
    --add-data "$QT_TRANSLATIONS/qtbase_ja.qm:PySide6/translations" \
    --add-data "assets/img:assets/img" \
    --add-data "assets/icons:assets/icons" \
    src/mdtools/main.py

echo "Build output: dist/MDTools/MDTools"
