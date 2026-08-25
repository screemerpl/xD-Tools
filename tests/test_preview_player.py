"""PreviewPlayerBar: the one-track-at-a-time audition transport shared by
RecordDialog, TapeRecordDialog and BurnDialog (see preview_player.py's own
docstring for why one widget, wired into three dialogs).

AudioPlayer is faked throughout -- there is no real audio hardware needed
to run this suite, same pattern as test_tape_record_dialog.py's own
_FakePlayer.
"""

from pathlib import Path

import numpy as np
import pytest

from mdtools import audio_engine
from mdtools.panels import preview_player as preview_module
from mdtools.panels.preview_player import PreviewPlayerBar


class _FakePlayer:
    instances: list["_FakePlayer"] = []

    def __init__(self, device=None, gain_db=0.0, samplerate=44100, channels=2):
        self.device = device
        self.gain_db = gain_db
        self.samplerate = samplerate
        self.stopped = False
        self.paused = False
        self.played_buffers = None
        self.on_finished = None
        self.position_seconds = 0.0
        self.seeked_to: float | None = None
        _FakePlayer.instances.append(self)

    def play(self, buffers, on_track_boundary=None, on_finished=None):
        self.played_buffers = buffers
        self.on_finished = on_finished

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

    def seek(self, seconds):
        self.seeked_to = seconds
        self.position_seconds = seconds

    def stop(self):
        self.stopped = True


@pytest.fixture(autouse=True)
def fake_player(monkeypatch):
    _FakePlayer.instances = []
    monkeypatch.setattr(preview_module.audio_engine, "AudioPlayer", _FakePlayer)
    monkeypatch.setattr(
        preview_module.audio_engine,
        "load_for_preview",
        lambda path: (np.zeros(44100 * 4, dtype=np.float32), 44100),  # 4s, fake
    )
    return _FakePlayer


def _bar(qt_app) -> PreviewPlayerBar:
    return PreviewPlayerBar()


# --- selection state -------------------------------------------------------


def test_starts_disabled_with_no_track_selected(qt_app):
    bar = _bar(qt_app)

    assert not bar.play_btn.isEnabled()
    assert not bar.slider.isEnabled()
    assert not bar.prev_btn.isEnabled()
    assert not bar.next_btn.isEnabled()


def test_selecting_a_track_enables_play_and_reflects_prev_next(qt_app):
    bar = _bar(qt_app)

    bar.set_current(Path("a.flac"), has_prev=True, has_next=False)

    assert bar.play_btn.isEnabled()
    assert bar.prev_btn.isEnabled()
    assert not bar.next_btn.isEnabled()


def test_clearing_the_selection_disables_everything_again(qt_app):
    bar = _bar(qt_app)
    bar.set_current(Path("a.flac"), has_prev=False, has_next=True)

    bar.set_current(None)

    assert not bar.play_btn.isEnabled()
    assert not bar.slider.isEnabled()


def test_reselecting_the_same_path_does_not_restart_playback(qt_app):
    """Only prev/next enabled state should refresh -- an unrelated re-fire
    of the selection signal (e.g. after a reorder) must not interrupt
    whatever is already playing."""
    bar = _bar(qt_app)
    bar.set_current(Path("a.flac"), has_prev=False, has_next=True)
    bar._on_play_pause_clicked()
    player = _FakePlayer.instances[-1]

    bar.set_current(Path("a.flac"), has_prev=True, has_next=True)

    assert not player.stopped
    assert bar.prev_btn.isEnabled()  # the refreshed flag did take effect


# --- play / pause -----------------------------------------------------------


def test_pressing_play_decodes_and_plays_the_selected_track(qt_app):
    bar = _bar(qt_app)
    bar.set_current(Path("a.flac"))

    bar._on_play_pause_clicked()

    assert bar.play_btn.text() == "Pause"
    assert _FakePlayer.instances[-1].played_buffers is not None
    assert bar.total_label.text() == "0:04"


def test_pressing_play_again_pauses(qt_app):
    bar = _bar(qt_app)
    bar.set_current(Path("a.flac"))
    bar._on_play_pause_clicked()
    player = _FakePlayer.instances[-1]

    bar._on_play_pause_clicked()

    assert player.paused
    assert bar.play_btn.text() == "Play"


def test_pressing_play_a_third_time_resumes_the_same_player(qt_app):
    bar = _bar(qt_app)
    bar.set_current(Path("a.flac"))
    bar._on_play_pause_clicked()  # play
    bar._on_play_pause_clicked()  # pause
    player = _FakePlayer.instances[-1]

    bar._on_play_pause_clicked()  # resume

    assert not player.paused
    assert bar.play_btn.text() == "Pause"
    assert len(_FakePlayer.instances) == 1  # no new decode/player


def test_a_decode_error_is_shown_without_crashing(qt_app, monkeypatch):
    monkeypatch.setattr(
        preview_module.audio_engine,
        "load_for_preview",
        lambda path: (_ for _ in ()).throw(audio_engine.AudioEngineError("nope")),
    )
    bar = _bar(qt_app)
    bar.set_current(Path("bad.flac"))

    bar._on_play_pause_clicked()

    assert bar.total_label.text() == "Error"
    assert bar.play_btn.text() == "Play"


# --- finishing on its own ---------------------------------------------------


def test_a_track_finishing_resets_to_the_ready_state(qt_app):
    bar = _bar(qt_app)
    bar.set_current(Path("a.flac"))
    bar._on_play_pause_clicked()
    player = _FakePlayer.instances[-1]

    player.on_finished()

    assert bar.play_btn.text() == "Play"
    assert player.stopped
    assert bar.slider.value() == 0


# --- prev / next -------------------------------------------------------------


def test_next_and_prev_buttons_emit_signals(qt_app):
    bar = _bar(qt_app)
    bar.set_current(Path("a.flac"), has_prev=True, has_next=True)
    prev_calls = []
    next_calls = []
    bar.prev_requested.connect(lambda: prev_calls.append(True))
    bar.next_requested.connect(lambda: next_calls.append(True))

    bar.prev_btn.click()
    bar.next_btn.click()

    assert prev_calls == [True]
    assert next_calls == [True]


def test_switching_tracks_while_playing_continues_playback_on_the_new_one(qt_app):
    bar = _bar(qt_app)
    bar.set_current(Path("a.flac"), has_next=True)
    bar._on_play_pause_clicked()
    first_player = _FakePlayer.instances[-1]

    bar.set_current(Path("b.flac"), has_prev=True)

    assert first_player.stopped
    assert len(_FakePlayer.instances) == 2  # a new decode/player for b.flac
    assert bar.play_btn.text() == "Pause"


def test_switching_tracks_while_paused_does_not_autoplay(qt_app):
    bar = _bar(qt_app)
    bar.set_current(Path("a.flac"), has_next=True)
    bar._on_play_pause_clicked()  # play
    bar._on_play_pause_clicked()  # pause

    bar.set_current(Path("b.flac"), has_prev=True)

    assert bar.play_btn.text() == "Play"
    assert len(_FakePlayer.instances) == 1  # b.flac not decoded until Play


# --- the seek slider ---------------------------------------------------------


def test_dragging_the_slider_suppresses_the_timers_own_updates(qt_app, monkeypatch):
    bar = _bar(qt_app)
    bar.set_current(Path("a.flac"))
    bar._on_play_pause_clicked()
    player = _FakePlayer.instances[-1]
    player.position_seconds = 2.0
    monkeypatch.setattr(bar.slider, "isSliderDown", lambda: True)
    bar.slider.setValue(999)

    bar._refresh_position()

    assert bar.slider.value() == 999  # not overwritten by the timer


def test_releasing_the_slider_seeks_the_player(qt_app):
    bar = _bar(qt_app)
    bar.set_current(Path("a.flac"))
    bar._on_play_pause_clicked()
    player = _FakePlayer.instances[-1]
    bar.slider.setValue(500)  # halfway through a 4s track

    bar._on_slider_released()

    assert player.seeked_to == pytest.approx(2.0)


# --- teardown ----------------------------------------------------------------


def test_stop_tears_down_a_live_player_and_resets_the_bar(qt_app):
    bar = _bar(qt_app)
    bar.set_current(Path("a.flac"))
    bar._on_play_pause_clicked()
    player = _FakePlayer.instances[-1]

    bar.stop()

    assert player.stopped
    assert bar.play_btn.text() == "Play"
    assert bar.total_label.text() == "--:--"


def test_stop_before_ever_playing_is_a_no_op(qt_app):
    bar = _bar(qt_app)
    bar.set_current(Path("a.flac"))

    bar.stop()  # must not raise
