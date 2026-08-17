"""A software Sony MD remote, driving the deck through the MDRem infrared
adapter -- opened from the startup screen's "Remote" button.

Structured like the physical remote it stands in for (transport, numeric
keypad, play modes, display, titling), because that is what makes a remote
readable at a glance.

Unlike Upload Tracklist, this needs no worker thread: one key press is a
handful of infrared frames, about 200 ms, which is short enough to send
straight from the GUI thread. The serial port is opened once for the
window's lifetime rather than per press, since opening it is far slower
than sending.

The deck cannot answer, so the status line reports only what was *sent*.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from mdtools import mdrem

# (row, column, key name, button label). Grouped exactly as they are laid
# out on screen; the key names are the firmware's own, see its key table.
_TRANSPORT: list[tuple[int, int, str, str]] = [
    (0, 0, "PREV", "|<<"),
    (0, 1, "PLAY", "Play"),
    (0, 2, "NEXT", ">>|"),
    (1, 0, "SCANREV", "<<"),
    (1, 1, "PAUSE", "Pause"),
    (1, 2, "SCANFWD", ">>"),
    (2, 0, "STOP", "Stop"),
    (2, 1, "POWER", "Power"),
    (2, 2, "EJECT", "Eject"),
]

_MODES: list[tuple[int, int, str, str]] = [
    (0, 0, "CONTINUOUS", "Continuous"),
    (0, 1, "SHUFFLE", "Shuffle"),
    (0, 2, "PROGRAM", "Program"),
    (1, 0, "REPEAT", "Repeat"),
    (1, 1, "ABREPEAT", "A-B"),
    (1, 2, "OVER25", ">25"),
]

_DISPLAY: list[tuple[int, int, str, str]] = [
    (0, 0, "DISPLAY", "Display"),
    (0, 1, "SCROLL", "Scroll"),
]

_TITLING: list[tuple[int, int, str, str]] = [
    (0, 0, "NAME", "Name"),
    (0, 1, "ENTER", "Enter"),
    (1, 0, "DELETE", "Delete"),
    (1, 1, "CANCEL", "Cancel"),
]

# Kept in its own group, away from anything reachable by a stray click near
# the transport keys: on a physical remote Record is a deliberate reach, and
# a mouse makes accidental presses much easier than a thumb does.
_RECORDING: list[tuple[int, int, str, str]] = [
    (0, 0, "RECORD", "Record"),
    (0, 1, "MUSICSYNC", "Music Sync"),
    (0, 2, "TREC", "T.Rec"),
    (1, 0, "DREC", "D.Rec"),
    (1, 1, "ASPACE", "A.Space"),
    (1, 2, "MSCAN", "M.Scan"),
]

_NUMERIC_COLUMNS = 5
_NUMERIC_TRACKS = 10


class RemoteDialog(QDialog):
    def __init__(self, port: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Remote"))
        self._port = port
        self._client: mdrem.MDRemClient | None = None

        layout = QVBoxLayout(self)
        layout.addWidget(self._group(self.tr("Transport"), _TRANSPORT))
        layout.addWidget(self._numeric_group())
        layout.addWidget(self._group(self.tr("Play Mode"), _MODES))
        layout.addWidget(self._group(self.tr("Display"), _DISPLAY))
        layout.addWidget(self._group(self.tr("Titling"), _TITLING))

        recording = self._group(self.tr("Recording"), _RECORDING)
        recording.setToolTip(
            self.tr("These start or arm recording on the deck. A write-protected disc ignores them.")
        )
        layout.addWidget(recording)

        self.status_label = QLabel(self.tr("Connecting..."))
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._connect()

    # --- construction helpers -----------------------------------------

    def _group(self, title: str, keys: list[tuple[int, int, str, str]]) -> QGroupBox:
        box = QGroupBox(title)
        grid = QGridLayout(box)
        for row, column, key, label in keys:
            grid.addWidget(self._key_button(key, label), row, column)
        return box

    def _numeric_group(self) -> QGroupBox:
        """Direct track selection. Stops at 10 -- the deck's own numeric
        keys do too, with 11-25 reached via the >25 key on a real remote
        (the firmware still has TRACK11..TRACK25 codes, they just have no
        button here)."""
        box = QGroupBox(self.tr("Tracks"))
        grid = QGridLayout(box)
        for index in range(1, _NUMERIC_TRACKS + 1):
            position = index - 1
            button = self._key_button(f"TRACK{index}", str(index))
            grid.addWidget(button, position // _NUMERIC_COLUMNS, position % _NUMERIC_COLUMNS)
        return box

    def _key_button(self, key: str, label: str) -> QPushButton:
        button = QPushButton(label)
        button.setToolTip(key)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.clicked.connect(lambda _checked=False, k=key: self._send(k))
        return button

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
