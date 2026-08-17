"""Project > "Erase MiniDisc..." -- clears a disc through the MDRem
adapter.

This is the most destructive thing MDTools can ask a deck to do, and it is
the operation we know least about, so it is built differently from the rest:
it does not claim to know what will happen, it asks.

What is actually known, from the MDRem firmware's own findings: `ERASE`
(SIRC 0x07DA) is *recognised* by an MDS-JE480 as a write command -- sending
it to a write-protected disc produced the deck's protection message, which a
wrong code would not have done. What it does to an *unprotected* disc was
never established. The whole write group was only ever tested behind the
write-protect tab, deliberately, and at three-second intervals the deck's
message never cleared between keys, so nothing distinguished one from
another.

Two consequences shape this dialog:

- **It is a guided sequence, not a single button.** ERASE is sent, and then
  the user is asked what their deck's display actually says, because that is
  the only instrument available -- there is no feedback channel of any kind.
  Only after they confirm a prompt appeared does ENTER go out to accept it.
  This mirrors RecordDialog arming the deck and then asking whether it
  really armed, which exists for exactly the same reason.
- **Backing out sends CANCEL.** If the deck is sitting on a confirmation the
  user does not want to accept, leaving it there would arm a destructive
  prompt for whoever next touches the deck.

Nothing is committed to the disc until it is ejected -- the same volatile
TOC that makes MDRemUploadDialog offer to eject after writing titles, and
the same reason this one does too.
"""

from __future__ import annotations

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
_BACK_OUT_KEY = "SEND CANCEL"


class EraseDiscDialog(QDialog):
    def __init__(self, port: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Erase MiniDisc"))
        self.resize(460, 260)
        self._port = port
        self._client: mdrem.MDRemClient | None = None
        # True once the confirmation key has actually gone out. Read by
        # tests, and by the eject prompt -- there is nothing to save to the
        # disc if the erase was never accepted.
        self.erased = False

        layout = QVBoxLayout(self)

        intro = QLabel(
            self.tr(
                "This asks the deck to erase everything on the disc. It cannot be undone, and MDTools cannot "
                "see the result -- the deck has no way to report back.\n\n"
                "Make sure the right disc is loaded and its write-protect tab is closed."
            )
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        caution = QLabel(
            self.tr(
                "Note: which editing menu your deck opens in response is not something MDTools can know, so "
                "it will ask you what the display shows before confirming anything."
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
        if not self._send(_PREPARE_KEY) or not self._send(_ERASE_KEY):
            return

        if self._deck_is_asking():
            if not self._send(_CONFIRM_KEY):
                return
            self.erased = True
            self._show(
                self.tr(
                    "The confirmation was accepted. Check the deck -- it should now report a blank disc.\n\n"
                    "Nothing is written to the disc until it is ejected."
                )
            )
            self._offer_eject()
        else:
            # Either nothing happened (a protected disc, or a deck that does
            # not take this key) or it erased outright. Backing the deck out
            # of whatever state it is in is the safe move either way.
            self._send(_BACK_OUT_KEY)
            self._show(
                self.tr(
                    "No confirmation was accepted, so nothing was sent to complete an erase. If the disc is "
                    "write-protected, close its tab and try again; otherwise erase it from the deck's own "
                    "front panel."
                )
            )

        self._close_client()
        self.erase_btn.setEnabled(True)
        self.close_btn.setText(self.tr("Close"))

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

    def _deck_is_asking(self) -> bool:
        """The only instrument available is the user's own eyes.

        Deliberately phrased as a question about the display rather than
        "did it work" -- the answer decides whether a confirmation key is
        sent, so it has to be about something observable, not about an
        outcome nobody can see yet."""
        answer = QMessageBox.question(
            self,
            self.tr("Erase MiniDisc"),
            self.tr(
                "Erase was sent to the deck.\n\nIs it now asking you to confirm -- showing something like "
                '"All Erase?" or "Erase??"'
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _offer_eject(self) -> None:
        """An erased TOC lives in the deck's memory until the disc is
        ejected, exactly as a written one does -- see
        MDRemUploadDialog._offer_eject. Asked rather than done silently,
        since it physically opens the tray."""
        answer = QMessageBox.question(
            self,
            self.tr("Erase MiniDisc"),
            self.tr(
                "The erase is only held in the deck's memory until the disc is ejected -- it is lost if the "
                "deck powers off first.\n\nEject now to make it permanent?"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._send("SEND EJECT")

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
