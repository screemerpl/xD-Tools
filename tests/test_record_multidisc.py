"""Recording one album across several MiniDiscs, and reordering it first.

Kept apart from test_record_dialog.py, which covers the ordinary one-disc
recording: everything here is about what happens *between* discs -- the
split, the titles going out without being asked about, the eject, and the
next disc.

Nothing here touches a real serial port, a real foobar2000 or a real deck.
An accidental send would arm a deck for recording, which is destructive.
"""

import pytest

from mdtools import foobar
from mdtools.panels import record_dialog as record_module
from mdtools.panels.record_dialog import RecordDialog


class FakeClient:
    def __init__(self, items=None):
        self._items = items if items is not None else []
        self.stopped = False
        self.prepared = False
        self.played = None
        self.volume_set = None
        self.stop_after_track: list[bool] = []
        self.moves: list = []
        self.state = foobar.PlayerState(foobar.STOPPED, "", -1, 0.0, 0.0)

    def current_playlist(self):
        return foobar.Playlist(id="p1", title="Default Playlist", item_count=len(self._items), is_current=True)

    def playlist_items(self, playlist_id, limit=500):
        return self._items

    def player_state(self):
        return self.state

    def prepare_for_recording(self):
        self.prepared = True

    def set_volume(self, db):
        self.volume_set = db

    def set_stop_after_current_track(self, stop):
        self.stop_after_track.append(bool(stop))

    def stop(self):
        self.stopped = True

    def play(self, playlist_id, index):
        self.played = (playlist_id, index)

    def clear_playlist(self, playlist_id):
        self._items = []

    def move_playlist_items(self, playlist_id, indexes, target):
        self.moves.append((list(indexes), target))
        for offset, index in enumerate(sorted(indexes)):
            self._items.insert(target + offset, self._items.pop(index))


class _NoTimer:
    """Stands in for QTimer once the dialog has already built its own.

    Every step between discs is handed to QTimer.singleShot -- the lead-in
    before playback, and the two-second wait before the titles go out -- so
    a test that could not intercept those would either race a real event
    loop or never see them fire at all."""

    scheduled: list[tuple[int, object]] = []

    @staticmethod
    def singleShot(ms, callback):
        _NoTimer.scheduled.append((ms, callback))

    # Also stands in for an *instance*, since a test that puts it in place
    # before the dialog is built gets asked for the poll timer too. Nothing
    # here needs to tick: every test drives _poll() itself.
    def __init__(self, *args, **kwargs):
        self.timeout = _NoTimer._Connectable()

    class _Connectable:
        def connect(self, *args, **kwargs):
            pass

    def setInterval(self, *args, **kwargs):
        pass

    def start(self, *args, **kwargs):
        pass

    def stop(self, *args, **kwargs):
        pass


def _items(count: int, seconds: int = 300, with_paths: bool = False) -> list[foobar.PlaylistItem]:
    return [
        foobar.PlaylistItem.from_columns(
            [
                f"{i:02d}",
                f"Track {i}",
                "Artist",
                "Album",
                "2024",
                str(seconds),
                "",
                f"C:/music/{i:02d}.flac" if with_paths else "",
            ]
        )
        for i in range(1, count + 1)
    ]


@pytest.fixture(autouse=True)
def no_cover_lookup(monkeypatch):
    """The dialog looks a cover up as soon as the playlist loads."""
    monkeypatch.setattr(record_module, "fetch_into", lambda *a, **k: None)


@pytest.fixture(autouse=True)
def no_timers(monkeypatch):
    _NoTimer.scheduled = []
    yield
    _NoTimer.scheduled = []


@pytest.fixture
def no_hardware(monkeypatch):
    """Never let a test reach the adapter -- SEND RECORD on a real deck
    would start overwriting a disc."""
    sent: list[str] = []

    class FakeMDRem:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def open(self):
            pass

        def close(self):
            pass

        def command(self, text, **kwargs):
            sent.append(text)

    monkeypatch.setattr(record_module.mdrem, "MDRemClient", FakeMDRem)
    return sent


def _dialog(client: FakeClient, monkeypatch, connected: bool = True) -> RecordDialog:
    monkeypatch.setattr(record_module.foobar, "FoobarClient", lambda *a, **k: client)
    dialog = RecordDialog("COM_TEST")
    if connected:
        dialog._deck = record_module.mdrem.MDRemClient("COM_TEST")
    return dialog


def _double_album(monkeypatch, tracks: int = 30, seconds: int = 300, with_paths: bool = False):
    """150 minutes with the option on: two discs of fifteen tracks."""
    client = FakeClient(_items(tracks, seconds=seconds, with_paths=with_paths))
    dialog = _dialog(client, monkeypatch)
    dialog.multi_check.setChecked(True)
    return dialog, client


def _uploads(monkeypatch, succeeded: bool = True) -> list:
    """Stands in for the titling dialog, and records what it was asked to
    write onto which disc."""
    made: list = []

    class _FakeUpload:
        def __init__(self, metadata, port, parent=None, clear_default=True, unattended=False):
            made.append((metadata, unattended, clear_default))
            self.succeeded = succeeded

        def exec(self):
            return 0

    monkeypatch.setattr(record_module, "MDRemUploadDialog", _FakeUpload)
    return made


def _answer_affirmatively(*args, **kwargs):
    """Yes to "is the deck armed?", OK to "put the next disc in"."""
    buttons = args[3] if len(args) > 3 else None
    if buttons is not None and buttons & record_module.QMessageBox.StandardButton.Ok:
        return record_module.QMessageBox.StandardButton.Ok
    return record_module.QMessageBox.StandardButton.Yes


# --- the album's own order, from the files ---------------------------------


def _interleaved(discs: int = 2, per_disc: int = 3) -> list[foobar.PlaylistItem]:
    """What a double album looks like after foobar2000 has sorted a folder
    of it by filename: both discs number their tracks from one, so they
    come back interleaved."""
    items = []
    for track in range(1, per_disc + 1):
        for disc in range(1, discs + 1):
            items.append(
                foobar.PlaylistItem.from_columns(
                    [
                        f"{track:02d}",
                        f"Disc {disc} track {track}",
                        "Artist",
                        "Album",
                        "2024",
                        "300",
                        "",
                        f"C:/music/cd{disc}/{track:02d}.flac",
                        str(disc),
                    ]
                )
            )
    return items


def test_a_double_album_is_listed_in_its_own_order_not_foobars(qt_app, monkeypatch, no_hardware):
    monkeypatch.setattr(record_module, "QTimer", _NoTimer)
    dialog = _dialog(FakeClient(_interleaved()), monkeypatch)

    assert [item.display_title() for item in dialog._items] == [
        "Disc 1 track 1", "Disc 1 track 2", "Disc 1 track 3",
        "Disc 2 track 1", "Disc 2 track 2", "Disc 2 track 3",
    ]
    assert dialog.tree.topLevelItem(0).text(record_module.COL_TITLE) == "Disc 1 track 1"


def test_the_sorted_order_is_pushed_into_foobar_as_the_dialog_opens(
    qt_app, monkeypatch, no_hardware
):
    """Sorting only the table would leave foobar playing its own order --
    which is exactly how a recording ended up with the wrong track."""
    monkeypatch.setattr(record_module, "QTimer", _NoTimer)
    dialog = _dialog(FakeClient(_interleaved()), monkeypatch)

    assert dialog._order_changed
    assert _NoTimer.scheduled and _NoTimer.scheduled[0] == (0, dialog._push_order_now)


def test_a_playlist_already_in_album_order_is_left_alone(qt_app, monkeypatch, no_hardware):
    """No reordering means no rebuild -- which costs seconds and replaces
    the user's playlist."""
    monkeypatch.setattr(record_module, "QTimer", _NoTimer)
    dialog = _dialog(FakeClient(_items(4)), monkeypatch)

    assert not dialog._order_changed
    assert _NoTimer.scheduled == []


def test_a_track_list_handed_in_is_reordered_with_the_files(qt_app, monkeypatch, no_hardware):
    """Record Folder and the Telegram hand-off both pass a track list built
    from the files as they sat on disk. Sorting the files without it put one
    track's title against another track's file -- reported as the tracks
    being in the wrong order, and the split with them."""
    from mdtools.project import ProjectMetadata, Track

    items = _interleaved(discs=2, per_disc=2)  # d1t1, d2t1, d1t2, d2t2
    given = ProjectMetadata(
        artist="Artist",
        album="Album",
        tracks=[Track(title=item.title, time_seconds=300) for item in items],
    )
    monkeypatch.setattr(record_module, "QTimer", _NoTimer)
    monkeypatch.setattr(record_module.foobar, "FoobarClient", lambda *a, **k: FakeClient(items))
    dialog = RecordDialog("COM_TEST", metadata=given)

    shown = [
        dialog.tree.topLevelItem(row).text(record_module.COL_TITLE)
        for row in range(dialog.tree.topLevelItemCount())
    ]
    assert shown == ["Disc 1 track 1", "Disc 1 track 2", "Disc 2 track 1", "Disc 2 track 2"]
    assert [item.display_title() for item in dialog._items] == shown, "titles follow their own files"


def test_the_disc_splits_come_from_the_files_that_declare_them(qt_app, monkeypatch, no_hardware):
    monkeypatch.setattr(record_module, "QTimer", _NoTimer)
    dialog = _dialog(FakeClient(_interleaved()), monkeypatch)

    assert dialog._manual_breaks == [3]
    assert [len(disc.tracks) for disc in dialog._plan.discs] == [3, 3]
    assert "2-disc album" in dialog.summary_label.text()


def test_files_that_declare_two_discs_turn_the_option_on_themselves(
    qt_app, monkeypatch, no_hardware
):
    """Not a guess about anything -- the album says what it is. Reported
    directly: with the box clear, the table showed 01..n twice over with
    the Disc column hidden and nothing explaining why."""
    monkeypatch.setattr(record_module, "QTimer", _NoTimer)
    dialog = _dialog(FakeClient(_interleaved()), monkeypatch)

    assert dialog.multi_check.isChecked()
    assert dialog._plan.count == 2
    assert not dialog.tree.isColumnHidden(record_module.COL_DISC)


def test_a_single_disc_album_leaves_the_option_alone(qt_app, monkeypatch, no_hardware):
    monkeypatch.setattr(record_module, "QTimer", _NoTimer)
    dialog = _dialog(FakeClient(_items(4)), monkeypatch)

    assert not dialog.multi_check.isChecked()


def test_merely_overrunning_one_disc_still_does_not_tick_it(qt_app, monkeypatch, no_hardware):
    """That one *is* an assumption about the deck: LP2 holds 160 minutes and
    nothing here can read which mode it is in."""
    monkeypatch.setattr(record_module, "QTimer", _NoTimer)
    dialog = _dialog(FakeClient(_items(30, seconds=300)), monkeypatch)  # 150 minutes

    assert not dialog.multi_check.isChecked()
    assert not dialog.warning_label.isHidden()


def test_the_arithmetic_can_still_be_asked_for_instead(qt_app, monkeypatch, no_hardware):
    monkeypatch.setattr(record_module, "QTimer", _NoTimer)
    dialog = _dialog(FakeClient(_interleaved(per_disc=4)), monkeypatch)
    assert dialog._plan.breaks == [4]

    dialog._auto_split()

    assert dialog._manual_breaks is None
    assert dialog._plan.count == 1, "8 tracks of five minutes fit one disc"


# --- the split on screen ---------------------------------------------------


def test_turning_the_option_on_splits_a_long_album(qt_app, monkeypatch, no_hardware):
    dialog, _client = _double_album(monkeypatch)

    assert dialog._plan.count == 2
    assert dialog._multi()
    assert not dialog.tree.isColumnHidden(record_module.COL_DISC)
    assert dialog.tree.topLevelItem(0).text(record_module.COL_DISC) == "1"
    assert dialog.tree.topLevelItem(14).text(record_module.COL_DISC) == "1"
    assert dialog.tree.topLevelItem(15).text(record_module.COL_DISC) == "2"
    assert not dialog.split_label.isHidden()


def test_an_album_that_fits_stays_one_disc_whatever_the_checkbox_says(qt_app, monkeypatch, no_hardware):
    """Otherwise everything downstream would have to ask twice: the option
    being on, and the album actually needing it."""
    dialog, _client = _double_album(monkeypatch, tracks=10)

    assert dialog._plan.count == 1
    assert not dialog._multi()
    assert dialog.tree.isColumnHidden(record_module.COL_DISC)


def test_a_longer_recording_mode_puts_the_album_back_on_one_disc(qt_app, monkeypatch, no_hardware):
    """Which mode the deck is in cannot be read from here, so the number is
    the user's to state."""
    dialog, _client = _double_album(monkeypatch)
    dialog.disc_minutes_spin.setValue(160)

    assert dialog._plan.count == 1


def test_the_one_disc_warning_gives_way_to_the_split(qt_app, monkeypatch, no_hardware):
    """"This is longer than 80 minutes" is only worth saying while nothing
    is being done about it."""
    dialog, _client = _double_album(monkeypatch)
    assert dialog.warning_label.isHidden()

    dialog.multi_check.setChecked(False)
    assert not dialog.warning_label.isHidden()
    assert "LP2" in dialog.warning_label.text()


# --- moving the splits by hand ---------------------------------------------


def test_placing_a_split_by_hand_starts_from_the_one_already_on_screen(
    qt_app, monkeypatch, no_hardware
):
    """Editing what is shown, rather than starting from nothing: on an
    album that needs three discs, moving one boundary must not throw the
    other two away and leave the user to place them all again."""
    dialog, _client = _double_album(monkeypatch)
    assert dialog._plan.breaks == [15]

    dialog.tree.setCurrentItem(dialog.tree.topLevelItem(9))
    dialog._toggle_split()

    assert dialog._plan.breaks == [9, 15]
    assert dialog._plan.manual
    assert dialog.tree.topLevelItem(9).text(record_module.COL_DISC) == "2"


def test_a_boundary_is_moved_by_placing_the_new_one_and_removing_the_old(
    qt_app, monkeypatch, no_hardware
):
    dialog, _client = _double_album(monkeypatch)

    dialog.tree.setCurrentItem(dialog.tree.topLevelItem(9))
    dialog._toggle_split()
    dialog.tree.setCurrentItem(dialog.tree.topLevelItem(15))
    assert dialog.split_btn.text() == "Do Not Start Disc Here", "the button says which it would do"
    dialog._toggle_split()

    assert dialog._plan.breaks == [9]
    assert [len(disc.tracks) for disc in dialog._plan.discs] == [9, 21]


def test_a_hand_placed_split_survives_the_capacity_changing(qt_app, monkeypatch, no_hardware):
    """The arithmetic putting its own break back the moment anything else
    changed is exactly what the user just said they did not want."""
    dialog, _client = _double_album(monkeypatch)
    dialog.tree.setCurrentItem(dialog.tree.topLevelItem(9))
    dialog._toggle_split()

    dialog.disc_minutes_spin.setValue(75)

    assert dialog._plan.breaks == [9, 15]


def test_splitting_again_at_the_same_track_takes_the_split_away(qt_app, monkeypatch, no_hardware):
    dialog, _client = _double_album(monkeypatch)
    dialog.tree.setCurrentItem(dialog.tree.topLevelItem(9))
    dialog._toggle_split()
    dialog._toggle_split()

    assert dialog._plan.breaks == [15], "back to what it was, and still adjustable"


def test_the_splits_can_be_handed_back_to_the_arithmetic(qt_app, monkeypatch, no_hardware):
    dialog, _client = _double_album(monkeypatch)
    dialog.tree.setCurrentItem(dialog.tree.topLevelItem(3))
    dialog._toggle_split()

    dialog._auto_split()

    assert dialog._manual_breaks is None
    assert dialog._plan.breaks == [15]


def test_the_first_track_cannot_be_made_to_start_a_second_disc(qt_app, monkeypatch, no_hardware):
    dialog, _client = _double_album(monkeypatch)
    dialog.tree.setCurrentItem(dialog.tree.topLevelItem(0))

    dialog._toggle_split()

    assert dialog._plan.breaks == [15]


# --- moving tracks ---------------------------------------------------------


def test_moving_a_track_down_moves_its_row_and_its_file(qt_app, monkeypatch, no_hardware):
    dialog, _client = _double_album(monkeypatch, tracks=3)
    dialog.tree.setCurrentItem(dialog.tree.topLevelItem(0))

    dialog._move_selected(1)

    assert [item.display_title() for item in dialog._items] == ["Track 2", "Track 1", "Track 3"]
    assert dialog.tree.topLevelItem(0).text(record_module.COL_TITLE) == "Track 2"
    assert dialog._order_changed


def test_moving_a_track_takes_its_own_title_with_it(qt_app, monkeypatch, no_hardware):
    """Everything downstream pairs the seed's track list with the playlist
    by index, so leaving one behind would put one track's title against
    another track's file."""
    dialog, _client = _double_album(monkeypatch, tracks=3)
    dialog.tree.setCurrentItem(dialog.tree.topLevelItem(2))

    dialog._move_selected(-1)

    assert [track.title for track in dialog._seed.tracks] == ["Track 1", "Track 3", "Track 2"]


def test_a_track_cannot_be_moved_off_either_end(qt_app, monkeypatch, no_hardware):
    dialog, _client = _double_album(monkeypatch, tracks=3)

    dialog.tree.setCurrentItem(dialog.tree.topLevelItem(0))
    dialog._move_selected(-1)
    dialog.tree.setCurrentItem(dialog.tree.topLevelItem(2))
    dialog._move_selected(1)

    assert [item.display_title() for item in dialog._items] == ["Track 1", "Track 2", "Track 3"]
    assert not dialog._order_changed


def test_a_reordered_table_is_pushed_into_foobar_before_anything_records(
    qt_app, monkeypatch, no_hardware
):
    """The recording *is* foobar playing its own playlist, so a table
    reordered only here would title the disc in one order and record it in
    another."""
    dialog, client = _double_album(monkeypatch, tracks=3, with_paths=True)
    monkeypatch.setattr(
        record_module.foobar,
        "replace_current_playlist",
        lambda *a, **k: pytest.fail("moving the items is enough"),
    )
    monkeypatch.setattr(record_module.QMessageBox, "warning", lambda *a, **k: record_module.QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(record_module.QMessageBox, "question", _answer_affirmatively)
    monkeypatch.setattr(record_module, "QTimer", _NoTimer)

    dialog.tree.setCurrentItem(dialog.tree.topLevelItem(0))
    dialog._move_selected(1)
    dialog._start()

    assert [item.path for item in client._items] == [
        "C:/music/02.flac",
        "C:/music/01.flac",
        "C:/music/03.flac",
    ]
    assert client.prepared, "the recording still went ahead afterwards"
    assert not dialog._order_changed


def test_the_playlist_is_reordered_in_place_rather_than_rebuilt(
    qt_app, monkeypatch, no_hardware
):
    """Moving items touches no files and clears nothing, so a locked or
    moved file cannot cost the user their playlist."""
    monkeypatch.setattr(record_module, "QTimer", _NoTimer)
    monkeypatch.setattr(
        record_module.foobar,
        "replace_current_playlist",
        lambda *a, **k: pytest.fail("the heavy path must be the fallback, not the first move"),
    )
    client = FakeClient(_interleaved())
    dialog = _dialog(client, monkeypatch)

    dialog._push_order_now()

    assert not dialog._order_changed
    assert client.moves, "it moved items"
    assert [item.path for item in client._items] == [item.path for item in dialog._items]


def test_an_untouched_order_never_rebuilds_the_playlist(qt_app, monkeypatch, no_hardware):
    """Rebuilding costs seconds of a frozen window and replaces the user's
    playlist -- not something to do for a recording that changed nothing."""
    dialog, _client = _double_album(monkeypatch, tracks=3, with_paths=True)
    monkeypatch.setattr(
        record_module.foobar,
        "replace_current_playlist",
        lambda *a, **k: pytest.fail("nothing was reordered"),
    )
    monkeypatch.setattr(record_module.QMessageBox, "warning", lambda *a, **k: record_module.QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(record_module.QMessageBox, "question", _answer_affirmatively)
    monkeypatch.setattr(record_module, "QTimer", _NoTimer)

    dialog._start()


def test_an_order_that_cannot_be_reached_at_all_stops_the_recording(
    qt_app, monkeypatch, no_hardware
):
    """Moving is tried first and the rebuild is the fallback -- but if the
    playlist entries are not files on disk, the fallback has nothing to add
    back, and recording in an order foobar does not have is the one outcome
    that must not happen."""
    dialog, client = _double_album(monkeypatch, tracks=3)  # no paths
    monkeypatch.setattr(record_module.QMessageBox, "warning", lambda *a, **k: record_module.QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(
        record_module.QMessageBox, "question", lambda *a, **k: pytest.fail("nothing may be armed")
    )
    monkeypatch.setattr(record_module, "QTimer", _NoTimer)

    dialog.tree.setCurrentItem(dialog.tree.topLevelItem(0))
    dialog._move_selected(1)
    dialog._start()

    assert not client.prepared, "nothing may be recorded in an order foobar does not have"


# --- one disc after another ------------------------------------------------


def test_the_end_of_a_disc_writes_its_titles_without_asking(qt_app, monkeypatch, no_hardware):
    """Nobody sits through forty minutes of album, so a confirmation here
    would leave the deck holding an untitled disc until somebody came back."""
    dialog, client = _double_album(monkeypatch)
    monkeypatch.setattr(record_module, "QTimer", _NoTimer)
    monkeypatch.setattr(
        record_module.QMessageBox, "question", lambda *a, **k: pytest.fail("nothing may be asked here")
    )
    dialog._recording = True
    dialog._started = True
    dialog._highest_index = 14  # the whole of disc one played

    dialog._poll()  # the client is still reporting "stopped"

    assert "SEND STOP" in no_hardware
    assert _NoTimer.scheduled == [(record_module.TITLING_DELAY_MS, dialog._title_current_disc)]
    assert record_module.TITLING_DELAY_MS == 2000


def test_each_disc_is_titled_with_its_own_tracks_numbered_from_one(qt_app, monkeypatch, no_hardware):
    """The deck numbers its own tracks from one, so track 16 of the album
    is track 1 of disc two -- and two discs titled identically are
    indistinguishable on a shelf."""
    dialog, _client = _double_album(monkeypatch)
    made = _uploads(monkeypatch)
    monkeypatch.setattr(record_module, "QTimer", _NoTimer)
    monkeypatch.setattr(record_module.QMessageBox, "question", _answer_affirmatively)
    dialog._capture_metadata()

    dialog._disc = 1
    dialog._title_current_disc()

    metadata, unattended, clear_default = made[0]
    assert unattended is True
    assert clear_default is False, "a disc just recorded has no titles to erase"
    assert metadata.album == "Album [2/2]"
    assert [track.title for track in metadata.tracks] == [f"Track {n}" for n in range(16, 31)]


def test_a_finished_disc_is_followed_by_a_prompt_and_then_the_next_one(
    qt_app, monkeypatch, no_hardware
):
    dialog, _client = _double_album(monkeypatch)
    _uploads(monkeypatch, succeeded=True)
    monkeypatch.setattr(record_module, "QTimer", _NoTimer)
    monkeypatch.setattr(record_module.QMessageBox, "question", _answer_affirmatively)
    dialog._capture_metadata()

    dialog._title_current_disc()

    assert dialog._disc == 1
    assert no_hardware.count("SEND RECORD") == 1, "the deck was armed again for disc two"
    assert dialog._marked_index == 15, "and its first track must not be marked"


def test_declining_the_next_disc_ends_the_run_where_it_is(qt_app, monkeypatch, no_hardware):
    dialog, _client = _double_album(monkeypatch)
    _uploads(monkeypatch, succeeded=True)
    monkeypatch.setattr(record_module, "QTimer", _NoTimer)
    monkeypatch.setattr(
        record_module.QMessageBox, "question", lambda *a, **k: record_module.QMessageBox.StandardButton.Cancel
    )
    dialog._capture_metadata()

    dialog._title_current_disc()

    assert dialog._disc == 0
    assert "SEND RECORD" not in no_hardware
    assert "disc 1" in dialog.status_label.text()


def test_titles_that_could_not_be_written_stop_the_run(qt_app, monkeypatch, no_hardware):
    """Carrying on would eject an untitled disc and ask for the next as
    though nothing had happened."""
    dialog, _client = _double_album(monkeypatch)
    _uploads(monkeypatch, succeeded=False)
    monkeypatch.setattr(record_module, "QTimer", _NoTimer)
    monkeypatch.setattr(
        record_module.QMessageBox, "question", lambda *a, **k: pytest.fail("the next disc must not be asked for")
    )
    dialog._capture_metadata()

    dialog._title_current_disc()

    assert dialog._disc == 0
    assert "titles" in dialog.status_label.text()


def test_the_last_disc_ends_the_whole_run(qt_app, monkeypatch, no_hardware):
    dialog, _client = _double_album(monkeypatch)
    _uploads(monkeypatch, succeeded=True)
    monkeypatch.setattr(record_module, "QTimer", _NoTimer)
    monkeypatch.setattr(
        record_module.QMessageBox, "question", lambda *a, **k: pytest.fail("there is no next disc to ask for")
    )
    dialog._capture_metadata()
    dialog._disc = 1

    dialog._title_current_disc()

    assert "2" in dialog.status_label.text()
    assert dialog.close_btn.text() == "Close"


def test_what_the_project_adopts_is_the_whole_album_not_one_disc(qt_app, monkeypatch, no_hardware):
    """The label describes the record, which is both discs of it."""
    dialog, _client = _double_album(monkeypatch)
    dialog._capture_metadata()

    assert len(dialog.result_metadata.tracks) == 30
    assert dialog.result_metadata.album == "Album"


# --- where a disc actually ends --------------------------------------------


def test_foobar_is_told_to_stop_at_the_end_of_the_disc(qt_app, monkeypatch, no_hardware):
    """Armed on the transition *into* the last track: the flag applies to
    whatever is playing when it is read, so setting it earlier would end
    the disc after its first track."""
    dialog, client = _double_album(monkeypatch)
    dialog._recording = True
    dialog._started = True

    client.state = foobar.PlayerState(foobar.PLAYING, "p1", 13, 5.0, 300.0)
    dialog._poll()
    assert client.stop_after_track == []

    client.state = foobar.PlayerState(foobar.PLAYING, "p1", 14, 5.0, 300.0)
    dialog._poll()

    assert client.stop_after_track == [True]


def test_playback_running_past_the_disc_ends_it_anyway(qt_app, monkeypatch, no_hardware):
    """If the stop-after-this-track flag did not take, ending the disc here
    costs a fraction of the next track; letting it run would put the whole
    of the next disc onto this one."""
    dialog, client = _double_album(monkeypatch)
    monkeypatch.setattr(record_module, "QTimer", _NoTimer)
    dialog._recording = True
    dialog._started = True
    dialog._highest_index = 14

    client.state = foobar.PlayerState(foobar.PLAYING, "p1", 15, 1.0, 300.0)
    dialog._poll()

    assert client.stopped
    assert not dialog._recording
    assert "SEND STOP" in no_hardware


def test_playback_stopping_inside_a_disc_is_still_incomplete(qt_app, monkeypatch, no_hardware):
    """And is counted within the disc, not the album: stopping at track 3
    of disc two is track 3, not track 18."""
    dialog, client = _double_album(monkeypatch)
    monkeypatch.setattr(record_module, "QTimer", _NoTimer)
    monkeypatch.setattr(
        record_module.QMessageBox, "question", lambda *a, **k: pytest.fail("nothing to ask about")
    )
    dialog._disc = 1
    dialog._recording = True
    dialog._started = True
    dialog._highest_index = 17  # track 3 of disc two

    dialog._poll()

    assert "3 of 15" in dialog.status_label.text()
