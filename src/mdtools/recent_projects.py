"""Tracks the last few project files opened/saved -- backs File > Open
Recent and the startup dialog's recent-projects list.

Persisted the same way i18n stores the language choice: an explicit
QSettings(path, IniFormat) pointing at settings.ini in AppConfigLocation,
deliberately not the default QSettings() (native registry on Windows) --
that requires QApplication.organizationName to be set, which would change
QStandardPaths.AppConfigLocation (adding an extra folder level) and
silently relocate templates.json away from where templates/registry.py
has always read/written it. See i18n/__init__.py's _settings() for the
same reasoning.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, QStandardPaths

MAX_RECENT = 12
_SETTINGS_KEY = "recent_projects"


def _settings() -> QSettings:
    config_dir = Path(QStandardPaths.writableLocation(QStandardPaths.AppConfigLocation))
    config_dir.mkdir(parents=True, exist_ok=True)
    return QSettings(str(config_dir / "settings.ini"), QSettings.Format.IniFormat)


def recent_projects() -> list[str]:
    """Most-recently-used first. Entries whose file no longer exists on
    disk are silently dropped -- a moved/deleted project would otherwise
    clutter the list with an entry that can only fail to open."""
    stored = _settings().value(_SETTINGS_KEY, [])
    if isinstance(stored, str):
        # QSettings collapses a single-item string list down to a bare
        # string on some backends -- normalize back to a list.
        stored = [stored] if stored else []
    return [path for path in stored if Path(path).is_file()]


def add_recent_project(path: str) -> None:
    """Moves `path` to the front of the list, dedupes, and trims to
    MAX_RECENT. Called on every successful open/save so "recently edited"
    reflects both, not just files explicitly opened."""
    path = str(Path(path))
    existing = [p for p in recent_projects() if Path(p) != Path(path)]
    _settings().setValue(_SETTINGS_KEY, [path] + existing[: MAX_RECENT - 1])
