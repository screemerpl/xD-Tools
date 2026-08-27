"""Ripping a set of CDs as one album.

Kept apart from test_cd_rip_dialog.py, which covers a single disc: this is
about what carries over from one disc of a set to the next -- the folder,
the album's name, the tags that put it back in order, and the playlist.

No drive, no disc, no network: every tool is faked and the worker is never
started as a thread.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mdtools import app_settings, cdrip, musicbrainz
from mdtools.panels import cd_rip_dialog as module
from mdtools.panels.cd_rip_dialog import CdRipDialog

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


@pytest.fixture(autouse=True)
def no_cover_lookup(monkeypatch):
    monkeypatch.setattr(module, "fetch_into", lambda *a, **k: None)


@pytest.fixture
def dialog(qt_app, monkeypatch, tmp_path):
    monkeypatch.setattr(module.cdrip, "list_drives", lambda: [cdrip.CdDrive("D:", "AUDIO CD", True)])
    monkeypatch.setattr(module.cdrip, "missing_tools", lambda: [])
    monkeypatch.setattr(app_settings, "cd_rip_folder", lambda: str(tmp_path / "rips"))
    dialog = CdRipDialog()
    dialog.multi_check.setChecked(True)
    return dialog


def _release(title, artist, year, tracks):
    return musicbrainz.DiscRelease(
        release_id="x", title=title, artist=artist, year=year, track_titles=tracks
    )


def _read(dialog, monkeypatch, toc, releases):
    monkeypatch.setattr(module.cdrip, "read_toc", lambda device: toc)
    monkeypatch.setattr(module.musicbrainz, "lookup_disc", lambda t: releases)
    dialog._read_disc()


class _FakeWorker:
    made: list = []

    def __init__(self, device, plan, parent=None):
        self.plan = plan
        self.dialog = parent
        # What the dialog itself computed as "everything ripped so far plus
        # this disc" -- there is no playlist any more to read it back from.
        self.playlist_paths = list(parent._current_paths) if parent is not None else []
        _FakeWorker.made.append(self)
        for name in (
            "track_started", "progress", "track_progress", "stage", "failed", "cancelled", "succeeded", "finished"
        ):
            setattr(self, name, _Signal())

    def start(self):
        pass

    def cancel(self):
        pass

    def isRunning(self):
        return False

    def finish_successfully(self):
        self.succeeded.emit()
        self.finished.emit()


class _Signal:
    def __init__(self):
        self._slots = []

    def connect(self, slot):
        self._slots.append(slot)

    def emit(self, *args):
        for slot in list(self._slots):
            slot(*args)


@pytest.fixture
def fake_worker(monkeypatch):
    _FakeWorker.made = []
    monkeypatch.setattr(module, "_RipWorker", _FakeWorker)
    return _FakeWorker.made


def _answer(monkeypatch, *replies):
    """Answers the "put the next disc in" question, in order."""
    queue = list(replies)

    def _question(*args, **kwargs):
        return queue.pop(0) if queue else module.QMessageBox.StandardButton.Cancel

    monkeypatch.setattr(module.QMessageBox, "question", _question)


# -- what the tags and filenames say --------------------------------------


def test_a_disc_of_a_set_is_tagged_with_which_disc_it_is(dialog, monkeypatch, toc):
    """DISCNUMBER is what puts the album back into its own order later --
    both discs number their tracks from one, so nothing else could."""
    _read(dialog, monkeypatch, toc, [_release("Best Of", "Bajm", 2018, ["A", "B", "C"])])

    plan = dialog.build_plan()

    assert all(task.tags["DISCNUMBER"] == "1" for task in plan.tasks)


def test_the_second_discs_files_do_not_land_on_the_firsts(dialog, monkeypatch, toc):
    """One folder, and both discs have a track 01."""
    _read(dialog, monkeypatch, toc, [_release("Best Of", "Bajm", 2018, ["A", "B", "C"])])
    first = dialog.build_plan()
    dialog._disc = 2
    second = dialog.build_plan()

    assert not set(first.flac_paths) & set(second.flac_paths)
    assert first.tasks[0].flac_path.name.startswith("1-01")
    assert second.tasks[0].flac_path.name.startswith("2-01")


def test_a_single_disc_rip_keeps_the_names_it_always_had(qt_app, monkeypatch, tmp_path, toc):
    """Nothing about a plain rip changes: no disc prefix, no DISCNUMBER."""
    monkeypatch.setattr(module.cdrip, "list_drives", lambda: [cdrip.CdDrive("D:", "AUDIO CD", True)])
    monkeypatch.setattr(module.cdrip, "missing_tools", lambda: [])
    monkeypatch.setattr(app_settings, "cd_rip_folder", lambda: str(tmp_path / "rips"))
    dialog = CdRipDialog()
    _read(dialog, monkeypatch, toc, [_release("Nevermind", "Nirvana", 1991, ["A", "B", "C"])])

    plan = dialog.build_plan()

    assert plan.tasks[0].flac_path.name.startswith("01 - ")
    assert "DISCNUMBER" not in plan.tasks[0].tags


# -- one disc after another -----------------------------------------------


def test_the_next_disc_is_asked_for_and_read(dialog, monkeypatch, toc, fake_worker):
    _read(dialog, monkeypatch, toc, [_release("Best Of", "Bajm", 2018, ["A", "B", "C"])])
    _answer(monkeypatch, module.QMessageBox.StandardButton.Ok)
    dialog._start()

    fake_worker[0].finish_successfully()

    assert dialog._disc == 2
    assert dialog.isVisible() or not dialog.result(), "the dialog stays open for the next disc"


def test_stopping_after_a_disc_hands_over_what_was_ripped(dialog, monkeypatch, toc, fake_worker):
    _read(dialog, monkeypatch, toc, [_release("Best Of", "Bajm", 2018, ["A", "B", "C"])])
    _answer(monkeypatch, module.QMessageBox.StandardButton.Cancel)
    dialog._start()

    fake_worker[0].finish_successfully()

    assert dialog._disc == 1
    assert dialog.result_metadata is not None


def test_every_disc_of_a_set_shares_one_folder(dialog, monkeypatch, toc, fake_worker):
    """A second disc identified as its own release would otherwise make a
    second folder, which is two albums rather than one."""
    _read(dialog, monkeypatch, toc, [_release("Best Of", "Bajm", 2018, ["A", "B", "C"])])
    _answer(monkeypatch, module.QMessageBox.StandardButton.Ok)
    dialog._start()
    first_folder = fake_worker[0].plan.folder
    fake_worker[0].finish_successfully()

    # The next disc identifies itself under a title of its own.
    _read(dialog, monkeypatch, toc, [_release("Best Of [Disc 2]", "Bajm", 2018, ["D", "E", "F"])])
    _answer(monkeypatch, module.QMessageBox.StandardButton.Cancel)
    dialog._start()

    assert fake_worker[1].plan.folder == first_folder


def test_the_album_keeps_its_name_across_the_set(dialog, monkeypatch, toc, fake_worker):
    _read(dialog, monkeypatch, toc, [_release("Best Of", "Bajm", 2018, ["A", "B", "C"])])
    _answer(monkeypatch, module.QMessageBox.StandardButton.Ok)
    dialog._start()
    fake_worker[0].finish_successfully()

    # _read_next_disc has already run, with the second disc's own release.
    assert dialog.album_edit.text() == "Best Of"
    assert dialog.artist_edit.text() == "Bajm"


def test_the_result_ends_up_holding_the_whole_set(dialog, monkeypatch, toc, fake_worker):
    """Not just the disc that finished last -- what gets recorded is the
    album."""
    _read(dialog, monkeypatch, toc, [_release("Best Of", "Bajm", 2018, ["A", "B", "C"])])
    _answer(monkeypatch, module.QMessageBox.StandardButton.Ok)
    dialog._start()
    fake_worker[0].finish_successfully()
    _answer(monkeypatch, module.QMessageBox.StandardButton.Cancel)
    dialog._start()

    assert len(fake_worker[0].playlist_paths) == 3
    assert len(fake_worker[1].playlist_paths) == 6
    fake_worker[1].finish_successfully()
    assert len(dialog.result_paths) == 6


def test_the_metadata_handed_on_covers_every_disc(dialog, monkeypatch, toc, fake_worker):
    _read(dialog, monkeypatch, toc, [_release("Best Of", "Bajm", 2018, ["A", "B", "C"])])
    _answer(monkeypatch, module.QMessageBox.StandardButton.Ok)
    dialog._start()
    fake_worker[0].finish_successfully()
    _read(dialog, monkeypatch, toc, [_release("Best Of", "Bajm", 2018, ["D", "E", "F"])])
    _answer(monkeypatch, module.QMessageBox.StandardButton.Cancel)
    dialog._start()
    fake_worker[1].finish_successfully()

    titles = [track.title for track in dialog.result_metadata.tracks]
    assert titles == ["A", "B", "C", "D", "E", "F"]


def test_the_first_disc_is_not_tidied_away_by_the_second(dialog, monkeypatch, toc, tmp_path, fake_worker):
    """This app used to clean up "stale" rip folders before each new disc
    of a set -- removed outright (not just fixed) after it swept up a real
    user's permanently organized albums elsewhere in this same shared
    folder, since a folder of nothing but .flac files looks exactly like a
    stale rip either way. Nothing here may delete anything any more, so
    disc one's own files must still be there once disc two starts."""
    assert not hasattr(cdrip, "clean_stale_rip_folders"), "this must not come back"
    _read(dialog, monkeypatch, toc, [_release("Best Of", "Bajm", 2018, ["A", "B", "C"])])
    _answer(monkeypatch, module.QMessageBox.StandardButton.Ok)
    dialog._start()
    disc_one_folder = dialog.build_plan().folder
    disc_one_folder.mkdir(parents=True, exist_ok=True)
    (disc_one_folder / "01 - A.flac").write_bytes(b"disc one, track one")
    fake_worker[0].finish_successfully()
    _answer(monkeypatch, module.QMessageBox.StandardButton.Cancel)
    dialog._start()

    assert (disc_one_folder / "01 - A.flac").read_bytes() == b"disc one, track one"
