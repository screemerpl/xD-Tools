"""The one shape every operation dialog has to present to MainWindow's
bottom progress bar (#27), asserted in one place rather than five.

_drive_recording_bar()/_release_recording_bar() connect these by name and
call request_stop()/request_show() with no idea which dialog they hold, so
a dialog that quietly stopped offering one of them would not fail until
somebody pressed the button in a real recording.
"""

from __future__ import annotations

import pytest

from mdtools.panels.burn_dialog import BurnDialog
from mdtools.panels.cd_rip_dialog import CdRipDialog
from mdtools.panels.mdrem_upload_dialog import MDRemUploadDialog
from mdtools.panels.metadata_dialog import MetadataDialog
from mdtools.panels.record_dialog import RecordDialog
from mdtools.panels.tape_record_dialog import TapeRecordDialog
from mdtools.panels.telegram_chat_dialog import TelegramChatDialog

# Every dialog MainWindow can hand to _drive_recording_bar() -- not only
# the six recording/rip/burn/upload dialogs: TelegramChatDialog is wired
# in too, not because it competes for the same MDRem port/audio device/
# optical drive (it doesn't), but because it drives the same one shared
# bar with its own download-queue status.
DRIVING_DIALOGS = [RecordDialog, TapeRecordDialog, BurnDialog, CdRipDialog, MetadataDialog, TelegramChatDialog]

# The ones the user can hide -- MetadataDialog is left out on purpose: it
# only ever proxies for the MDRemUploadDialog it opens, and has no Hide
# button of its own (see its own request_show()).
HIDEABLE_DIALOGS = [RecordDialog, TapeRecordDialog, BurnDialog, CdRipDialog, MDRemUploadDialog, TelegramChatDialog]

# Per-track progress exists only where it is genuinely available. Burning
# is the deliberate exclusion: cdrecord writes a disc as one continuous
# DAO stream with no per-track breakdown to report. Titling has no
# per-track concept at all, and MetadataDialog only ever proxies titling.
# A Telegram download queue has no single "current track" either -- up to
# _MAX_CONCURRENT_DOWNLOADS files can be in flight at once.
NO_TRACK_PROGRESS = [BurnDialog, MDRemUploadDialog, MetadataDialog, TelegramChatDialog]


def _build(dialog_class):
    """Each of these takes a different set of required arguments; none of
    them touches a device or a thread on construction."""
    if dialog_class is RecordDialog:
        return RecordDialog("COM7", [], None)
    if dialog_class is TapeRecordDialog:
        return TapeRecordDialog([], None)
    return BurnDialog([], album="a", artist="b", year=2020, parent=None)


@pytest.mark.parametrize("dialog_class", DRIVING_DIALOGS, ids=lambda c: c.__name__)
def test_it_offers_everything_the_progress_bar_connects_to(dialog_class):
    for name in ("running_changed", "overall_progress_changed", "visibility_changed"):
        assert hasattr(dialog_class, name), f"{dialog_class.__name__} is missing {name}"


@pytest.mark.parametrize("dialog_class", DRIVING_DIALOGS, ids=lambda c: c.__name__)
def test_it_can_be_stopped_and_re_shown_from_the_bar(dialog_class):
    assert callable(getattr(dialog_class, "request_stop", None))
    assert callable(getattr(dialog_class, "request_show", None))


@pytest.mark.parametrize("dialog_class", HIDEABLE_DIALOGS, ids=lambda c: c.__name__)
def test_a_hideable_dialog_carries_what_exec_hideable_needs(dialog_class):
    """exec_hideable() tells a deliberate Hide apart from a cancel by
    these two -- without them a Hide reads as "the user cancelled", which
    is the whole bug that module exists for."""
    assert hasattr(dialog_class, "show_requested")
    # The way in is the window's own X now, not a Hide button -- which
    # needs both a closeEvent to intercept it and an is_busy() to say
    # whether this is a moment worth intercepting.
    assert callable(getattr(dialog_class, "closeEvent", None))
    assert callable(getattr(dialog_class, "is_busy", None))


@pytest.mark.parametrize("dialog_class", NO_TRACK_PROGRESS, ids=lambda c: c.__name__)
def test_the_deliberate_exclusions_stay_excluded(dialog_class):
    """A guard for the scope decision, not an implementation detail: if
    per-track progress is ever added to one of these, that is a choice
    somebody has to make on purpose."""
    assert not hasattr(dialog_class, "track_progress_changed")


@pytest.mark.parametrize("dialog_class", [RecordDialog, TapeRecordDialog, CdRipDialog], ids=lambda c: c.__name__)
def test_the_rest_do_report_per_track_progress(dialog_class):
    assert hasattr(dialog_class, "track_progress_changed")


# Every dialog that offers the preview player must also take it away
# while it is actually recording/burning -- see PreviewPlayerBar.set_locked().
PREVIEW_DIALOGS = [RecordDialog, TapeRecordDialog, BurnDialog]


@pytest.mark.parametrize("dialog_class", PREVIEW_DIALOGS, ids=lambda c: c.__name__)
def test_the_preview_player_is_locked_while_the_dialog_is_running(dialog_class, qt_app):
    """Wired to each dialog's own running_changed rather than toggled by
    hand at every start/finish/fail site, so this holds however many of
    those there are. Asserted through the signal, not the connection, so
    it stays true whatever the wiring looks like."""
    dialog = _build(dialog_class)

    dialog.running_changed.emit(True)
    assert not dialog.preview_bar.play_btn.isEnabled()
    assert not dialog.preview_bar.next_btn.isEnabled()

    dialog.running_changed.emit(False)
    assert dialog.preview_bar._locked is False


# --- the window's X, now that the Hide buttons are gone ----------------------
#
# Hiding used to be a button in a row of buttons on six separate windows.
# It is the title bar's own X now: closing a window whose work carries on
# regardless is what backgrounding looks like everywhere else. The rule is
# only ever "while busy" -- an idle window that could not be shut with its
# own X would be far more surprising than the hiding is.


def _mark_busy(dialog, busy: bool) -> None:
    """Each dialog reads a different flag; this sets whichever one its own
    is_busy() actually consults."""

    class _Running:
        def isRunning(self):
            return True

    if hasattr(dialog, "_recording"):
        dialog._recording = busy
    else:
        dialog._worker = _Running() if busy else None


@pytest.mark.parametrize("dialog_class", PREVIEW_DIALOGS + [CdRipDialog], ids=lambda c: c.__name__)
def test_the_window_x_hides_while_busy_and_closes_when_idle(dialog_class, qt_app):
    from PySide6.QtGui import QCloseEvent

    dialog = _build(dialog_class) if dialog_class in PREVIEW_DIALOGS else CdRipDialog(None)

    idle = QCloseEvent()
    dialog.closeEvent(idle)
    assert idle.isAccepted(), "an idle window must still close from its own X"
    assert dialog.hidden_for_background is False

    _mark_busy(dialog, True)
    busy = QCloseEvent()
    dialog.closeEvent(busy)
    assert not busy.isAccepted(), "a busy window's X must be refused, not close the dialog"
    assert dialog.hidden_for_background is True, "and it must read as a hide, not a cancel"
    assert dialog.isHidden()


@pytest.mark.parametrize("dialog_class", HIDEABLE_DIALOGS, ids=lambda c: c.__name__)
def test_no_hide_button_is_left_behind(dialog_class):
    """The button is gone from all six; a stray one left on a single
    dialog would be the odd window out rather than a feature."""
    assert not hasattr(dialog_class, "_on_hide_clicked")
