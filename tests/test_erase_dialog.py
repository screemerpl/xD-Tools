"""Erasing a disc, with no adapter and no deck.

Sends a fixed sequence -- Stop, Erase, Enter, Enter, Eject -- behind a
single "are you sure?" confirmation and nothing further. See
erase_dialog.py's own module docstring for why this replaced an earlier,
interactive design (guided Enter presses plus a Done/Nothing Happened
choice): that existed because a single Enter was found to do nothing
visible on a real MDS-JE480 with no feedback channel to check further --
two Enters is what was actually measured to work, and this dialog now
sends exactly that, blind, by explicit request. Where the button that
opens this dialog lives (a button on the MiniDisc record dialog, not a
Recording menu entry) is covered in test_record_dialog.py instead.
"""

from __future__ import annotations

from PySide6.QtWidgets import QMessageBox

from mdtools.panels import erase_dialog as module
from mdtools.panels.erase_dialog import EraseDiscDialog


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


def _wire(monkeypatch, *, confirm=True, fail_on=None, sleeps=None):
    """Fakes the adapter and the single up-front confirmation -- there is
    nothing else modal left in this dialog to fake. Also stubs out the
    pause between keys (real IR pacing, not something a test should wait
    through) -- pass `sleeps` to record how many/how long instead of just
    swallowing them."""
    client = _FakeClient("COM7", fail_on)
    monkeypatch.setattr(module.mdrem, "MDRemClient", lambda port: client)

    ok = QMessageBox.StandardButton.Ok if confirm else QMessageBox.StandardButton.Cancel
    monkeypatch.setattr(module.QMessageBox, "warning", staticmethod(lambda *a, **k: ok))

    if sleeps is None:
        monkeypatch.setattr(module.time, "sleep", lambda seconds: None)
    else:
        monkeypatch.setattr(module.time, "sleep", lambda seconds: sleeps.append(seconds))
    return client


def test_declining_the_warning_sends_nothing_at_all(qt_app, monkeypatch):
    client = _wire(monkeypatch, confirm=False)
    dialog = EraseDiscDialog("COM7")

    dialog._erase()

    assert client.sent == []
    assert dialog.erased is False


def test_the_full_sequence_goes_out_in_order_with_nothing_asked_in_between(qt_app, monkeypatch):
    """Stop, Erase, two Enters, then Eject -- the exact sequence measured
    to work on a real MDS-JE480, sent without stopping to ask anything."""
    client = _wire(monkeypatch)
    dialog = EraseDiscDialog("COM7")

    dialog._erase()

    assert client.sent == ["SEND STOP", "SEND ERASE", "SEND ENTER", "SEND ENTER", "SEND EJECT"]
    assert dialog.erased is True
    assert client.closed


def test_a_pause_separates_every_key_but_none_precedes_the_first_one(qt_app, monkeypatch):
    """Reported directly: sent back to back with no gap, the deck doesn't
    reliably keep up. One pause between each of the five keys -- four gaps
    for five keys -- and no wasted pause before Stop, which has nothing
    before it to wait on."""
    sleeps: list[float] = []
    _wire(monkeypatch, sleeps=sleeps)
    dialog = EraseDiscDialog("COM7")

    dialog._erase()

    assert sleeps == [module._KEY_GAP_S] * 4


def test_a_failure_partway_stops_the_sequence_and_reports_it(qt_app, monkeypatch):
    client = _wire(monkeypatch, fail_on="SEND ERASE")
    dialog = EraseDiscDialog("COM7")

    dialog._erase()

    assert dialog.erased is False
    assert client.closed
    assert "MDRem" in dialog.status_label.text()
    # Stop went out before the failure; nothing after it did.
    assert client.sent == ["SEND STOP"]


def test_the_port_is_released_when_the_dialog_is_dismissed(qt_app, monkeypatch):
    client = _wire(monkeypatch)
    dialog = EraseDiscDialog("COM7")
    dialog._client = client

    dialog.reject()

    assert client.closed
