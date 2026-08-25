"""TelegramChatDialog: the generic mini-chat with the user's own bot.

Same two-layer coverage as test_telegram_login_dialog.py: a fast
synchronous check that reject()/accept() never block the GUI thread on a
busy worker, and slower end-to-end tests that start a real _ChatWorker
QThread against the fake Telethon-shaped client from test_telegram_bot.py
and pump the Qt event loop until its signals arrive.

**Every test that calls start_connecting() must stop the worker again
before the test function returns.** Unlike _LoginWorker (a one-shot
exchange that finishes on its own), _ChatWorker loops forever until
cancel()'d -- and Qt aborts the whole process with no Python traceback if
a QThread's C++ object is destroyed while still running. This is exactly
what produced a silent, output-less crash while first writing these tests:
TelegramChatDialog used to start a real worker straight from __init__, and
a test that substituted a fake `_worker` to check reject()/accept()'s
own logic left the *original*, real one (parented to the dialog, so kept
alive by Qt regardless of the Python attribute reassignment) running in
the background with no mocked client -- trying to connect to real
Telegram servers, then eventually getting garbage collected mid-suite
while still "running" and aborting the whole process with zero output.
Two fixes came out of that: `start_connecting()` is a separate, explicit
call (so plain construction is always inert -- see its own docstring),
and `_shutdown()` below is mandatory bookkeeping in every test that does
call it.
"""

from __future__ import annotations

import asyncio
import base64
import time
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QDialog

from mdtools import app_settings
from mdtools.panels import telegram_chat_dialog as module
from mdtools.panels.telegram_chat_dialog import TelegramChatDialog
from tests.test_telegram_bot import FakeButton, FakeEvent, FakeFile, FakeMessage, FakeTelethonClient


def _pump_until(condition, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            pytest.fail("timed out waiting for the worker thread")
        QApplication.processEvents()
        time.sleep(0.01)


def _use_fake_client(monkeypatch, fake: FakeTelethonClient) -> None:
    monkeypatch.setattr(module.telegram_bot, "create_telethon_client", lambda *a, **k: fake)


def _use_fake_translate(monkeypatch) -> None:
    """Every incoming message with text triggers a fire-and-forget
    translation attempt (see _ChatWorker._load_translation) -- without this,
    every end-to-end test in this file would make a real HTTP call to
    MyMemory as an unwanted side effect. Raising TranslationError is the
    fastest, most inert stand-in: _load_translation already treats that as
    "nothing to show", the same as a real network failure would."""

    def _raise(text: str, target_language: str) -> str:
        raise module.mdtools_translate.TranslationError("mocked in tests")

    monkeypatch.setattr(module.mdtools_translate, "translate", _raise)


def _dialog(monkeypatch, tmp_path, fake: FakeTelethonClient | None = None, **kwargs) -> TelegramChatDialog:
    """Always mocks the client factory first, then starts connecting --
    plain construction alone is inert (see TelegramChatDialog.start_connecting's
    own docstring), so every test that wants the real worker running has to
    ask for it explicitly, with a fake client already in place."""
    _use_fake_client(monkeypatch, fake or FakeTelethonClient(authorized=False))
    _use_fake_translate(monkeypatch)
    dialog = TelegramChatDialog("123456", "hash", "@my_bot", tmp_path, **kwargs)
    # A child QLabel's isVisible() reflects its own explicit flag *and*
    # every ancestor's -- without this, translation_label/photo_label would
    # report not-visible forever regardless of set_translation()/set_photo()
    # ever running, since the dialog itself was never shown. offscreen mode
    # (QT_QPA_PLATFORM=offscreen) makes this safe/cheap in tests -- no real
    # window is created.
    dialog.show()
    dialog.start_connecting()
    return dialog


# A real, minimal 1x1 transparent PNG -- QPixmap.loadFromData() needs actual
# valid image bytes to succeed, unlike the placeholder bytes FakeMessage
# defaults to, which are only good enough for the download-to-disk tests.
_TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def _deliver(dialog: TelegramChatDialog, fake: FakeTelethonClient, message: FakeMessage, edit: bool = False) -> None:
    """Simulates the bot sending (or, with edit=True, editing) `message` --
    schedules the registered event handler onto the worker's own event
    loop, exactly as Telethon would from a different thread than the one
    calling this.

    `edit=True` waits on the widget's *text* changing rather than on
    `message.id in dialog._message_widgets`, since an edit reuses an id
    already in that dict from the original message -- the plain "id is
    present" check would return true immediately, before the edit has
    actually been processed, which is exactly the trap the first version
    of the edit tests fell into.

    A file-bearing message never gets a transcript widget at all -- it
    goes to `dialog._queue_items` instead (see the module docstring's
    "file attachments render only in the download queue" note), so the
    wait condition has to look there for one."""
    callback, _event_filter = fake.handlers[0]

    async def _fire() -> None:
        await callback(FakeEvent(message))

    loop = dialog._worker._loop
    loop.call_soon_threadsafe(lambda: asyncio.ensure_future(_fire(), loop=loop))
    has_file_name = message.file is not None and message.file.name is not None
    if edit:
        _pump_until(lambda: message.raw_text in dialog._message_widgets[message.id].text_label.text())
    elif has_file_name:
        # A photo also carries a `file` (see FakeFile(None, size) in the
        # photo tests) but is *not* routed to the queue -- only a message
        # whose File actually has a name is (ChatMessage.file_name is what
        # the real dialog code branches on; a photo's File.name is always
        # None, per ChatMessage.is_photo's own docstring).
        _pump_until(lambda: message.id in dialog._queue_items)
    else:
        _pump_until(lambda: message.id in dialog._message_widgets)


def _shutdown(dialog: TelegramChatDialog) -> None:
    """Stops whatever real worker is still attached and waits for the
    thread to actually exit -- see the module docstring for why this is
    mandatory, not just tidy, for every test in this file."""
    if dialog._worker is not None:
        dialog.reject()
        _pump_until(lambda: dialog._worker is None)


class _BusyWorker:
    """A worker-shaped fake that is always "running" -- used to prove
    reject()/accept() never call .wait() on the GUI thread, with no real
    thread involved."""

    def __init__(self):
        self.cancelled = False

    def isRunning(self):
        return True

    def cancel(self):
        self.cancelled = True

    def wait(self, *a):
        pytest.fail("must not wait on the worker from the GUI thread")


# --- plain construction must stay inert ---------------------------------


def test_enter_in_the_message_field_sends_rather_than_triggering_record(qt_app, tmp_path):
    """Reported directly: pressing Enter while typing a chat message opened
    the "Choose Album" picker instead of sending the message. Qt falls
    back to the first enabled AcceptRole button in the QDialogButtonBox
    (Record Downloaded Albums...) once focus leaves whatever held it
    initially, unless Send is explicitly made the dialog's default and the
    others are excluded from autoDefault."""
    dialog = TelegramChatDialog("123456", "hash", "@my_bot", tmp_path)
    try:
        assert dialog.send_btn.isDefault()
        assert dialog.continue_btn.autoDefault() is False
        assert dialog.close_btn.autoDefault() is False
    finally:
        dialog.close()


def test_plain_construction_starts_no_worker(qt_app, tmp_path):
    """The regression this whole file is built around -- see the module
    docstring. Deliberately does *not* mock the client factory: if this
    ever regresses back to auto-starting from __init__, that absence is
    exactly what would make the real worker try to reach actual Telegram
    servers."""
    dialog = TelegramChatDialog("123456", "hash", "@my_bot", tmp_path)
    try:
        assert dialog._worker is None
    finally:
        dialog.close()


# --- reject()/accept() must never block on a busy worker ---------------------


def test_stopping_does_not_block_on_the_worker(qt_app, monkeypatch, tmp_path):
    dialog = _dialog(monkeypatch, tmp_path)
    # Let the real (fake-client-backed, not-authorized) worker finish on
    # its own before substituting the fake below -- otherwise it is
    # orphaned mid-flight, and Qt aborts the process once it is GC'd while
    # still running.
    _pump_until(lambda: dialog._worker is None)

    worker = _BusyWorker()
    dialog._worker = worker
    dialog.show()

    dialog.reject()

    assert worker.cancelled
    assert dialog._closing
    assert not dialog.isHidden(), "stays open until the worker actually finishes"

    dialog._worker = None
    dialog._on_worker_finished()
    assert dialog.isHidden()


def test_accept_also_waits_for_the_worker_to_stop_before_closing(qt_app, monkeypatch, tmp_path):
    """"Record Downloaded Albums..." calls accept(), which needs the exact
    same graceful shutdown reject() gets -- this worker, unlike the login
    one, keeps running for as long as the dialog is open."""
    dialog = _dialog(monkeypatch, tmp_path)
    _pump_until(lambda: dialog._worker is None)

    worker = _BusyWorker()
    dialog._worker = worker
    dialog.show()

    dialog.accept()

    assert worker.cancelled
    assert not dialog.isHidden()

    dialog._worker = None
    dialog._on_worker_finished()
    assert dialog.isHidden()
    assert dialog.result() == QDialog.DialogCode.Accepted


# --- end to end, a real _ChatWorker QThread -----------------------------------


def test_end_to_end_connects_and_shows_the_bots_name(qt_app, monkeypatch, tmp_path):
    fake = FakeTelethonClient(authorized=True)
    dialog = _dialog(monkeypatch, tmp_path, fake)
    try:
        _pump_until(lambda: dialog._session_folder is not None)

        assert "my_bot" in dialog.status_label.text()
        assert dialog.message_edit.isEnabled()
        assert Path(dialog._session_folder).is_dir()
    finally:
        _shutdown(dialog)


def test_downloads_land_directly_in_the_configured_folder_not_a_per_session_subfolder(
    qt_app, monkeypatch, tmp_path
):
    """Regression: reported directly -- a fresh, timestamped subfolder per
    chat session scattered downloads across a new folder every time the
    dialog was reopened. Everything now goes straight into the one
    configured download folder, so a later "Sort into Album Folders" (or
    the standalone Experimental action) sees everything accumulated so
    far, not just the current session's files."""
    fake = FakeTelethonClient(authorized=True)
    dialog = _dialog(monkeypatch, tmp_path, fake)
    try:
        _pump_until(lambda: dialog._session_folder is not None)
        assert dialog._session_folder == str(tmp_path)
    finally:
        _shutdown(dialog)

    # A second, separate "session" (a new dialog instance) must land in the
    # exact same folder, not a different one of its own.
    fake2 = FakeTelethonClient(authorized=True)
    dialog2 = _dialog(monkeypatch, tmp_path, fake2)
    try:
        _pump_until(lambda: dialog2._session_folder is not None)
        assert dialog2._session_folder == str(tmp_path)
    finally:
        _shutdown(dialog2)


def test_end_to_end_not_authorized_offers_a_sign_in_button(qt_app, monkeypatch, tmp_path):
    fake = FakeTelethonClient(authorized=False)
    dialog = _dialog(monkeypatch, tmp_path, fake)
    try:
        _pump_until(lambda: "Not signed in" in dialog.status_label.text())
        assert dialog.message_edit.isEnabled() is False
    finally:
        _shutdown(dialog)


def test_end_to_end_an_incoming_message_with_buttons_renders_and_clicking_reaches_the_bot(
    qt_app, monkeypatch, tmp_path
):
    fake = FakeTelethonClient(authorized=True)
    dialog = _dialog(monkeypatch, tmp_path, fake)
    try:
        _pump_until(lambda: dialog._session_folder is not None)

        raw = FakeMessage(text="pick one", buttons=[[FakeButton("Album A"), FakeButton("Album B")]])
        _deliver(dialog, fake, raw)

        widget = dialog._message_widgets[raw.id]
        widget.button_clicked.emit(raw.id, 0, 1)

        _pump_until(lambda: raw.clicked == [(0, 1)])
    finally:
        _shutdown(dialog)


def test_end_to_end_sending_a_message_reaches_the_bot(qt_app, monkeypatch, tmp_path):
    fake = FakeTelethonClient(authorized=True)
    dialog = _dialog(monkeypatch, tmp_path, fake)
    try:
        _pump_until(lambda: dialog._session_folder is not None)

        dialog.message_edit.setText("hello there")
        dialog._on_send()

        _pump_until(lambda: len(fake.sent_messages) == 1)
        assert fake.sent_messages[0].raw_text == "hello there"
        assert dialog.message_edit.text() == ""
    finally:
        _shutdown(dialog)


def test_end_to_end_downloading_a_file_enables_continue_when_mdrem_is_on(qt_app, monkeypatch, tmp_path):
    """A file now downloads on its own -- no _on_download_requested() call
    needed, unlike before auto-download existed."""
    app_settings.set_mdrem_enabled(True)
    fake = FakeTelethonClient(authorized=True)
    dialog = _dialog(monkeypatch, tmp_path, fake)
    try:
        _pump_until(lambda: dialog._session_folder is not None)
        assert dialog.continue_btn.isEnabled() is False

        raw = FakeMessage(text="here", file=FakeFile("Unleashed.flac", 100))
        _deliver(dialog, fake, raw)
        _pump_until(lambda: dialog.continue_btn.isEnabled())

        assert raw.download_target == dialog._session_folder
        assert dialog._downloaded_files[raw.id] == Path(dialog._session_folder) / "Unleashed.flac"

        dialog._on_continue_clicked()
        assert dialog.downloaded_folder == dialog._session_folder
    finally:
        _shutdown(dialog)


def test_continue_stays_disabled_without_mdrem_even_after_a_download(qt_app, monkeypatch, tmp_path):
    app_settings.set_mdrem_enabled(False)
    fake = FakeTelethonClient(authorized=True)
    dialog = _dialog(monkeypatch, tmp_path, fake)
    try:
        _pump_until(lambda: dialog._session_folder is not None)
        assert dialog.continue_btn.toolTip() != ""

        raw = FakeMessage(text="here", file=FakeFile("Unleashed.flac", 100))
        _deliver(dialog, fake, raw)
        _pump_until(lambda: raw.id in dialog._downloaded_files)

        assert dialog.continue_btn.isEnabled() is False
    finally:
        _shutdown(dialog)


# --- inline photo previews and translation ------------------------------------


def test_end_to_end_a_photo_message_renders_inline_automatically(qt_app, monkeypatch, tmp_path):
    """The actual bug report this fixes: a bot's photo (e.g. album art)
    used to render as nothing at all -- no filename branch fires for a
    photo, and there was no image-preview branch either."""
    fake = FakeTelethonClient(authorized=True)
    dialog = _dialog(monkeypatch, tmp_path, fake)
    try:
        _pump_until(lambda: dialog._session_folder is not None)

        raw = FakeMessage(text="cover art", photo=True, file=FakeFile(None, len(_TINY_PNG)), content=_TINY_PNG)
        _deliver(dialog, fake, raw)

        widget = dialog._message_widgets[raw.id]
        assert widget.photo_label is not None

        _pump_until(lambda: not widget.photo_label.pixmap().isNull())
        assert raw.download_target is bytes
    finally:
        _shutdown(dialog)


def test_end_to_end_a_bad_image_shows_a_fallback_message(qt_app, monkeypatch, tmp_path):
    fake = FakeTelethonClient(authorized=True)
    dialog = _dialog(monkeypatch, tmp_path, fake)
    try:
        _pump_until(lambda: dialog._session_folder is not None)

        raw = FakeMessage(photo=True, file=FakeFile(None, 5), content=b"not-an-image")
        _deliver(dialog, fake, raw)

        widget = dialog._message_widgets[raw.id]
        _pump_until(lambda: widget.photo_label.text() != "Loading image...")
        assert "Could not display image" in widget.photo_label.text()
    finally:
        _shutdown(dialog)


# --- saving a photo out of the transcript (#8) ------------------------------


def test_clicking_a_loaded_photo_saves_it_to_the_artwork_folder(qt_app, monkeypatch, tmp_path):
    """The bytes behind the inline preview are already on the widget by the
    time it can be clicked at all -- saving must not re-download anything,
    only write out what's already there."""
    artwork_dir = tmp_path / "artwork"

    def _fake_artwork_dir():
        # Mirrors the real user_paths.artwork_dir()'s own contract: it
        # creates the folder on demand, the caller never has to.
        artwork_dir.mkdir(parents=True, exist_ok=True)
        return artwork_dir

    monkeypatch.setattr(module.user_paths, "artwork_dir", _fake_artwork_dir)
    fake = FakeTelethonClient(authorized=True)
    dialog = _dialog(monkeypatch, tmp_path, fake)
    try:
        _pump_until(lambda: dialog._session_folder is not None)

        raw = FakeMessage(photo=True, file=FakeFile(None, len(_TINY_PNG)), content=_TINY_PNG)
        _deliver(dialog, fake, raw)
        widget = dialog._message_widgets[raw.id]
        _pump_until(lambda: not widget.photo_label.pixmap().isNull())

        widget.photo_label.clicked.emit()

        saved = list(artwork_dir.iterdir())
        assert len(saved) == 1
        assert saved[0].read_bytes() == _TINY_PNG
        assert saved[0].suffix == ".png"
        assert str(saved[0]) in dialog.status_label.text()
    finally:
        _shutdown(dialog)


def test_clicking_a_photo_that_has_not_finished_loading_does_nothing(qt_app, monkeypatch, tmp_path):
    """Deliberately built by hand rather than through the full async
    worker + _deliver() pipeline -- _deliver()'s own pump loop drains
    Qt's whole pending event queue on every iteration, so by the time it
    returns, a fake (near-instant) photo download has usually *already*
    arrived too, making the "not loaded yet" moment impossible to land on
    reliably through that path. A bare widget with no set_photo() call at
    all is the actual state under test: still just "Loading image...",
    with nothing yet on self._photo_bytes."""
    artwork_dir = tmp_path / "artwork"
    monkeypatch.setattr(module.user_paths, "artwork_dir", lambda: artwork_dir)
    dialog = TelegramChatDialog("123456", "hash", "@my_bot", tmp_path)
    message = module.telegram_bot.ChatMessage(id=1, outgoing=False, text="", is_photo=True)
    widget = module._MessageWidget(message, "my_bot")
    dialog._message_widgets[message.id] = widget
    assert widget._photo_bytes is None

    dialog._on_photo_save_requested(message.id)

    assert not artwork_dir.exists()


def test_a_bad_image_cannot_be_saved_since_nothing_was_ever_kept(qt_app, monkeypatch, tmp_path):
    artwork_dir = tmp_path / "artwork"

    def _fake_artwork_dir():
        # Mirrors the real user_paths.artwork_dir()'s own contract: it
        # creates the folder on demand, the caller never has to.
        artwork_dir.mkdir(parents=True, exist_ok=True)
        return artwork_dir

    monkeypatch.setattr(module.user_paths, "artwork_dir", _fake_artwork_dir)
    fake = FakeTelethonClient(authorized=True)
    dialog = _dialog(monkeypatch, tmp_path, fake)
    try:
        _pump_until(lambda: dialog._session_folder is not None)

        raw = FakeMessage(photo=True, file=FakeFile(None, 5), content=b"not-an-image")
        _deliver(dialog, fake, raw)
        widget = dialog._message_widgets[raw.id]
        _pump_until(lambda: widget.photo_label.text() != "Loading image...")

        dialog._on_photo_save_requested(raw.id)

        assert not artwork_dir.exists()
    finally:
        _shutdown(dialog)


# --- the download queue's aggregate summary (#7) ----------------------------


def test_queue_summary_is_hidden_with_no_files(qt_app, tmp_path):
    dialog = TelegramChatDialog("123456", "hash", "@my_bot", tmp_path)

    assert dialog.queue_summary_label.isVisible() is False


def test_queue_summary_reports_counts_and_overall_progress(qt_app, tmp_path):
    """Built directly against the dialog's own handlers rather than through
    the full async worker + _deliver() pipeline: this suite's fake download
    reports progress in one single (size, size) callback, which makes
    landing on an in-between "still downloading" moment through the real
    pipeline just as unreliable to time as the equivalent photo-preview
    race noted above -- calling the signal handlers directly gives full
    control over which state each of several files is in at once."""
    dialog = TelegramChatDialog("123456", "hash", "@my_bot", tmp_path)
    dialog.show()  # isVisible() reflects the whole ancestor chain, not just its own flag

    def _msg(message_id: int, size: int) -> module.telegram_bot.ChatMessage:
        return module.telegram_bot.ChatMessage(
            id=message_id, outgoing=False, text="", file_name=f"{message_id}.flac", file_size=size
        )

    finished_msg = _msg(1, 100)
    active_msg = _msg(2, 200)
    queued_msg = _msg(3, 300)
    failed_msg = _msg(4, 400)
    for msg in (finished_msg, active_msg, queued_msg, failed_msg):
        dialog._on_file_message(msg, is_new=True)

    dialog._on_download_started(finished_msg.id)
    dialog._on_download_finished(finished_msg.id, str(tmp_path / "1.flac"))
    dialog._on_download_started(active_msg.id)
    dialog._on_download_progress(active_msg.id, 100, 200)  # half-way
    dialog._on_download_started(failed_msg.id)
    dialog._on_download_failed(failed_msg.id, "network gone")
    # queued_msg is left untouched -- still just sitting in the queue.

    assert dialog.queue_summary_label.isVisible() is True
    text = dialog.queue_summary_label.text()
    assert "1/4 done" in text
    assert "1 queued" in text
    assert "1 downloading" in text
    assert "1 failed" in text
    # known totals: 100 (finished) + 200 (active) + 300 (queued, seeded at
    # 0/size the moment it was queued) + 400 (failed, seeded then never
    # progressed) = 1000; current: 100 + 100 + 0 + 0 = 200 -> 20%.
    assert "20% overall" in text


def test_a_retry_resets_that_files_own_progress_and_clears_its_failed_state(qt_app, tmp_path):
    dialog = TelegramChatDialog("123456", "hash", "@my_bot", tmp_path)
    msg = module.telegram_bot.ChatMessage(id=1, outgoing=False, text="", file_name="a.flac", file_size=100)
    dialog._on_file_message(msg, is_new=True)

    dialog._on_download_started(msg.id)
    dialog._on_download_progress(msg.id, 80, 100)
    dialog._on_download_failed(msg.id, "network gone")
    assert "1 failed" in dialog.queue_summary_label.text()

    dialog._on_download_started(msg.id)  # the retry

    assert "1 failed" not in dialog.queue_summary_label.text()
    assert "1 downloading" in dialog.queue_summary_label.text()
    assert dialog._download_progress[msg.id] == (0, 100)


def test_end_to_end_downloading_updates_the_queue_summary(qt_app, monkeypatch, tmp_path):
    fake = FakeTelethonClient(authorized=True)
    dialog = _dialog(monkeypatch, tmp_path, fake)
    try:
        _pump_until(lambda: dialog._session_folder is not None)

        raw = FakeMessage(text="here", file=FakeFile("Unleashed.flac", 100))
        _deliver(dialog, fake, raw)
        _pump_until(lambda: raw.id in dialog._downloaded_files)

        assert dialog.queue_summary_label.isVisible() is True
        assert "1/1 done" in dialog.queue_summary_label.text()
        assert "100% overall" in dialog.queue_summary_label.text()
    finally:
        _shutdown(dialog)


def test_end_to_end_an_incoming_message_gets_translated(qt_app, monkeypatch, tmp_path):
    fake = FakeTelethonClient(authorized=True)
    dialog = _dialog(monkeypatch, tmp_path, fake)
    try:
        _pump_until(lambda: dialog._session_folder is not None)

        # Override the blanket "always fails" stand-in _dialog() installed,
        # with one that actually returns something -- proving the
        # translated text reaches the widget, not just that failure is
        # tolerated (already covered by every other end-to-end test, which
        # all send text through the same always-failing stand-in).
        monkeypatch.setattr(
            module.mdtools_translate, "translate", lambda text, target_language: "Przetłumaczony tekst"
        )

        raw = FakeMessage(text="Here are your search results")
        _deliver(dialog, fake, raw)

        widget = dialog._message_widgets[raw.id]
        _pump_until(lambda: widget.translation_label.isVisible())
        assert "Przetłumaczony tekst" in widget.translation_label.text()
    finally:
        _shutdown(dialog)


def test_end_to_end_a_translation_identical_to_the_original_is_not_shown(qt_app, monkeypatch, tmp_path):
    fake = FakeTelethonClient(authorized=True)
    dialog = _dialog(monkeypatch, tmp_path, fake)
    try:
        _pump_until(lambda: dialog._session_folder is not None)
        monkeypatch.setattr(
            module.mdtools_translate, "translate", lambda text, target_language: text
        )

        raw = FakeMessage(text="Already in the target language")
        _deliver(dialog, fake, raw)

        widget = dialog._message_widgets[raw.id]
        # Give the fire-and-forget translation task a moment to run and
        # decide there is nothing worth showing -- there is no positive
        # signal to pump for here, so this pumps the event loop briefly and
        # then asserts the negative.
        for _ in range(20):
            QApplication.processEvents()
            time.sleep(0.01)
        assert widget.translation_label.isVisible() is False
    finally:
        _shutdown(dialog)


def test_outgoing_messages_are_never_translated(qt_app, monkeypatch, tmp_path):
    """Translation is for reading the bot, not re-reading what we just
    typed -- _MessageWidget doesn't even build a translation_label for an
    outgoing message."""
    fake = FakeTelethonClient(authorized=True)
    dialog = _dialog(monkeypatch, tmp_path, fake)
    try:
        _pump_until(lambda: dialog._session_folder is not None)

        dialog.message_edit.setText("hello there")
        dialog._on_send()
        _pump_until(lambda: len(fake.sent_messages) == 1)
        _pump_until(lambda: fake.sent_messages[0].id in dialog._message_widgets)

        widget = dialog._message_widgets[fake.sent_messages[0].id]
        assert widget.translation_label is None
    finally:
        _shutdown(dialog)


# --- auto-scroll ---------------------------------------------------------


def test_the_transcript_auto_scrolls_to_the_newest_message(qt_app, monkeypatch, tmp_path):
    """Real report: the transcript did not follow new messages -- a
    QTimer.singleShot(0, ...) scroll-to-bottom call could fire before Qt
    had finished recomputing the transcript's size for the just-added
    widget. Fixed by scrolling from QScrollBar.rangeChanged instead, which
    only ever fires once the range (and so the "bottom") is actually
    correct. A small dialog height forces real overflow -- a single short
    message might not overflow the viewport at all, which would make
    value()==maximum() true trivially, proving nothing."""
    fake = FakeTelethonClient(authorized=True)
    dialog = _dialog(monkeypatch, tmp_path, fake)
    try:
        dialog.resize(400, 160)
        _pump_until(lambda: dialog._session_folder is not None)

        bar = dialog.scroll_area.verticalScrollBar()
        for i in range(20):
            _deliver(dialog, fake, FakeMessage(text=f"message number {i}"))

        assert bar.maximum() > 0, "the transcript must actually overflow for this test to mean anything"
        assert bar.value() == bar.maximum()
    finally:
        _shutdown(dialog)


# --- edited messages (a bot "menu" that morphs in place) ----------------------


def test_end_to_end_an_edited_message_replaces_its_widget_in_place(qt_app, monkeypatch, tmp_path):
    """Real report: a bot that edits its own message (a common "menu"
    pattern) left the dialog showing the stale pre-edit buttons forever --
    it only ever listened for brand new messages. One widget per message
    id, updated in place on an edit, not a second one appended."""
    fake = FakeTelethonClient(authorized=True)
    dialog = _dialog(monkeypatch, tmp_path, fake)
    try:
        _pump_until(lambda: dialog._session_folder is not None)

        original = FakeMessage(text="pick an album", buttons=[[FakeButton("Old Album")]])
        _deliver(dialog, fake, original)
        assert len(dialog._message_widgets) == 1

        edited = FakeMessage(text="pick a different album", buttons=[[FakeButton("New Album")]])
        edited.id = original.id
        _deliver(dialog, fake, edited, edit=True)

        assert len(dialog._message_widgets) == 1, "an edit must replace, not add, a widget"
        widget = dialog._message_widgets[original.id]
        assert "pick a different album" in widget.text_label.text()

        # And the freshly rendered button reaches the *edited* raw message,
        # not the stale pre-edit one -- proving the click path picked up
        # the overwritten cache entry, not just that the label changed.
        widget.button_clicked.emit(original.id, 0, 0)
        _pump_until(lambda: edited.clicked == [(0, 0)])
        assert original.clicked == []
    finally:
        _shutdown(dialog)


def test_end_to_end_an_edited_message_stays_in_its_original_position(qt_app, monkeypatch, tmp_path):
    """Editing an earlier message must not reorder the conversation -- it
    should update where it already is, not jump to the bottom as though it
    were a brand new message."""
    fake = FakeTelethonClient(authorized=True)
    dialog = _dialog(monkeypatch, tmp_path, fake)
    try:
        _pump_until(lambda: dialog._session_folder is not None)

        first = FakeMessage(text="first message", buttons=[[FakeButton("A")]])
        _deliver(dialog, fake, first)
        second = FakeMessage(text="second message")
        _deliver(dialog, fake, second)

        edited_first = FakeMessage(text="first message, edited", buttons=[[FakeButton("A2")]])
        edited_first.id = first.id
        _deliver(dialog, fake, edited_first, edit=True)

        first_index = dialog._transcript_layout.indexOf(dialog._message_widgets[first.id])
        second_index = dialog._transcript_layout.indexOf(dialog._message_widgets[second.id])
        assert first_index < second_index
    finally:
        _shutdown(dialog)


# --- quick command buttons ------------------------------------------------


def test_quick_command_buttons_start_disabled_and_enable_once_connected(qt_app, monkeypatch, tmp_path):
    fake = FakeTelethonClient(authorized=True)
    dialog = _dialog(monkeypatch, tmp_path, fake)
    try:
        assert len(dialog.quick_command_buttons) == 2
        _pump_until(lambda: dialog._session_folder is not None)
        assert all(button.isEnabled() for button in dialog.quick_command_buttons)
    finally:
        _shutdown(dialog)


def test_clicking_a_quick_command_button_sends_it_like_typed_text(qt_app, monkeypatch, tmp_path):
    fake = FakeTelethonClient(authorized=True)
    dialog = _dialog(monkeypatch, tmp_path, fake)
    try:
        _pump_until(lambda: dialog._session_folder is not None)

        start_button = next(b for b in dialog.quick_command_buttons if b.text() == "/start")
        start_button.click()

        _pump_until(lambda: len(fake.sent_messages) == 1)
        assert fake.sent_messages[0].raw_text == "/start"
    finally:
        _shutdown(dialog)


# --- auto-download ---------------------------------------------------------


def test_a_file_message_downloads_with_no_click_needed(qt_app, monkeypatch, tmp_path):
    """Real report: a file used to just sit there with a Download button
    until clicked. It now starts on its own, and never gets a transcript
    row at all -- only a row in the download queue on the right."""
    fake = FakeTelethonClient(authorized=True)
    dialog = _dialog(monkeypatch, tmp_path, fake)
    try:
        _pump_until(lambda: dialog._session_folder is not None)

        raw = FakeMessage(text="here", file=FakeFile("Unleashed.flac", 100))
        _deliver(dialog, fake, raw)

        assert raw.id not in dialog._message_widgets
        item = dialog._queue_items[raw.id]
        assert item.retry_btn.isVisible() is False

        _pump_until(lambda: raw.id in dialog._downloaded_files)
        assert raw.download_target == dialog._session_folder
        assert item.status_label.text() == "Saved"
    finally:
        _shutdown(dialog)


def test_a_failed_auto_download_shows_a_retry_button(qt_app, monkeypatch, tmp_path):
    fake = FakeTelethonClient(authorized=True)
    dialog = _dialog(monkeypatch, tmp_path, fake)
    try:
        _pump_until(lambda: dialog._session_folder is not None)

        raw = FakeMessage(text="here", file=FakeFile("Unleashed.flac", 100))

        async def _broken_download(file, progress_callback=None):
            raise RuntimeError("network gone")

        raw.download_media = _broken_download
        _deliver(dialog, fake, raw)

        item = dialog._queue_items[raw.id]
        _pump_until(lambda: item.retry_btn.isVisible())
        assert "Failed" in item.status_label.text()
    finally:
        _shutdown(dialog)


def test_retrying_a_failed_download_reaches_the_worker(qt_app, monkeypatch, tmp_path):
    fake = FakeTelethonClient(authorized=True)
    dialog = _dialog(monkeypatch, tmp_path, fake)
    try:
        _pump_until(lambda: dialog._session_folder is not None)

        raw = FakeMessage(text="here", file=FakeFile("Unleashed.flac", 100))
        calls = {"n": 0}
        real_download = raw.download_media

        async def _fail_once(file, progress_callback=None):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("network gone")
            return await real_download(file, progress_callback)

        raw.download_media = _fail_once
        _deliver(dialog, fake, raw)

        item = dialog._queue_items[raw.id]
        _pump_until(lambda: item.retry_btn.isVisible())

        item.retry_btn.click()
        _pump_until(lambda: raw.id in dialog._downloaded_files)
        assert calls["n"] == 2
    finally:
        _shutdown(dialog)


def test_the_queue_panel_caps_concurrent_downloads(qt_app, monkeypatch, tmp_path):
    """_MAX_CONCURRENT_DOWNLOADS files download at once at most -- an album
    arriving as a burst of file messages used to start every one of them
    immediately with no limit at all."""
    fake = FakeTelethonClient(authorized=True)
    dialog = _dialog(monkeypatch, tmp_path, fake)
    try:
        _pump_until(lambda: dialog._session_folder is not None)

        # Each download blocks on its own asyncio.Event until released, so
        # however many actually started can be observed directly rather
        # than inferred from timing.
        started: list[int] = []
        events: dict[int, asyncio.Event] = {}
        raws = [FakeMessage(text=f"track {n}", file=FakeFile(f"{n}.flac", 10)) for n in range(5)]
        for raw in raws:
            events[raw.id] = asyncio.Event()

            async def _blocking_download(file, progress_callback=None, _raw=raw):
                started.append(_raw.id)
                await events[_raw.id].wait()
                return str(Path(file) / _raw.file.name)

            raw.download_media = _blocking_download

        for raw in raws:
            _deliver(dialog, fake, raw)  # only waits for the queue row, not for the download to finish

        _pump_until(lambda: len(started) == module._MAX_CONCURRENT_DOWNLOADS)
        # Give the remaining, still-queued messages a brief window in which
        # a bug (no cap at all) would have let them start too.
        for _ in range(20):
            QApplication.processEvents()
            time.sleep(0.01)
        assert len(started) == module._MAX_CONCURRENT_DOWNLOADS

        # Release exactly one -- exactly one more should now be free to start.
        loop = dialog._worker._loop
        loop.call_soon_threadsafe(events[started[0]].set)
        _pump_until(lambda: len(started) == module._MAX_CONCURRENT_DOWNLOADS + 1)

        # Release everything still outstanding so the worker can shut down
        # cleanly.
        for raw in raws:
            loop.call_soon_threadsafe(events[raw.id].set)
        _pump_until(lambda: len(dialog._downloaded_files) == len(raws))
    finally:
        _shutdown(dialog)


def test_sort_and_continue_buttons_disabled_while_a_download_is_active(qt_app, monkeypatch, tmp_path):
    """Reported directly: sorting or recording while a file is still
    downloading can act on a folder that's about to change out from under
    it -- both buttons must stay disabled for as long as anything is in
    the queue's "downloading" state, even if an earlier file already
    finished and would otherwise have made them usable."""
    app_settings.set_mdrem_enabled(True)
    fake = FakeTelethonClient(authorized=True)
    dialog = _dialog(monkeypatch, tmp_path, fake)
    try:
        _pump_until(lambda: dialog._session_folder is not None)

        first = FakeMessage(text="track 1", file=FakeFile("a.flac", 10))
        _deliver(dialog, fake, first)
        _pump_until(lambda: first.id in dialog._downloaded_files)
        _pump_until(lambda: dialog.sort_btn.isEnabled() and dialog.continue_btn.isEnabled())

        # A second file whose download blocks until released -- same
        # technique test_the_queue_panel_caps_concurrent_downloads() uses.
        second = FakeMessage(text="track 2", file=FakeFile("b.flac", 10))
        release = asyncio.Event()

        async def _blocking_download(file, progress_callback=None):
            await release.wait()
            return str(Path(file) / second.file.name)

        second.download_media = _blocking_download
        _deliver(dialog, fake, second)

        _pump_until(lambda: second.id in dialog._active_downloads)
        assert dialog.sort_btn.isEnabled() is False
        assert dialog.continue_btn.isEnabled() is False
        assert dialog.sort_btn.toolTip() != ""
        assert dialog.continue_btn.toolTip() != ""

        loop = dialog._worker._loop
        loop.call_soon_threadsafe(release.set)
        _pump_until(lambda: second.id in dialog._downloaded_files)

        assert dialog.sort_btn.isEnabled() is True
        assert dialog.continue_btn.isEnabled() is True
    finally:
        _shutdown(dialog)


def test_sort_and_continue_buttons_re_enable_after_a_failed_download(qt_app, monkeypatch, tmp_path):
    """A download that fails (rather than finishes) must still clear the
    "active" gate -- otherwise a single failure would permanently disable
    both buttons for the rest of the session."""
    app_settings.set_mdrem_enabled(True)
    fake = FakeTelethonClient(authorized=True)
    dialog = _dialog(monkeypatch, tmp_path, fake)
    try:
        _pump_until(lambda: dialog._session_folder is not None)

        first = FakeMessage(text="track 1", file=FakeFile("a.flac", 10))
        _deliver(dialog, fake, first)
        _pump_until(lambda: first.id in dialog._downloaded_files)
        _pump_until(lambda: dialog.sort_btn.isEnabled() and dialog.continue_btn.isEnabled())

        second = FakeMessage(text="track 2", file=FakeFile("b.flac", 10))
        release = asyncio.Event()

        async def _failing_download(file, progress_callback=None):
            await release.wait()
            raise RuntimeError("boom")

        second.download_media = _failing_download
        _deliver(dialog, fake, second)
        _pump_until(lambda: second.id in dialog._active_downloads)
        assert dialog.sort_btn.isEnabled() is False
        assert dialog.continue_btn.isEnabled() is False

        loop = dialog._worker._loop
        loop.call_soon_threadsafe(release.set)
        _pump_until(lambda: second.id not in dialog._active_downloads)

        assert dialog.sort_btn.isEnabled() is True
        assert dialog.continue_btn.isEnabled() is True
    finally:
        _shutdown(dialog)


# --- Record Downloaded Albums tooltip ---------------------------------------


def test_continue_tooltip_explains_the_adapter_is_off(qt_app, monkeypatch, tmp_path):
    app_settings.set_mdrem_enabled(False)
    dialog = _dialog(monkeypatch, tmp_path)
    try:
        assert "MDRem" in dialog.continue_btn.toolTip()
    finally:
        _shutdown(dialog)


def test_continue_tooltip_explains_nothing_downloaded_yet(qt_app, monkeypatch, tmp_path):
    app_settings.set_mdrem_enabled(True)
    dialog = _dialog(monkeypatch, tmp_path, FakeTelethonClient(authorized=True))
    try:
        _pump_until(lambda: dialog._session_folder is not None)
        assert dialog.continue_btn.isEnabled() is False
        assert dialog.continue_btn.toolTip() != ""
        assert "MDRem" not in dialog.continue_btn.toolTip()
    finally:
        _shutdown(dialog)


def test_continue_has_no_tooltip_once_actually_usable(qt_app, monkeypatch, tmp_path):
    app_settings.set_mdrem_enabled(True)
    fake = FakeTelethonClient(authorized=True)
    dialog = _dialog(monkeypatch, tmp_path, fake)
    try:
        _pump_until(lambda: dialog._session_folder is not None)
        raw = FakeMessage(text="here", file=FakeFile("Unleashed.flac", 100))
        _deliver(dialog, fake, raw)
        _pump_until(lambda: dialog.continue_btn.isEnabled())

        assert dialog.continue_btn.toolTip() == ""
    finally:
        _shutdown(dialog)


# --- "Sort into Album Folders" ----------------------------------------------


def test_sort_button_disabled_until_something_has_downloaded(qt_app, monkeypatch, tmp_path):
    fake = FakeTelethonClient(authorized=True)
    dialog = _dialog(monkeypatch, tmp_path, fake)
    try:
        _pump_until(lambda: dialog._session_folder is not None)
        assert dialog.sort_btn.isEnabled() is False

        raw = FakeMessage(text="here", file=FakeFile("Unleashed.flac", 100))
        _deliver(dialog, fake, raw)
        _pump_until(lambda: dialog.sort_btn.isEnabled())
    finally:
        _shutdown(dialog)


def test_buttons_reflect_what_an_earlier_session_left_in_the_folder(qt_app, monkeypatch, tmp_path):
    """Found while auditing for the same class of bug as the sorting one:
    both buttons gated on `self._downloaded_files`, i.e. this dialog
    session's downloads only. With the folder now shared across sessions,
    opening the chat on a folder that already held tracks left Sort and
    Record disabled even though there was plenty to act on."""
    app_settings.set_mdrem_enabled(True)
    # Already sitting in the download folder before this dialog ever opens.
    (tmp_path / "leftover.flac").write_bytes(b"x")

    fake = FakeTelethonClient(authorized=True)
    dialog = _dialog(monkeypatch, tmp_path, fake)
    try:
        _pump_until(lambda: dialog._session_folder is not None)

        assert dialog._downloaded_files == {}, "nothing was downloaded in this session"
        assert dialog.sort_btn.isEnabled(), "there is a loose track waiting to be sorted"
        assert dialog.continue_btn.isEnabled(), "and it is recordable"
    finally:
        _shutdown(dialog)


def test_an_already_sorted_folder_still_allows_recording(qt_app, monkeypatch, tmp_path):
    """Only album subfolders, nothing loose: there is nothing to sort, but
    recording one of them is exactly what the user would want."""
    app_settings.set_mdrem_enabled(True)
    (tmp_path / "Some Album").mkdir()
    (tmp_path / "Some Album" / "track.flac").write_bytes(b"x")

    fake = FakeTelethonClient(authorized=True)
    dialog = _dialog(monkeypatch, tmp_path, fake)
    try:
        _pump_until(lambda: dialog._session_folder is not None)

        assert dialog.sort_btn.isEnabled() is False
        assert dialog.sort_btn.toolTip() != "", "a disabled button with no tooltip reads as broken"
        assert dialog.continue_btn.isEnabled()
    finally:
        _shutdown(dialog)


def test_sorting_with_only_one_album_reports_nothing_to_do(qt_app, monkeypatch, tmp_path):
    fake = FakeTelethonClient(authorized=True)
    dialog = _dialog(monkeypatch, tmp_path, fake)
    try:
        _pump_until(lambda: dialog._session_folder is not None)
        raw = FakeMessage(text="here", file=FakeFile("Unleashed.flac", 100))
        _deliver(dialog, fake, raw)
        _pump_until(lambda: dialog.sort_btn.isEnabled())

        informed = []
        monkeypatch.setattr(
            module.QMessageBox, "information", staticmethod(lambda *a, **k: informed.append(a[2]))
        )
        dialog._sort_downloads()

        assert informed and "one album" in informed[0].lower()
    finally:
        _shutdown(dialog)


def test_sorting_an_already_sorted_folder_says_so_rather_than_claiming_one_album(
    qt_app, monkeypatch, tmp_path
):
    """"Only one album was detected" was reported for both reasons a sort
    can move nothing, and it is plainly wrong for the already-sorted one --
    which is the case the user actually hit and described."""
    (tmp_path / "Some Album").mkdir()
    (tmp_path / "Some Album" / "track.flac").write_bytes(b"x")

    fake = FakeTelethonClient(authorized=True)
    dialog = _dialog(monkeypatch, tmp_path, fake)
    try:
        _pump_until(lambda: dialog._session_folder is not None)
        informed = []
        monkeypatch.setattr(
            module.QMessageBox, "information", staticmethod(lambda *a, **k: informed.append(a[2]))
        )

        dialog._sort_downloads()

        assert informed, "it still has to say something"
        assert "one album" not in informed[0].lower()
        assert "already sorted" in informed[0].lower()
    finally:
        _shutdown(dialog)


def test_sorting_two_albums_creates_two_subfolders(qt_app, monkeypatch, tmp_path):
    fake = FakeTelethonClient(authorized=True)
    dialog = _dialog(monkeypatch, tmp_path, fake)
    try:
        _pump_until(lambda: dialog._session_folder is not None)

        monkeypatch.setattr(
            module.album_sort, "read_album_tag", lambda p: ("Skillet", "Unleashed")
            if p.name.startswith("a") else ("Caskets", "Lost Souls")
        )

        a = FakeMessage(text="track a", file=FakeFile("a.flac", 10))
        _deliver(dialog, fake, a)
        _pump_until(lambda: a.id in dialog._downloaded_files)
        b = FakeMessage(text="track b", file=FakeFile("b.flac", 10))
        _deliver(dialog, fake, b)
        _pump_until(lambda: b.id in dialog._downloaded_files)

        informed = []
        monkeypatch.setattr(
            module.QMessageBox, "information", staticmethod(lambda *a, **k: informed.append(a[2]))
        )
        dialog._sort_downloads()

        subfolders = sorted(p.name for p in Path(dialog._session_folder).iterdir() if p.is_dir())
        assert subfolders == ["Caskets - Lost Souls", "Skillet - Unleashed"]
        assert "2" in informed[0]
    finally:
        _shutdown(dialog)


# --- the multi-album picker on Continue -------------------------------------


def test_continue_records_directly_when_only_one_album_present(qt_app, monkeypatch, tmp_path):
    app_settings.set_mdrem_enabled(True)
    fake = FakeTelethonClient(authorized=True)
    dialog = _dialog(monkeypatch, tmp_path, fake)
    try:
        _pump_until(lambda: dialog._session_folder is not None)
        raw = FakeMessage(text="here", file=FakeFile("Unleashed.flac", 100))
        _deliver(dialog, fake, raw)
        _pump_until(lambda: dialog.continue_btn.isEnabled())

        monkeypatch.setattr(
            module.QInputDialog,
            "getItem",
            staticmethod(lambda *a, **k: pytest.fail("must not ask when there is nothing to choose between")),
        )

        dialog._on_continue_clicked()
        # accept() defers to _on_worker_finished (never wait()s on the GUI
        # thread -- see TelegramChatDialog's own shutdown notes), so
        # dialog.result() only reflects Accepted once that has run.
        _pump_until(lambda: dialog.result() == QDialog.DialogCode.Accepted)

        assert dialog.downloaded_folder == dialog._session_folder
    finally:
        _shutdown(dialog)


def test_continue_asks_which_album_when_more_than_one_subfolder_exists(qt_app, monkeypatch, tmp_path):
    app_settings.set_mdrem_enabled(True)
    fake = FakeTelethonClient(authorized=True)
    dialog = _dialog(monkeypatch, tmp_path, fake)
    try:
        _pump_until(lambda: dialog._session_folder is not None)
        root = Path(dialog._session_folder)
        (root / "Album One").mkdir()
        (root / "Album Two").mkdir()
        dialog._downloaded_files[1] = root / "Album One" / "x.flac"  # just to enable Continue
        dialog._update_continue_button()

        monkeypatch.setattr(
            module.QInputDialog, "getItem", staticmethod(lambda *a, **k: ("Album Two", True))
        )

        dialog._on_continue_clicked()
        _pump_until(lambda: dialog.result() == QDialog.DialogCode.Accepted)

        assert dialog.downloaded_folder == str(root / "Album Two")
    finally:
        _shutdown(dialog)


def test_continue_auto_sorts_a_still_flat_multi_album_session_first(qt_app, monkeypatch, tmp_path):
    """Regression: clicking "Record Downloaded Albums..." straight away,
    without ever pressing "Sort into Album Folders" by hand, used to leave
    two albums' worth of files flat in the session folder -- pick_album_folder()
    then saw zero subfolders and silently handed back the whole mixed folder
    as if it were one album. _on_continue_clicked() now runs
    album_sort.sort_downloads() itself first."""
    app_settings.set_mdrem_enabled(True)
    fake = FakeTelethonClient(authorized=True)
    dialog = _dialog(monkeypatch, tmp_path, fake)
    try:
        _pump_until(lambda: dialog._session_folder is not None)

        monkeypatch.setattr(
            module.album_sort, "read_album_tag", lambda p: ("Skillet", "Unleashed")
            if p.name.startswith("a") else ("Caskets", "Lost Souls")
        )

        a = FakeMessage(text="track a", file=FakeFile("a.flac", 10))
        _deliver(dialog, fake, a)
        _pump_until(lambda: a.id in dialog._downloaded_files)
        b = FakeMessage(text="track b", file=FakeFile("b.flac", 10))
        _deliver(dialog, fake, b)
        _pump_until(lambda: b.id in dialog._downloaded_files)

        # Still flat at this point -- nothing has sorted anything yet.
        root = Path(dialog._session_folder)
        assert not any(p.is_dir() for p in root.iterdir())

        monkeypatch.setattr(
            module.QInputDialog, "getItem", staticmethod(lambda *a, **k: ("Skillet - Unleashed", True))
        )

        dialog._on_continue_clicked()
        _pump_until(lambda: dialog.result() == QDialog.DialogCode.Accepted)

        subfolders = sorted(p.name for p in root.iterdir() if p.is_dir())
        assert subfolders == ["Caskets - Lost Souls", "Skillet - Unleashed"]
        assert dialog.downloaded_folder == str(root / "Skillet - Unleashed")
    finally:
        _shutdown(dialog)


def test_cancelling_the_album_picker_leaves_the_dialog_open(qt_app, monkeypatch, tmp_path):
    app_settings.set_mdrem_enabled(True)
    fake = FakeTelethonClient(authorized=True)
    dialog = _dialog(monkeypatch, tmp_path, fake)
    try:
        _pump_until(lambda: dialog._session_folder is not None)
        root = Path(dialog._session_folder)
        (root / "Album One").mkdir()
        (root / "Album Two").mkdir()
        dialog._downloaded_files[1] = root / "Album One" / "x.flac"
        dialog._update_continue_button()

        monkeypatch.setattr(module.QInputDialog, "getItem", staticmethod(lambda *a, **k: ("", False)))

        dialog._on_continue_clicked()

        assert dialog.downloaded_folder is None
        assert dialog.result() != QDialog.DialogCode.Accepted
    finally:
        _shutdown(dialog)


# --- "Open Download Folder" -------------------------------------------------


def test_open_folder_button_disabled_until_connected(qt_app, monkeypatch, tmp_path):
    dialog = _dialog(monkeypatch, tmp_path)
    try:
        # Checked before any event-loop pumping: _on_ready can only have
        # run once Qt has actually delivered the worker's queued signal.
        assert dialog.open_folder_btn.isEnabled() is False
    finally:
        _shutdown(dialog)


def test_open_folder_button_opens_the_session_folder(qt_app, monkeypatch, tmp_path):
    fake = FakeTelethonClient(authorized=True)
    dialog = _dialog(monkeypatch, tmp_path, fake)
    try:
        _pump_until(lambda: dialog._session_folder is not None)
        assert dialog.open_folder_btn.isEnabled()

        opened = []
        monkeypatch.setattr(module.QDesktopServices, "openUrl", staticmethod(lambda url: opened.append(url)))

        dialog.open_folder_btn.click()

        assert len(opened) == 1
        # QUrl round-trips through forward slashes internally even on
        # Windows -- compare as Paths, which treat "/" and "\" the same.
        assert Path(opened[0].toLocalFile()) == Path(dialog._session_folder)
    finally:
        _shutdown(dialog)
