"""The Experimental menu is the landing spot for whatever work-in-progress
feature comes next -- gated by Window > Settings' "Show experimental
features" checkbox, exactly like MDRem's entry points are gated by "Enable
MDRem IR remote adapter" (see test_mdrem_menu_sync.py). It's built once at
startup as a QMenu, not a QAction, so it needs its own explicit re-sync
after Settings closes, same as _sync_mdrem_actions().
"""

from pathlib import Path

import pytest

from mdtools import album_sort, app_settings
from mdtools import app_window as app_module
from mdtools.app_window import MainWindow
from mdtools.panels.settings_dialog import SettingsDialog


def _window() -> MainWindow:
    return MainWindow(show_startup_dialog=False)


def _settings_returning(monkeypatch, enabled: bool):
    class _Fake:
        def __init__(self, parent=None):
            pass

        def exec(self):
            app_settings.set_experimental_features_enabled(enabled)
            return 1

    monkeypatch.setattr(app_module, "SettingsDialog", _Fake)


def test_the_menu_is_hidden_by_default(qt_app):
    app_settings.set_experimental_features_enabled(False)

    window = _window()
    assert window.experimental_menu.menuAction().isVisible() is False


def test_the_menu_appears_when_the_flag_is_switched_on(qt_app, monkeypatch):
    app_settings.set_experimental_features_enabled(False)
    window = _window()
    _settings_returning(monkeypatch, True)

    window._show_settings()

    assert window.experimental_menu.menuAction().isVisible()


def test_the_menu_disappears_when_the_flag_is_switched_off(qt_app, monkeypatch):
    app_settings.set_experimental_features_enabled(True)
    window = _window()
    assert window.experimental_menu.menuAction().isVisible(), "precondition"
    _settings_returning(monkeypatch, False)

    window._show_settings()

    assert window.experimental_menu.menuAction().isVisible() is False


def test_experimental_settings_action_opens_its_own_dialog(qt_app, monkeypatch):
    """Experimental features get their own settings dialog, separate from
    Window > Settings -- reached from a menu entry that already only shows
    up while the flag is on, so it needs no separate gating of its own."""
    opened = []

    def fake_exec(self):
        opened.append(self)
        return 0

    monkeypatch.setattr(app_module.ExperimentalSettingsDialog, "exec", fake_exec)

    window = _window()
    window._show_experimental_settings()

    assert len(opened) == 1
    assert isinstance(opened[0], app_module.ExperimentalSettingsDialog)


def test_the_real_settings_dialog_keeps_the_menu_in_step(qt_app, monkeypatch):
    """Not just the stand-in above -- the actual dialog writes the setting on
    OK, and the menu has to reflect that."""
    app_settings.set_experimental_features_enabled(False)
    window = _window()
    monkeypatch.setattr(
        SettingsDialog,
        "exec",
        lambda self: (self.experimental_check.setChecked(True), self._on_accept())[1],
    )

    window._show_settings()

    assert app_settings.experimental_features_enabled() is True
    assert window.experimental_menu.menuAction().isVisible()


# --- the Telegram chat entry -- gated a second time, on a local session file -


def test_the_chat_entry_is_hidden_without_a_session(qt_app):
    app_settings.telegram_session_path().parent.mkdir(parents=True, exist_ok=True)
    app_settings.telegram_session_path().unlink(missing_ok=True)

    window = _window()

    assert window.telegram_chat_action.isVisible() is False


def test_the_chat_entry_appears_once_a_session_file_exists(qt_app):
    window = _window()
    assert window.telegram_chat_action.isVisible() is False, "precondition"

    session_path = app_settings.telegram_session_path()
    session_path.parent.mkdir(parents=True, exist_ok=True)
    session_path.write_bytes(b"fake session")
    window._sync_experimental_menu()

    assert window.telegram_chat_action.isVisible()


def test_signing_in_through_experimental_settings_reveals_the_entry_immediately(qt_app, monkeypatch):
    """No restart required: _show_experimental_settings() must re-sync the
    menu itself once the dialog closes, the same way _show_settings()
    already does for the MDRem/experimental-flag actions."""
    window = _window()
    assert window.telegram_chat_action.isVisible() is False, "precondition"

    def fake_exec(self):
        session_path = app_settings.telegram_session_path()
        session_path.parent.mkdir(parents=True, exist_ok=True)
        session_path.write_bytes(b"fake session")
        return 0

    monkeypatch.setattr(app_module.ExperimentalSettingsDialog, "exec", fake_exec)

    window._show_experimental_settings()

    assert window.telegram_chat_action.isVisible()


# --- Sort/Record from Telegram Downloads -- act on the configured folder ---
#
# Neither needs a bot connection or a signed-in session at all -- they just
# organize/record whatever has already accumulated in the one configured
# download folder (see telegram_chat_dialog.py: downloads no longer land in
# a fresh per-session subfolder, explicit user request).


def _touch(root: Path, name: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / name
    path.write_bytes(b"x")
    return path


@pytest.fixture
def downloads(tmp_path) -> Path:
    """A subfolder of tmp_path, not tmp_path itself -- the autouse
    _isolated_app_settings fixture (conftest.py) also writes its own
    _app_settings.ini directly into tmp_path, and sort_folder()/read_album_tag()
    would otherwise trip over that extra, untagged file sitting right next
    to the ones a test actually put there."""
    folder = tmp_path / "downloads"
    folder.mkdir()
    return folder


def test_sort_telegram_downloads_sorts_the_configured_folder(qt_app, monkeypatch, downloads):
    app_settings.set_cd_rip_folder(str(downloads))
    a = _touch(downloads, "a.flac")
    b = _touch(downloads, "b.flac")
    tags = {a: ("Caskets", "Lost Souls"), b: ("Skillet", "Unleashed")}
    monkeypatch.setattr(album_sort, "read_album_tag", lambda p: tags[p])
    informed = []
    monkeypatch.setattr(
        app_module.QMessageBox, "information", staticmethod(lambda *a, **k: informed.append(a[2]))
    )

    _window()._sort_telegram_downloads()

    assert (downloads / "Caskets - Lost Souls" / "a.flac").exists()
    assert (downloads / "Skillet - Unleashed" / "b.flac").exists()
    assert "2" in informed[0]


def test_sort_telegram_downloads_creates_the_folder_if_missing(qt_app, monkeypatch, tmp_path):
    """Nothing to sort in a folder that doesn't exist yet -- must not
    crash, same "created on demand" rule as cdrip.ensure_folder()."""
    missing = tmp_path / "not-created-yet"
    app_settings.set_cd_rip_folder(str(missing))
    informed = []
    monkeypatch.setattr(
        app_module.QMessageBox, "information", staticmethod(lambda *a, **k: informed.append(a[2]))
    )

    _window()._sort_telegram_downloads()

    assert missing.is_dir()
    # Reported directly: this used to say "already sorted", which is not
    # true of a folder with nothing in it at all.
    assert "empty" in informed[0]


def test_record_from_telegram_downloads_sorts_then_asks_which_album(qt_app, monkeypatch, downloads):
    app_settings.set_cd_rip_folder(str(downloads))
    a = _touch(downloads, "a.flac")
    b = _touch(downloads, "b.flac")
    tags = {a: ("Caskets", "Lost Souls"), b: ("Skillet", "Unleashed")}
    monkeypatch.setattr(album_sort, "read_album_tag", lambda p: tags[p])
    monkeypatch.setattr(
        app_module.QInputDialog, "getItem", staticmethod(lambda *a, **k: ("Skillet - Unleashed", True))
    )
    recorded: list[Path] = []
    window = _window()
    monkeypatch.setattr(window, "_record_folder_dialog", recorded.append)

    window._record_from_telegram_downloads()

    # sort_folder() already ran, so both albums are in their own subfolder.
    assert (downloads / "Caskets - Lost Souls").is_dir()
    assert recorded == [downloads / "Skillet - Unleashed"]


def test_record_from_telegram_downloads_with_one_album_skips_the_picker(qt_app, monkeypatch, downloads):
    app_settings.set_cd_rip_folder(str(downloads))
    _touch(downloads, "a.flac")
    monkeypatch.setattr(
        app_module.QInputDialog,
        "getItem",
        staticmethod(lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not ask for just one album"))),
    )
    recorded: list[Path] = []
    window = _window()
    monkeypatch.setattr(window, "_record_folder_dialog", recorded.append)

    window._record_from_telegram_downloads()

    assert recorded == [downloads]


def test_record_from_audio_folder_with_nothing_in_it_says_so_and_opens_nothing(qt_app, monkeypatch, downloads):
    """Reported directly: an empty audio folder used to open
    FolderRecordDialog anyway (which then showed its own disabled-Record,
    "no audio files" state -- easy to mistake for the metadata editor,
    since it has the same kind of Artist/Album/Year fields) instead of
    saying up front that there is nothing to record."""
    app_settings.set_cd_rip_folder(str(downloads))
    informed = []
    monkeypatch.setattr(
        app_module.QMessageBox, "information", staticmethod(lambda *a, **k: informed.append(a[2]))
    )
    window = _window()
    monkeypatch.setattr(
        window,
        "_record_folder_dialog",
        lambda *a, **k: pytest.fail("must not open a recording dialog for an empty folder"),
    )

    window._record_from_telegram_downloads()

    assert informed
    assert "nothing to record" in informed[0]


def test_record_from_audio_folder_asks_among_already_sorted_albums_too(qt_app, monkeypatch, downloads):
    """Not just freshly-sorted loose files -- a folder that already holds
    several album subfolders (the normal case once CD rips and Telegram
    downloads share one folder: whatever accumulated there over past
    sessions) must still offer the picker. sort_folder() only ever acts on
    files sitting loose directly in the folder, so pre-existing subfolders
    have to be picked up by pick_album_folder() on their own."""
    app_settings.set_cd_rip_folder(str(downloads))
    _touch(downloads / "Caskets - Lost Souls", "01.flac")
    _touch(downloads / "Skillet - Unleashed", "01.flac")
    _touch(downloads / "Falling In Reverse - Popular Monster", "01.flac")
    monkeypatch.setattr(
        app_module.QInputDialog, "getItem", staticmethod(lambda *a, **k: ("Skillet - Unleashed", True))
    )
    recorded: list[Path] = []
    window = _window()
    monkeypatch.setattr(window, "_record_folder_dialog", recorded.append)

    window._record_from_telegram_downloads()

    assert recorded == [downloads / "Skillet - Unleashed"]


def test_cancelling_the_album_picker_does_not_record(qt_app, monkeypatch, downloads):
    app_settings.set_cd_rip_folder(str(downloads))
    a = _touch(downloads, "a.flac")
    b = _touch(downloads, "b.flac")
    tags = {a: ("Caskets", "Lost Souls"), b: ("Skillet", "Unleashed")}
    monkeypatch.setattr(album_sort, "read_album_tag", lambda p: tags[p])
    monkeypatch.setattr(app_module.QInputDialog, "getItem", staticmethod(lambda *a, **k: ("", False)))
    window = _window()
    monkeypatch.setattr(
        window, "_record_folder_dialog", lambda *a, **k: pytest.fail("must not record after cancelling")
    )

    window._record_from_telegram_downloads()
