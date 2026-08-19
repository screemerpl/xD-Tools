"""Recording onto a cassette: the split, the leader silence, and the flip.

foobar2000 is faked throughout. There is no deck to fake -- that is the
point of this medium: MDTools plays the tracks and tells the user what to
press, and the only thing it can get wrong is *when*.
"""

import pytest
from PySide6.QtWidgets import QMessageBox

from mdtools import foobar, tape
from mdtools.panels import tape_record_dialog as tape_module
from mdtools.panels.tape_record_dialog import TapeRecordDialog


class FakeClient:
    def __init__(self, items=None, error: Exception | None = None):
        self._items = items if items is not None else []
        self._error = error
        self.prepared = False
        self.stopped = False
        self.volume_set = None
        self.played: tuple[str, int] | None = None
        self.stop_after: list[bool] = []
        self.state = foobar.PlayerState(foobar.STOPPED, "", -1, 0.0, 0.0)

    def current_playlist(self):
        if self._error:
            raise self._error
        return foobar.Playlist(id="p1", title="Default Playlist", item_count=len(self._items), is_current=True)

    def playlist_items(self, playlist_id, limit=500):
        if self._error:
            raise self._error
        return self._items

    def player_state(self):
        return self.state

    def prepare_for_recording(self):
        self.prepared = True

    def set_volume(self, db):
        self.volume_set = db

    def set_stop_after_current_track(self, stop):
        self.stop_after.append(stop)

    def stop(self):
        self.stopped = True

    def play(self, playlist_id, index):
        self.played = (playlist_id, index)
        self.state = foobar.PlayerState(foobar.PLAYING, playlist_id, index, 0.0, 200.0)

    def playing(self, index, position=0.0):
        self.state = foobar.PlayerState(foobar.PLAYING, "p1", index, position, 200.0)

    def ended(self):
        self.state = foobar.PlayerState(foobar.STOPPED, "p1", -1, 0.0, 0.0)


def _items(count: int, seconds: int = 300) -> list[foobar.PlaylistItem]:
    return [
        foobar.PlaylistItem.from_columns([f"{i:02d}", f"Track {i}", "Artist", "Album", "2024", str(seconds)])
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


def _dialog(client: FakeClient, monkeypatch, **kwargs) -> TapeRecordDialog:
    monkeypatch.setattr(tape_module.foobar, "FoobarClient", lambda *a, **k: client)
    return TapeRecordDialog(**kwargs)


def _run_countdown(dialog: TapeRecordDialog) -> None:
    """The leader silence, without waiting ten real seconds for it."""
    while dialog._remaining > 0:
        dialog._tick()


# --- preflight -------------------------------------------------------------


def test_the_playlist_is_listed_and_split_into_two_sides(qt_app, monkeypatch):
    dialog = _dialog(FakeClient(_items(6, seconds=300)), monkeypatch)

    assert dialog.tree.topLevelItemCount() == 6
    sides = [dialog.tree.topLevelItem(i).text(0) for i in range(6)]
    assert sides == ["A", "A", "A", "B", "B", "B"]
    assert "Side A" in dialog.fit_label.text()


def test_an_empty_playlist_cannot_be_recorded(qt_app, monkeypatch):
    assert not _dialog(FakeClient([]), monkeypatch).start_btn.isEnabled()


def test_an_unreachable_foobar_explains_itself_instead_of_raising(qt_app, monkeypatch):
    dialog = _dialog(FakeClient(error=foobar.FoobarError("connection refused")), monkeypatch)

    assert not dialog.start_btn.isEnabled()
    assert "foo_beefweb" in dialog.summary_label.text()


def test_a_shorter_tape_moves_the_side_break(qt_app, monkeypatch):
    dialog = _dialog(FakeClient(_items(8, seconds=300)), monkeypatch)  # 40 minutes

    dialog._select_length(90)
    long_break = [dialog.tree.topLevelItem(i).text(0) for i in range(8)].count("A")
    dialog._select_length(46)
    short_break = [dialog.tree.topLevelItem(i).text(0) for i in range(8)].count("A")

    assert short_break <= long_break
    assert dialog.total_minutes == 46


def test_an_album_too_long_for_the_chosen_tape_says_so_without_refusing(qt_app, monkeypatch):
    dialog = _dialog(FakeClient(_items(6, seconds=600)), monkeypatch)  # an hour

    dialog._select_length(46)

    assert "longer cassette" in dialog.fit_label.text()
    assert dialog.start_btn.isEnabled(), "it is the user's tape and the user's call"


# --- side A ----------------------------------------------------------------


def test_nothing_plays_until_the_leader_silence_has_run(qt_app, monkeypatch):
    client = FakeClient(_items(4))
    dialog = _dialog(client, monkeypatch)

    dialog._on_start_clicked()

    assert client.played is None
    assert str(tape.LEADER_SECONDS) in dialog.status_label.text()
    _run_countdown(dialog)
    assert client.played == ("p1", 0)


def test_starting_a_side_backs_the_volume_off_and_forces_straight_playback(qt_app, monkeypatch):
    client = FakeClient(_items(4))
    dialog = _dialog(client, monkeypatch)

    dialog._on_start_clicked()

    assert client.prepared is True
    assert client.volume_set == tape_module.RECORDING_VOLUME_DB


def test_foobar_is_told_to_stop_when_the_sides_last_track_starts(qt_app, monkeypatch):
    """Not caught afterwards: a poll can only notice the next track once it
    has already been recorded onto the end of the side."""
    client = FakeClient(_items(4, seconds=300))
    dialog = _dialog(client, monkeypatch)
    dialog._on_start_clicked()
    _run_countdown(dialog)

    client.playing(0)
    dialog._poll()
    assert client.stop_after == []

    client.playing(1)  # side A is tracks 0-1, so this is its last
    dialog._poll()
    assert client.stop_after == [True]

    dialog._poll()
    assert client.stop_after == [True], "armed once, not on every poll"


def test_the_fields_are_frozen_once_the_tape_is_rolling(qt_app, monkeypatch):
    dialog = _dialog(FakeClient(_items(4)), monkeypatch)

    dialog._on_start_clicked()

    assert not dialog.album_edit.isEnabled()
    assert not dialog.length_combo.isEnabled(), "the split is already half recorded"


# --- the flip --------------------------------------------------------------


def test_the_end_of_side_a_asks_for_the_tape_to_be_turned_over(qt_app, monkeypatch):
    client = FakeClient(_items(4, seconds=300))
    dialog = _dialog(client, monkeypatch)
    dialog._on_start_clicked()
    _run_countdown(dialog)
    for index in (0, 1):
        client.playing(index)
        dialog._poll()

    client.ended()
    dialog._poll()

    assert dialog.result_metadata is None, "half a recording is not a recording"
    assert "turn it over" in dialog.instruction_label.text()
    assert dialog.start_btn.isEnabled()


def test_side_b_starts_at_the_track_the_break_fell_on(qt_app, monkeypatch):
    client = FakeClient(_items(4, seconds=300))
    dialog = _dialog(client, monkeypatch)
    dialog._on_start_clicked()
    _run_countdown(dialog)
    for index in (0, 1):
        client.playing(index)
        dialog._poll()
    client.ended()
    dialog._poll()

    dialog._on_start_clicked()
    _run_countdown(dialog)

    assert client.played == ("p1", 2)


def test_both_sides_recorded_reports_the_album_back(qt_app, monkeypatch):
    client = FakeClient(_items(4, seconds=300))
    dialog = _dialog(client, monkeypatch)

    for side_indices in ((0, 1), (2, 3)):
        dialog._on_start_clicked()
        _run_countdown(dialog)
        for index in side_indices:
            client.playing(index)
            dialog._poll()
        client.ended()
        dialog._poll()

    assert dialog.result_metadata is not None
    assert [t.title for t in dialog.result_metadata.tracks] == [f"Track {i}" for i in range(1, 5)]
    assert "Both sides" in dialog.instruction_label.text()


def test_a_side_that_stopped_early_is_not_treated_as_finished(qt_app, monkeypatch):
    client = FakeClient(_items(6, seconds=300))
    dialog = _dialog(client, monkeypatch)
    dialog._on_start_clicked()
    _run_countdown(dialog)
    client.playing(0)
    dialog._poll()

    client.ended()
    dialog._poll()

    assert "incomplete" in dialog.status_label.text()
    assert dialog._side == 0, "still side A -- nothing has been turned over"
    assert dialog.result_metadata is None


def test_stopping_before_playback_ever_started_is_not_the_end_of_a_side(qt_app, monkeypatch):
    """The gap between play() returning and foobar actually running."""
    client = FakeClient(_items(4))
    dialog = _dialog(client, monkeypatch)
    dialog._on_start_clicked()
    _run_countdown(dialog)
    client.ended()

    dialog._poll()

    assert dialog._recording is True
    assert dialog.result_metadata is None
