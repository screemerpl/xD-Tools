"""Global, user-level app settings -- e.g. the DPI values used for the
on-screen canvas, exports, and Bake Layers. Deliberately NOT part of any
project (see project.py/io/project_io.py for project-scoped settings
instead) -- these apply the same way regardless of which project is open,
so they're persisted per-user, not saved into .mdproj files.

Persisted the same way i18n and recent_projects store their own settings:
an explicit QSettings(path, IniFormat) pointing at the shared settings.ini
in AppConfigLocation, deliberately not the default QSettings() -- see
i18n/__init__.py's _settings() for why (organizationName side effects on
where templates.json lives).
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, QStandardPaths

# Fallback defaults -- what every DPI value used to be as a fixed constant
# before it became user-configurable. Used until the user opens Window >
# Settings... and changes something, and as the reset target there.
DEFAULT_SCREEN_DPI = 96.0
DEFAULT_EXPORT_DPI = 300.0
DEFAULT_BAKE_DPI = DEFAULT_EXPORT_DPI * 3

_SCREEN_DPI_KEY = "screen_dpi"
_EXPORT_DPI_KEY = "default_export_dpi"
_BAKE_DPI_KEY = "bake_dpi"
_MDREM_ENABLED_KEY = "mdrem_enabled"
_MDREM_PORT_KEY = "mdrem_port"
_FOOBAR_URL_KEY = "foobar_url"

# foo_beefweb's own default listening address.
DEFAULT_FOOBAR_URL = "http://localhost:8880"


def _settings() -> QSettings:
    config_dir = Path(QStandardPaths.writableLocation(QStandardPaths.AppConfigLocation))
    config_dir.mkdir(parents=True, exist_ok=True)
    return QSettings(str(config_dir / "settings.ini"), QSettings.Format.IniFormat)


def screen_dpi() -> float:
    """Dots-per-inch used to convert mm to on-screen pixels at 100% zoom
    (mdtools.constants.mm_to_px/px_to_mm) -- NOT necessarily the display's
    real physical DPI; a CSS-style 96 default that the user can override
    from Window > Settings... if content looks the wrong physical size on
    their particular screen."""
    return float(_settings().value(_SCREEN_DPI_KEY, DEFAULT_SCREEN_DPI))


def set_screen_dpi(value: float) -> None:
    _settings().setValue(_SCREEN_DPI_KEY, float(value))


def default_export_dpi() -> float:
    """Default DPI Export Print PNG/Export Print PNG (Grayscale) use --
    still overridable per call (export_png()'s own `dpi` parameter), this
    is just what a fresh export starts from."""
    return float(_settings().value(_EXPORT_DPI_KEY, DEFAULT_EXPORT_DPI))


def set_default_export_dpi(value: float) -> None:
    _settings().setValue(_EXPORT_DPI_KEY, float(value))


def bake_dpi() -> float:
    """DPI Tools > Bake Layers renders at -- deliberately higher than
    default_export_dpi() by default (a baked layer's resolution is locked
    in for good, unlike a re-renderable vector layer), see constants.py's
    former BAKE_DPI docstring/note for the full reasoning."""
    return float(_settings().value(_BAKE_DPI_KEY, DEFAULT_BAKE_DPI))


def set_bake_dpi(value: float) -> None:
    _settings().setValue(_BAKE_DPI_KEY, float(value))


def mdrem_enabled() -> bool:
    """Whether the MDRem IR remote adapter is available -- gates the
    Metadata dialog's Upload Tracklist button and the startup screen's
    Remote button, both of which are meaningless without hardware.

    Note the string handling: an IniFormat QSettings round-trips a bool
    back as the *text* "true"/"false", and `bool("false")` is True, so
    reading this with a plain bool() would make the setting impossible to
    ever turn back off."""
    value = _settings().value(_MDREM_ENABLED_KEY, False)
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes")
    return bool(value)


def set_mdrem_enabled(value: bool) -> None:
    _settings().setValue(_MDREM_ENABLED_KEY, bool(value))


def mdrem_port() -> str:
    """Serial port the adapter is on, e.g. "COM3". Empty means "not chosen
    yet" -- callers fall back to mdrem.detect_port()."""
    return str(_settings().value(_MDREM_PORT_KEY, "") or "")


def set_mdrem_port(value: str) -> None:
    _settings().setValue(_MDREM_PORT_KEY, str(value))


def foobar_url() -> str:
    """Base URL of foobar2000's Beefweb Remote Control component, used by
    Record to MiniDisc. Configurable because Beefweb's port is."""
    return str(_settings().value(_FOOBAR_URL_KEY, DEFAULT_FOOBAR_URL) or DEFAULT_FOOBAR_URL)


def set_foobar_url(value: str) -> None:
    _settings().setValue(_FOOBAR_URL_KEY, str(value).strip() or DEFAULT_FOOBAR_URL)
