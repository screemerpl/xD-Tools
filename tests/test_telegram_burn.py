"""A downloaded album can land on a MiniDisc/cassette or be burned to CD --
one "Record" entry now does either, dispatching on the open project's
medium (see app_window._record_folder_dialog). There used to be a second,
separate "Burn Downloaded Album to CD..." button/action; it collapsed into
this one, the same way the Recording menu's own folder/foobar2000 entries
did.

The one thing worth guarding here is what the original request flagged: a
CD project must not need an MDRem adapter to record from Telegram
downloads, since burning needs the drive rather than the infrared.
"""

from pathlib import Path

import pytest

from mdtools import app_settings
from mdtools.app_window import MainWindow
from mdtools.panels import telegram_chat_dialog
from mdtools.panels.telegram_chat_dialog import TelegramChatDialog
from mdtools.project import MEDIUM_CD, MEDIUM_MD


def _downloads(tmp_path: Path) -> Path:
    root = tmp_path / "telegram"
    (root / "Skillet - Unleashed").mkdir(parents=True, exist_ok=True)
    (root / "Skillet - Unleashed" / "01.flac").write_bytes(b"")
    return root


# --- the menu entry -----------------------------------------------------


def test_recording_from_telegram_downloads_burns_on_a_cd_project(qt_app, tmp_path, monkeypatch):
    """No adapter needed at all: a CD project's "Record from Telegram
    Downloads..." dispatches straight to burning."""
    root = _downloads(tmp_path)
    monkeypatch.setattr(app_settings, "telegram_download_folder", lambda: str(root))
    monkeypatch.setattr(app_settings, "mdrem_enabled", lambda: False)
    burned = []
    monkeypatch.setattr(MainWindow, "_burn_folder", lambda self, folder: burned.append(folder))

    window = MainWindow(show_startup_dialog=False)
    window.project.medium = MEDIUM_CD

    window._record_from_telegram_downloads()

    # With a single album there is nothing to ask about: the root is handed
    # over as it is, and audio_folder.list_audio_files() recurses into the
    # one subfolder itself (the rule pick_album_folder leans on).
    assert burned == [root]


def test_recording_from_telegram_downloads_records_on_a_minidisc_project(qt_app, tmp_path, monkeypatch):
    root = _downloads(tmp_path)
    monkeypatch.setattr(app_settings, "telegram_download_folder", lambda: str(root))
    recorded = []
    monkeypatch.setattr(MainWindow, "_record_folder_dialog", lambda self, folder: recorded.append(folder))

    window = MainWindow(show_startup_dialog=False)
    window.project.medium = MEDIUM_MD

    window._record_from_telegram_downloads()

    assert recorded == [root]


def test_the_recording_entry_asks_which_album_only_when_there_is_more_than_one(qt_app, tmp_path, monkeypatch):
    """The album picker is shared by both destinations -- one helper, so
    they cannot drift apart."""
    root = _downloads(tmp_path)
    (root / "Falling In Reverse - Popular Monster").mkdir()
    (root / "Falling In Reverse - Popular Monster" / "01.flac").write_bytes(b"")
    monkeypatch.setattr(app_settings, "telegram_download_folder", lambda: str(root))

    asked = []

    def fake_pick(parent, folder):
        asked.append(folder)
        return folder / "Skillet - Unleashed", True

    monkeypatch.setattr("mdtools.app_window.pick_album_folder", fake_pick)
    monkeypatch.setattr(MainWindow, "_burn_folder", lambda self, folder: None)
    monkeypatch.setattr(MainWindow, "_record_folder_dialog", lambda self, folder: None)

    window = MainWindow(show_startup_dialog=False)
    window.project.medium = MEDIUM_CD
    window._record_from_telegram_downloads()
    window.project.medium = MEDIUM_MD
    window._record_from_telegram_downloads()

    assert asked == [root, root]


def test_a_cancelled_album_picker_does_nothing(qt_app, tmp_path, monkeypatch):
    monkeypatch.setattr(app_settings, "telegram_download_folder", lambda: str(_downloads(tmp_path)))
    monkeypatch.setattr("mdtools.app_window.pick_album_folder", lambda parent, folder: (folder, False))
    monkeypatch.setattr(
        MainWindow, "_burn_folder", lambda self, folder: pytest.fail("nothing was chosen")
    )

    window = MainWindow(show_startup_dialog=False)
    window.project.medium = MEDIUM_CD
    window._record_from_telegram_downloads()


# --- the button in the chat dialog --------------------------------------


def _dialog(qt_app, tmp_path, monkeypatch) -> TelegramChatDialog:
    monkeypatch.setattr(app_settings, "telegram_download_folder", lambda: str(tmp_path / "dl"))
    # Construction alone is inert -- no worker, no network -- which is
    # exactly what these tests want (see TelegramChatDialog.start_connecting).
    dialog = TelegramChatDialog("123456", "hash", "@my_bot", tmp_path / "dl")
    dialog._session_folder = str(_downloads(tmp_path))
    return dialog


def test_there_is_only_one_button_now(qt_app, tmp_path, monkeypatch):
    """The separate "Burn Downloaded Album to CD..." button is gone --
    _record_folder_dialog dispatches to burning itself once app_window
    reads back the chosen folder."""
    dialog = _dialog(qt_app, tmp_path, monkeypatch)
    assert not hasattr(dialog, "burn_btn")


def test_clicking_the_button_hands_back_the_chosen_folder(qt_app, tmp_path, monkeypatch):
    monkeypatch.setattr(app_settings, "mdrem_enabled", lambda: True)
    monkeypatch.setattr(
        telegram_chat_dialog, "pick_album_folder", lambda parent, folder: (folder / "Skillet - Unleashed", True)
    )

    dialog = _dialog(qt_app, tmp_path, monkeypatch)
    dialog._on_continue_clicked()

    assert dialog.downloaded_folder.endswith("Skillet - Unleashed")
