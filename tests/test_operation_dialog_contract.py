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
    assert callable(getattr(dialog_class, "_on_hide_clicked", None))


@pytest.mark.parametrize("dialog_class", NO_TRACK_PROGRESS, ids=lambda c: c.__name__)
def test_the_deliberate_exclusions_stay_excluded(dialog_class):
    """A guard for the scope decision, not an implementation detail: if
    per-track progress is ever added to one of these, that is a choice
    somebody has to make on purpose."""
    assert not hasattr(dialog_class, "track_progress_changed")


@pytest.mark.parametrize("dialog_class", [RecordDialog, TapeRecordDialog, CdRipDialog], ids=lambda c: c.__name__)
def test_the_rest_do_report_per_track_progress(dialog_class):
    assert hasattr(dialog_class, "track_progress_changed")
