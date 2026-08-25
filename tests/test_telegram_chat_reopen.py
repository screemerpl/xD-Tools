"""_open_telegram_bot_chat()'s participation in #27's shared machinery:
it is not one of the six recording/rip/burn/upload dialogs and does not
compete with them for the MDRem port/audio device/optical drive, but it
drives the very same single bottom progress bar with its own
download-queue status -- so it goes through the same
_guard_no_concurrent_operation()/_drive_recording_bar() pair they do, to
keep that one shared bar from ever being fought over.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QDialog, QMessageBox

from mdtools import app_window as app_module
from mdtools.app_window import MainWindow


class _FakeTelegramDialog(QDialog):
    """A stand-in for TelegramChatDialog: a real QDialog with the real
    signals/attributes _drive_recording_bar() and exec_hideable() need."""

    running_changed = Signal(bool)
    overall_progress_changed = Signal(float, str)
    visibility_changed = Signal(bool)
    show_requested = Signal()

    downloaded_folder = None

    def __init__(self, *args, **kwargs):
        super().__init__()
        self.hidden_for_background = False
        self.during_exec = None

    def start_connecting(self) -> None:
        # The real one emits this from here -- see TelegramChatDialog.
        # Faithful on purpose: connecting the bar *after* this call missed
        # the emission entirely, so the bar never appeared and a chat
        # hidden right after opening could not be got back.
        self.running_changed.emit(True)

    def request_stop(self) -> None:
        pass

    def request_show(self) -> None:
        self.visibility_changed.emit(False)

    def exec(self) -> int:
        self.running_changed.emit(True)
        self.overall_progress_changed.emit(0.5, "1/2 done")
        if self.during_exec is not None:
            self.during_exec(self)
        self.running_changed.emit(False)
        return QDialog.DialogCode.Rejected


def _window() -> MainWindow:
    return MainWindow(show_startup_dialog=False)


def _configured(monkeypatch) -> None:
    monkeypatch.setattr(app_module.app_settings, "telegram_bot_username", lambda: "@my_bot")
    monkeypatch.setattr(app_module.app_settings, "telegram_api_id", lambda: "123456")
    monkeypatch.setattr(app_module.app_settings, "telegram_api_hash", lambda: "hash")


def test_download_progress_reaches_the_bar_while_the_chat_runs(qt_app, monkeypatch):
    window = _window()
    _configured(monkeypatch)
    seen: dict = {}

    def capture(dialog):
        bar = window.recording_bar
        seen["shown"] = not bar.isHidden()
        seen["overall"] = (bar.overall_bar.value(), bar.overall_label.text())
        seen["track_hidden"] = bar.track_bar.isHidden()

    def factory(*args, **kwargs):
        dialog = _FakeTelegramDialog()
        dialog.during_exec = capture
        return dialog

    monkeypatch.setattr(app_module, "TelegramChatDialog", factory)

    window._open_telegram_bot_chat()

    assert seen["shown"] is True
    assert seen["overall"] == (500, "1/2 done")
    # track_progress=False, same as BurnDialog/MDRemUploadDialog -- a
    # Telegram download queue has no single "current track" to show.
    assert seen["track_hidden"] is True


def test_the_bar_and_guard_are_released_once_the_chat_closes(qt_app, monkeypatch):
    window = _window()
    _configured(monkeypatch)
    monkeypatch.setattr(app_module, "TelegramChatDialog", _FakeTelegramDialog)

    window._open_telegram_bot_chat()

    assert window.recording_bar.isHidden()
    assert window._active_recording_dialog is None


def test_a_running_recording_blocks_opening_the_chat(qt_app, monkeypatch):
    """The guard's whole point: the chat would otherwise fight a real
    recording over the one shared bottom bar."""
    window = _window()
    _configured(monkeypatch)
    window._active_recording_dialog = object()
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)

    def _explode(*args, **kwargs):
        raise AssertionError("must not construct TelegramChatDialog while something else is running")

    monkeypatch.setattr(app_module, "TelegramChatDialog", _explode)

    window._open_telegram_bot_chat()  # must return via the guard, not raise


def test_the_bar_catches_the_running_signal_start_connecting_emits(qt_app, monkeypatch):
    """TelegramChatDialog emits running_changed(True) from
    start_connecting(), so the bar has to be wired up before that call,
    not after it. Wired up after, the emission was missed, the bar never
    appeared, and a chat hidden straight after opening was unreachable."""
    window = _window()
    _configured(monkeypatch)
    seen: dict = {}

    class _HidesImmediately(_FakeTelegramDialog):
        def exec(self):
            # What the user did: clicked Hide before anything had run.
            seen["bar_up"] = not window.recording_bar.isHidden()
            self.visibility_changed.emit(True)
            seen["can_get_back"] = not window.recording_bar.show_dialog_btn.isHidden()
            return QDialog.DialogCode.Rejected

    monkeypatch.setattr(app_module, "TelegramChatDialog", _HidesImmediately)

    window._open_telegram_bot_chat()

    assert seen["bar_up"] is True
    assert seen["can_get_back"] is True
