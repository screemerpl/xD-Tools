"""Recording onto a cassette: the split, the leader silence, and the flip.

AudioPlayer is faked throughout (see _FakePlayer). There is no deck to
fake -- that is the point of this medium: xD-Tools plays the tracks and
tells the user what to press, and the only thing it can get wrong is
*when*.
"""

import pytest
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
        tape_module.audio_engine, "load_for_playback", lambda paths, samplerate=None: [None] * len(paths)
    )


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


def test_nothing_plays_until_the_leader_silence_has_run(qt_app, monkeypatch):
    dialog = _dialog(_items(4), monkeypatch)

    dialog._on_start_clicked()

    assert dialog._player.played_buffers is None
    assert str(tape.LEADER_SECONDS) in dialog.status_label.text()
    _run_countdown(dialog)
    assert dialog._player.played_buffers == [None, None]  # side A: tracks 1-2


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


# --- cancelling --------------------------------------------------------------


def test_stopping_mid_recording_stops_playback(qt_app, monkeypatch):
    dialog = _dialog(_items(4), monkeypatch)
    dialog._on_start_clicked()
    _run_countdown(dialog)

    dialog.reject()

    assert dialog._player.stopped
