"""Language selection: persisted user choice + installing the matching
compiled Qt translation (.qm).

The .qm files live in this same package directory, alongside the .ts
source files they're compiled from -- see pyside6-lupdate/pyside6-lrelease
usage in the project docs. English ("en") is the language the source code
is written in, so it has no .ts/.qm of its own; selecting it just removes
whatever translator was previously installed.
"""

from __future__ import annotations

import importlib.resources
from pathlib import Path

from PySide6.QtCore import QLibraryInfo, QSettings, QStandardPaths, QTranslator
from PySide6.QtWidgets import QApplication

DEFAULT_LANGUAGE = "en"
AVAILABLE_LANGUAGES = {
    "en": "English",
    "pl": "Polski",
    "ja": "日本語",
}

_SETTINGS_KEY = "language"

# Kept alive for the life of the app: QApplication.installTranslator() does
# not itself keep a Python reference, so a purely-local QTranslator would be
# garbage collected (and silently stop translating) as soon as this module's
# install function returns.
_active_translator: QTranslator | None = None

# Separate from _active_translator above -- this one carries Qt's OWN
# built-in strings ("Close", "Cancel", "OK", ... used by e.g.
# QDialogButtonBox.StandardButton), not any of MDTools' own self.tr(...)
# text. mdtools_<code>.qm never contains these -- they live in Qt's own
# qtbase_<code>.qm, shipped inside the PySide6 wheel itself (found via
# QLibraryInfo, not this package's own directory) -- installing only
# mdtools_<code>.qm (the bug this fixes) leaves every Qt standard-button
# label in English regardless of the selected language.
_active_qt_translator: QTranslator | None = None


def _settings() -> QSettings:
    # An explicit path + IniFormat, deliberately NOT the default
    # QSettings() (native registry on Windows) -- that requires
    # QApplication.organizationName to be set, and setting it would change
    # QStandardPaths.AppConfigLocation (adding an extra folder level),
    # silently relocating templates.json away from where
    # templates/registry.py has always read/written it. Reusing that same
    # AppConfigLocation directory here (same call registry.py makes) keeps
    # everything in one place without touching organizationName at all.
    config_dir = Path(QStandardPaths.writableLocation(QStandardPaths.AppConfigLocation))
    config_dir.mkdir(parents=True, exist_ok=True)
    return QSettings(str(config_dir / "settings.ini"), QSettings.Format.IniFormat)


def current_language() -> str:
    value = _settings().value(_SETTINGS_KEY, DEFAULT_LANGUAGE)
    return value if value in AVAILABLE_LANGUAGES else DEFAULT_LANGUAGE


def set_language(code: str) -> None:
    _settings().setValue(_SETTINGS_KEY, code)


def install_translator(app: QApplication, code: str) -> None:
    """Installs the translator(s) for `code` on `app`, replacing whichever
    were installed before. Existing widgets do not retranslate live --
    callers should prompt for a restart after switching languages.

    Two independent QTranslators are installed: MDTools' own
    mdtools_<code>.qm (this package's own self.tr(...) strings) and Qt's
    own qtbase_<code>.qm (standard strings Qt itself owns, e.g. "Close"/
    "Cancel"/"OK" on a QDialogButtonBox.StandardButton) -- installing only
    the former leaves every Qt standard-button label in English regardless
    of the selected language, since mdtools_<code>.qm was never asked to
    translate text MDTools' own code never passes through self.tr()."""
    global _active_translator, _active_qt_translator
    if _active_translator is not None:
        app.removeTranslator(_active_translator)
        _active_translator = None
    if _active_qt_translator is not None:
        app.removeTranslator(_active_qt_translator)
        _active_qt_translator = None

    if code == DEFAULT_LANGUAGE or code not in AVAILABLE_LANGUAGES:
        return

    translator = QTranslator()
    qm_name = f"mdtools_{code}.qm"
    try:
        qm_path = importlib.resources.files(__package__) / qm_name
        loaded = qm_path.is_file() and translator.load(str(qm_path))
    except (FileNotFoundError, ModuleNotFoundError):
        loaded = False

    if loaded:
        app.installTranslator(translator)
        _active_translator = translator

    qt_translator = QTranslator()
    qt_translations_dir = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    if qt_translator.load(f"qtbase_{code}", qt_translations_dir):
        app.installTranslator(qt_translator)
        _active_qt_translator = qt_translator
