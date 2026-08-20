"""The software remote: its two modes, and the keyboard.

No adapter and no deck. The dialog is constructed against a port that
cannot open -- which is a supported state, reported on its status line --
and a stand-in client is then put in its place, so what these tests read is
the exact line that would have gone down the wire.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QPushButton

from mdtools import app_settings, mdrem
from mdtools.panels import remote_dialog as module
from mdtools.panels.remote_dialog import RemoteDialog

# Every key name the adapter's own table resolves, written out rather than
# read from the firmware repo (which is not a dependency of this one). A
# key added there and forgotten here is exactly what this catches.
EVERY_KEY = [
    "PLAY", "STOP", "PAUSE", "RECORD", "NEXT", "PREV", "SCANFWD", "SCANREV",
    "POWER", "EJECT", "DISPLAY", "SCROLL",
    "CONTINUOUS", "SHUFFLE", "PROGRAM", "REPEAT", "ABREPEAT",
    "DPRE", "DREC", "TREC", "ASPACE", "MSCAN", "MUSICSYNC",
    "NAME", "CHAR", "NUM", "OVER25",
    "DELETE", "CLEAR2", "CANCEL",
    "ENTER", "ERASE", "DIVIDE",
]


class _FakeClient:
    def __init__(self):
        self.sent: list[str] = []

    def command(self, text, **kwargs):
        self.sent.append(text)


@pytest.fixture
def dialog(qt_app, monkeypatch):
    # Ordinary typing is slower than the gap, so it never waits in real
    # use; a test types faster than any human and would sit in sleep().
    monkeypatch.setattr(mdrem, "MIN_CHARACTER_GAP_S", 0.0)
    dialog = RemoteDialog("COM_TEST")
    dialog._client = _FakeClient()
    return dialog


def _buttons(dialog) -> dict[str, QPushButton]:
    """By the firmware key name, which is each button's own tooltip."""
    found = {}
    for button in dialog.findChildren(QPushButton):
        name = button.toolTip().split("\n", 1)[0]
        if name:
            found[name] = button
    return found


def _press(dialog, key, text="", autorepeat=False, modifiers=Qt.KeyboardModifier.NoModifier):
    event = QKeyEvent(QKeyEvent.Type.KeyPress, key, modifiers, text, autorepeat)
    dialog.keyPressEvent(event)


# --- the two modes ---------------------------------------------------------


def test_standard_mode_is_the_physical_remote_and_nothing_more(dialog):
    """Not "basic": these are the keys the plastic remote actually has."""
    dialog.extended_check.setChecked(False)
    buttons = _buttons(dialog)

    assert buttons["PLAY"].isVisibleTo(dialog)
    assert buttons["TRACK10"].isVisibleTo(dialog)
    for absent in ("CHAR", "NUM", "CLEAR2", "DPRE", "ERASE", "DIVIDE", "TRACK11"):
        assert not buttons[absent].isVisibleTo(dialog), absent


def test_extended_mode_shows_every_key_the_adapter_knows(dialog):
    dialog.extended_check.setChecked(True)
    buttons = _buttons(dialog)

    for key in EVERY_KEY:
        assert key in buttons, f"{key} has no button at all"
        assert buttons[key].isVisibleTo(dialog), f"{key} is hidden in extended mode"


def test_every_track_with_a_code_of_its_own_gets_a_button(dialog):
    """1-25 are single codes; past that the number is typed, which is a
    sequence rather than a key, so it is not a button here."""
    dialog.extended_check.setChecked(True)
    buttons = _buttons(dialog)

    assert all(f"TRACK{n}" in buttons for n in range(1, mdrem.DIRECT_KEY_MAX + 1))
    assert f"TRACK{mdrem.DIRECT_KEY_MAX + 1}" not in buttons


def test_the_choice_is_remembered_between_openings(qt_app, monkeypatch):
    monkeypatch.setattr(mdrem, "MIN_CHARACTER_GAP_S", 0.0)
    first = RemoteDialog("COM_TEST")
    first.extended_check.setChecked(True)

    assert app_settings.mdrem_extended_remote()
    assert RemoteDialog("COM_TEST").extended_check.isChecked()


def test_nothing_in_the_window_takes_the_keyboard_focus(dialog):
    """A focused checkbox eats the space bar and toggles itself; a focused
    button eats space and Enter. Every key belongs to the deck."""
    dialog.extended_check.setChecked(True)

    for widget in dialog.findChildren(QPushButton) + [dialog.extended_check]:
        assert widget.focusPolicy() == Qt.FocusPolicy.NoFocus


# --- the keyboard ----------------------------------------------------------


def test_a_letter_goes_straight_to_the_deck(dialog):
    dialog.extended_check.setChecked(True)

    _press(dialog, Qt.Key.Key_A, "A")

    assert dialog._client.sent == ["SEND A"]


def test_case_is_kept_because_the_deck_has_two_different_codes(dialog):
    dialog.extended_check.setChecked(True)

    _press(dialog, Qt.Key.Key_A, "a")

    assert dialog._client.sent == ["SEND a"]


def test_a_space_goes_out_as_its_raw_code(dialog):
    """SEND splits its own arguments on whitespace, so a space cannot be
    handed to it -- the character's own code can."""
    dialog.extended_check.setChecked(True)

    _press(dialog, Qt.Key.Key_Space, " ")

    assert dialog._client.sent == ["RAW 61D20 20"]


def test_an_accented_letter_arrives_as_the_letter(dialog):
    """Transliterated exactly as an uploaded title is, rather than being
    dropped in silence by the firmware."""
    dialog.extended_check.setChecked(True)

    _press(dialog, Qt.Key.Key_L, "ł")

    assert dialog._client.sent == ["SEND l"]


def test_a_keystroke_the_deck_cannot_show_is_refused_out_loud(dialog):
    dialog.extended_check.setChecked(True)

    _press(dialog, Qt.Key.Key_unknown, "日")

    assert dialog._client.sent == []
    assert "日" in dialog.status_label.text()


def test_backspace_enter_and_the_arrows_mean_what_they_do_on_the_deck(dialog):
    dialog.extended_check.setChecked(True)

    _press(dialog, Qt.Key.Key_Backspace, "\b")
    _press(dialog, Qt.Key.Key_Return, "\r")
    _press(dialog, Qt.Key.Key_Left, "")
    _press(dialog, Qt.Key.Key_Right, "")

    assert dialog._client.sent == ["SEND DELETE", "SEND ENTER", "SEND SCANREV", "SEND SCANFWD"]


def test_a_held_key_is_not_poured_at_the_deck(dialog):
    """The deck reads presses arriving too fast as one key held down --
    a different thing, not a lost one."""
    dialog.extended_check.setChecked(True)

    _press(dialog, Qt.Key.Key_A, "A")
    _press(dialog, Qt.Key.Key_A, "A", autorepeat=True)
    _press(dialog, Qt.Key.Key_A, "A", autorepeat=True)

    assert dialog._client.sent == ["SEND A"]


def test_a_shortcut_is_aimed_somewhere_else_not_at_the_disc(dialog):
    dialog.extended_check.setChecked(True)

    _press(dialog, Qt.Key.Key_C, "c", modifiers=Qt.KeyboardModifier.ControlModifier)

    assert dialog._client.sent == []


def test_standard_mode_types_nothing(dialog):
    """The plastic remote this mode stands in for has no letters on it."""
    dialog.extended_check.setChecked(False)

    _press(dialog, Qt.Key.Key_A, "A")
    _press(dialog, Qt.Key.Key_Backspace, "\b")

    assert dialog._client.sent == []


def test_typing_with_no_adapter_says_so_rather_than_failing(dialog):
    dialog.extended_check.setChecked(True)
    dialog._client = None

    _press(dialog, Qt.Key.Key_A, "A")

    assert "connect" in dialog.status_label.text().lower()
