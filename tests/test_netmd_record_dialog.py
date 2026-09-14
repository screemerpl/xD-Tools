"""NetMdRecordDialog -- the NetMD counterpart to RecordDialog.

Nothing here touches a real deck or a real subprocess: `netmd.send_tracks`/
`netmd.prepare_track_wavs` are monkeypatched at the module-function level,
the same pattern test_burn_dialog.py uses for cdburn.prepare_wavs/burn.
Track lists are built directly as tracks.PlaylistItems, bypassing real
mutagen reads, exactly as test_record_dialog.py does.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QMessageBox

from mdtools import app_settings, netmd, tracks
from mdtools.panels import netmd_record_dialog as netmd_module
from mdtools.panels.netmd_record_dialog import COL_TITLE, NetMdRecordDialog, _NetMdRecordWorker


def _items(count: int, seconds: int = 200) -> list[tracks.PlaylistItem]:
    return [
        tracks.PlaylistItem(
            track_number=f"{i:02d}",
            title=f"Track {i}",
            album_artist="Artist",
            album="Album",
            date="2024",
            length_seconds=seconds,
            path=f"/music/{i:02d}.flac",
        )
        for i in range(1, count + 1)
    ]


def _dialog(items, monkeypatch) -> NetMdRecordDialog:
    monkeypatch.setattr(netmd_module.tracks, "playlist_items_from_paths", lambda paths: items)
    monkeypatch.setattr(netmd_module, "fetch_into", lambda *a, **k: None)
    return NetMdRecordDialog([item.path for item in items], None)


def _properties(seconds: float):
    from mdtools import decode

    return decode.AudioProperties(
        sample_rate=44100, bits_per_sample=16, channels=2, frames=int(seconds * 44100)
    )


# --- the plan built from what is on screen ---------------------------------


def test_the_plan_is_built_from_the_edited_titles(qt_app, monkeypatch):
    dialog = _dialog(_items(2), monkeypatch)
    dialog.tree.topLevelItem(0).setText(COL_TITLE, "Corrected Title")

    plan = netmd.build_record_plan(
        dialog._disc_sources(), disc_title=dialog._disc_album_title(), analyze=lambda p: _properties(200.0)
    )

    assert plan.tracks[0].title == "Corrected Title"
    assert plan.disc_title == "Album"


def test_disc_minutes_is_fixed_from_the_settings_mode(qt_app, monkeypatch):
    app_settings.set_netmd_recording_mode(netmd.MODE_LP2)
    dialog = _dialog(_items(2), monkeypatch)

    assert dialog.disc_minutes_spin.value() == 160
    assert dialog.disc_minutes_spin.isEnabled() is False


# --- the worker --------------------------------------------------------


def test_the_worker_prepares_then_sends(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(netmd, "prepare_track_wavs", lambda plan, directory, **k: calls.append("prepare") or ["01.wav"])
    monkeypatch.setattr(netmd, "send_tracks", lambda plan, directory, names, **k: calls.append("send"))

    plan = netmd.build_record_plan([("a.flac", "one")], analyze=lambda p: _properties(10.0))
    worker = _NetMdRecordWorker(plan, tmp_path)
    succeeded = []
    worker.succeeded.connect(lambda: succeeded.append(True))

    worker.run()

    assert calls == ["prepare", "send"]
    assert succeeded == [True]


def test_the_worker_reports_failure_rather_than_raising(tmp_path, monkeypatch):
    monkeypatch.setattr(netmd, "prepare_track_wavs", lambda plan, directory, **k: ["01.wav"])

    def fail(*args, **kwargs):
        raise netmd.NetMdError("no NetMD device found")

    monkeypatch.setattr(netmd, "send_tracks", fail)

    plan = netmd.build_record_plan([("a.flac", "one")], analyze=lambda p: _properties(10.0))
    worker = _NetMdRecordWorker(plan, tmp_path)
    failures = []
    worker.failed.connect(lambda message: failures.append(message))

    worker.run()

    assert failures == ["no NetMD device found"]


def test_the_worker_can_be_cancelled_before_sending(tmp_path, monkeypatch):
    def cancel_immediately(plan, directory, *, on_progress=None, should_cancel=None):
        should_cancel()  # simulate the worker having been told to stop
        raise netmd.NetMdCancelled()

    monkeypatch.setattr(netmd, "prepare_track_wavs", cancel_immediately)
    sent = []
    monkeypatch.setattr(netmd, "send_tracks", lambda *a, **k: sent.append(True))

    plan = netmd.build_record_plan([("a.flac", "one")], analyze=lambda p: _properties(10.0))
    worker = _NetMdRecordWorker(plan, tmp_path)
    worker.cancel()
    cancelled = []
    worker.cancelled.connect(lambda: cancelled.append(True))

    worker.run()

    assert cancelled == [True]
    assert sent == []


# --- the dialog end to end, worker run synchronously ------------------------


class _FakeSignal:
    def __init__(self):
        self._slots = []

    def connect(self, slot):
        self._slots.append(slot)

    def emit(self, *args):
        for slot in self._slots:
            slot(*args)


class FakeWorker:
    def __init__(self, plan, work_dir, *, parent=None):
        self.plan = plan
        self.work_dir = work_dir
        self.stage = _FakeSignal()
        self.progress = _FakeSignal()
        self.track_started = _FakeSignal()
        self.failed = _FakeSignal()
        self.cancelled = _FakeSignal()
        self.succeeded = _FakeSignal()
        self.finished = _FakeSignal()

    def start(self):
        self.succeeded.emit()
        self.finished.emit()

    def cancel(self):
        pass


def test_a_successful_recording_closes_the_dialog_and_captures_metadata(qt_app, tmp_path, monkeypatch):
    monkeypatch.setattr(netmd_module, "_NetMdRecordWorker", FakeWorker)
    monkeypatch.setattr(app_settings, "cd_rip_folder", lambda: str(tmp_path))
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.StandardButton.Ok)

    dialog = _dialog(_items(2), monkeypatch)
    monkeypatch.setattr(
        dialog,
        "_build_plan",
        lambda: netmd.build_record_plan(
            dialog._disc_sources(), disc_title=dialog._disc_album_title(), analyze=lambda p: _properties(200.0)
        ),
    )
    accepted = []
    dialog.accepted.connect(lambda: accepted.append(True))

    dialog._start()

    assert accepted == [True]
    assert dialog.result_metadata is not None
    assert [t.title for t in dialog.result_metadata.tracks] == ["Track 1", "Track 2"]


def test_a_failed_recording_re_enables_the_start_button(qt_app, tmp_path, monkeypatch):
    class FailingWorker(FakeWorker):
        def start(self):
            self.failed.emit("no NetMD device found")
            self.finished.emit()

    monkeypatch.setattr(netmd_module, "_NetMdRecordWorker", FailingWorker)
    monkeypatch.setattr(app_settings, "cd_rip_folder", lambda: str(tmp_path))
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: None)

    dialog = _dialog(_items(1), monkeypatch)
    monkeypatch.setattr(
        dialog,
        "_build_plan",
        lambda: netmd.build_record_plan(
            dialog._disc_sources(), disc_title=dialog._disc_album_title(), analyze=lambda p: _properties(200.0)
        ),
    )
    dialog._start()

    assert dialog.start_btn.isEnabled() is True
    assert "no NetMD device found" in dialog.status_label.text()


def test_erase_asks_first_and_calls_netmd_directly(qt_app, monkeypatch):
    dialog = _dialog(_items(1), monkeypatch)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.StandardButton.Ok)
    erased = []
    monkeypatch.setattr(netmd, "erase_disc", lambda: erased.append(True))

    dialog._erase_disc()

    assert erased == [True]
