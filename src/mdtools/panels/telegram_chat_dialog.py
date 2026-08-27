"""Experimental > "Download Album from Telegram Bot..." -- a generic mini
chat with the user's own bot: shows whatever it sends (text, inline
buttons, file attachments), lets the user reply, downloads any file the
bot offers, and hands the resulting folder to the existing Record Folder
to MiniDisc flow (panels/folder_record_dialog.py) -- xD-Tools doesn't care
where the audio came from once it's on disk, same as a ripped CD or a
folder of files already picked by hand.

**File attachments render only in the download queue on the right, never
in the transcript.** A chat that downloads a whole album is mostly file
messages; showing each one as its own transcript row (as an earlier
version did, with a Download button and its own progress bar) buried the
actual conversation under a wall of near-identical rows. The queue panel
is the single place a file's name/size/progress/speed is shown, and it
also enforces a concurrency cap (see `_ChatWorker._download_semaphore`) --
so it doubles as the answer to "how many are downloading right now",
which a flat transcript had no good way to show either.

Deliberately not a rigid "type a query, get a numbered list" protocol --
the exact command syntax of a user-built bot isn't knowable in advance, so
this shows and lets the user drive whatever the bot actually does: plain
text, Telegram's own inline keyboard buttons, or a file attached straight
to a reply.

**`_ChatWorker` extends telegram_login_dialog.py's `_LoginWorker` pattern
from a one-shot exchange to a *running* conversation.** Same persistent
asyncio event loop, client constructed inside run() -- but instead of
finishing after one sign-in, it loops for as long as the dialog is open,
dispatching between two queues: incoming bot messages (fed by Telethon's
own event handler, entirely within this thread's loop -- no
call_soon_threadsafe needed for *that* direction) and outgoing commands
from the GUI thread (send this text / click this button / download this
file), which *does* need call_soon_threadsafe, exactly like
_LoginWorker.submit_code()."""

from __future__ import annotations

import asyncio
import html
import threading
import time
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QThread, QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from mdtools import album_sort, app_settings, cdrip, i18n, telegram_bot, user_paths
from mdtools import translate as mdtools_translate
from mdtools.panels.hideable_dialog import hide_for_background

# Inline photo previews are scaled down to this width if wider -- large
# enough to actually judge a cover, small enough that a whole album's worth
# of search results doesn't turn the transcript into a wall of full-size
# images.
_PHOTO_MAX_WIDTH = 320

# How many files _ChatWorker will download at once -- a whole album
# arriving as a burst of file messages used to start every one of them
# immediately, with no limit at all.
_MAX_CONCURRENT_DOWNLOADS = 3


def _guess_image_extension(data: bytes) -> str:
    """A Telegram "photo" carries no filename at all (see ChatMessage.
    is_photo's own docstring), so there is no extension to reuse the way a
    real file attachment's own name already provides one -- sniffed from
    the bytes' own magic number instead of trusting a guess. Telegram
    photos are JPEG almost universally, which is also the fallback for
    anything unrecognised."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return ".gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return ".jpg"

# A progress callback fires often; recomputing speed on every single call
# makes it noisy (dividing a tiny byte delta by a tiny time delta). Only
# updated speed at most this often -- see _DownloadQueueItem.set_progress().
_SPEED_UPDATE_INTERVAL_S = 0.5

# Same reasoning as telegram_login_dialog.py's own constant: generous
# because this only ever has to cover the sliver of time between
# QThread.start() returning and run() reaching asyncio.new_event_loop().
_READY_TIMEOUT_S = 5.0


def _human_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"  # pragma: no cover -- unreachable, loop above always returns first


def pick_album_folder(parent, root: Path) -> tuple[Path, bool]:
    """The "which album?" question, module-level (not a TelegramChatDialog
    method) so app_window.py's standalone "Record from Last Telegram
    Download..." action can ask it too, without ever opening a chat.

    Zero or one immediate subfolder is already handled correctly by
    audio_folder.list_audio_files()'s own "recurse only if nothing sits
    directly in the folder" rule, so this only asks when `root` actually
    holds more than one -- returns `(root, True)` straight away otherwise.
    The second element is only False when the user was asked and
    cancelled.

    Uses QCoreApplication.translate() with a fixed context, not
    `parent.tr(...)` -- a QObject's tr() resolves its translation context
    from its own *runtime* class (verified directly: it is not the literal
    "parent" identifier lupdate's static scan records it under), which
    would silently look up a different, wrong context depending on which
    class happens to call this shared helper (TelegramChatDialog today,
    MainWindow once the standalone Experimental menu action reuses it) --
    and lupdate can never enumerate those call-site classes itself, so no
    translation supplied under either one would ever actually be found.
    A fixed, explicit context is the same fix this codebase's own i18n
    notes already prescribe for a translatable string in a plain
    module-level function -- see project.py's metadata_menu_entries() and
    layers_panel.py's module-level _label_for()."""
    # "burn" is cdrip.py's own reserved scratch subfolder name
    # (RESERVED_SCRATCH_DIRNAMES) -- CD burning works there, never in this
    # folder directly. Excluded here so it never shows up as if it were
    # something to record. (Ripping has no scratch folder of its own --
    # ripped files land directly in this shared folder and stay there.)
    subfolders = sorted(
        p for p in root.iterdir() if p.is_dir() and p.name not in cdrip.RESERVED_SCRATCH_DIRNAMES
    )
    if len(subfolders) <= 1:
        return root, True
    names = [p.name for p in subfolders]
    choice, ok = QInputDialog.getItem(
        parent,
        QCoreApplication.translate("TelegramChatDialog", "Choose Album"),
        QCoreApplication.translate(
            "TelegramChatDialog",
            # Neutral about what happens next: this picker is shared by
            # recording to MiniDisc and burning to CD, and said "record"
            # in both -- caught on screen while burning.
            "More than one album was downloaded -- which one do you want to use?",
        ),
        names,
        0,
        False,
    )
    if not ok:
        return root, False
    return root / choice, True


class _ChatWorker(QThread):
    """Runs the whole conversation on one persistent event loop -- see the
    module docstring for why this can't be a one-shot run() like every
    other worker in this codebase except _LoginWorker, whose shape this
    directly extends."""

    ready = Signal(str, str)  # bot display name, session download folder
    not_authorized = Signal()
    connect_failed = Signal(str)
    message_received = Signal(object)  # telegram_bot.ChatMessage
    send_failed = Signal(str)
    click_failed = Signal(str)
    download_started = Signal(int)  # message_id -- the semaphore let it through, actually downloading now
    download_progress = Signal(int, int, int)  # message_id, current, total
    download_finished = Signal(int, str)  # message_id, saved path
    download_failed = Signal(int, str)  # message_id, error
    photo_loaded = Signal(int, bytes)  # message_id, image data
    translation_loaded = Signal(int, str)  # message_id, translated text

    def __init__(
        self,
        api_id: int,
        api_hash: str,
        bot_username: str,
        download_root: Path,
        target_language: str,
        parent=None,
    ):
        super().__init__(parent)
        self._api_id = api_id
        self._api_hash = api_hash
        self._bot_username = bot_username
        self._download_root = download_root
        self._target_language = target_language
        self._loop: asyncio.AbstractEventLoop | None = None
        self._incoming: asyncio.Queue | None = None
        self._outgoing: asyncio.Queue | None = None
        self._cancel_event: asyncio.Event | None = None
        self._download_semaphore: asyncio.Semaphore | None = None
        self._ready = threading.Event()

    # --- entry point, on the worker thread ---------------------------------

    def run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._incoming = asyncio.Queue()
        self._outgoing = asyncio.Queue()
        self._cancel_event = asyncio.Event()
        self._download_semaphore = asyncio.Semaphore(_MAX_CONCURRENT_DOWNLOADS)
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
            # A stale/since-revoked local session file still opens this
            # dialog (the menu's own gate only checks the file exists) --
            # this live check is what actually decides whether chatting is
            # possible, same "local = fast optimistic gate, live = the real
            # one" split as ExperimentalSettingsDialog's status label.
            if not await bot_client.is_authorized():
                self.not_authorized.emit()
                return
            bot_name = await bot_client.resolve_bot(self._bot_username)
        except telegram_bot.TelegramError as exc:
            self.connect_failed.emit(str(exc))
            await bot_client.disconnect()
            return

        # Deliberately not a fresh, timestamped subfolder per session --
        # explicit user request. Everything lands directly in the one
        # configured download folder across every chat session, and
        # "Sort into Album Folders" (or the standalone Experimental >
        # "Sort Telegram Downloads into Album Folders..." action) is what
        # organizes whatever has accumulated there, from this session and
        # any earlier one, into per-album subfolders in one pass.
        session_folder = self._download_root
        session_folder.mkdir(parents=True, exist_ok=True)

        await bot_client.start_watching(self._incoming.put_nowait)
        self.ready.emit(bot_name, str(session_folder))

        try:
            while True:
                incoming_task = asyncio.ensure_future(self._incoming.get())
                outgoing_task = asyncio.ensure_future(self._outgoing.get())
                cancel_task = asyncio.ensure_future(self._cancel_event.wait())
                done, pending = await asyncio.wait(
                    {incoming_task, outgoing_task, cancel_task}, return_when=asyncio.FIRST_COMPLETED
                )
                for task in pending:
                    task.cancel()
                if cancel_task in done:
                    break
                if incoming_task in done:
                    message = incoming_task.result()
                    self.message_received.emit(message)
                    # Fire-and-forget on this same loop -- none of a photo
                    # preview, a translation, or a file's own download is
                    # worth making the rest of the conversation wait on;
                    # a failure in any of them is handled where it's
                    # awaited (_load_photo/_load_translation/_run_download),
                    # so there is nothing here to await or check.
                    if message.is_photo:
                        asyncio.ensure_future(self._load_photo(bot_client, message.id))
                    if message.text.strip():
                        asyncio.ensure_future(self._load_translation(message.id, message.text))
                    if message.file_name:
                        asyncio.ensure_future(self._run_download(bot_client, session_folder, message.id))
                if outgoing_task in done:
                    await self._dispatch(bot_client, session_folder, outgoing_task.result())
        finally:
            await bot_client.disconnect()

    async def _load_photo(self, bot_client: telegram_bot.TelegramBotClient, message_id: int) -> None:
        try:
            data = await bot_client.download_bytes(message_id)
        except telegram_bot.TelegramError:
            return  # a missing preview is not worth interrupting the chat over
        self.photo_loaded.emit(message_id, data)

    async def _load_translation(self, message_id: int, text: str) -> None:
        """Runs the (blocking) HTTP call in a thread-pool executor -- this
        module's own event loop must keep dispatching other messages/clicks/
        downloads while a translation is in flight, so mdtools.translate's
        plain urllib call can't run directly on it."""
        loop = asyncio.get_event_loop()
        try:
            translated = await loop.run_in_executor(
                None, mdtools_translate.translate, text, self._target_language
            )
        except mdtools_translate.TranslationError:
            return  # same "silently skip, original text is still shown" rule as the photo preview
        if translated.strip().casefold() == text.strip().casefold():
            return  # nothing useful to add -- already in (or indistinguishable from) the target language
        self.translation_loaded.emit(message_id, translated)

    async def _dispatch(self, bot_client: telegram_bot.TelegramBotClient, session_folder: Path, command: tuple) -> None:
        kind = command[0]
        if kind == "send":
            _, text = command
            try:
                message = await bot_client.send_text(text)
            except telegram_bot.TelegramError as exc:
                self.send_failed.emit(str(exc))
                return
            self.message_received.emit(message)
        elif kind == "click":
            _, message_id, row, col = command
            try:
                await bot_client.click(message_id, row, col)
            except telegram_bot.TelegramError as exc:
                self.click_failed.emit(str(exc))
        elif kind == "download":
            _, message_id = command
            await self._run_download(bot_client, session_folder, message_id)

    async def _run_download(
        self, bot_client: telegram_bot.TelegramBotClient, session_folder: Path, message_id: int
    ) -> None:
        """Shared by the automatic trigger (a file-bearing message starts
        downloading the moment it arrives, no click needed) and the manual
        "download" command -- which still exists as the *retry* path a
        failed automatic download leaves behind via
        _DownloadQueueItem.set_download_failed() showing its Retry button.

        Every call queues up on `_download_semaphore` first -- at most
        `_MAX_CONCURRENT_DOWNLOADS` calls ever get past the `async with`
        at once, so an album arriving as a burst of file messages doesn't
        start them all immediately. `download_started` fires only once
        the semaphore actually lets this one through, which is what tells
        the queue panel to move an item from "Queued" to "Downloading"."""
        async with self._download_semaphore:
            self.download_started.emit(message_id)

            def progress(current: int, total: int, _id=message_id) -> None:
                self.download_progress.emit(_id, current, total)

            try:
                saved = await bot_client.download(message_id, session_folder, progress_callback=progress)
            except telegram_bot.TelegramError as exc:
                self.download_failed.emit(message_id, str(exc))
                return
            self.download_finished.emit(message_id, str(saved))

    # --- called from the GUI thread ----------------------------------------

    def send_text(self, text: str) -> None:
        self._submit(("send", text))

    def click_button(self, message_id: int, row: int, col: int) -> None:
        self._submit(("click", message_id, row, col))

    def download_file(self, message_id: int) -> None:
        self._submit(("download", message_id))

    def _submit(self, command: tuple) -> None:
        if not self._ready.wait(_READY_TIMEOUT_S):
            return
        if self._loop is not None and self._outgoing is not None:
            self._loop.call_soon_threadsafe(self._outgoing.put_nowait, command)

    def cancel(self) -> None:
        """Takes effect at the next loop iteration, not mid network call --
        same "between steps, not during one" rule MDRemUploadDialog's and
        _LoginWorker's cancel() follow."""
        if not self._ready.wait(_READY_TIMEOUT_S):
            return
        if self._loop is not None and self._cancel_event is not None:
            self._loop.call_soon_threadsafe(self._cancel_event.set)


class _ClickableImageLabel(QLabel):
    """A photo preview that is also the button for saving it -- same
    press-then-release-inside-the-label pattern as cover_preview.py's own
    CoverPreview, reused here rather than duplicated by accident: a press
    that wanders off the label before letting go is how anyone cancels a
    misclick, on either widget."""

    clicked = Signal()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class _MessageWidget(QWidget):
    """One row in the transcript -- plain text, an inline photo preview,
    and/or a row of inline buttons. Not a chat-bubble look, matching this
    app's existing utilitarian dialog style (tree/list based) rather than
    inventing a new visual language for one dialog.

    A file attachment is deliberately *not* rendered here at all -- see
    the module docstring for why it lives only in the download queue on
    the right (_DownloadQueueItem below). A message with a file and no
    text/buttons/photo of its own therefore never gets a transcript row;
    _on_file_message() routes it to the queue instead of here."""

    button_clicked = Signal(int, int, int)  # message_id, row, col
    photo_save_requested = Signal(int)  # message_id

    def __init__(self, message: telegram_bot.ChatMessage, bot_name: str, parent=None):
        super().__init__(parent)
        self.message_id = message.id

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)

        who = self.tr("You") if message.outgoing else bot_name
        text = html.escape(message.text)
        self.text_label = QLabel(f"<b>{html.escape(who)}:</b> {text}" if text else f"<b>{html.escape(who)}</b>")
        self.text_label.setWordWrap(True)
        layout.addWidget(self.text_label)

        # Translation, when one arrives (mdtools.translate, via
        # _ChatWorker._load_translation) -- never replaces the original,
        # since it can be wrong and the original may carry information
        # (an exact command, a filename) a translation would obscure.
        self.translation_label: QLabel | None = None
        if not message.outgoing and text:
            self.translation_label = QLabel()
            self.translation_label.setWordWrap(True)
            self.translation_label.setVisible(False)
            italic_font = self.translation_label.font()
            italic_font.setItalic(True)
            self.translation_label.setFont(italic_font)
            layout.addWidget(self.translation_label)

        # A Telegram "photo" has no filename (see ChatMessage.is_photo's
        # own docstring) -- shown inline here, not routed to the download
        # queue the way a real file attachment is. The bytes behind the
        # preview are kept on the widget (set_photo()) so clicking it to
        # save doesn't have to re-download anything already on screen.
        self.photo_label: _ClickableImageLabel | None = None
        self._photo_bytes: bytes | None = None
        if message.is_photo:
            self.photo_label = _ClickableImageLabel(self.tr("Loading image..."))
            self.photo_label.setToolTip(self.tr("Click to save this image"))
            self.photo_label.clicked.connect(lambda: self.photo_save_requested.emit(self.message_id))
            layout.addWidget(self.photo_label)

        for row_index, row in enumerate(message.buttons):
            row_layout = QHBoxLayout()
            for col_index, label in enumerate(row):
                button = QPushButton(label)
                button.clicked.connect(
                    lambda checked=False, r=row_index, c=col_index: self.button_clicked.emit(self.message_id, r, c)
                )
                row_layout.addWidget(button)
            row_layout.addStretch(1)
            layout.addLayout(row_layout)

    def set_photo(self, data: bytes) -> None:
        if self.photo_label is None:
            return
        pixmap = QPixmap()
        if not pixmap.loadFromData(data):
            self.photo_label.setText(self.tr("Could not display image"))
            return
        self._photo_bytes = data
        if pixmap.width() > _PHOTO_MAX_WIDTH:
            pixmap = pixmap.scaledToWidth(_PHOTO_MAX_WIDTH, Qt.TransformationMode.SmoothTransformation)
        self.photo_label.setPixmap(pixmap)

    def set_translation(self, translated: str) -> None:
        if self.translation_label is None:
            return
        self.translation_label.setText(self.tr("Translated: {text}").format(text=html.escape(translated)))
        self.translation_label.setVisible(True)



class _DownloadQueueItem(QWidget):
    """One row in the download queue panel -- the only place a file
    attachment's name/size/progress/speed is shown at all (see the module
    docstring). Created the moment a file message arrives ("Queued"),
    before _ChatWorker's concurrency-limiting semaphore has necessarily let
    it start."""

    retry_requested = Signal(int)  # message_id

    def __init__(self, message: telegram_bot.ChatMessage, parent=None):
        super().__init__(parent)
        self.message_id = message.id
        # Read by TelegramChatDialog's own aggregate summary -- kept here
        # rather than re-derived, since this is the one place that already
        # has the original message to read it from.
        self.file_size = message.file_size
        self.last_speed_bps: float | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        # A caption sent alongside the file (e.g. "Track 3 of 12") is real
        # conversational content -- worth keeping even though the file
        # itself doesn't get a transcript row of its own.
        if message.text.strip():
            caption = QLabel(html.escape(message.text))
            caption.setWordWrap(True)
            layout.addWidget(caption)

        size_text = f" ({_human_size(message.file_size)})" if message.file_size else ""
        name_label = QLabel(f"{message.file_name}{size_text}")
        name_label.setWordWrap(True)
        layout.addWidget(name_label)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        layout.addWidget(self.progress)

        self.status_label = QLabel(self.tr("Queued"))
        layout.addWidget(self.status_label)

        self.retry_btn = QPushButton(self.tr("Retry"))
        self.retry_btn.setVisible(False)
        self.retry_btn.clicked.connect(lambda: self.retry_requested.emit(self.message_id))
        layout.addWidget(self.retry_btn)

        # Speed is derived from consecutive progress callbacks, not
        # reported by Telethon directly -- see set_progress().
        self._last_update_time: float | None = None
        self._last_bytes = 0

    def set_downloading(self) -> None:
        self.retry_btn.setVisible(False)
        self.status_label.setText(self.tr("Downloading..."))
        self._last_update_time = None
        self._last_bytes = 0

    def set_progress(self, current: int, total: int) -> None:
        if total:
            self.progress.setValue(int(current * 100 / total))
        now = time.monotonic()
        if self._last_update_time is None:
            # First callback for this download -- nothing to measure a
            # speed against yet, just establish the baseline.
            self._last_update_time = now
            self._last_bytes = current
            return
        elapsed = now - self._last_update_time
        if elapsed < _SPEED_UPDATE_INTERVAL_S:
            return  # too soon to recompute -- avoids a noisy, jumpy speed reading
        speed = (current - self._last_bytes) / elapsed
        self._last_update_time = now
        self._last_bytes = current
        self.last_speed_bps = speed
        self.status_label.setText(self.tr("Downloading... ({speed}/s)").format(speed=_human_size(int(speed))))

    def set_downloaded(self) -> None:
        self.progress.setValue(100)
        self.status_label.setText(self.tr("Saved"))
        self.last_speed_bps = None

    def set_download_failed(self, error: str) -> None:
        self.status_label.setText(self.tr("Failed: {error}").format(error=error))
        self.retry_btn.setVisible(True)
        self.last_speed_bps = None


class TelegramChatDialog(QDialog):
    """Opened only while a local session file exists (app_window.py's own
    gate before ever constructing this) -- but that's only the fast,
    optimistic half; _ChatWorker's own is_authorized() check is what
    actually decides whether chatting is possible, and not_authorized()
    below is what a stale/revoked session looks like once opened anyway.

    Wired into #27's shared machinery exactly like the six recording/rip/
    burn/upload dialogs -- see app_window._open_telegram_bot_chat(), which
    hands this to the same _drive_recording_bar()/_release_recording_bar()
    and _guard_no_concurrent_operation() they use. A chat session touches
    no MDRem port, audio device or optical drive, so it is not blocked by
    the same *reason* those dialogs are -- but it drives the very same
    single bottom progress bar (download-queue status, mirroring the
    aggregate line above the queue panel itself), and that bar can only
    ever belong to one dialog at a time, so reusing the one-at-a-time
    guard is what keeps it from being fought over rather than inventing a
    second, parallel mechanism just for this dialog."""

    # Mirrored by MainWindow's own bottom-of-window progress bar (#27) --
    # see app_window.py's _drive_recording_bar()/_release_recording_bar().
    running_changed = Signal(bool)
    overall_progress_changed = Signal(float, str)
    visibility_changed = Signal(bool)
    # Asked for by the progress bar's "Show recording window" button --
    # see panels/hideable_dialog.py, which is what actually re-shows this.
    show_requested = Signal()

    def __init__(self, api_id: str, api_hash: str, bot_username: str, download_root: Path, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Telegram Bot"))
        # Set by the Hide button, read by exec_hideable() -- see
        # panels/hideable_dialog.py for why a hide has to be told apart
        # from a cancel at all.
        self.hidden_for_background = False
        # Wider than a plain single-pane chat would need -- the transcript
        # and the download queue (added alongside each other in a
        # QSplitter, see __init__ below) each need real room now that
        # there are two panes side by side, not one.
        self.resize(880, 640)
        self._api_id = api_id
        self._api_hash = api_hash
        self._bot_username = bot_username
        self._download_root = download_root
        self._worker: _ChatWorker | None = None
        self._closing = False
        self._pending_finish = None
        self._bot_name = bot_username
        self._session_folder: str | None = None
        self._message_widgets: dict[int, _MessageWidget] = {}
        self._queue_items: dict[int, _DownloadQueueItem] = {}
        # Every message id, in the order first seen -- *not* touched by a
        # later edit (see _on_message_received), so this stays true arrival
        # order for album_sort.batches_from_arrival_order()'s benefit.
        self._message_order: list[int] = []
        # message id -> saved path, filled in by _on_download_finished --
        # the other half album_sort.sort_downloads() needs.
        self._downloaded_files: dict[int, Path] = {}
        # message ids currently between download_started and
        # download_finished/download_failed -- see _update_sort_button()/
        # _update_continue_button() below, which both refuse to run while
        # this is non-empty.
        self._active_downloads: set[int] = set()
        # message ids whose most recent attempt ended in download_failed --
        # discarded again the moment a retry restarts them. Both this and
        # _download_progress below exist purely to feed _update_queue_summary().
        self._failed_downloads: set[int] = set()
        # message id -> (bytes so far, total bytes) for every queued file
        # with a known size -- an aggregate progress needs each item's own
        # current position, not just whichever one last emitted a signal.
        self._download_progress: dict[int, tuple[int, int]] = {}
        # Read by app_window.py after exec() == Accepted, and handed to
        # _record_folder_dialog() exactly like a folder picked by hand --
        # that dispatches to burning itself on a CD project, so this dialog
        # only ever needs the one "Record" button now, whatever medium the
        # open project turns out to be.
        self.downloaded_folder: str | None = None

        layout = QVBoxLayout(self)

        self.status_label = QLabel(self.tr("Connecting..."))
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        # Transcript (left) and download queue (right) side by side, in a
        # QSplitter rather than a fixed split -- resizable by the user, and
        # the queue panel's own preferred width (see below) still gives it
        # a sensible starting size without either pane fighting the other.
        splitter = QSplitter(Qt.Orientation.Horizontal)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self._transcript = QWidget()
        self._transcript_layout = QVBoxLayout(self._transcript)
        self._transcript_layout.addStretch(1)
        self.scroll_area.setWidget(self._transcript)
        # rangeChanged fires exactly when the scrollbar's max actually
        # updates to reflect newly added content -- unlike a plain
        # QTimer.singleShot(0, ...) after inserting a widget, which can run
        # before Qt has finished recomputing the transcript's size (layout
        # recalculation and timer firing aren't ordered relative to each
        # other), leaving the view one message behind. This is the standard
        # "always scroll a growing QScrollArea to the bottom" idiom.
        self.scroll_area.verticalScrollBar().rangeChanged.connect(self._scroll_to_bottom)
        splitter.addWidget(self.scroll_area)

        queue_pane = QWidget()
        queue_pane_layout = QVBoxLayout(queue_pane)
        queue_pane_layout.setContentsMargins(0, 0, 0, 0)
        # self.tr(...) has to be called outside the f-string -- see
        # experimental_settings_dialog.py's near-identical header for why
        # (pyside6-lupdate's static scanner never sees a tr() call nested
        # inside an f-string's {...} interpolation).
        queue_title = self.tr("Downloads")
        queue_header = QLabel(f"<b>{queue_title}</b>")
        queue_pane_layout.addWidget(queue_header)
        # An aggregate line -- queued/active/done counts, overall progress,
        # summed speed -- fed by the same download_started/progress/
        # finished/failed signals every per-row _DownloadQueueItem already
        # reacts to (#7). Hidden until there's anything to report at all.
        self.queue_summary_label = QLabel()
        self.queue_summary_label.setWordWrap(True)
        self.queue_summary_label.setVisible(False)
        queue_pane_layout.addWidget(self.queue_summary_label)
        self.queue_scroll_area = QScrollArea()
        self.queue_scroll_area.setWidgetResizable(True)
        self._queue = QWidget()
        self._queue_layout = QVBoxLayout(self._queue)
        self._queue_layout.addStretch(1)
        self.queue_scroll_area.setWidget(self._queue)
        self.queue_scroll_area.verticalScrollBar().rangeChanged.connect(self._scroll_queue_to_bottom)
        queue_pane_layout.addWidget(self.queue_scroll_area)
        queue_pane.setMinimumWidth(200)
        splitter.addWidget(queue_pane)

        splitter.setStretchFactor(0, 1)  # the transcript gets any extra space by default
        splitter.setSizes([360, 200])
        layout.addWidget(splitter, 1)

        # A handful of bot commands are near-universal (every BotFather bot
        # answers /start; /help is the other near-guaranteed one), so
        # they're worth a one-click shortcut rather than making the user
        # type them every time -- sent through the exact same
        # worker.send_text() the free-text box uses, so they show up in the
        # transcript identically to anything typed by hand.
        quick_row = QHBoxLayout()
        quick_row.addWidget(QLabel(self.tr("Quick commands:")))
        self.quick_command_buttons: list[QPushButton] = []
        for command in ("/start", "/help"):
            button = QPushButton(command)
            button.setEnabled(False)
            button.clicked.connect(lambda checked=False, c=command: self._send_quick_command(c))
            quick_row.addWidget(button)
            self.quick_command_buttons.append(button)
        quick_row.addStretch(1)
        layout.addLayout(quick_row)

        send_row = QHBoxLayout()
        self.message_edit = QLineEdit()
        self.message_edit.setEnabled(False)
        self.message_edit.returnPressed.connect(self._on_send)
        send_row.addWidget(self.message_edit, 1)
        self.send_btn = QPushButton(self.tr("Send"))
        self.send_btn.setEnabled(False)
        # Without this, Qt falls back to the first enabled AcceptRole
        # button in the QDialogButtonBox below the moment focus leaves
        # whatever held it initially -- which made pressing Enter in this
        # field also fire "Record Downloaded Albums...", opening the album
        # picker. Reported directly.
        self.send_btn.setDefault(True)
        self.send_btn.clicked.connect(self._on_send)
        send_row.addWidget(self.send_btn)
        layout.addLayout(send_row)

        # Folder-level actions -- available as soon as there's a folder
        # worth acting on, independent of the MDRem-gated recording step
        # below.
        folder_row = QHBoxLayout()
        self.open_folder_btn = QPushButton(self.tr("Open Download Folder"))
        self.open_folder_btn.setEnabled(False)
        self.open_folder_btn.clicked.connect(self._open_download_folder)
        folder_row.addWidget(self.open_folder_btn)
        self.sort_btn = QPushButton(self.tr("Sort into Album Folders"))
        self.sort_btn.setEnabled(False)
        self.sort_btn.clicked.connect(self._sort_downloads)
        folder_row.addWidget(self.sort_btn)
        folder_row.addStretch(1)
        layout.addLayout(folder_row)

        self.buttons = QDialogButtonBox()
        self.continue_btn = QPushButton(self.tr("Record Downloaded Albums..."))
        self.continue_btn.setEnabled(False)
        self.continue_btn.setAutoDefault(False)
        self.continue_btn.clicked.connect(self._on_continue_clicked)
        self.buttons.addButton(self.continue_btn, QDialogButtonBox.ButtonRole.AcceptRole)
        self.hide_btn = QPushButton(self.tr("Hide"))
        self.hide_btn.setToolTip(
            self.tr("Hide this window and keep the chat and any downloads running in the "
                    "background -- use \"Show recording window\" in the bar at the bottom of "
                    "the main window to bring it back.")
        )
        self.hide_btn.setAutoDefault(False)
        self.hide_btn.clicked.connect(self._on_hide_clicked)
        self.buttons.addButton(self.hide_btn, QDialogButtonBox.ButtonRole.ActionRole)
        self.close_btn = QPushButton(self.tr("Close"))
        self.close_btn.setAutoDefault(False)
        self.close_btn.clicked.connect(self.reject)
        self.buttons.addButton(self.close_btn, QDialogButtonBox.ButtonRole.RejectRole)
        layout.addWidget(self.buttons)
        self._update_continue_button()

        # Deliberately *not* called here -- see start_connecting()'s own
        # docstring for why plain construction has to stay inert, and
        # app_window._open_telegram_bot_chat() for where this is actually
        # invoked in production.

    # --- starting the worker -----------------------------------------------

    def start_connecting(self) -> None:
        """Starts the worker thread connecting to Telegram.

        Not called from __init__: unlike every other dialog in this
        codebase, plain construction here would otherwise always start a
        real background thread (and, without a mocked client, a real
        network connection attempt) as a side effect -- a landmine for any
        test, or any future caller, that just wants to build/inspect a
        TelegramChatDialog. _ChatWorker also loops forever until
        cancelled (unlike _LoginWorker's one-shot exchange), and Qt aborts
        the whole process if a QThread is destroyed while still running --
        so whoever calls this must also make sure the dialog gets a
        reject()/accept() (and so a chance to cancel the worker) before it
        is discarded. app_window._open_telegram_bot_chat() calls this right
        after construction, before exec()."""
        try:
            api_id = int(self._api_id)
        except ValueError:
            self.status_label.setText(self.tr("The Telegram API ID must be a number."))
            return

        self._worker = _ChatWorker(
            api_id, self._api_hash, self._bot_username, self._download_root, i18n.current_language(), self
        )
        self._worker.ready.connect(self._on_ready)
        self._worker.not_authorized.connect(self._on_not_authorized)
        self._worker.connect_failed.connect(self._on_connect_failed)
        self._worker.message_received.connect(self._on_message_received)
        self._worker.send_failed.connect(self._on_send_failed)
        self._worker.click_failed.connect(self._on_click_failed)
        self._worker.download_started.connect(self._on_download_started)
        self._worker.download_progress.connect(self._on_download_progress)
        self._worker.download_finished.connect(self._on_download_finished)
        self._worker.download_failed.connect(self._on_download_failed)
        self._worker.photo_loaded.connect(self._on_photo_loaded)
        self._worker.translation_loaded.connect(self._on_translation_loaded)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()
        # Spans the whole session, not just active downloads -- there is
        # no natural "operation ends" moment for an interactive chat short
        # of the dialog actually closing (see _on_worker_finished()),
        # unlike the six recording dialogs' own single run.
        self.running_changed.emit(True)

    def _on_ready(self, bot_name: str, session_folder: str) -> None:
        self._bot_name = bot_name
        self._session_folder = session_folder
        self.status_label.setText(self.tr("Connected to {name}.").format(name=bot_name))
        self.message_edit.setEnabled(True)
        self.send_btn.setEnabled(True)
        self.open_folder_btn.setEnabled(True)
        for button in self.quick_command_buttons:
            button.setEnabled(True)
        # Both, and only now that _session_folder is known: whatever earlier
        # sessions left in that folder is already sortable/recordable before
        # this session downloads anything at all.
        self._update_sort_button()
        self._update_continue_button()

    def _on_not_authorized(self) -> None:
        self.status_label.setText(self.tr("Not signed in to Telegram."))
        sign_in_btn = QPushButton(self.tr("Sign in..."))
        sign_in_btn.clicked.connect(self._open_experimental_settings)
        self._transcript_layout.insertWidget(self._transcript_layout.count() - 1, sign_in_btn)

    def _open_experimental_settings(self) -> None:
        from mdtools.panels.experimental_settings_dialog import ExperimentalSettingsDialog

        ExperimentalSettingsDialog(self).exec()

    def _on_connect_failed(self, message: str) -> None:
        self.status_label.setText(self.tr("Could not connect: {error}").format(error=message))

    # --- the conversation ---------------------------------------------------

    def _on_message_received(self, message: telegram_bot.ChatMessage) -> None:
        """Handles both a brand new message and an edit of one already
        shown -- Telegram keeps a message's id across an edit (a common
        pattern: a bot "menu" that morphs one message's text/buttons in
        place rather than sending a fresh message every step), so the same
        id arriving again means "replace this widget's content", not
        "append a new message" -- appending would have left the transcript
        showing the stale pre-edit buttons forever, which is exactly what
        was reported.

        A file attachment never gets a transcript row at all (see the
        module docstring) -- _on_file_message() below routes it to the
        download queue instead, but arrival-order bookkeeping still has to
        happen here, unconditionally, since album_sort needs *every*
        message's arrival position, file or not."""
        is_new = message.id not in self._message_widgets and message.id not in self._queue_items
        if is_new:
            self._message_order.append(message.id)

        if message.file_name:
            self._on_file_message(message, is_new)
            return

        existing = self._message_widgets.pop(message.id, None)
        if existing is not None:
            index = self._transcript_layout.indexOf(existing)
            self._transcript_layout.removeWidget(existing)
            existing.deleteLater()
        else:
            index = self._transcript_layout.count() - 1  # just before the trailing stretch

        widget = _MessageWidget(message, self._bot_name)
        widget.button_clicked.connect(self._on_button_clicked)
        widget.photo_save_requested.connect(self._on_photo_save_requested)
        self._message_widgets[message.id] = widget
        self._transcript_layout.insertWidget(index, widget)
        # No explicit scroll call here -- the rangeChanged connection set up
        # in __init__ handles it once the transcript's new size actually
        # takes effect (which a new message almost always causes, so this
        # covers the normal case already; the widget growing further later,
        # e.g. an image finishing loading, is handled the same way since
        # that also changes the transcript's size and re-fires rangeChanged).

    def _on_file_message(self, message: telegram_bot.ChatMessage, is_new: bool) -> None:
        """A file attachment's whole life -- queued, downloading, done or
        failed -- is shown only in the download queue panel. An edit to an
        already-queued file message (rare -- bots essentially never edit an
        attachment after sending it) is simply left alone rather than
        rebuilding its row, since there is nothing meaningful to update."""
        if not is_new:
            return
        item = _DownloadQueueItem(message)
        item.retry_requested.connect(self._on_download_requested)
        self._queue_items[message.id] = item
        self._queue_layout.insertWidget(self._queue_layout.count() - 1, item)
        # Seeded at 0/file_size (not just once downloading actually starts)
        # so a still-queued file already contributes its own full size to
        # the aggregate's denominator -- "overall progress" means across
        # the whole batch shown in this panel, not only whichever files
        # happen to be active right now.
        self._download_progress[message.id] = (0, message.file_size or 0)
        self._update_queue_summary()

    def _scroll_to_bottom(self, minimum: int = 0, maximum: int = 0) -> None:
        """Connected directly to QScrollBar.rangeChanged(min, max), hence
        the two unused positional parameters -- Qt always passes both."""
        bar = self.scroll_area.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _scroll_queue_to_bottom(self, minimum: int = 0, maximum: int = 0) -> None:
        bar = self.queue_scroll_area.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _on_send(self) -> None:
        text = self.message_edit.text().strip()
        if not text or self._worker is None:
            return
        self.message_edit.clear()
        self._worker.send_text(text)

    def _send_quick_command(self, command: str) -> None:
        if self._worker is not None:
            self._worker.send_text(command)

    def _on_send_failed(self, message: str) -> None:
        self.status_label.setText(self.tr("Could not send: {error}").format(error=message))

    def _on_button_clicked(self, message_id: int, row: int, col: int) -> None:
        if self._worker is not None:
            self._worker.click_button(message_id, row, col)

    def _on_click_failed(self, message: str) -> None:
        self.status_label.setText(self.tr("Could not do that: {error}").format(error=message))

    def _on_photo_save_requested(self, message_id: int) -> None:
        """Saves a photo already shown inline in the transcript -- the
        bytes are already on the widget (set when the preview finished
        loading), so this never re-downloads anything. A project's own
        cover art lives inside the .mdproj once chosen; this is only for
        keeping a picture the bot sent before it has a project to belong
        to at all, hence a folder of its own (user_paths.artwork_dir())
        rather than reusing gallery.downloaded_covers_dir()."""
        widget = self._message_widgets.get(message_id)
        if widget is None or widget._photo_bytes is None:
            return
        data = widget._photo_bytes
        path = user_paths.artwork_dir() / f"telegram-photo-{message_id}{_guess_image_extension(data)}"
        try:
            path.write_bytes(data)
        except OSError as exc:
            self.status_label.setText(self.tr("Could not save image: {error}").format(error=exc))
            return
        self.status_label.setText(self.tr("Saved image to {path}").format(path=str(path)))

    # --- downloading ---------------------------------------------------

    def _on_download_requested(self, message_id: int) -> None:
        """Also the retry path -- connected to _DownloadQueueItem's own
        retry_requested signal, not just an internal call."""
        if self._worker is not None:
            self._worker.download_file(message_id)

    def _on_download_started(self, message_id: int) -> None:
        item = self._queue_items.get(message_id)
        if item is not None:
            item.set_downloading()
        self._active_downloads.add(message_id)
        # A retry restarting a previously-failed download -- no longer
        # failed, and its progress (if any survived from the failed
        # attempt) starts over from zero.
        self._failed_downloads.discard(message_id)
        self._download_progress[message_id] = (0, item.file_size if item is not None and item.file_size else 0)
        self._update_sort_button()
        self._update_continue_button()
        self._update_queue_summary()

    def _on_download_progress(self, message_id: int, current: int, total: int) -> None:
        item = self._queue_items.get(message_id)
        if item is not None:
            item.set_progress(current, total)
        self._download_progress[message_id] = (current, total)
        self._update_queue_summary()

    def _on_download_finished(self, message_id: int, path: str) -> None:
        item = self._queue_items.get(message_id)
        if item is not None:
            item.set_downloaded()
            if item.file_size:
                self._download_progress[message_id] = (item.file_size, item.file_size)
        self._downloaded_files[message_id] = Path(path)
        self._active_downloads.discard(message_id)
        self._update_sort_button()
        self._update_continue_button()
        self._update_queue_summary()

    def _on_download_failed(self, message_id: int, error: str) -> None:
        item = self._queue_items.get(message_id)
        if item is not None:
            item.set_download_failed(error)
        self._active_downloads.discard(message_id)
        self._failed_downloads.add(message_id)
        self._update_sort_button()
        self._update_continue_button()
        self._update_queue_summary()

    def _update_queue_summary(self) -> None:
        """The aggregate line above the download queue (#7) -- counts plus
        an overall progress and a summed speed, all derived from state the
        four handlers above already keep (nothing new is asked of
        _ChatWorker for this)."""
        total = len(self._queue_items)
        if total == 0:
            self.queue_summary_label.setVisible(False)
            return

        active = len(self._active_downloads)
        failed = len(self._failed_downloads)
        finished = len(self._downloaded_files)
        queued = max(0, total - active - failed - finished)

        current_bytes = 0
        known_total_bytes = 0
        for message_id in self._queue_items:
            current, item_total = self._download_progress.get(message_id, (0, 0))
            if item_total:
                current_bytes += current
                known_total_bytes += item_total

        speed_bps = sum(
            item.last_speed_bps or 0.0
            for message_id, item in self._queue_items.items()
            if message_id in self._active_downloads
        )

        parts = [self.tr("{finished}/{total} done").format(finished=finished, total=total)]
        if queued:
            parts.append(self.tr("{count} queued").format(count=queued))
        if active:
            parts.append(self.tr("{count} downloading").format(count=active))
        if failed:
            parts.append(self.tr("{count} failed").format(count=failed))
        if known_total_bytes:
            percent = int(current_bytes * 100 / known_total_bytes)
            parts.append(self.tr("{percent}% overall").format(percent=percent))
        if speed_bps > 0:
            parts.append(self.tr("{speed}/s").format(speed=_human_size(int(speed_bps))))

        summary = " · ".join(parts)
        self.queue_summary_label.setText(summary)
        self.queue_summary_label.setVisible(True)

        # Mirrored into MainWindow's own bottom progress bar (#27) -- the
        # same aggregate this label already shows, so the two can never
        # disagree. Byte-accurate when at least one file's size is known
        # (known_total_bytes), falling back to a plain file count
        # otherwise (a file with no reported size, e.g. one still
        # queued behind Telegram not having sent it yet).
        fraction = current_bytes / known_total_bytes if known_total_bytes else finished / total
        self.overall_progress_changed.emit(fraction, summary)

    # --- folder-level actions -------------------------------------------------

    def _has_loose_downloads(self) -> bool:
        """Whether there is anything in the download folder still waiting to
        be sorted -- **asked of the folder, not of `self._downloaded_files`**.

        Both buttons used to gate on that dict, which only ever holds *this*
        dialog session's downloads. Since the folder is now shared across
        sessions, opening the chat on a folder that already held two albums
        left Sort and Record disabled with nothing to explain why -- the same
        "content present but unreachable" failure as the sorting bug itself,
        one layer up in the UI."""
        if self._session_folder is None:
            return False
        return bool(album_sort.loose_audio_files(Path(self._session_folder)))

    def _has_anything_to_record(self) -> bool:
        """Loose files or already-sorted album subfolders -- either is
        recordable, since _on_continue_clicked() sorts before picking."""
        if self._session_folder is None:
            return False
        root = Path(self._session_folder)
        return bool(album_sort.loose_audio_files(root)) or album_sort.has_album_subfolders(root)

    def _update_sort_button(self) -> None:
        """Kept in sync from _on_ready() (so a folder that already holds
        earlier sessions' downloads enables this immediately) and from
        _on_download_started()/_on_download_finished()/_on_download_failed()
        -- reported directly: sorting (or recording, see
        _update_continue_button() below) while a download is still in flight
        can race a file that's only partially written to disk, or sort a
        session that's about to gain one more file the button's own click
        just missed."""
        if self._active_downloads:
            self.sort_btn.setEnabled(False)
            self.sort_btn.setToolTip(self.tr("Wait for the current download(s) to finish first."))
        elif not self._has_loose_downloads():
            self.sort_btn.setEnabled(False)
            self.sort_btn.setToolTip(self.tr("Nothing is waiting to be sorted."))
        else:
            self.sort_btn.setEnabled(True)
            self.sort_btn.setToolTip("")

    def _update_continue_button(self) -> None:
        """Kept in sync from _on_ready() (so the reason is visible from the
        moment the dialog connects, not just after the first download) and
        _on_download_started()/_on_download_finished()/_on_download_failed()
        -- reported as looking permanently disabled with no explanation; a
        disabled button with no tooltip at all reads as broken, not as
        "waiting for something". The adapter-off check stays first even
        though a download in progress would also block proceeding, since
        turning MDRem on is the more fundamental blocker of the two -- it
        doesn't go away just because the current download finishes."""
        if not app_settings.mdrem_enabled():
            self.continue_btn.setEnabled(False)
            self.continue_btn.setToolTip(
                self.tr("Enable the MDRem adapter in Window > Settings to record.")
            )
        elif self._active_downloads:
            self.continue_btn.setEnabled(False)
            self.continue_btn.setToolTip(self.tr("Wait for the current download(s) to finish first."))
        elif not self._has_anything_to_record():
            self.continue_btn.setEnabled(False)
            self.continue_btn.setToolTip(self.tr("Download at least one file first."))
        else:
            self.continue_btn.setEnabled(True)
            self.continue_btn.setToolTip("")

    def _on_continue_clicked(self) -> None:
        if self._session_folder is None:
            return
        session_folder = Path(self._session_folder)
        # Sorting is idempotent and a no-op for a single album (see
        # album_sort._create_folders_and_move), so it's safe to run here
        # unconditionally rather than depending on the user having already
        # clicked "Sort into Album Folders" themselves -- without this, a
        # multi-album session whose files are still flat in the folder would
        # silently be treated by pick_album_folder() below as one album,
        # mixing every downloaded album's tracks into a single recording.
        album_sort.sort_downloads(session_folder, self._downloaded_files, self._message_order)
        folder, ok = pick_album_folder(self, session_folder)
        if not ok:
            return
        self.downloaded_folder = str(folder)
        self.accept()

    def _open_download_folder(self) -> None:
        if self._session_folder is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._session_folder))

    def _sort_downloads(self) -> None:
        if self._session_folder is None:
            return
        root = Path(self._session_folder)
        folders = album_sort.sort_downloads(root, self._downloaded_files, self._message_order)
        if not folders:
            # See app_window._sort_telegram_downloads() for why this branches
            # rather than always claiming "only one album".
            if album_sort.loose_audio_files(root):
                message = self.tr("These tracks all belong to one album -- there is nothing to separate.")
            else:
                message = self.tr("Everything is already sorted into album folders.")
            QMessageBox.information(self, self.tr("Sort into Album Folders"), message)
        else:
            QMessageBox.information(
                self,
                self.tr("Sort into Album Folders"),
                self.tr("Sorted into {count} album folders.").format(count=len(folders)),
            )
        # Whatever just happened changed what is loose in the folder, so the
        # buttons' own preconditions have to be re-read rather than left
        # showing the state from before the click.
        self._update_sort_button()
        self._update_continue_button()

    # --- photo previews / translation ---------------------------------------

    def _on_photo_loaded(self, message_id: int, data: bytes) -> None:
        widget = self._message_widgets.get(message_id)
        if widget is not None:
            widget.set_photo(data)

    def _on_translation_loaded(self, message_id: int, text: str) -> None:
        widget = self._message_widgets.get(message_id)
        if widget is not None:
            widget.set_translation(text)

    # --- hide/show -----------------------------------------------------

    def request_stop(self) -> None:
        """What MainWindow's own Stop button calls -- closes the chat,
        cancelling the worker gracefully via reject() (see _close_with()
        below), same as clicking Close by hand."""
        self.reject()

    def request_show(self) -> None:
        """What the progress bar's "Show recording window" button calls."""
        self.show_requested.emit()

    def _on_hide_clicked(self) -> None:
        hide_for_background(self)

    # --- shutdown -----------------------------------------------------
    #
    # Unlike TelegramLoginDialog (a one-shot exchange whose worker finishes
    # on its own), this worker keeps running for as long as the dialog is
    # open -- so *both* accept() (via "Record Downloaded Albums...") and
    # reject() need the same "never call worker.wait() on the GUI thread"
    # graceful shutdown, not just reject().

    def accept(self) -> None:
        self._close_with(super().accept)

    def reject(self) -> None:
        self._close_with(super().reject)

    def _close_with(self, finish) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._closing = True
            self._pending_finish = finish
            self._worker.cancel()
            self.status_label.setText(self.tr("Disconnecting..."))
            return
        finish()

    def _on_worker_finished(self) -> None:
        self._worker = None
        # Before the closing branch below, not after -- same ordering
        # CdRipDialog's own _on_worker_finished uses, and for the same
        # reason: if this dialog is hidden right now, MainWindow's
        # running_changed(False) handler asks for it back (see
        # app_window._on_recording_running_changed()'s own "stranded
        # hidden dialog" fix), and that has to happen before finish()
        # potentially closes it for good below.
        self.running_changed.emit(False)
        if self._closing and self._pending_finish is not None:
            self._pending_finish()

    def closeEvent(self, event) -> None:
        if self._worker is not None and self._worker.isRunning():
            self.reject()
            event.ignore()
            return
        super().closeEvent(event)
