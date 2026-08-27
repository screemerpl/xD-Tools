"""The Experimental menu is the landing spot for whatever work-in-progress
feature comes next -- gated by Window > Settings' "Show experimental
features" checkbox, exactly like MDRem's entry points are gated by "Enable
MDRem IR remote adapter" (see test_mdrem_menu_sync.py). It's built once at
startup as a QMenu, not a QAction, so it needs its own explicit re-sync
after Settings closes, same as _sync_mdrem_actions().

It currently holds nothing: the bot account became a group in Window >
Settings and the chat became a Source. So it is hidden regardless of the
flag -- an empty dropdown on the menu bar reads as something broken --
and these tests add an action of their own to exercise the flag, which is
also what proves the menu comes back on its own for the next feature that
lands in it.

The flag did not retire with the menu, though: it still gates the chat
entry in its new home, because moving an unfinished feature to a better
menu did not finish it.
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


def _with_a_future_feature(window) -> None:
    """Stands in for whatever lands in the menu next -- the menu is empty
    today and stays off the menu bar while it is."""
    window.experimental_menu.addAction("Some Future Thing...")


def test_the_menu_is_hidden_by_default(qt_app):
    app_settings.set_experimental_features_enabled(False)

    window = _window()
    assert window.experimental_menu.menuAction().isVisible() is False


def test_an_empty_menu_stays_off_the_menu_bar_even_with_the_flag_on(qt_app, monkeypatch):
    """Its contents all found homes of their own. Keeping the menu is for
    the next feature, not for showing an empty dropdown in the meantime."""
    app_settings.set_experimental_features_enabled(False)
    window = _window()
    _settings_returning(monkeypatch, True)

    window._show_settings()

    assert not window.experimental_menu.actions(), "precondition: it is empty"
    assert window.experimental_menu.menuAction().isVisible() is False


def test_the_menu_appears_when_the_flag_is_switched_on(qt_app, monkeypatch):
    app_settings.set_experimental_features_enabled(False)
    window = _window()
    _with_a_future_feature(window)
    _settings_returning(monkeypatch, True)

    window._show_settings()

    assert window.experimental_menu.menuAction().isVisible()


def test_the_menu_disappears_when_the_flag_is_switched_off(qt_app, monkeypatch):
    app_settings.set_experimental_features_enabled(True)
    window = _window()
    _with_a_future_feature(window)
    window._sync_experimental_menu()
    assert window.experimental_menu.menuAction().isVisible(), "precondition"
    _settings_returning(monkeypatch, False)

    window._show_settings()

    assert window.experimental_menu.menuAction().isVisible() is False


def test_the_menu_no_longer_carries_a_settings_entry_of_its_own(qt_app):
    """The one thing it held -- the Telegram bot account -- is a group in
    Window > Settings now, so there is one place to look for what
    xD-Tools is configured to do rather than two, one of them filed under
    Experimental."""
    window = _window()

    labels = [a.text() for a in window.experimental_menu.actions()]

    assert not any("Settings" in label for label in labels), labels


def test_the_real_settings_dialog_keeps_the_menu_in_step(qt_app, monkeypatch):
    """Not just the stand-in above -- the actual dialog writes the setting on
    OK, and the menu has to reflect that."""
    app_settings.set_experimental_features_enabled(False)
    window = _window()
    _with_a_future_feature(window)
    monkeypatch.setattr(
        SettingsDialog,
        "exec",
        lambda self: (self.experimental_check.setChecked(True), self._on_accept())[1],
    )

    window._show_settings()

    assert app_settings.experimental_features_enabled() is True
    assert window.experimental_menu.menuAction().isVisible()


# --- the Telegram chat entry -- in the Source menu, gated twice over ------
#
# It moved out of this menu, and kept the flag: a download is a source the
# way a CD is, but signing in to a bot account is still unfinished work.
# The second, independent gate is a local Telegram session file existing at
# all, which is what says there is anything to open a chat with.


def _sign_in() -> None:
    session_path = app_settings.telegram_session_path()
    session_path.parent.mkdir(parents=True, exist_ok=True)
    session_path.write_bytes(b"fake session")


def test_the_chat_entry_is_hidden_without_a_session(qt_app):
    app_settings.set_experimental_features_enabled(True)
    app_settings.telegram_session_path().parent.mkdir(parents=True, exist_ok=True)
    app_settings.telegram_session_path().unlink(missing_ok=True)

    window = _window()

    assert window.telegram_chat_action.isVisible() is False


def test_the_chat_entry_is_hidden_without_the_flag_even_with_a_session(qt_app):
    """Moving it to a menu everyone can see did not make it finished."""
    app_settings.set_experimental_features_enabled(False)
    _sign_in()

    window = _window()

    assert window.telegram_chat_action.isVisible() is False


def test_the_chat_entry_appears_once_a_session_file_exists(qt_app):
    app_settings.set_experimental_features_enabled(True)
    window = _window()
    assert window.telegram_chat_action.isVisible() is False, "precondition"

    _sign_in()
    window._sync_experimental_menu()

    assert window.telegram_chat_action.isVisible()


def test_the_chat_entry_is_in_the_source_menu(qt_app):
    """Not in Experimental, which holds nothing now -- and next to the
    other way audio gets into the audio folder."""
    app_settings.set_experimental_features_enabled(True)
    _sign_in()
    window = _window()

    assert window.telegram_chat_action.parent() is window.rip_cd_action.parent()


def test_signing_in_through_settings_reveals_the_entry_immediately(qt_app, monkeypatch):
    """No restart required: _show_settings() re-syncs the menu once the
    dialog closes, which now matters for signing in to Telegram too --
    that happens in the settings window's own Telegram group."""
    app_settings.set_experimental_features_enabled(True)
    window = _window()
    assert window.telegram_chat_action.isVisible() is False, "precondition"

    def fake_exec(self):
        _sign_in()
        return 0

    monkeypatch.setattr(app_module.SettingsDialog, "exec", fake_exec)

    window._show_settings()

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
