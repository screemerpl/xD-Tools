"""A downloaded album can be burned to CD, not only recorded to MiniDisc.

The one thing worth guarding here is what the request itself flagged: the
recording entry is hidden without an MDRem adapter, and copying that gate
onto burning would hide it from exactly the person most likely to want it,
since burning needs the drive rather than the infrared.
"""

from pathlib import Path

import pytest

from mdtools import app_settings
from mdtools.app_window import MainWindow
from mdtools.panels import telegram_chat_dialog
from mdtools.panels.telegram_chat_dialog import BURN, RECORD, TelegramChatDialog


def _downloads(tmp_path: Path) -> Path:
    root = tmp_path / "telegram"
    (root / "Skillet - Unleashed").mkdir(parents=True, exist_ok=True)
    (root / "Skillet - Unleashed" / "01.flac").write_bytes(b"")
    return root


# --- the menu entry -----------------------------------------------------


def test_burning_telegram_downloads_picks_an_album_and_burns_it(qt_app, tmp_path, monkeypatch):
    root = _downloads(tmp_path)
    monkeypatch.setattr(app_settings, "telegram_download_folder", lambda: str(root))
    burned = []
    monkeypatch.setattr(MainWindow, "_burn_folder", lambda self, folder: burned.append(folder))

    MainWindow(show_startup_dialog=False)._burn_from_telegram_downloads()

    # With a single album there is nothing to ask about: the root is handed
    # over as it is, and audio_folder.list_audio_files() recurses into the
    # one subfolder itself (the rule pick_album_folder leans on).
    assert burned == [root]


def test_the_recording_and_burning_entries_share_their_album_picker(qt_app, tmp_path, monkeypatch):
    """Both sort first, and both ask which album only when there is more
    than one -- one helper, so they cannot drift apart."""
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
    window._burn_from_telegram_downloads()
    window._record_from_telegram_downloads()

    assert asked == [root, root]


def test_a_cancelled_album_picker_burns_nothing(qt_app, tmp_path, monkeypatch):
    monkeypatch.setattr(app_settings, "telegram_download_folder", lambda: str(_downloads(tmp_path)))
    monkeypatch.setattr("mdtools.app_window.pick_album_folder", lambda parent, folder: (folder, False))
    monkeypatch.setattr(
        MainWindow, "_burn_folder", lambda self, folder: pytest.fail("nothing was chosen")
    )

    MainWindow(show_startup_dialog=False)._burn_from_telegram_downloads()


# --- the button in the chat dialog --------------------------------------


def _dialog(qt_app, tmp_path, monkeypatch) -> TelegramChatDialog:
    monkeypatch.setattr(app_settings, "telegram_download_folder", lambda: str(tmp_path / "dl"))
    # Construction alone is inert -- no worker, no network -- which is
    # exactly what these tests want (see TelegramChatDialog.start_connecting).
    dialog = TelegramChatDialog("123456", "hash", "@my_bot", tmp_path / "dl")
    dialog._session_folder = str(_downloads(tmp_path))
    return dialog


def test_the_burn_button_does_not_need_an_adapter(qt_app, tmp_path, monkeypatch):
    monkeypatch.setattr(app_settings, "mdrem_enabled", lambda: False)
    dialog = _dialog(qt_app, tmp_path, monkeypatch)

    dialog._update_continue_button()
    dialog._update_burn_button()

    assert dialog.continue_btn.isEnabled() is False
    assert dialog.burn_btn.isEnabled() is True
    assert dialog.burn_btn.toolTip() == ""


def test_neither_button_works_while_a_download_is_in_flight(qt_app, tmp_path, monkeypatch):
    monkeypatch.setattr(app_settings, "mdrem_enabled", lambda: True)
    dialog = _dialog(qt_app, tmp_path, monkeypatch)
    dialog._active_downloads.add(7)

    dialog._update_burn_button()

    assert dialog.burn_btn.isEnabled() is False
    assert "download" in dialog.burn_btn.toolTip().lower()


def test_which_button_was_pressed_is_what_the_caller_reads(qt_app, tmp_path, monkeypatch):
    monkeypatch.setattr(app_settings, "mdrem_enabled", lambda: True)
    monkeypatch.setattr(
        telegram_chat_dialog, "pick_album_folder", lambda parent, folder: (folder / "Skillet - Unleashed", True)
    )

    dialog = _dialog(qt_app, tmp_path, monkeypatch)
    dialog._on_burn_clicked()
    assert dialog.downloaded_action == BURN
    assert dialog.downloaded_folder.endswith("Skillet - Unleashed")

    other = _dialog(qt_app, tmp_path, monkeypatch)
    other._on_continue_clicked()
    assert other.downloaded_action == RECORD


def test_the_default_action_is_recording(qt_app, tmp_path, monkeypatch):
    """So a dialog closed any other way cannot be mistaken for a burn."""
    assert _dialog(qt_app, tmp_path, monkeypatch).downloaded_action == RECORD
