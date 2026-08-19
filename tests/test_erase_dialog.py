"""Erasing a disc, with no adapter and no deck.

The point of most of these is that the confirmation key must not go out
unless the user said they could see the deck asking for it. There is no
feedback channel, the operation is irreversible, and what the ERASE key
actually does to an unprotected disc was never established -- so "sent the
key and hoped" is not an acceptable shape for this one.
"""

from __future__ import annotations

import pytest

from mdtools import app_settings
from mdtools import app_window as app_module
from mdtools.app_window import MainWindow
from mdtools.panels import erase_dialog as module
from mdtools.panels.erase_dialog import EraseDiscDialog


@pytest.fixture
def isolated_settings(tmp_path, monkeypatch):
    from PySide6.QtCore import QSettings

    path = tmp_path / "settings.ini"
    monkeypatch.setattr(app_settings, "_settings", lambda: QSettings(str(path), QSettings.Format.IniFormat))
    return path


class _FakeClient:
    """Records what would have gone out over infrared."""

    def __init__(self, port, fail_on: str | None = None):
        self.port = port
        self.sent: list[str] = []
        self.closed = False
        self._fail_on = fail_on

    def open(self):
        return True

    def command(self, text, timeout_ms=None):
        if self._fail_on is not None and text == self._fail_on:
            raise module.mdrem.MDRemError("no adapter")
        self.sent.append(text)
        return []

    def close(self):
        self.closed = True


def _wire(monkeypatch, *, confirm=True, enter_presses=1, done=None, eject=False, fail_on=None):
    """Fakes the adapter and every modal answer.

    The confirmation prompt is a real dialog now, not a Yes/No box, so its
    exec() is replaced by one that presses Send Enter `enter_presses` times
    through the actual handler -- the key really goes out through the fake
    client -- and then answers Done or Nothing Happened. A real exec() would
    block forever under the offscreen platform.
    """
    from PySide6.QtWidgets import QDialog, QMessageBox

    client = _FakeClient("COM7", fail_on)
    monkeypatch.setattr(module.mdrem, "MDRemClient", lambda port: client)

    ok = QMessageBox.StandardButton.Ok if confirm else QMessageBox.StandardButton.Cancel
    monkeypatch.setattr(module.QMessageBox, "warning", staticmethod(lambda *a, **k: ok))

    accept = enter_presses > 0 if done is None else done

    def fake_prompt_exec(self):
        for _ in range(enter_presses):
            self._send_enter()
        return QDialog.DialogCode.Accepted if accept else QDialog.DialogCode.Rejected

    monkeypatch.setattr(module.ConfirmPromptDialog, "exec", fake_prompt_exec)

    monkeypatch.setattr(
        module.QMessageBox,
        "question",
        staticmethod(
            lambda *a, **k: QMessageBox.StandardButton.Yes if eject else QMessageBox.StandardButton.No
        ),
    )
    return client


def test_declining_the_warning_sends_nothing_at_all(qt_app, monkeypatch):
    client = _wire(monkeypatch, confirm=False)
    dialog = EraseDiscDialog("COM7")

    dialog._erase()

    assert client.sent == []
    assert dialog.erased is False


def test_erasing_stops_the_deck_first_then_asks_it_to_erase(qt_app, monkeypatch):
    """A deck mid-playback will not accept an edit, and assuming it was
    already stopped is not something that can be checked from here."""
    client = _wire(monkeypatch)
    EraseDiscDialog("COM7")._erase()

    assert client.sent[:2] == ["SEND STOP", "SEND ERASE"]


def test_the_confirmation_key_goes_out_only_once_the_user_has_seen_the_prompt(qt_app, monkeypatch):
    client = _wire(monkeypatch)
    dialog = EraseDiscDialog("COM7")

    dialog._erase()

    assert "SEND ENTER" in client.sent
    assert dialog.erased is True


def test_a_deck_that_never_asked_is_never_confirmed(qt_app, monkeypatch):
    """The whole safeguard. If the display showed nothing, sending ENTER
    would be pressing a button on a menu nobody can see."""
    client = _wire(monkeypatch, enter_presses=0)
    dialog = EraseDiscDialog("COM7")

    dialog._erase()

    assert "SEND ENTER" not in client.sent
    assert dialog.erased is False


def test_backing_out_cancels_so_the_deck_is_not_left_on_a_destructive_prompt(qt_app, monkeypatch):
    client = _wire(monkeypatch, enter_presses=0)
    EraseDiscDialog("COM7")._erase()

    assert client.sent[-1] == "SEND CANCEL"


def test_a_successful_erase_offers_to_eject(qt_app, monkeypatch):
    """The erased TOC is volatile until the disc comes out, exactly as a
    written one is."""
    client = _wire(monkeypatch, eject=True)
    EraseDiscDialog("COM7")._erase()

    assert client.sent[-1] == "SEND EJECT"


def test_declining_the_eject_leaves_the_disc_in(qt_app, monkeypatch):
    client = _wire(monkeypatch, eject=False)
    EraseDiscDialog("COM7")._erase()

    assert "SEND EJECT" not in client.sent


def test_a_failure_partway_reports_it_and_closes_the_port(qt_app, monkeypatch):
    client = _wire(monkeypatch, fail_on="SEND ERASE")
    dialog = EraseDiscDialog("COM7")

    dialog._erase()

    assert dialog.erased is False
    assert client.closed
    assert "MDRem" in dialog.status_label.text()


def test_the_port_is_released_when_the_dialog_is_dismissed(qt_app, monkeypatch):
    client = _wire(monkeypatch, enter_presses=0)
    dialog = EraseDiscDialog("COM7")
    dialog._client = client

    dialog.reject()

    assert client.closed


def test_enter_can_be_sent_as_many_times_as_the_deck_needs(qt_app, monkeypatch):
    """The reason this stopped being a Yes/No box: one press did nothing
    visible on a real MDS-JE480, and nothing here can tell how many a given
    model wants."""
    client = _wire(monkeypatch, enter_presses=3)
    dialog = EraseDiscDialog("COM7")

    dialog._erase()

    assert client.sent.count("SEND ENTER") == 3
    assert dialog.erased is True


def test_done_without_ever_sending_enter_is_not_an_erase(qt_app, monkeypatch):
    """Otherwise Done would be a way to claim an erase that was never
    confirmed -- and the deck would be left parked on the prompt."""
    client = _wire(monkeypatch, enter_presses=0, done=True)
    dialog = EraseDiscDialog("COM7")

    dialog._erase()

    assert "SEND ENTER" not in client.sent
    assert dialog.erased is False
    assert client.sent[-1] == "SEND CANCEL"


def test_the_prompt_window_really_has_an_enter_button_wired_to_the_key(qt_app):
    """Straight through the widget, not through the fake exec above."""
    sent: list[str] = []
    prompt = module.ConfirmPromptDialog(lambda key: (sent.append(key), True)[1])

    prompt.enter_btn.click()
    prompt.enter_btn.click()

    assert sent == ["SEND ENTER", "SEND ENTER"]
    assert prompt.sent == 2
    assert "2" in prompt.status_label.text()


def test_a_dead_adapter_closes_the_prompt_instead_of_counting_presses(qt_app):
    prompt = module.ConfirmPromptDialog(lambda key: False)

    prompt.enter_btn.click()

    assert prompt.sent == 0
    assert prompt.result() != 1


# --- the menu entry ---------------------------------------------------


def test_the_entry_is_hidden_without_the_adapter(qt_app, isolated_settings):
    app_settings.set_mdrem_enabled(False)
    assert MainWindow(show_startup_dialog=False).erase_disc_action.isVisible() is False


def test_the_entry_appears_with_the_adapter(qt_app, isolated_settings):
    app_settings.set_mdrem_enabled(True)
    assert MainWindow(show_startup_dialog=False).erase_disc_action.isVisible()


def test_erasing_refuses_outright_without_the_adapter(qt_app, isolated_settings, monkeypatch):
    app_settings.set_mdrem_enabled(False)
    monkeypatch.setattr(
        app_module, "resolve_port", lambda *a, **k: pytest.fail("must not go looking for a port")
    )

    MainWindow(show_startup_dialog=False)._erase_disc()


def test_erasing_needs_no_open_project(qt_app, isolated_settings, monkeypatch):
    """It acts on whatever disc is physically in the deck, which has nothing
    to do with which label happens to be open."""
    app_settings.set_mdrem_enabled(True)
    monkeypatch.setattr(app_module, "resolve_port", lambda *a, **k: "COM7")
    opened: list = []

    class _Fake:
        def __init__(self, port, parent=None):
            opened.append(port)

        def exec(self):
            return 0

    monkeypatch.setattr(app_module, "EraseDiscDialog", _Fake)
    window = MainWindow(show_startup_dialog=False)
    window.project = None

    window._erase_disc()

    assert opened == ["COM7"]
