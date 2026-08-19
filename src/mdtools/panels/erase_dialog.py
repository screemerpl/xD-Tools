"""Recording > "Erase MiniDisc..." -- clears a disc through the MDRem
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
  ENTER only goes out when they press it themselves, on a prompt window that
  stays open so they can press it again: on a real MDS-JE480 one press did
  nothing visible, and how many a given model's menu wants is not knowable
  from here (see ConfirmPromptDialog). This mirrors RecordDialog arming the
  deck and then asking whether it really armed, for the same reason.
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


class ConfirmPromptDialog(QDialog):
    """Asks what the deck's display shows, with ENTER as a button.

    ENTER used to be sent once, automatically, the moment the user answered
    "yes it is asking me" -- and on a real MDS-JE480 that turned out to do
    nothing visible, with "maybe it needs it twice?" the obvious next
    thought and no way to try. The deck cannot be read back, so how many
    presses a particular model's menu takes is not knowable from here; the
    only workable answer is to hand the key to the person who can see the
    display and let them press it as many times as it takes.

    Three ways out, and they are not the same:
      - **Done** -- the prompt was accepted. Only counts if ENTER actually
        went out at least once, which is what stops "Done" becoming a way
        to claim an erase that was never confirmed.
      - **Nothing happened** -- the deck never asked. The caller backs it
        out with CANCEL rather than leaving it parked on a destructive
        prompt for whoever next walks past.
      - closing the window, which is the same as the above.
    """

    def __init__(self, send, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Erase MiniDisc"))
        self.resize(440, 220)
        self._send = send
        # How many times ENTER actually went out. Read by the caller: a Done
        # with none sent is not a confirmed erase.
        self.sent = 0

        layout = QVBoxLayout(self)
        question = QLabel(
            self.tr(
                "Erase was sent to the deck.\n\nIs it now asking you to confirm -- showing something like "
                '"All Erase?"\n\nIf it is, press Send Enter and watch the display. Some decks need it '
                "more than once."
            )
        )
        question.setWordWrap(True)
        layout.addWidget(question)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.status_label.setVisible(False)
        layout.addWidget(self.status_label)

        layout.addStretch(1)

        buttons = QDialogButtonBox()
        self.enter_btn = QPushButton(self.tr("Send Enter"))
        self.enter_btn.setDefault(True)
        self.enter_btn.clicked.connect(self._send_enter)
        buttons.addButton(self.enter_btn, QDialogButtonBox.ButtonRole.ActionRole)
        self.done_btn = QPushButton(self.tr("Done"))
        self.done_btn.clicked.connect(self.accept)
        buttons.addButton(self.done_btn, QDialogButtonBox.ButtonRole.AcceptRole)
        self.nothing_btn = QPushButton(self.tr("Nothing Happened"))
        self.nothing_btn.clicked.connect(self.reject)
        buttons.addButton(self.nothing_btn, QDialogButtonBox.ButtonRole.RejectRole)
        layout.addWidget(buttons)

    def _send_enter(self) -> None:
        if not self._send(_CONFIRM_KEY):
            # The caller has already reported why; there is nothing further
            # this window can offer once the adapter has gone.
            self.reject()
            return
        self.sent += 1
        self.status_label.setText(
            self.tr(
                "Enter sent ({count}). If the display has not changed, send it again; if the disc is "
                "blank now, press Done."
            ).format(count=self.sent)
        )
        self.status_label.setVisible(True)


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

        if self._run_confirm_prompt():
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

    def _run_confirm_prompt(self) -> bool:
        """Hands ENTER to the user and reports whether they got anywhere.

        The only instrument available is their own eyes, so this asks about
        the *display* -- something observable -- rather than about the
        outcome, which nobody can see yet. True means ENTER went out at
        least once and they said the deck took it."""
        prompt = ConfirmPromptDialog(self._send, self)
        accepted = prompt.exec() == QDialog.DialogCode.Accepted
        return accepted and prompt.sent > 0

    def _offer_eject(self) -> None:
        """An erased TOC lives in the deck's memory until the disc is
        ejected, exactly as a written one does -- see
        MDRemUploadDialog._eject. Asked rather than done silently,
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
