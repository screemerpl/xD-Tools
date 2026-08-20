"""A software Sony MD remote, driving the deck through the MDRem infrared
adapter -- opened from the startup screen's "Remote" button.

Structured like the physical remote it stands in for (transport, numeric
keypad, play modes, display, titling), because that is what makes a remote
readable at a glance.

Two modes, and the split is not "basic and advanced": **standard mode is
the physical RM-D10P**, key for key, and extended mode is everything else
the adapter has a code for. Those extras exist for different reasons --
one pair is the deck's own character entry that this app deliberately
bypasses, one key does nothing at all in the mode you would reach for it,
two edit the disc's table of contents, and the track numbers past 10 have
codes but no key on the plastic remote. All worth reaching; none of it
what somebody opening a remote is looking for.

Extended mode also restores the thing the RM-D10P is actually named after
and this window never had: **the keyboard**. There is no on-screen QWERTY
grid and deliberately so -- the remote has keys because a deck has none,
and a computer running this already has a better keyboard than any grid of
buttons. Typing happens on the real one; see keyPressEvent.

Unlike Upload Tracklist, this needs no worker thread: one key press is a
handful of infrared frames, about 200 ms, which is short enough to send
straight from the GUI thread. That holds for a typed character too -- it
is one press like any other. The serial port is opened once for the
window's lifetime rather than per press, since opening it is far slower
than sending.

The deck cannot answer, so the status line reports only what was *sent*.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from mdtools import app_settings, mdrem


@dataclass(frozen=True)
class _Key:
    """One button. `row`/`column` place it inside its own group; the key
    name is the firmware's own, see its key table."""

    row: int
    column: int
    key: str
    label: str
    extended: bool = False


_TRANSPORT: list[_Key] = [
    _Key(0, 0, "PREV", "|<<"),
    _Key(0, 1, "PLAY", "Play"),
    _Key(0, 2, "NEXT", ">>|"),
    _Key(1, 0, "SCANREV", "<<"),
    _Key(1, 1, "PAUSE", "Pause"),
    _Key(1, 2, "SCANFWD", ">>"),
    _Key(2, 0, "STOP", "Stop"),
    _Key(2, 1, "POWER", "Power"),
    _Key(2, 2, "EJECT", "Eject"),
]

_MODES: list[_Key] = [
    _Key(0, 0, "CONTINUOUS", "Continuous"),
    _Key(0, 1, "SHUFFLE", "Shuffle"),
    _Key(0, 2, "PROGRAM", "Program"),
    _Key(1, 0, "REPEAT", "Repeat"),
    _Key(1, 1, "ABREPEAT", "A-B"),
    _Key(1, 2, "OVER25", ">25"),
]

_DISPLAY: list[_Key] = [
    _Key(0, 0, "DISPLAY", "Display"),
    _Key(0, 1, "SCROLL", "Scroll"),
]

_TITLING: list[_Key] = [
    _Key(0, 0, "NAME", "Name"),
    _Key(0, 1, "ENTER", "Enter"),
    _Key(0, 2, "CHAR", "Char", extended=True),
    _Key(1, 0, "DELETE", "Delete"),
    _Key(1, 1, "CANCEL", "Cancel"),
    _Key(1, 2, "NUM", "Num", extended=True),
    _Key(2, 0, "CLEAR2", "Clear 2", extended=True),
]

# Kept in its own group, away from anything reachable by a stray click near
# the transport keys: on a physical remote Record is a deliberate reach, and
# a mouse makes accidental presses much easier than a thumb does.
_RECORDING: list[_Key] = [
    _Key(0, 0, "RECORD", "Record"),
    _Key(0, 1, "MUSICSYNC", "Music Sync"),
    _Key(0, 2, "TREC", "T.Rec"),
    _Key(1, 0, "DREC", "D.Rec"),
    _Key(1, 1, "ASPACE", "A.Space"),
    _Key(1, 2, "MSCAN", "M.Scan"),
    _Key(2, 0, "DPRE", "D.Pre", extended=True),
]

# Both of these edit the disc's own table of contents. ERASE was tried on a
# real disc and asked before doing anything, which is the only reason this
# group is offered at all rather than left to the adapter's own console.
_EDITING: list[_Key] = [
    _Key(0, 0, "ERASE", "Erase Track", extended=True),
    _Key(0, 1, "DIVIDE", "Divide", extended=True),
]

# Keys that are not characters but mean something in name-edit mode. Left
# and Right move the cursor across the field (SCANFWD/SCANREV do that
# there, not seeking); Backspace maps to the deck's Delete, which takes the
# character *under* the cursor rather than the one before it. Escape is
# left alone on purpose -- it closes the window, as it does in every other
# dialog here.
# Keyed by plain int, and looked up the same way: a Qt enum member is not
# reliably equal to (or hashed as) its own numeric value across PySide
# versions, and Qt.Key(n) raises for a key code the enum has no name for --
# which some keyboards do produce.
_EDITING_KEYS: dict[int, str] = {
    int(Qt.Key.Key_Backspace): "DELETE",
    int(Qt.Key.Key_Delete): "DELETE",
    int(Qt.Key.Key_Return): "ENTER",
    int(Qt.Key.Key_Enter): "ENTER",
    int(Qt.Key.Key_Left): "SCANREV",
    int(Qt.Key.Key_Right): "SCANFWD",
}

_NUMERIC_COLUMNS = 5
_STANDARD_TRACKS = 10  # what the physical remote has number keys for
# Above 10 the remote's own keys stop, but the adapter still has a code per
# track up to 25 -- a second, discontiguous block, of which TRACK11 and
# TRACK20 are both confirmed on an MDS-JE480 and the rest follows the same
# pattern. Past 25 there is no code at all: the number is typed instead,
# which is a sequence rather than a key and so not something a button here
# stands for.
_EXTENDED_TRACKS = mdrem.DIRECT_KEY_MAX


def _hint_for(key: str) -> str:
    """What is actually known about a key, beyond its name.

    Written out per key rather than carried on _Key so every string sits
    literally inside a translate() call -- pyside6-lupdate scans
    statically and does not see a string handed in through a variable.
    """
    if key in ("NEXT", "PREV"):
        return QCoreApplication.translate(
            "RemoteDialog",
            "While the deck is in name-edit mode this scrolls the character under the cursor "
            "instead of changing track, so it will quietly corrupt a title.",
        )
    if key == "OVER25":
        return QCoreApplication.translate(
            "RemoteDialog",
            "Opens a track number field on the deck's display, which closes itself as soon as "
            "two digits have been typed -- no Enter needed, and no room for a third digit.",
        )
    if key == "RECORD":
        return QCoreApplication.translate(
            "RemoteDialog",
            "Pressed while the deck is already recording, this puts a track mark in -- which "
            "is how this app splits an album that plays without gaps.",
        )
    if key in ("CHAR", "NUM"):
        return QCoreApplication.translate(
            "RemoteDialog",
            "Switches the deck's own character set, part of the entry method this app bypasses "
            "by sending character codes directly. Known to work, and of no use here.",
        )
    if key == "CLEAR2":
        return QCoreApplication.translate(
            "RemoteDialog",
            "One of three keys the deck's code table calls Clear. Tried in name-edit mode with "
            "the cursor at the start, in the middle, and held down: it does nothing there. It "
            "most likely clears a play program.",
        )
    if key == "DPRE":
        return QCoreApplication.translate(
            "RemoteDialog",
            "Recognised by the deck as a recording command, but which of that group does what "
            "was never told apart -- they have only been tried on a write-protected disc, "
            "where every one of them answers the same way.",
        )
    if key == "ERASE":
        return QCoreApplication.translate(
            "RemoteDialog",
            "Erases the track the deck is sitting on. Tried on a real disc: it asks on the "
            "display first and does nothing until Enter, so Cancel backs out of it.",
        )
    if key == "DIVIDE":
        return QCoreApplication.translate(
            "RemoteDialog",
            "Splits the current track in two. Never tried on an unprotected disc -- Erase, the "
            "one key of this group that has been, asked before acting.",
        )
    return ""


class RemoteDialog(QDialog):
    def __init__(self, port: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Remote"))
        self._port = port
        self._client: mdrem.MDRemClient | None = None
        self._extended_widgets: list[QPushButton] = []
        self._extended_groups: list[QGroupBox] = []
        self._last_character_at = 0.0

        layout = QVBoxLayout(self)

        # Two columns, because extended mode is otherwise a metre of
        # window: every key the adapter knows, stacked, came to a taller
        # dialog than a laptop screen, at which point Qt squeezes the
        # groups rather than the window and the track numbers stop being
        # readable. Standard mode is short enough either way, but a remote
        # whose keys move when a checkbox is ticked would be worse than one
        # that is a little wider than it needs to be.
        columns = QHBoxLayout()
        left = QVBoxLayout()
        right = QVBoxLayout()

        self.extended_check = QCheckBox(self.tr("Extended mode -- every key the adapter knows"))
        self.extended_check.setToolTip(
            self.tr(
                "Standard mode is the physical remote, key for key. Extended mode adds what has "
                "no key on it: tracks 11 to 25, the deck's own character entry, the rest of the "
                "recording group, the two keys that edit the disc, and typing."
            )
        )
        self.extended_check.setChecked(app_settings.mdrem_extended_remote())
        self.extended_check.toggled.connect(self._on_extended_toggled)
        # Nothing in this window may hold the keyboard focus while extended
        # mode is on -- a focused checkbox eats the space bar and toggles
        # itself, and a focused button eats space and Enter. Every key
        # belongs to the deck.
        self.extended_check.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        layout.addWidget(self.extended_check)

        left.addWidget(self._group(self.tr("Transport"), _TRANSPORT))
        left.addWidget(self._numeric_group())
        left.addWidget(self._group(self.tr("Play Mode"), _MODES))
        left.addWidget(self._group(self.tr("Display"), _DISPLAY))
        left.addStretch(1)

        right.addWidget(self._group(self.tr("Titling"), _TITLING))
        right.addWidget(self._typing_group())

        recording = self._group(self.tr("Recording"), _RECORDING)
        recording.setToolTip(
            self.tr("These start or arm recording on the deck. A write-protected disc ignores them.")
        )
        right.addWidget(recording)

        editing = self._group(self.tr("Disc Editing"), _EDITING)
        editing.setToolTip(
            self.tr(
                "These change what is on the disc. The deck asks on its own display before doing "
                "anything and waits for Enter -- read what it is asking before pressing it."
            )
        )
        self._extended_groups.append(editing)
        right.addWidget(editing)
        right.addStretch(1)

        columns.addLayout(left)
        columns.addLayout(right)
        layout.addLayout(columns)

        self.status_label = QLabel(self.tr("Connecting..."))
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        for button in buttons.buttons():
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        layout.addWidget(buttons)

        self._apply_extended(self.extended_check.isChecked())
        self._connect()

    # --- construction helpers -----------------------------------------

    def _group(self, title: str, keys: list[_Key]) -> QGroupBox:
        box = QGroupBox(title)
        grid = QGridLayout(box)
        for entry in keys:
            button = self._key_button(entry.key, entry.label)
            if entry.extended:
                self._extended_widgets.append(button)
            grid.addWidget(button, entry.row, entry.column)
        return box

    def _numeric_group(self) -> QGroupBox:
        """Direct track selection. The physical remote's number keys stop
        at 10; 11-25 have codes of their own and appear in extended mode."""
        box = QGroupBox(self.tr("Tracks"))
        grid = QGridLayout(box)
        for index in range(1, _EXTENDED_TRACKS + 1):
            position = index - 1
            button = self._key_button(f"TRACK{index}", str(index))
            if index > _STANDARD_TRACKS:
                self._extended_widgets.append(button)
            grid.addWidget(button, position // _NUMERIC_COLUMNS, position % _NUMERIC_COLUMNS)
        return box

    def _typing_group(self) -> QGroupBox:
        """No buttons -- just the sentence that says the keyboard works.

        Typing is otherwise invisible: nothing on screen suggests that
        pressing a letter does anything, and there is no text box to draw
        the eye, because the deck's own display is the text box.
        """
        box = QGroupBox(self.tr("Typing"))
        inner = QVBoxLayout(box)
        note = QLabel(
            self.tr(
                "Type on your own keyboard and every letter, digit and symbol goes straight to "
                "the deck, which has to be in name-edit mode first -- press Name, or select a "
                "track and then Name. Backspace deletes, Enter commits the title, and the arrow "
                "keys move the cursor. Accented letters lose their marks; anything the deck "
                "cannot show at all is refused rather than sent as something else."
            )
        )
        note.setWordWrap(True)
        inner.addWidget(note)
        self._extended_groups.append(box)
        return box

    def _key_button(self, key: str, label: str) -> QPushButton:
        button = QPushButton(label)
        # The firmware's own name for the key, first: it is what the
        # adapter's console takes and what its documentation is written in.
        hint = _hint_for(key)
        button.setToolTip(f"{key}\n\n{hint}" if hint else key)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.clicked.connect(lambda _checked=False, k=key: self._send(k))
        return button

    # --- extended mode ------------------------------------------------

    def _on_extended_toggled(self, checked: bool) -> None:
        app_settings.set_mdrem_extended_remote(checked)
        self._apply_extended(checked)
        # The window keeps whatever size it had, which would leave a band
        # of empty space behind the keys that have just gone away.
        self.adjustSize()

    def _apply_extended(self, checked: bool) -> None:
        for widget in self._extended_widgets:
            widget.setVisible(checked)
        for group in self._extended_groups:
            group.setVisible(checked)

    # --- the keyboard -------------------------------------------------

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """The RM-D10P is a keyboard; this is that part of it.

        Only in extended mode: in standard mode this window is the plastic
        remote, and the plastic remote has no letters. Everything unhandled
        falls through to QDialog, which is what keeps Escape closing the
        window.
        """
        if not self.extended_check.isChecked():
            super().keyPressEvent(event)
            return
        # A held key would otherwise pour presses at the deck faster than
        # it can take them, and the deck reads that as one key held down
        # rather than as many presses -- a different thing, not a lost one.
        if event.isAutoRepeat():
            event.accept()
            return
        # Ctrl+letter and Alt+letter are shortcuts somebody is aiming
        # somewhere else, not characters meant for the disc.
        if event.modifiers() & (
            Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier
        ):
            super().keyPressEvent(event)
            return

        command = _EDITING_KEYS.get(int(event.key()))
        if command is not None:
            self._send(command)
            event.accept()
            return

        text = event.text()
        if text and text.isprintable():
            self._type(text)
            event.accept()
            return
        super().keyPressEvent(event)

    def _type(self, text: str) -> None:
        """One keystroke, which is not always one character.

        Anything the deck can already show goes as it is. Anything else is
        transliterated exactly as an uploaded title is, so "ł" arrives as
        "l" rather than being dropped in silence by the firmware -- and a
        keystroke with no Latin equivalent at all is refused out loud
        instead, since there is nothing to send and the deck cannot say so.

        The order matters for exactly one character: transliterate() ends
        by stripping, which is right for a title and would turn a pressed
        space bar into nothing at all.
        """
        if len(text) == 1 and mdrem.character_command(text) is not None:
            sendable = text
        else:
            sendable = mdrem.transliterate(text).text
        if not sendable:
            self.status_label.setText(
                self.tr("The deck cannot show {chars} -- nothing was sent.").format(chars=text)
            )
            return
        for char in sendable:
            command = mdrem.character_command(char)
            if command is None or not self._pace_and_send(command, char):
                return
        self.status_label.setText(self.tr("Typed: {text}").format(text=sendable))

    def _pace_and_send(self, command: str, char: str) -> bool:
        """Sends one character, no sooner than the deck can take it.

        The gap is the firmware's own: three frames and then a clear pause,
        or two presses run together into one held key. Waiting out only the
        remainder means ordinary typing never waits at all -- fingers are
        slower than 150 ms -- while a paste or a held key is slowed to
        something the deck actually reads.
        """
        if self._client is None:
            self.status_label.setText(self.tr("Not connected -- nothing was sent."))
            return False
        remaining = mdrem.MIN_CHARACTER_GAP_S - (time.monotonic() - self._last_character_at)
        if remaining > 0:
            time.sleep(remaining)
        try:
            self._client.command(command)
        except mdrem.MDRemError as exc:
            self.status_label.setText(self.tr("{key} failed: {error}").format(key=char, error=exc))
            return False
        self._last_character_at = time.monotonic()
        return True

    # --- device -------------------------------------------------------

    def _connect(self) -> None:
        try:
            self._client = mdrem.MDRemClient(self._port)
            self._client.open()
        except mdrem.MDRemError as exc:
            self._client = None
            self.status_label.setText(self.tr("Not connected: {error}").format(error=exc))
            return
        self.status_label.setText(self.tr("Connected on {port}.").format(port=self._port))

    def _send(self, key: str) -> None:
        if self._client is None:
            self.status_label.setText(self.tr("Not connected -- nothing was sent."))
            return
        try:
            self._client.command(f"SEND {key}")
        except mdrem.MDRemError as exc:
            self.status_label.setText(self.tr("{key} failed: {error}").format(key=key, error=exc))
            return
        # Deliberately "Sent", not "Done": the deck never reports back, so
        # this can only ever mean the adapter accepted the command.
        self.status_label.setText(self.tr("Sent: {key}").format(key=key))

    def reject(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None
        super().reject()
