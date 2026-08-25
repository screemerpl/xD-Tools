"""The burn dialog, and the two menu entries that fill it.

The worker's run() is called directly rather than started as a thread, the
same way test_cd_rip_dialog.py drives its own: what is being tested is the
order of the stages and which signal comes out, not Qt's threading.
"""

import wave
from pathlib import Path

import pytest
from PySide6.QtWidgets import QFileDialog, QMessageBox

from mdtools import app_settings, audio_engine, cdburn
from mdtools.app_window import MainWindow
from mdtools.panels.burn_dialog import COL_ARTIST, COL_STATUS, COL_TITLE, BurnDialog, _BurnWorker
from mdtools.project import MEDIUM_CD, MEDIUM_MD


class _FakePreviewPlayer:
    """Stands in for audio_engine.AudioPlayer, for the preview bar's own
    use -- not the burn worker's, which never touches AudioPlayer at all
    (it decodes and hands the result straight to cdrecord)."""

    def __init__(self, device=None, gain_db=0.0, samplerate=44100, channels=2):
        self.stopped = False
        self.on_finished = None

    def play(self, buffers, on_track_boundary=None, on_finished=None):
        self.on_finished = on_finished

    def pause(self):
        pass

    def resume(self):
        pass

    def seek(self, seconds):
        pass

    def stop(self):
        self.stopped = True


def _write_wav(path, *, seconds=10.0, rate=44100, channels=2):
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"\x00" * int(rate * seconds) * 2 * channels)
    return path


def _sources(tmp_path, count=2, **kwargs):
    return [
        (_write_wav(tmp_path / f"{i:02d}.wav", **kwargs), f"Track {i}", "Artist")
        for i in range(1, count + 1)
    ]


@pytest.fixture
def burnable(monkeypatch):
    """A machine with cdrecord and a burner in it."""
    monkeypatch.setattr(cdburn, "cdrecord_path", lambda: "cdrecord")
    monkeypatch.setattr(cdburn, "missing_tools", lambda: [])
    monkeypatch.setattr(
        cdburn, "list_burners", lambda: [cdburn.Burner(device="1,0,0", description="ASUS BW-16D1HT")]
    )


# -- what the dialog shows before anything is written --------------------


def test_each_track_gets_a_verdict_before_the_button(qt_app, tmp_path, burnable):
    """A surround file is a wall -- audio_engine deliberately doesn't mix
    channels -- and the button has to say so rather than let a disc be
    spent finding out."""
    sources = _sources(tmp_path, 1) + [
        (_write_wav(tmp_path / "surround.wav", rate=48000, channels=6), "Surround", "A")
    ]
    dialog = BurnDialog(sources, album="Album", artist="Artist")

    assert dialog.table.item(0, COL_STATUS).text() == "OK"
    assert "48000" in dialog.table.item(1, COL_STATUS).text()
    assert dialog.burn_button.isEnabled() is False, "a disc that cannot be written must not offer to be"


def test_a_track_that_will_be_converted_says_so_without_blocking_the_burn(qt_app, tmp_path, burnable):
    sources = _sources(tmp_path, 1) + [(_write_wav(tmp_path / "hi.wav", rate=48000), "Hi-res", "A")]

    dialog = BurnDialog(sources, album="Album", artist="Artist")

    assert "converted" in dialog.table.item(1, COL_STATUS).text()
    assert dialog.burn_button.isEnabled() is True


def test_the_summary_shows_the_length_against_the_disc(qt_app, tmp_path, burnable):
    dialog = BurnDialog(_sources(tmp_path, 3), album="Album", artist="Artist")

    assert "80:00" in dialog.summary_label.text()
    assert "0:32" in dialog.summary_label.text()  # 3 x 10s plus the 2s lead-in


def test_characters_cd_text_cannot_carry_are_named_up_front(qt_app, tmp_path, burnable):
    """The same promise the MiniDisc upload dialog makes -- and the same
    transliterator underneath."""
    dialog = BurnDialog([(_write_wav(tmp_path / "a.wav"), "君の名は", "Artist")], album="A", artist="B")

    assert "CD-Text" in dialog.summary_label.text()


def test_a_missing_tool_does_not_hide_what_the_plan_says(qt_app, tmp_path, monkeypatch):
    monkeypatch.setattr(cdburn, "missing_tools", lambda: ["cdrecord"])
    monkeypatch.setattr(cdburn, "list_burners", lambda: [])

    dialog = BurnDialog(_sources(tmp_path, 2), album="Album", artist="Artist")

    assert "cdrecord" in dialog.tools_label.text()
    assert "80:00" in dialog.summary_label.text()
    assert dialog.burn_button.isEnabled() is False


# -- what is on screen is what gets written ------------------------------


def test_an_edited_title_is_what_reaches_the_disc(qt_app, tmp_path, burnable):
    dialog = BurnDialog(_sources(tmp_path, 2), album="Album", artist="Artist")
    dialog.table.item(0, COL_TITLE).setText("Corrected Title")
    dialog.table.item(0, COL_ARTIST).setText("Corrected Artist")

    plan = dialog.build_plan()

    assert plan.tracks[0].title == "Corrected Title"
    # and it is what cdrecord will read out of the .inf file as CD-Text
    assert "Tracktitle=\t'Corrected Title'" in cdburn.inf_text(plan, 1)
    assert dialog.metadata().tracks[0].artist == "Corrected Artist"


def test_an_emptied_title_falls_back_to_the_filename(qt_app, tmp_path, burnable):
    """A disc of blank track names is worse than one named after its
    files."""
    dialog = BurnDialog(_sources(tmp_path, 1), album="Album", artist="Artist")
    dialog.table.item(0, COL_TITLE).setText("   ")

    assert dialog.build_plan().tracks[0].title == "01"


def test_the_metadata_handed_on_is_the_album_as_edited(qt_app, tmp_path, burnable):
    dialog = BurnDialog(_sources(tmp_path, 2), album="Wrong", artist="Artist", year=2016)
    dialog.album_edit.setText("Unleashed")

    metadata = dialog.metadata()

    assert (metadata.album, metadata.artist, metadata.year) == ("Unleashed", "Artist", 2016)
    assert [track.title for track in metadata.tracks] == ["Track 1", "Track 2"]


def test_burning_without_a_burner_says_so_and_starts_nothing(qt_app, tmp_path, monkeypatch):
    monkeypatch.setattr(cdburn, "missing_tools", lambda: [])
    monkeypatch.setattr(cdburn, "list_burners", lambda: [])
    warned = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: warned.append(args))
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *a, **k: pytest.fail("nothing should be confirmed when there is no drive"),
    )

    dialog = BurnDialog(_sources(tmp_path, 1), album="Album", artist="Artist")
    dialog._start()

    assert warned
    assert dialog._worker is None


def test_starting_a_real_burn_asks_first_and_says_it_cannot_be_undone(qt_app, tmp_path, burnable, monkeypatch):
    asked = []

    def fake_question(parent, title, text, *args, **kwargs):
        asked.append(text)
        return QMessageBox.StandardButton.Cancel

    monkeypatch.setattr(QMessageBox, "question", fake_question)

    dialog = BurnDialog(_sources(tmp_path, 2), album="Album", artist="Artist")
    dialog._start()

    assert asked and "cannot be rewritten" in asked[0]
    assert dialog._worker is None, "cancelling the question must not start anything"


def test_a_simulated_run_is_not_described_as_writing_a_disc(qt_app, tmp_path, burnable, monkeypatch):
    asked = []
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda parent, title, text, *a, **k: (asked.append(text), QMessageBox.StandardButton.Cancel)[1],
    )

    dialog = BurnDialog(_sources(tmp_path, 1), album="Album", artist="Artist")
    dialog.simulate_check.setChecked(True)
    dialog._start()

    assert asked and "Nothing will be written" in asked[0]


# -- the audition preview bar (#18) ---------------------------------------


def test_selecting_a_track_enables_the_preview_bar_with_correct_prev_next(qt_app, tmp_path, burnable):
    dialog = BurnDialog(_sources(tmp_path, 3), album="Album", artist="Artist")

    dialog.table.setCurrentCell(0, 0)
    assert dialog.preview_bar.play_btn.isEnabled()
    assert not dialog.preview_bar.prev_btn.isEnabled()
    assert dialog.preview_bar.next_btn.isEnabled()

    dialog.table.setCurrentCell(2, 0)
    assert dialog.preview_bar.prev_btn.isEnabled()
    assert not dialog.preview_bar.next_btn.isEnabled()


def test_starting_the_burn_stops_any_playing_preview(qt_app, tmp_path, burnable, monkeypatch):
    monkeypatch.setattr(audio_engine, "AudioPlayer", _FakePreviewPlayer)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Ok)
    dialog = BurnDialog(_sources(tmp_path, 2), album="Album", artist="Artist")
    # _burn_current_disc() spins up the real worker/scratch-folder machinery
    # -- out of scope here, which is only checking that preview_bar.stop()
    # is reached once the confirmation is accepted.
    monkeypatch.setattr(dialog, "_burn_current_disc", lambda: None)
    dialog.table.setCurrentCell(0, 0)
    dialog.preview_bar._on_play_pause_clicked()
    preview_player_instance = dialog.preview_bar._player
    assert preview_player_instance is not None

    dialog._start()

    assert preview_player_instance.stopped


# -- the worker ----------------------------------------------------------


def _plan(tmp_path, count=2):
    return cdburn.build_burn_plan(_sources(tmp_path, count), album="Album", artist="Artist")


def test_the_worker_decodes_then_writes_then_reports_success(qt_app, tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        cdburn, "prepare_wavs", lambda plan, directory, **kwargs: (calls.append("decode"), ["01.wav"])[1]
    )
    monkeypatch.setattr(cdburn, "write_inf_files", lambda plan, directory: ["01.inf"])
    monkeypatch.setattr(cdburn, "burn", lambda *args, **kwargs: calls.append("burn"))

    worker = _BurnWorker(_plan(tmp_path), "1,0,0", tmp_path, speed=8, simulate=False, eject=True)
    stages, succeeded = [], []
    worker.stage.connect(stages.append)
    worker.succeeded.connect(lambda: succeeded.append(True))
    worker.run()

    assert calls == ["decode", "burn"]
    assert stages == ["decode", "burn"]
    assert succeeded == [True]


def test_progress_and_stage_are_mirrored_out_for_the_main_windows_own_bar(qt_app, tmp_path):
    """#27. A stage change carries the *last known* fraction with it:
    decode->burn rewrites the status text without necessarily arriving
    with a fresh progress tick, and a bar that snapped back to 0 there
    would read as the burn having restarted."""
    dialog = BurnDialog(_sources(tmp_path, 2), album="Album", artist="Artist")
    seen: list = []
    dialog.overall_progress_changed.connect(lambda f, t: seen.append((f, t)))

    dialog._on_stage("decode")
    dialog._on_progress(0.4)
    dialog._on_stage("burn")

    assert seen[0] == (0.0, dialog.tr("Preparing audio..."))
    assert seen[1][0] == pytest.approx(0.4)
    # The stage change kept the fraction it already had.
    assert seen[2][0] == pytest.approx(0.4)
    assert seen[2][1] == dialog.stage_label.text()


def test_running_changed_follows_the_single_place_a_burn_starts_and_stops(qt_app, tmp_path):
    """_set_running() is the one choke point both _burn_current_disc()
    and _on_worker_finished() already go through, so a multi-disc burn
    gets the bar back between discs for free."""
    dialog = BurnDialog(_sources(tmp_path, 2), album="Album", artist="Artist")
    seen: list[bool] = []
    dialog.running_changed.connect(seen.append)

    dialog._set_running(True)
    dialog._set_running(False)

    assert seen == [True, False]


def test_the_worker_reports_a_failure_rather_than_raising(qt_app, tmp_path, monkeypatch):
    monkeypatch.setattr(cdburn, "prepare_wavs", lambda *a, **k: ["01.wav"])
    monkeypatch.setattr(cdburn, "write_inf_files", lambda *a, **k: ["01.inf"])

    def fail(*args, **kwargs):
        raise cdburn.BurnError("Cannot open SCSI device")

    monkeypatch.setattr(cdburn, "burn", fail)

    worker = _BurnWorker(_plan(tmp_path), "1,0,0", tmp_path, speed=8, simulate=False, eject=True)
    failures = []
    worker.failed.connect(failures.append)
    worker.run()

    assert failures == ["Cannot open SCSI device"]


def test_cancelling_during_the_decode_stage_costs_nothing(qt_app, tmp_path, monkeypatch):
    """No disc has been touched at that point -- only a scratch folder."""
    burned = []

    def cancel_immediately(plan, directory, *, on_progress=None, should_cancel=None, **kwargs):
        assert should_cancel is not None and should_cancel()
        raise cdburn.BurnCancelled()

    monkeypatch.setattr(cdburn, "prepare_wavs", cancel_immediately)
    monkeypatch.setattr(cdburn, "burn", lambda *a, **k: burned.append(True))

    worker = _BurnWorker(_plan(tmp_path), "1,0,0", tmp_path, speed=8, simulate=False, eject=True)
    cancelled = []
    worker.cancelled.connect(lambda: cancelled.append(True))
    worker.cancel()
    worker.run()

    assert cancelled == [True]
    assert burned == [], "the drive must never be reached once the run was cancelled"


def test_stopping_asks_about_the_disc_and_does_not_wait_on_the_worker(qt_app, tmp_path, burnable, monkeypatch):
    """reject() must never block the GUI thread on a worker -- that is what
    froze the MDRem upload dialog once already."""

    class BusyWorker:
        def __init__(self):
            self.cancelled = False

        def cancel(self):
            self.cancelled = True

        def wait(self, *args):
            raise AssertionError("reject() must not wait on the worker")

    dialog = BurnDialog(_sources(tmp_path, 1), album="Album", artist="Artist")
    worker = BusyWorker()
    dialog._worker = worker

    asked = []
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda parent, title, text, *a, **k: (asked.append(text), QMessageBox.StandardButton.Ok)[1],
    )
    dialog.reject()

    assert asked and "unfinished" in asked[0]
    assert worker.cancelled is True

    dialog._worker = None  # so the dialog can be torn down normally


def test_declining_the_stop_question_leaves_the_burn_running(qt_app, tmp_path, burnable, monkeypatch):
    class BusyWorker:
        cancelled = False

        def cancel(self):
            type(self).cancelled = True

    dialog = BurnDialog(_sources(tmp_path, 1), album="Album", artist="Artist")
    dialog._worker = BusyWorker()
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Cancel)

    dialog.reject()

    assert BusyWorker.cancelled is False
    dialog._worker = None


# -- the menu entries ----------------------------------------------------


def test_burning_from_a_folder_reads_the_files_tags(qt_app, tmp_path, monkeypatch):
    folder = tmp_path / "Skillet - Unleashed (2016)"
    folder.mkdir()
    _write_wav(folder / "01 One.wav")
    _write_wav(folder / "02 Two.wav")

    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(folder))
    captured = {}

    def fake_run(self, sources, *, album, artist, year):
        captured["sources"] = sources
        captured["album"] = album

    monkeypatch.setattr(MainWindow, "_run_burn_dialog", fake_run)

    MainWindow(show_startup_dialog=False)._burn_cd_from_folder()

    assert [Path(path).name for path, _t, _a in captured["sources"]] == ["01 One.wav", "02 Two.wav"]
    # untagged WAVs: the folder name is the only thing left to go on
    assert captured["album"] == "Unleashed"


def test_an_empty_folder_says_so_rather_than_opening_an_empty_dialog(qt_app, tmp_path, monkeypatch):
    folder = tmp_path / "nothing"
    folder.mkdir()
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(folder))
    warned = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: warned.append(args))
    monkeypatch.setattr(
        MainWindow, "_run_burn_dialog", lambda *a, **k: pytest.fail("nothing to burn, nothing to show")
    )

    MainWindow(show_startup_dialog=False)._burn_cd_from_folder()

    assert warned


def test_a_written_disc_offers_its_details_to_an_open_cd_project(qt_app, tmp_path, monkeypatch, burnable):
    window = MainWindow(show_startup_dialog=False)
    window.project.medium = MEDIUM_CD

    def fake_exec(self):
        self.result_metadata = self.metadata()
        return BurnDialog.DialogCode.Accepted

    monkeypatch.setattr(BurnDialog, "exec", fake_exec)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Ok)

    window._run_burn_dialog(_sources(tmp_path, 2), album="Unleashed", artist="Skillet", year=2016)

    assert window.project.metadata.album == "Unleashed"
    assert len(window.project.metadata.tracks) == 2


def test_a_minidisc_project_is_left_alone_by_a_cd_burn(qt_app, tmp_path, monkeypatch, burnable):
    """Burning is reachable with any project open, including one that has
    nothing to do with the disc."""
    window = MainWindow(show_startup_dialog=False)
    window.project.medium = MEDIUM_MD
    window.project.metadata.album = "Some MiniDisc"

    monkeypatch.setattr(
        BurnDialog,
        "exec",
        lambda self: (setattr(self, "result_metadata", self.metadata()), BurnDialog.DialogCode.Accepted)[1],
    )
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: pytest.fail("an unrelated project must not be asked about")
    )

    window._run_burn_dialog(_sources(tmp_path, 1), album="Unleashed", artist="Skillet", year=2016)

    assert window.project.metadata.album == "Some MiniDisc"


def test_the_burn_work_folder_sits_under_the_configured_rip_folder(qt_app, tmp_path, monkeypatch, burnable):
    """Scratch WAVs are raw material, like a rip -- they belong wherever the
    user pointed that, not next to their music."""
    monkeypatch.setattr(app_settings, "cd_rip_folder", lambda: str(tmp_path / "scratch"))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Ok)

    started = {}

    class _Anything:
        """Stands in for both a signal (connect) and a method (call)."""

        def __call__(self, *args, **kwargs):
            return None

        def connect(self, *args, **kwargs):
            return None

    class FakeWorker:
        def __init__(self, plan, device, work_dir, **kwargs):
            started["work_dir"] = work_dir

        def __getattr__(self, name):
            return _Anything()

    monkeypatch.setattr("mdtools.panels.burn_dialog._BurnWorker", FakeWorker)

    dialog = BurnDialog(_sources(tmp_path, 1), album="Album", artist="Artist")
    dialog._start()

    assert started["work_dir"] == tmp_path / "scratch" / "burn"
