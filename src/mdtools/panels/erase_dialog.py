"""Erase MiniDisc... -- clears a disc through the MDRem adapter.

A button on the MiniDisc record dialog (moved there from its own Recording
menu entry -- erasing the wrong disc is most likely to come up right
before recording onto it, and a menu entry reachable independent of any
open project served no one).

Sends a fixed sequence over infrared -- Stop, Erase, Enter, Enter, Eject --
behind a single "are you sure?" confirmation, with nothing further asked.

This used to be a guided, interactive sequence instead: Erase was sent,
then the user was asked what their deck's display showed, with Enter only
going out when they pressed it themselves (as many times as it took), and
a final Done/Nothing Happened choice at the end. That existed because the
MDRem firmware's own findings only ever established that a *single* Enter
did nothing visible on a real MDS-JE480 -- there is no feedback channel to
confirm how many presses a different model's menu might want, so "sent the
key and hoped" felt like the wrong shape for something irreversible.

Simplified to the fixed sequence above by explicit request: two Enters is
what was actually measured to work on that deck, and Eject now always
follows rather than being asked about separately -- deliberately trading
the old guided certainty for a one-click operation. If some other deck out
there needs a third Enter, or turns out not to like an unconditional
Eject, that is a real gap this trade accepts, not an oversight -- erasing
from the deck's own front panel is always the fallback.

What is actually known, from the MDRem firmware's own findings: `ERASE`
(SIRC 0x07DA) is *recognised* by an MDS-JE480 as a write command -- sending
it to a write-protected disc produced the deck's protection message, which
a wrong code would not have done.
"""

from __future__ import annotations

import time

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from mdtools import mdrem

# The deck will not accept an edit while it is playing, so it is stopped
# first rather than assuming it already was.
_PREPARE_KEY = "SEND STOP"
_ERASE_KEY = "SEND ERASE"
_CONFIRM_KEY = "SEND ENTER"
_EJECT_KEY = "SEND EJECT"

# Two Enters, then Eject with nothing asked in between -- see the module
# docstring for why this is a fixed, blind sequence rather than an
# interactive one.
_ERASE_SEQUENCE = (_PREPARE_KEY, _ERASE_KEY, _CONFIRM_KEY, _CONFIRM_KEY, _EJECT_KEY)

# Sent back to back with no gap, the deck doesn't reliably keep up --
# reported directly ("erase disc sequence is beamed with IR to quick"). One
# IR frame per key isn't the deck's own bottleneck here; it's the deck
# actually registering and acting on one key (STOP settling into stop mode,
# ERASE opening its confirmation menu, ...) before the next one arrives.
# Same reasoning mdrem.py's own MIN_CHARACTER_GAP_S already applies to
# typing a title character by character.
_KEY_GAP_S = 0.25


class EraseDiscDialog(QDialog):
    def __init__(self, port: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Erase MiniDisc"))
        self.resize(460, 220)
        self._port = port
        self._client: mdrem.MDRemClient | None = None
        # True once the whole sequence has gone out without a hardware
        # error. Read by tests, and by anything that cares whether the
        # disc is actually blank now.
        self.erased = False

        layout = QVBoxLayout(self)

        intro = QLabel(
            self.tr(
                "This erases everything on the disc: Stop, Erase, two confirmations, then Eject, sent "
                "over infrared with nothing further asked. It cannot be undone, and xD-Tools cannot see "
                "the result -- the deck has no way to report back.\n\n"
                "Make sure the right disc is loaded and its write-protect tab is closed."
            )
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        caution = QLabel(
            self.tr(
                "This exact sequence is what was confirmed to work on one real deck. If yours needs "
                "something different, erase it from its own front panel instead."
            )
        )
        caution.setWordWrap(True)
        layout.addWidget(caution)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.status_label.setVisible(False)
        layout.addWidget(self.status_label)

        layout.addStretch(1)

        self.buttons = QDialogButtonBox()
        self.erase_btn = QPushButton(self.tr("Erase Disc"))
        self.erase_btn.clicked.connect(self._erase)
        self.buttons.addButton(self.erase_btn, QDialogButtonBox.ButtonRole.AcceptRole)
        self.close_btn = QPushButton(self.tr("Cancel"))
        self.close_btn.clicked.connect(self.reject)
        self.buttons.addButton(self.close_btn, QDialogButtonBox.ButtonRole.RejectRole)
        layout.addWidget(self.buttons)

    # --- the sequence ---------------------------------------------------

    def _erase(self) -> None:
        if not self._confirm():
            return
        try:
            self._client = mdrem.MDRemClient(self._port)
            self._client.open()
        except mdrem.MDRemError as exc:
            self._client = None
            self._fail(self.tr("MDRem: {error}").format(error=exc))
            return

        self.erase_btn.setEnabled(False)
        for index, command in enumerate(_ERASE_SEQUENCE):
            if index > 0:
                time.sleep(_KEY_GAP_S)
            if not self._send(command):
                # _send already reported why, via _fail.
                return

        self.erased = True
        self._close_client()
        self.erase_btn.setEnabled(True)
        self.close_btn.setText(self.tr("Close"))
        self._show(self.tr("The disc has been erased and ejected."))

    def _confirm(self) -> bool:
        answer = QMessageBox.warning(
            self,
            self.tr("Erase MiniDisc"),
            self.tr(
                "Everything on the disc will be erased, including its titles. This cannot be undone.\n\n"
                "Continue?"
            ),
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        return answer == QMessageBox.StandardButton.Ok

    # --- helpers ----------------------------------------------------------

    def _send(self, command: str) -> bool:
        if self._client is None:
            self._fail(self.tr("MDRem: not connected"))
            return False
        try:
            self._client.command(command)
            return True
        except mdrem.MDRemError as exc:
            self._fail(self.tr("MDRem: {error}").format(error=exc))
            return False

    def _show(self, message: str) -> None:
        self.status_label.setText(message)
        self.status_label.setVisible(True)

    def _fail(self, message: str) -> None:
        self._close_client()
        self._show(message)
        self.erase_btn.setEnabled(True)
        self.close_btn.setText(self.tr("Close"))

    def _close_client(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def reject(self) -> None:
        self._close_client()
        super().reject()
