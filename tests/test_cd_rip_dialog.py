"""The Record CD dialog, with no drive, no disc and no network.

The worker's run() is called directly rather than started as a thread: it
takes no Qt objects of its own and every tool it drives is faked here, so
running it in place makes the test deterministic instead of waiting on a
thread to finish.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mdtools import app_settings, cdrip, foobar, musicbrainz
from mdtools.panels import cd_rip_dialog as module
from mdtools.panels.cd_rip_dialog import CdRipDialog, _RipWorker

TOC_TEXT = """
Table of contents (audio tracks only):
track        length               begin        copy pre ch
  1.    22617 [05:01.42]        0 [00:00.00]    no   no  2
  2.    19120 [04:14.70]    22617 [05:01.42]    no   no  2
  3.    16430 [03:39.05]    41737 [09:16.37]    no   no  2
"""


@pytest.fixture
def toc() -> cdrip.DiscToc:
    return cdrip.parse_toc(TOC_TEXT)


@pytest.fixture
def dialog(qt_app, monkeypatch, tmp_path):
    """A dialog with a drive present, the bundled tools accounted for, and
    the rip folder pointed somewhere disposable."""
    monkeypatch.setattr(module.cdrip, "list_drives", lambda: [cdrip.CdDrive("D:", "NEVERMIND", True)])
    monkeypatch.setattr(module.cdrip, "missing_tools", lambda: [])
    monkeypatch.setattr(app_settings, "cd_rip_folder", lambda: str(tmp_path / "rips"))
    return CdRipDialog()


def _read(dialog, monkeypatch, toc, releases):
    monkeypatch.setattr(module.cdrip, "read_toc", lambda device: toc)
    monkeypatch.setattr(module.musicbrainz, "lookup_disc", lambda t: releases)
    dialog._read_disc()


def _release(title, artist, year, tracks):
    return musicbrainz.DiscRelease(
        release_id="x", title=title, artist=artist, year=year, track_titles=tracks
    )


# --- before a disc ----------------------------------------------------


def test_with_no_drive_the_read_button_is_off_and_says_so(qt_app, monkeypatch):
    monkeypatch.setattr(module.cdrip, "list_drives", lambda: [])
    monkeypatch.setattr(module.cdrip, "missing_tools", lambda: [])

    dialog = CdRipDialog()

    assert dialog.read_btn.isEnabled() is False
    assert "No CD drive" in dialog.status_label.text()


def test_missing_bundled_tools_are_named_rather_than_failing_later(qt_app, monkeypatch):
    monkeypatch.setattr(module.cdrip, "list_drives", lambda: [cdrip.CdDrive("D:", "", True)])
    monkeypatch.setattr(module.cdrip, "missing_tools", lambda: ["cd-paranoia"])

    dialog = CdRipDialog()

    assert dialog.read_btn.isEnabled() is False
    assert "cd-paranoia" in dialog.status_label.text()


def test_pressing_refresh_does_not_re_enable_reading_when_tools_are_missing(qt_app, monkeypatch):
    """Refresh enables the button on its own, so the tool check has to run
    after it rather than only once at construction."""
    monkeypatch.setattr(module.cdrip, "list_drives", lambda: [cdrip.CdDrive("D:", "", True)])
    monkeypatch.setattr(module.cdrip, "missing_tools", lambda: ["flac"])
    dialog = CdRipDialog()

    dialog._refresh_drives()

    assert dialog.read_btn.isEnabled() is False


def test_ripping_cannot_start_before_a_disc_has_been_read(dialog):
    assert dialog.start_btn.isEnabled() is False


# --- reading a disc ---------------------------------------------------


def test_reading_a_disc_lists_its_tracks_with_lengths(dialog, monkeypatch, toc):
    _read(dialog, monkeypatch, toc, [])

    assert dialog.tree.topLevelItemCount() == 3
    assert dialog.tree.topLevelItem(0).text(3) == "5:01"
    assert dialog.start_btn.isEnabled()


def test_a_disc_nobody_has_catalogued_still_gets_editable_placeholder_titles(dialog, monkeypatch, toc):
    """Anyone with a home-burned disc has to type the titles anyway, so a
    miss must leave a usable dialog rather than an error."""
    _read(dialog, monkeypatch, toc, [])

    assert dialog.track_titles() == ["Track 1", "Track 2", "Track 3"]
    assert "not in MusicBrainz" in dialog.status_label.text()
    assert dialog.start_btn.isEnabled()


def test_a_lookup_failure_is_not_treated_as_a_failure_to_read_the_disc(dialog, monkeypatch, toc):
    monkeypatch.setattr(module.cdrip, "read_toc", lambda device: toc)

    def explode(_toc):
        raise musicbrainz.MusicBrainzError("offline")

    monkeypatch.setattr(module.musicbrainz, "lookup_disc", explode)
    dialog._read_disc()

    assert dialog.tree.topLevelItemCount() == 3
    assert dialog.start_btn.isEnabled()


def test_an_unreadable_disc_leaves_ripping_disabled(dialog, monkeypatch):
    def explode(device):
        raise cdrip.CdRipError("no audio CD in the drive")

    monkeypatch.setattr(module.cdrip, "read_toc", explode)
    dialog._read_disc()

    assert dialog.start_btn.isEnabled() is False
    assert "no audio CD" in dialog.status_label.text()


def test_a_single_candidate_fills_the_fields_without_showing_a_picker(dialog, monkeypatch, toc):
    _read(dialog, monkeypatch, toc, [_release("Nevermind", "Nirvana", 1991, ["A", "B", "C"])])

    assert dialog.artist_edit.text() == "Nirvana"
    assert dialog.album_edit.text() == "Nevermind"
    assert dialog.year_spin.value() == 1991
    assert dialog.track_titles() == ["A", "B", "C"]
    assert dialog.release_combo.isVisibleTo(dialog) is False


def test_several_candidates_offer_a_picker_that_swaps_the_titles(dialog, monkeypatch, toc):
    """Pressings are genuinely ambiguous, the same reason MetadataDialog
    shows a list rather than guessing."""
    first = _release("Nevermind", "Nirvana", 1991, ["A", "B", "C"])
    second = _release("Nevermind (Remaster)", "Nirvana", 2011, ["X", "Y", "Z"])
    _read(dialog, monkeypatch, toc, [first, second])
    assert dialog.release_combo.isVisibleTo(dialog)
    assert dialog.track_titles() == ["A", "B", "C"]

    dialog.release_combo.setCurrentIndex(1)

    assert dialog.track_titles() == ["X", "Y", "Z"]
    assert dialog.album_edit.text() == "Nevermind (Remaster)"


def test_a_disc_longer_than_an_md_warns_before_a_minute_is_spent_ripping(dialog, monkeypatch):
    """RecordDialog warns about this too, but by then the rip has already
    happened -- here the disc can still be swapped or the deck set to LP2."""
    long_toc = cdrip.DiscToc(
        tracks=[cdrip.TocTrack(1, 0, 81 * 60 * 75)], leadout_lba=81 * 60 * 75
    )
    _read(dialog, monkeypatch, long_toc, [])

    # isVisibleTo, not isVisible: the dialog itself is never shown in a test,
    # which would make isVisible() False whatever the code did.
    assert dialog.warning_label.isVisibleTo(dialog)
    assert "LP2" in dialog.warning_label.text()


def test_the_chosen_drive_is_remembered_for_the_next_disc(dialog, monkeypatch, toc):
    _read(dialog, monkeypatch, toc, [])
    assert app_settings.cd_drive() == "D:"


# --- the plan the dialog builds ---------------------------------------


def test_the_plan_uses_the_titles_as_edited_in_the_tree(dialog, monkeypatch, toc, tmp_path):
    """Titles are editable because they are written into the files, and the
    files are what the MiniDisc gets titled from."""
    _read(dialog, monkeypatch, toc, [_release("Nevermind", "Nirvana", 1991, ["A", "B", "C"])])
    dialog.tree.topLevelItem(1).setText(1, "In Bloom")

    plan = dialog.build_plan()

    assert plan.tasks[1].title == "In Bloom"
    assert plan.tasks[1].tags["TITLE"] == "In Bloom"
    assert plan.folder == tmp_path / "rips" / "Nirvana - Nevermind"


def test_a_blank_year_is_left_out_rather_than_written_as_zero(dialog, monkeypatch, toc):
    _read(dialog, monkeypatch, toc, [_release("A", "B", None, ["x", "y", "z"])])

    assert "DATE" not in dialog.build_plan().tasks[0].tags


# --- preflight --------------------------------------------------------


def test_a_rip_will_not_start_without_knowing_where_foobar_is(dialog, monkeypatch, toc):
    """Checked before the rip, not after: finding out the files cannot be
    handed over is worth minutes if it happens first and nothing if it
    happens last."""
    _read(dialog, monkeypatch, toc, [])
    monkeypatch.setattr(app_settings, "foobar_exe", lambda: "")
    monkeypatch.setattr(module.foobar, "find_foobar_exe", lambda: None)
    warned: list = []
    monkeypatch.setattr(module.QMessageBox, "warning", lambda *a, **k: warned.append(a))

    dialog._start()

    assert warned
    assert dialog._worker is None


def test_a_rip_will_not_start_with_foobar_unreachable(dialog, monkeypatch, toc, tmp_path):
    _read(dialog, monkeypatch, toc, [])
    exe = tmp_path / "foobar2000.exe"
    exe.write_bytes(b"")
    monkeypatch.setattr(app_settings, "foobar_exe", lambda: str(exe))

    def explode(self):
        raise foobar.FoobarError("connection refused")

    monkeypatch.setattr(foobar.FoobarClient, "current_playlist", explode)
    warned: list = []
    monkeypatch.setattr(module.QMessageBox, "warning", lambda *a, **k: warned.append(a))

    dialog._start()

    assert warned
    assert dialog._worker is None


# --- the worker -------------------------------------------------------


def _plan(tmp_path, count=3) -> cdrip.RipPlan:
    toc = cdrip.DiscToc(
        tracks=[cdrip.TocTrack(n + 1, n * 1000, 1000) for n in range(count)],
        leadout_lba=count * 1000,
    )
    return cdrip.build_rip_plan(toc, tmp_path, [f"Song {n + 1}" for n in range(count)])


def _wire(monkeypatch, *, rip=None, encode=None, replace=None):
    monkeypatch.setattr(module.cdrip, "rip_track", rip or (lambda *a, **k: None))
    monkeypatch.setattr(module.cdrip, "encode_track", encode or (lambda task: None))
    monkeypatch.setattr(module.foobar, "replace_current_playlist", replace or (lambda *a, **k: None))


def test_the_worker_rips_encodes_then_loads_the_playlist_in_that_order(qt_app, monkeypatch, tmp_path):
    order: list = []
    _wire(
        monkeypatch,
        rip=lambda device, task, **kw: order.append(f"rip{task.number}"),
        encode=lambda task: order.append(f"encode{task.number}"),
        replace=lambda client, exe, paths, **kw: order.append(f"playlist:{len(paths)}"),
    )
    worker = _RipWorker("D:", _plan(tmp_path), foobar.FoobarClient(), "fb2k.exe")
    done: list = []
    worker.succeeded.connect(lambda: done.append(True))

    worker.run()

    assert order == ["rip1", "encode1", "rip2", "encode2", "rip3", "encode3", "playlist:3"]
    assert done == [True]


def test_the_worker_hands_the_files_over_in_disc_order(qt_app, monkeypatch, tmp_path):
    handed: list = []
    _wire(monkeypatch, replace=lambda client, exe, paths, **kw: handed.extend(paths))
    worker = _RipWorker("D:", _plan(tmp_path), foobar.FoobarClient(), "fb2k.exe")

    worker.run()

    assert [Path(p).name for p in handed] == [
        "01 - Song 1.flac",
        "02 - Song 2.flac",
        "03 - Song 3.flac",
    ]


def test_progress_climbs_across_tracks_and_ends_at_one(qt_app, monkeypatch, tmp_path):
    def rip(device, task, on_progress=None, should_cancel=None):
        for fraction in (0.5, 1.0):
            on_progress(fraction)

    _wire(monkeypatch, rip=rip)
    worker = _RipWorker("D:", _plan(tmp_path), foobar.FoobarClient(), "fb2k.exe")
    seen: list[float] = []
    worker.progress.connect(seen.append)

    worker.run()

    assert seen == sorted(seen)
    assert seen[-1] == pytest.approx(1.0)


def test_a_failed_rip_stops_and_never_touches_the_playlist(qt_app, monkeypatch, tmp_path):
    """A half-ripped album loaded into foobar would be recorded as though it
    were the whole disc."""
    def rip(device, task, **kw):
        if task.number == 2:
            raise cdrip.CdRipError("scratch at sector 41737")

    _wire(monkeypatch, rip=rip, replace=lambda *a, **k: pytest.fail("must not load a partial rip"))
    worker = _RipWorker("D:", _plan(tmp_path), foobar.FoobarClient(), "fb2k.exe")
    failures: list = []
    worker.failed.connect(failures.append)

    worker.run()

    assert failures == ["scratch at sector 41737"]


def test_cancelling_reports_cancelled_rather_than_failed(qt_app, monkeypatch, tmp_path):
    """Nothing went wrong, so nothing should be reported as having done."""
    def rip(device, task, **kw):
        raise cdrip.CdRipCancelled()

    _wire(monkeypatch, rip=rip, replace=lambda *a, **k: pytest.fail("must not load a cancelled rip"))
    worker = _RipWorker("D:", _plan(tmp_path), foobar.FoobarClient(), "fb2k.exe")
    events: list = []
    worker.cancelled.connect(lambda: events.append("cancelled"))
    worker.failed.connect(lambda m: events.append("failed"))

    worker.run()

    assert events == ["cancelled"]


def test_a_cancel_between_tracks_stops_before_the_next_one(qt_app, monkeypatch, tmp_path):
    ripped: list = []

    def rip(device, task, **kw):
        ripped.append(task.number)
        worker.cancel()

    _wire(monkeypatch, rip=rip, replace=lambda *a, **k: pytest.fail("must not load a cancelled rip"))
    worker = _RipWorker("D:", _plan(tmp_path), foobar.FoobarClient(), "fb2k.exe")

    worker.run()

    assert ripped == [1]


def test_a_playlist_that_cannot_be_filled_is_reported_as_a_failure(qt_app, monkeypatch, tmp_path):
    def explode(*args, **kwargs):
        raise foobar.FoobarError("foobar2000 has no playlist open")

    _wire(monkeypatch, replace=explode)
    worker = _RipWorker("D:", _plan(tmp_path), foobar.FoobarClient(), "fb2k.exe")
    failures: list = []
    worker.failed.connect(failures.append)

    worker.run()

    assert failures == ["foobar2000 has no playlist open"]
