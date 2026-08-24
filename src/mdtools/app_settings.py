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

import os
from pathlib import Path

from PySide6.QtCore import QSettings, QStandardPaths

from mdtools import user_paths

# Fallback defaults -- what every DPI value used to be as a fixed constant
# before it became user-configurable. Used until the user opens Window >
# Settings... and changes something, and as the reset target there.
DEFAULT_SCREEN_DPI = 96.0
DEFAULT_EXPORT_DPI = 300.0
DEFAULT_BAKE_DPI = DEFAULT_EXPORT_DPI * 3

# xD-Tools' own Telegram API credentials are **injected at build time, never
# written in this file** -- see _bundled_telegram_credentials() below.
_TELEGRAM_API_ID_ENV = "MDTOOLS_TELEGRAM_API_ID"
_TELEGRAM_API_HASH_ENV = "MDTOOLS_TELEGRAM_API_HASH"

_SCREEN_DPI_KEY = "screen_dpi"
_EXPORT_DPI_KEY = "default_export_dpi"
_BAKE_DPI_KEY = "bake_dpi"
_MDREM_ENABLED_KEY = "mdrem_enabled"
_EXPERIMENTAL_FEATURES_ENABLED_KEY = "experimental_features_enabled"
_MDREM_PORT_KEY = "mdrem_port"
_MDREM_EXTENDED_REMOTE_KEY = "mdrem_extended_remote"
_FOOBAR_URL_KEY = "foobar_url"
_FOOBAR_EXE_KEY = "foobar_exe"
_CD_RIP_FOLDER_KEY = "cd_rip_folder"
_CD_DRIVE_KEY = "cd_drive"
_MUSIC_FOLDER_KEY = "music_folder"
_TELEGRAM_API_ID_KEY = "telegram_api_id"
_TELEGRAM_API_HASH_KEY = "telegram_api_hash"
_TELEGRAM_BOT_USERNAME_KEY = "telegram_bot_username"
_TELEGRAM_DOWNLOAD_FOLDER_KEY = "telegram_download_folder"
_TELEGRAM_PHONE_KEY = "telegram_phone"
_REGENERATE_FONT_FAMILY_KEY = "regenerate_font_family"
_AUDIO_OUTPUT_DEVICE_KEY = "audio_output_device"
_RECORDING_GAIN_DB_KEY = "recording_gain_db"

# foo_beefweb's own default listening address.
DEFAULT_FOOBAR_URL = "http://localhost:8880"


def _config_dir() -> Path:
    config_dir = Path(QStandardPaths.writableLocation(QStandardPaths.AppConfigLocation))
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def _settings() -> QSettings:
    return QSettings(str(_config_dir() / "settings.ini"), QSettings.Format.IniFormat)


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


def experimental_features_enabled() -> bool:
    """Whether work-in-progress features show up in the UI at all -- gates
    the Experimental menu (and whatever else lands there) the same way
    mdrem_enabled() gates the MDRem entry points above.

    Same string-handling caveat as mdrem_enabled(): an IniFormat QSettings
    round-trips a bool back as the text "true"/"false", and bool("false")
    is True, so this can't be read with a plain bool()."""
    value = _settings().value(_EXPERIMENTAL_FEATURES_ENABLED_KEY, False)
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes")
    return bool(value)


def set_experimental_features_enabled(value: bool) -> None:
    _settings().setValue(_EXPERIMENTAL_FEATURES_ENABLED_KEY, bool(value))


def mdrem_extended_remote() -> bool:
    """Whether the software remote shows every key code the firmware knows,
    rather than the ones a physical RM-D10P actually has a button for.

    Remembered rather than asked each time: it is a property of how someone
    uses the deck, not of the disc in front of them, and the dialog is
    rebuilt from scratch on every open.

    Same string-handling caveat as mdrem_enabled() above -- an IniFormat
    QSettings hands a bool back as the text "true"/"false", and
    bool("false") is True."""
    value = _settings().value(_MDREM_EXTENDED_REMOTE_KEY, False)
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes")
    return bool(value)


def set_mdrem_extended_remote(value: bool) -> None:
    _settings().setValue(_MDREM_EXTENDED_REMOTE_KEY, bool(value))


def mdrem_port() -> str:
    """Serial port the adapter is on, e.g. "COM3". Empty means "not chosen
    yet" -- callers fall back to mdrem.detect_port()."""
    return str(_settings().value(_MDREM_PORT_KEY, "") or "")


def set_mdrem_port(value: str) -> None:
    _settings().setValue(_MDREM_PORT_KEY, str(value))


def last_regenerate_font_family() -> str | None:
    """The font family last chosen in Toolbar > "Regenerate with
    Font..."'s picker, or None if it has never been used -- the dialog
    opens on this instead of the application's own default font, so a
    user who settles on a face doesn't have to re-pick it every time."""
    value = _settings().value(_REGENERATE_FONT_FAMILY_KEY, "")
    return str(value) if value else None


def set_last_regenerate_font_family(family: str) -> None:
    _settings().setValue(_REGENERATE_FONT_FAMILY_KEY, str(family))


def audio_output_device() -> str:
    """The output device xD-Tools' own audio engine plays a recording's
    source material through -- e.g. an interface's S/PDIF or line output
    feeding a MiniDisc deck or a CD burner's monitor path. Saved as a
    device *name* (PortAudio's own index is not stable across a reboot or
    a USB replug), same "a saved value is never silently replaced by
    whatever else happens to be plugged in" rule mdrem_port() follows.

    Empty means "not chosen yet" -- callers (audio_engine.resolve_device())
    fall back to the OS default output device, exactly like a preview
    playback always does regardless of this setting."""
    return str(_settings().value(_AUDIO_OUTPUT_DEVICE_KEY, "") or "")


def set_audio_output_device(value: str) -> None:
    _settings().setValue(_AUDIO_OUTPUT_DEVICE_KEY, str(value).strip())


# Headroom against clipping on the digital/analogue transfer -- explicit
# user request, previously a hardcoded RECORDING_VOLUME_DB constant
# duplicated in record_dialog.py and tape_record_dialog.py, applied via
# foobar2000's own set_volume(). Now a real setting this engine's own
# AudioPlayer reads instead, so it no longer has to live twice.
DEFAULT_RECORDING_GAIN_DB = -5.0


def recording_gain_db() -> float:
    """How far below full scale a recording's output is played, for
    headroom on the digital/analogue path into the deck or burner. A
    QSettings float round-trips as a string, hence the explicit float()
    the way screen_dpi()/etc. also need it."""
    return float(_settings().value(_RECORDING_GAIN_DB_KEY, DEFAULT_RECORDING_GAIN_DB))


def set_recording_gain_db(value: float) -> None:
    _settings().setValue(_RECORDING_GAIN_DB_KEY, float(value))


def foobar_url() -> str:
    """Base URL of foobar2000's Beefweb Remote Control component, used by
    Record to MiniDisc. Configurable because Beefweb's port is."""
    return str(_settings().value(_FOOBAR_URL_KEY, DEFAULT_FOOBAR_URL) or DEFAULT_FOOBAR_URL)


def set_foobar_url(value: str) -> None:
    _settings().setValue(_FOOBAR_URL_KEY, str(value).strip() or DEFAULT_FOOBAR_URL)


def foobar_exe() -> str:
    """foobar2000's own executable, which Record CD needs *in addition to*
    the Beefweb URL above -- the two do different halves of the same job.
    Beefweb cannot be given files outside its configured music directories
    (see foobar.add_files_via_cli), so the ripped tracks go in through the
    command line instead.

    Empty means "not chosen yet"; callers fall back to
    foobar.find_foobar_exe()."""
    return str(_settings().value(_FOOBAR_EXE_KEY, "") or "")


def set_foobar_exe(value: str) -> None:
    _settings().setValue(_FOOBAR_EXE_KEY, str(value).strip())


def default_cd_rip_folder() -> str:
    """XDProjects/Audio by default -- shared with Telegram bot downloads,
    since both are audio destined for the same recording flow. Previously
    the system temp folder, which did not survive a reboot and was not
    where a user would think to look for it. Changeable in Window >
    Settings for anyone who wants it somewhere else."""
    return str(user_paths.audio_dir())


def cd_rip_folder() -> str:
    return str(_settings().value(_CD_RIP_FOLDER_KEY, "") or default_cd_rip_folder())


def set_cd_rip_folder(value: str) -> None:
    _settings().setValue(_CD_RIP_FOLDER_KEY, str(value).strip())


def cd_drive() -> str:
    """The optical drive last ripped from, so a second disc does not have
    to be pointed at it again. Empty until one has been used."""
    return str(_settings().value(_CD_DRIVE_KEY, "") or "")


def set_cd_drive(value: str) -> None:
    _settings().setValue(_CD_DRIVE_KEY, str(value).strip())


def music_folder() -> str:
    """Where "Record Folder to MiniDisc..." last browsed -- the *parent* of
    the album picked, since the next album is far more likely to be its
    sibling than inside it. Empty until one has been chosen, at which point
    the picker falls back to the OS's own Music folder
    (user_paths.music_start_path).

    Not exposed in Window > Settings: it is a picker's memory, not a
    preference anyone would go looking for, unlike the rip folder, which
    decides where hundreds of megabytes land."""
    return str(_settings().value(_MUSIC_FOLDER_KEY, "") or "")


def set_music_folder(value: str) -> None:
    _settings().setValue(_MUSIC_FOLDER_KEY, str(value).strip())


# --- Telegram bot integration (experimental) --------------------------------
#
# A user-run bot the user searches/downloads albums from, over a real
# Telegram user login (see mdtools.telegram_bot for why: the Bot API forbids
# one bot messaging another, so this has to act as an actual account, not a
# bot token). Only reachable through the "Show experimental features"
# checkbox's own Experimental Settings dialog -- see
# panels/experimental_settings_dialog.py.
#
# A user's own override is stored in plain-text INI here, same as every other
# credential-shaped setting in this app (the foobar2000 path, the MDRem
# port) -- there is no secret-storage mechanism anywhere in this codebase,
# so this is not a new inconsistency, but it is worth stating plainly rather
# than quietly glossing over: anyone with access to this machine's
# settings.ini can read them.


def _bundled_telegram_credentials() -> tuple[str, str]:
    """xD-Tools' own registered API ID/Hash, or `("", "")` if this build was
    made without them.

    **Injected at build time and deliberately absent from the source tree**,
    so they never enter git history -- which for a repo with a public remote
    is the one exposure that is actually irreversible (a rewrite still leaves
    them in forks and caches). Two sources, in order:

    1. `MDTOOLS_TELEGRAM_API_ID`/`_HASH` in the environment -- for CI, or a
       developer who would rather not keep a file around.
    2. `mdtools/_build_credentials.py`, which `scripts/build_windows.ps1`/
       `build_linux.sh` write from those same environment variables before
       running PyInstaller. It is gitignored, so it stays a local, untracked
       artifact; keeping one locally is also how a dev-mode run gets working
       credentials.

    **This is not, and cannot be, secret storage.** The value has to be
    reconstructed in plaintext to be sent to Telegram, so it is recoverable
    from any build that carries it -- by `strings`, a debugger, or watching
    the handshake. What build-time injection buys is precisely the part that
    *can* be solved: the credentials are not published in source control.
    The exposure that remains is the normal one for this class of Telegram
    credential (an application/rate-limit identifier, not access to anyone's
    account -- that is `telegram_session_path()`), and the mitigation for it
    is the per-user override above, which lets a user switch to their own
    registered app if the bundled pair is ever rate-limited or banned.

    Missing credentials are a supported state, not an error: the app simply
    cannot sign in until the user supplies their own, and
    ExperimentalSettingsDialog._sign_in() says exactly that."""
    api_id = os.environ.get(_TELEGRAM_API_ID_ENV, "").strip()
    api_hash = os.environ.get(_TELEGRAM_API_HASH_ENV, "").strip()
    if api_id and api_hash:
        return api_id, api_hash
    try:
        from mdtools import _build_credentials
    except ImportError:
        return "", ""
    return (
        str(getattr(_build_credentials, "TELEGRAM_API_ID", "") or "").strip(),
        str(getattr(_build_credentials, "TELEGRAM_API_HASH", "") or "").strip(),
    )


def telegram_api_id() -> str:
    return str(_settings().value(_TELEGRAM_API_ID_KEY, "") or _bundled_telegram_credentials()[0])


def set_telegram_api_id(value: str) -> None:
    _settings().setValue(_TELEGRAM_API_ID_KEY, str(value).strip())


def telegram_api_hash() -> str:
    return str(_settings().value(_TELEGRAM_API_HASH_KEY, "") or _bundled_telegram_credentials()[1])


def set_telegram_api_hash(value: str) -> None:
    _settings().setValue(_TELEGRAM_API_HASH_KEY, str(value).strip())


def telegram_phone() -> str:
    """Prefills TelegramLoginDialog's phone field -- saved as soon as the
    user sends a code, independent of whether Experimental Settings' own
    OK/Cancel has been pressed, since it belongs to the login dialog rather
    than to the API ID/Hash/bot username block."""
    return str(_settings().value(_TELEGRAM_PHONE_KEY, "") or "")


def set_telegram_phone(value: str) -> None:
    _settings().setValue(_TELEGRAM_PHONE_KEY, str(value).strip())


def telegram_bot_username() -> str:
    return str(_settings().value(_TELEGRAM_BOT_USERNAME_KEY, "") or "")


def set_telegram_bot_username(value: str) -> None:
    _settings().setValue(_TELEGRAM_BOT_USERNAME_KEY, str(value).strip())


def default_telegram_download_folder() -> str:
    """XDProjects/Audio by default -- the same shared folder
    default_cd_rip_folder() points at, since a downloaded album and a CD
    rip are both audio on their way into the same recording flow."""
    return str(user_paths.audio_dir())


def telegram_download_folder() -> str:
    return str(_settings().value(_TELEGRAM_DOWNLOAD_FOLDER_KEY, "") or default_telegram_download_folder())


def set_telegram_download_folder(value: str) -> None:
    _settings().setValue(_TELEGRAM_DOWNLOAD_FOLDER_KEY, str(value).strip())


def telegram_session_path() -> Path:
    """Where Telethon keeps its own session database -- not a QSettings
    value, a derived path, same "computed, not stored" shape as
    default_cd_rip_folder(). This file is equivalent to a live login to the
    user's real Telegram account: never touched by any cleanup routine,
    never embedded in a .mdproj, and it lives beside settings.ini, not
    inside the repo, so there is no .gitignore concern either.

    Derived from _settings().fileName()'s own parent rather than
    recomputing _config_dir() independently -- tests isolate this whole
    module by monkeypatching _settings() alone (see conftest.py's autouse
    _isolated_app_settings), and a second, independent path computation
    here would silently point at the real per-user config directory even
    under that isolation."""
    return Path(_settings().fileName()).parent / "telegram.session"
