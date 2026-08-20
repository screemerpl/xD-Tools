"""Experimental Settings' "Sign in to Telegram..." button -- logs xD-Tools
in as the user's own Telegram account, which is what lets it later talk to
a bot the user runs themselves (see mdtools.telegram_bot's module docstring
for why a real user login is needed at all, not a bot token).

**Why this worker needs a persistent event loop, not a one-shot run() like
every other QThread in this codebase** (compare _UploadWorker/_RipWorker/
_LoadWorker, which each do one bounded job and finish): Telethon's sign_in()
needs the *same* TelegramClient instance that called send_code_request() --
it caches the phone-code-hash on the instance itself, not in the session
file. Disconnecting and reconnecting a fresh client between "code sent" and
"code entered" would silently trigger a second, wasted code request and
risk the user typing a now-stale code. So _LoginWorker.run() starts its own
asyncio event loop and keeps it alive across however long the user takes to
read an SMS and type it in (and, if the account has 2FA, a password after
that) -- fed from the GUI thread via loop.call_soon_threadsafe(), the
standard way to hand a value into a coroutine that's blocked on
`await queue.get()` in another thread's loop.
"""

from __future__ import annotations

import asyncio
import threading

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from mdtools import app_settings, telegram_bot

# How long the GUI thread waits for the worker's event loop to exist before
# giving up on delivering a code/password/cancel -- generous, since this
# only ever has to cover the sliver of time between QThread.start()
# returning and run() reaching asyncio.new_event_loop(), not a real network
# operation.
_READY_TIMEOUT_S = 5.0


class _LoginWorker(QThread):
    """Runs the whole phone -> code -> (optional) password exchange on one
    persistent event loop. The TelegramClient (and so the loop it's bound
    to) is constructed inside run(), never in __init__ -- same "belongs to
    the thread that uses it" rule mdrem.py's MDRemClient follows for its
    QSerialPort."""

    code_requested = Signal()
    password_requested = Signal()
    already_signed_in = Signal(str)  # display name
    signed_in = Signal(str)  # display name
    failed = Signal(str)

    def __init__(self, api_id: int, api_hash: str, phone: str, parent=None):
        super().__init__(parent)
        self._api_id = api_id
        self._api_hash = api_hash
        self._phone = phone
        self._loop: asyncio.AbstractEventLoop | None = None
        self._code_queue: asyncio.Queue | None = None
        self._password_queue: asyncio.Queue | None = None
        self._cancel_event: asyncio.Event | None = None
        self._ready = threading.Event()

    # --- entry point, on the worker thread ---------------------------------

    def run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._code_queue = asyncio.Queue()
        self._password_queue = asyncio.Queue()
        self._cancel_event = asyncio.Event()
        self._ready.set()
        try:
            self._loop.run_until_complete(self._flow())
        finally:
            self._loop.close()

    async def _flow(self) -> None:
        client = telegram_bot.create_telethon_client(
            self._api_id, self._api_hash, app_settings.telegram_session_path()
        )
        bot_client = telegram_bot.TelegramBotClient(client)
        try:
            await bot_client.connect()
            if await bot_client.is_authorized():
                self.already_signed_in.emit(await bot_client.me_display_name())
                return

            await bot_client.request_code(self._phone)
            self.code_requested.emit()
            code = await self._await_value(self._code_queue)
            if code is None:  # cancelled while waiting
                return

            result = await bot_client.submit_code(code)
            if result is telegram_bot.SignInResult.PASSWORD_REQUIRED:
                self.password_requested.emit()
                password = await self._await_value(self._password_queue)
                if password is None:  # cancelled while waiting
                    return
                await bot_client.submit_password(password)

            self.signed_in.emit(await bot_client.me_display_name())
        except telegram_bot.TelegramError as exc:
            self.failed.emit(str(exc))
        finally:
            await bot_client.disconnect()

    async def _await_value(self, queue: asyncio.Queue) -> str | None:
        """Blocks on either a value arriving in `queue` or cancel() being
        called -- whichever comes first. None means "cancelled"."""
        cancel_task = asyncio.ensure_future(self._cancel_event.wait())
        get_task = asyncio.ensure_future(queue.get())
        done, pending = await asyncio.wait({cancel_task, get_task}, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        if cancel_task in done:
            return None
        return get_task.result()

    # --- called from the GUI thread ----------------------------------------

    def submit_code(self, code: str) -> None:
        self._submit(lambda: self._code_queue, code)

    def submit_password(self, password: str) -> None:
        self._submit(lambda: self._password_queue, password)

    def _submit(self, queue_getter, value: str) -> None:
        if not self._ready.wait(_READY_TIMEOUT_S):
            return
        loop, queue = self._loop, queue_getter()
        if loop is not None and queue is not None:
            loop.call_soon_threadsafe(queue.put_nowait, value)

    def cancel(self) -> None:
        """Takes effect at the next point the flow is waiting on a code or
        password, not mid-network-call -- same "between steps, not during
        one" rule MDRemUploadDialog's cancel() follows."""
        if not self._ready.wait(_READY_TIMEOUT_S):
            return
        if self._loop is not None and self._cancel_event is not None:
            self._loop.call_soon_threadsafe(self._cancel_event.set)


class TelegramLoginDialog(QDialog):
    """A small wizard: phone number, then a code, then (if the account has
    two-factor authentication turned on) a password -- one field visible at
    a time, one button whose label/action follows whichever step is
    current."""

    def __init__(self, api_id: str, api_hash: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Sign in to Telegram"))
        self.resize(420, 220)
        self._api_id = api_id
        self._api_hash = api_hash
        self._worker: _LoginWorker | None = None
        self._closing = False
        self._stage = "phone"

        layout = QVBoxLayout(self)

        intro = QLabel(
            self.tr(
                "xD-Tools needs to sign in as your own Telegram account to talk to your bot -- "
                "Telegram does not let one bot message another directly."
            )
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form = QFormLayout()
        self.phone_edit = QLineEdit(app_settings.telegram_phone())
        self.phone_edit.setPlaceholderText("+1 555 0100")
        form.addRow(self.tr("Phone number"), self.phone_edit)

        self.code_edit = QLineEdit()
        form.addRow(self.tr("Code"), self.code_edit)

        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow(self.tr("Password"), self.password_edit)

        self._form = form
        layout.addLayout(form)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.buttons = QDialogButtonBox()
        self.primary_btn = QPushButton(self.tr("Send Code"))
        self.primary_btn.clicked.connect(self._on_primary_clicked)
        self.buttons.addButton(self.primary_btn, QDialogButtonBox.ButtonRole.AcceptRole)
        self.close_btn = QPushButton(self.tr("Cancel"))
        self.close_btn.clicked.connect(self.reject)
        self.buttons.addButton(self.close_btn, QDialogButtonBox.ButtonRole.RejectRole)
        layout.addWidget(self.buttons)

        self._set_stage("phone")

    # --- stage/visibility -----------------------------------------------------

    def _set_stage(self, stage: str) -> None:
        self._stage = stage
        self._form.setRowVisible(self.code_edit, stage in ("code", "password"))
        self._form.setRowVisible(self.password_edit, stage == "password")
        self.primary_btn.setText(self.tr("Send Code") if stage == "phone" else self.tr("Verify"))

    def _set_running(self, running: bool) -> None:
        self.phone_edit.setEnabled(not running)
        self.code_edit.setEnabled(not running)
        self.password_edit.setEnabled(not running)
        self.primary_btn.setEnabled(not running)

    # --- driving the worker -----------------------------------------------

    def _on_primary_clicked(self) -> None:
        if self._stage == "phone":
            self._start()
        elif self._stage == "code":
            self._set_running(True)
            self.status_label.setText(self.tr("Verifying..."))
            self._worker.submit_code(self.code_edit.text().strip())
        elif self._stage == "password":
            self._set_running(True)
            self.status_label.setText(self.tr("Verifying..."))
            self._worker.submit_password(self.password_edit.text())

    def _start(self) -> None:
        phone = self.phone_edit.text().strip()
        if not phone:
            self.status_label.setText(self.tr("Enter a phone number first."))
            return
        if not self._api_id or not self._api_hash:
            self.status_label.setText(
                self.tr("Set the Telegram API ID and API Hash first (from my.telegram.org).")
            )
            return
        try:
            api_id = int(self._api_id)
        except ValueError:
            self.status_label.setText(self.tr("The Telegram API ID must be a number."))
            return

        app_settings.set_telegram_phone(phone)
        self._set_running(True)
        self.status_label.setText(self.tr("Requesting a code from Telegram..."))

        self._worker = _LoginWorker(api_id, self._api_hash, phone, self)
        self._worker.code_requested.connect(self._on_code_requested)
        self._worker.password_requested.connect(self._on_password_requested)
        self._worker.already_signed_in.connect(lambda name: self._on_signed_in(name, already=True))
        self._worker.signed_in.connect(lambda name: self._on_signed_in(name, already=False))
        self._worker.failed.connect(self._on_failed)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()

    def _on_code_requested(self) -> None:
        self._set_stage("code")
        self._set_running(False)
        self.status_label.setText(self.tr("Enter the code Telegram just sent you."))

    def _on_password_requested(self) -> None:
        self._set_stage("password")
        self._set_running(False)
        self.status_label.setText(self.tr("This account has two-factor authentication -- enter its password."))

    def _on_signed_in(self, name: str, already: bool) -> None:
        self._set_running(False)
        self.primary_btn.setEnabled(False)
        self.close_btn.setText(self.tr("Close"))
        self.status_label.setText(
            self.tr("Already signed in as {name}.").format(name=name)
            if already
            else self.tr("Signed in as {name}.").format(name=name)
        )

    def _on_failed(self, message: str) -> None:
        self._set_stage("phone")
        self._set_running(False)
        self.status_label.setText(self.tr("Sign-in failed: {error}\n\nYou can try again.").format(error=message))

    def _on_worker_finished(self) -> None:
        self._worker = None
        if self._closing:
            super().reject()

    # --- shutdown -----------------------------------------------------

    def reject(self) -> None:
        """Never blocks the GUI thread on worker.wait() -- same rule
        MDRemUploadDialog follows, for the same reason: the worker may be
        mid network call, and wait() froze that dialog for real once
        already. Ask it to stop and return immediately; _on_worker_finished
        closes the dialog once the thread actually exits."""
        if self._worker is not None and self._worker.isRunning():
            self._closing = True
            self._worker.cancel()
            self.status_label.setText(self.tr("Stopping..."))
            self._set_running(True)
            return
        super().reject()

    def closeEvent(self, event) -> None:
        if self._worker is not None and self._worker.isRunning():
            self.reject()
            event.ignore()
            return
        super().closeEvent(event)
