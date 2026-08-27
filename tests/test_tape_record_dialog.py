"""Recording onto a cassette: the split, the leader silence, and the flip.

AudioPlayer is faked throughout (see _FakePlayer). There is no deck to
fake -- that is the point of this medium: xD-Tools plays the tracks and
tells the user what to press, and the only thing it can get wrong is
*when*.
"""

from pathlib import Path

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QMessageBox

from mdtools import tape, tracks
from mdtools.panels import tape_record_dialog as tape_module
from mdtools.panels.tape_record_dialog import TapeRecordDialog


class _FakePlayer:
    def __init__(self, device=None, gain_db=0.0, samplerate=44100, channels=2):
        self.gain_db = gain_db
        self.samplerate = samplerate
        self.stopped = False
        self.played_buffers = None
        self.on_track_boundary = None
        self.on_finished = None
        self.position_seconds = 0.0

    def play(self, buffers, on_track_boundary=None, on_finished=None):
        self.played_buffers = buffers
        self.on_track_boundary = on_track_boundary
        self.on_finished = on_finished

    def stop(self):
        self.stopped = True


def _items(count: int, seconds: int = 300) -> list[tracks.PlaylistItem]:
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


@pytest.fixture(autouse=True)
def no_cover_lookup(monkeypatch):
    monkeypatch.setattr(tape_module, "fetch_into", lambda *a, **k: None)


@pytest.fixture(autouse=True)
def no_modal_dialogs(monkeypatch):
    """A real .exec() blocks forever offscreen -- and the overwrite warning
    is on the path every recording test takes."""
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))


@pytest.fixture(autouse=True)
def fake_player(monkeypatch):
    """Never let a test reach sounddevice or a real file decode."""
    monkeypatch.setattr(tape_module.audio_engine, "AudioPlayer", _FakePlayer)
    monkeypatch.setattr(tape_module.audio_engine, "resolve_output_device", lambda name: None)
    monkeypatch.setattr(
        tape_module.audio_engine, "load_for_playback", lambda paths, **kwargs: [None] * len(paths)
    )


class _SyncDecoder(QObject):
    """DecodeWorker, minus the thread.

    Decoding a side runs on a QThread now -- doing it on the GUI thread
    froze the window for the whole of it -- so start() here decodes and
    emits inline instead, leaving every test below to assert on the real
    sequence with the waiting taken out."""

    progress = Signal(int, int, str)
    decoded = Signal(object)
    failed = Signal(str)
    finished = Signal()

    instances: list["_SyncDecoder"] = []

    def __init__(self, paths, *, samplerate, dithered, parent=None):
        super().__init__()
        self.paths = list(paths)
        self.samplerate = samplerate
        self.dithered = dithered
        self.cancelled = False
        self.started = False
        _SyncDecoder.instances.append(self)

    def cancel(self):
        self.cancelled = True

    def isRunning(self):
        return self.started and not self.cancelled

    def start(self):
        self.started = True
        try:
            buffers = tape_module.audio_engine.load_for_playback(
                self.paths, samplerate=self.samplerate, on_progress=self._progress
            )
        except tape_module.audio_engine.AudioEngineError as exc:
            self.failed.emit(str(exc))
        else:
            self.decoded.emit(buffers)
        self.finished.emit()

    def _progress(self, index, total, path):
        self.progress.emit(index, total, Path(path).stem)


@pytest.fixture(autouse=True)
def sync_decoder(monkeypatch):
    _SyncDecoder.instances.clear()
    monkeypatch.setattr(tape_module, "DecodeWorker", _SyncDecoder)
    return _SyncDecoder.instances


def _dialog(items: list[tracks.PlaylistItem], monkeypatch, **kwargs) -> TapeRecordDialog:
    monkeypatch.setattr(tape_module.tracks, "playlist_items_from_paths", lambda paths: items)
    return TapeRecordDialog([item.path for item in items] or [], **kwargs)


def _run_countdown(dialog: TapeRecordDialog) -> None:
    """The leader silence, without waiting ten real seconds for it."""
    while dialog._remaining > 0:
        dialog._tick()


# --- preflight -------------------------------------------------------------


def test_the_album_is_listed_and_split_into_two_sides(qt_app, monkeypatch):
    dialog = _dialog(_items(6, seconds=300), monkeypatch)

    assert dialog.tree.topLevelItemCount() == 6
    sides = [dialog.tree.topLevelItem(i).text(0) for i in range(6)]
    assert sides == ["A", "A", "A", "B", "B", "B"]
    assert "Side A" in dialog.fit_label.text()


def test_no_tracks_cannot_be_recorded(qt_app, monkeypatch):
    assert not _dialog([], monkeypatch).start_btn.isEnabled()


def test_a_shorter_tape_moves_the_side_break(qt_app, monkeypatch):
    dialog = _dialog(_items(8, seconds=300), monkeypatch)  # 40 minutes

    dialog._select_length(90)
    long_break = [dialog.tree.topLevelItem(i).text(0) for i in range(8)].count("A")
    dialog._select_length(46)
    short_break = [dialog.tree.topLevelItem(i).text(0) for i in range(8)].count("A")

    assert short_break <= long_break
    assert dialog.total_minutes == 46


def test_an_album_too_long_for_the_chosen_tape_says_so_without_refusing(qt_app, monkeypatch):
    dialog = _dialog(_items(6, seconds=600), monkeypatch)  # an hour

    dialog._select_length(46)

    assert "longer cassette" in dialog.fit_label.text()
    assert dialog.start_btn.isEnabled(), "it is the user's tape and the user's call"


# --- side A ----------------------------------------------------------------


def test_the_initial_instruction_says_to_press_record_and_pause(qt_app, monkeypatch):
    """Reported directly: nothing told the user to arm the deck into
    record-*pause* specifically (only "put it into record"), so it wasn't
    clear the deck should be armed but not yet moving at this point."""
    dialog = _dialog(_items(4, seconds=300), monkeypatch)

    assert "PAUSE" in dialog.instruction_label.text()
    assert "record-pause" in dialog.instruction_label.text()


def test_finishing_decode_tells_the_user_to_release_pause(qt_app, monkeypatch):
    """Reported directly: after the files finished decoding to WAV, nothing
    told the user this was the moment to take the deck off pause -- the
    instruction label was left showing the stale "arm it" text from before
    Start was even clicked."""
    dialog = _dialog(_items(4, seconds=300), monkeypatch)

    dialog._on_start_clicked()

    assert "Release Pause" in dialog.instruction_label.text()


def test_finishing_decode_pops_up_a_dialog_to_release_pause(qt_app, monkeypatch):
    """Reported directly a second time: the label-only version above was
    too easy to miss ("no popup, it just goes straight into the
    countdown") -- this now also blocks with a real QMessageBox, which the
    no_modal_dialogs fixture stubs out; this test replaces that stub with
    a spy to prove the call actually happens."""
    calls = []
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: calls.append(a)))
    dialog = _dialog(_items(4, seconds=300), monkeypatch)

    dialog._on_start_clicked()

    assert len(calls) == 1
    assert "Release Pause" in calls[0][-1]


def test_side_bs_own_instruction_also_says_to_press_record_and_pause(qt_app, monkeypatch):
    dialog = _dialog(_items(4, seconds=300), monkeypatch)
    dialog._on_start_clicked()
    _run_countdown(dialog)

    dialog._on_side_finished()

    assert "PAUSE" in dialog.instruction_label.text()
    assert "record-pause" in dialog.instruction_label.text()


def test_nothing_plays_until_the_leader_silence_has_run(qt_app, monkeypatch):
    dialog = _dialog(_items(4), monkeypatch)

    dialog._on_start_clicked()

    assert dialog._player.played_buffers is None
    assert str(tape.LEADER_SECONDS) in dialog.status_label.text()
    _run_countdown(dialog)
    assert dialog._player.played_buffers == [None, None]  # side A: tracks 1-2


def test_decode_progress_updates_the_status_label(qt_app, monkeypatch):
    """Decoding a side up front (see _on_start_clicked) can take a few real
    seconds -- without this, that gap reads as the dialog having hung."""
    dialog = _dialog(_items(4), monkeypatch)

    dialog._report_decode_progress(1, 2, "01 Track")

    text = dialog.status_label.text()
    assert "1" in text
    assert "2" in text
    assert "01 Track" in text


def test_the_side_is_decoded_on_a_worker_thread(qt_app, monkeypatch):
    """Reported against the MiniDisc dialog, which does the same work with
    dither on top: decoding on the GUI thread froze the window for the
    whole of it. A side is a real stretch of soxr work too."""
    from PySide6.QtCore import QThread

    from mdtools.panels.decode_worker import DecodeWorker

    assert issubclass(DecodeWorker, QThread)

    dialog = _dialog(_items(4), monkeypatch)
    dialog._on_start_clicked()

    decoder = _SyncDecoder.instances[-1]
    assert decoder.dithered is False, "a cassette's analogue line-out needs no dither"
    assert [Path(p) for p in decoder.paths] == [Path(f"/music/{i:02d}.flac") for i in (1, 2)]


def test_stopping_mid_decode_cancels_it_and_never_starts_the_countdown(qt_app, monkeypatch):
    """Nothing has been played and the user has not been told to release
    Pause yet, so stopping here is silent -- but the worker still has to be
    cancelled rather than left running with nobody holding it."""
    dialog = _dialog(_items(4), monkeypatch)

    class _NeverFinishes(_SyncDecoder):
        def start(self):
            self.started = True  # and emits nothing: still decoding

    monkeypatch.setattr(tape_module, "DecodeWorker", _NeverFinishes)

    dialog._on_start_clicked()
    assert dialog.is_busy(), "a running decode worker counts as busy"

    dialog.reject()

    assert _SyncDecoder.instances[-1].cancelled is True
    assert dialog._recording is False
    assert dialog._remaining == 0, "the leader countdown never started"


def test_starting_a_side_builds_the_player_with_the_configured_gain(qt_app, monkeypatch):
    monkeypatch.setattr(tape_module.app_settings, "recording_gain_db", lambda: -5.0)
    dialog = _dialog(_items(4), monkeypatch)

    dialog._on_start_clicked()

    assert dialog._player.gain_db == -5.0


def test_the_fields_are_frozen_once_the_tape_is_rolling(qt_app, monkeypatch):
    dialog = _dialog(_items(4), monkeypatch)

    dialog._on_start_clicked()

    assert not dialog.album_edit.isEnabled()
    assert not dialog.length_combo.isEnabled(), "the split is already half recorded"


# --- the flip --------------------------------------------------------------


def test_the_end_of_side_a_asks_for_the_tape_to_be_turned_over(qt_app, monkeypatch):
    dialog = _dialog(_items(4, seconds=300), monkeypatch)
    dialog._on_start_clicked()
    _run_countdown(dialog)

    dialog._on_side_finished()

    assert dialog.result_metadata is None, "half a recording is not a recording"
    assert "turn it over" in dialog.instruction_label.text()
    assert dialog.start_btn.isEnabled()


def test_side_b_starts_at_the_track_the_break_fell_on(qt_app, monkeypatch):
    dialog = _dialog(_items(4, seconds=300), monkeypatch)
    dialog._on_start_clicked()
    _run_countdown(dialog)
    dialog._on_side_finished()

    dialog._on_start_clicked()
    _run_countdown(dialog)

    assert dialog._side_bounds() == (2, 3)


def test_both_sides_recorded_reports_the_album_back(qt_app, monkeypatch):
    dialog = _dialog(_items(4, seconds=300), monkeypatch)

    for _ in range(2):
        dialog._on_start_clicked()
        _run_countdown(dialog)
        dialog._on_side_finished()

    assert dialog.result_metadata is not None
    assert [t.title for t in dialog.result_metadata.tracks] == [f"Track {i}" for i in range(1, 5)]
    assert "Both sides" in dialog.instruction_label.text()


def test_the_bridge_actually_delivers_the_finished_signal(qt_app, monkeypatch):
    """End-to-end through PlaybackBridge rather than calling
    _on_side_finished directly, proving the wiring in __init__/
    _begin_playback is real."""
    dialog = _dialog(_items(4, seconds=300), monkeypatch)
    dialog._on_start_clicked()
    _run_countdown(dialog)

    dialog._player.on_finished()

    assert not dialog._recording, "the bridge's finished signal reached _on_side_finished"


# --- progress --------------------------------------------------------------


def test_progress_follows_the_position_within_the_side(qt_app, monkeypatch):
    dialog = _dialog(_items(4, seconds=300), monkeypatch)
    dialog._on_start_clicked()
    _run_countdown(dialog)

    dialog._player.position_seconds = 50.0
    dialog._refresh_progress()
    early = dialog.progress.value()

    dialog._player.on_track_boundary(1)
    dialog._player.position_seconds = 10.0
    dialog._refresh_progress()

    assert dialog.progress.value() > early
    assert "Track 2" in dialog.status_label.text()


def test_progress_is_mirrored_out_for_the_main_windows_own_bar(qt_app, monkeypatch):
    """#27, and the same rule RecordDialog follows: what the dialog draws
    for itself is exactly what goes out to MainWindow's bottom bar."""
    dialog = _dialog(_items(4, seconds=300), monkeypatch)
    overall: list = []
    per_track: list = []
    dialog.overall_progress_changed.connect(lambda f, t: overall.append((f, t)))
    dialog.track_progress_changed.connect(lambda f, t: per_track.append((f, t)))

    dialog._on_start_clicked()
    _run_countdown(dialog)
    dialog._player.position_seconds = 75.0
    dialog._refresh_progress()

    assert overall and per_track
    assert overall[-1][1] == dialog.status_label.text()
    # A quarter into a 300-second track, whatever the side adds up to.
    assert per_track[-1][0] == pytest.approx(0.25)
    assert "Track 1" in per_track[-1][1]


def test_running_changed_reports_each_side_starting_and_ending(qt_app, monkeypatch):
    """Unlike RecordDialog's disc-to-disc titling, nothing happens
    between sides on its own -- the user has to turn the tape over and
    press Start again, so the bar goes away in between."""
    dialog = _dialog(_items(4, seconds=300), monkeypatch)
    seen: list[bool] = []
    dialog.running_changed.connect(seen.append)

    dialog._on_start_clicked()
    _run_countdown(dialog)
    assert seen == [True]

    dialog._on_side_finished()
    assert seen == [True, False]


# --- cancelling --------------------------------------------------------------


def test_stopping_mid_recording_stops_playback(qt_app, monkeypatch):
    dialog = _dialog(_items(4), monkeypatch)
    dialog._on_start_clicked()
    _run_countdown(dialog)

    dialog.reject()

    assert dialog._player.stopped


# --- the audition preview bar (#18) -----------------------------------------


def test_selecting_a_track_enables_the_preview_bar_with_correct_prev_next(qt_app, monkeypatch):
    dialog = _dialog(_items(4, seconds=300), monkeypatch)

    dialog.tree.setCurrentItem(dialog.tree.topLevelItem(0))
    assert dialog.preview_bar.play_btn.isEnabled()
    assert not dialog.preview_bar.prev_btn.isEnabled()
    assert dialog.preview_bar.next_btn.isEnabled()

    dialog.tree.setCurrentItem(dialog.tree.topLevelItem(3))
    assert dialog.preview_bar.prev_btn.isEnabled()
    assert not dialog.preview_bar.next_btn.isEnabled()


def test_starting_a_side_stops_any_playing_preview(qt_app, monkeypatch):
    monkeypatch.setattr(tape_module.audio_engine, "load_for_preview", lambda path: ([0.0] * 10, 44100))
    dialog = _dialog(_items(4, seconds=300), monkeypatch)
    dialog.tree.setCurrentItem(dialog.tree.topLevelItem(0))
    dialog.preview_bar._on_play_pause_clicked()
    preview_player_instance = dialog.preview_bar._player
    assert preview_player_instance is not None

    dialog._on_start_clicked()

    assert preview_player_instance.stopped


def test_rejecting_the_dialog_stops_any_playing_preview(qt_app, monkeypatch):
    monkeypatch.setattr(tape_module.audio_engine, "load_for_preview", lambda path: ([0.0] * 10, 44100))
    dialog = _dialog(_items(4, seconds=300), monkeypatch)
    dialog.tree.setCurrentItem(dialog.tree.topLevelItem(0))
    dialog.preview_bar._on_play_pause_clicked()
    preview_player_instance = dialog.preview_bar._player
    assert preview_player_instance is not None

    dialog.reject()

    assert preview_player_instance.stopped
