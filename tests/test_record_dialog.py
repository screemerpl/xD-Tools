"""Record to MiniDisc from foobar2000 -- the preflight checks and the
end-of-album detection, with both foobar and the adapter faked out.

Nothing here touches a real serial port or a real foobar2000: an accidental
send would arm a deck for recording, which is destructive.
"""

import pytest

from mdtools import foobar
from mdtools.metadata_lookup import AlbumCandidate
from mdtools.panels import record_dialog as record_module
from mdtools.panels.record_dialog import RecordDialog


class FakeClient:
    def __init__(self, items=None, error: Exception | None = None):
        self._items = items if items is not None else []
        self._error = error
        self.stopped = False
        self.prepared = False
        self.played = None
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

    def stop(self):
        self.stopped = True

    def play(self, playlist_id, index):
        self.played = (playlist_id, index)


def _items(count: int, seconds: int = 200) -> list[foobar.PlaylistItem]:
    return [
        foobar.PlaylistItem.from_columns([f"{i:02d}", f"Track {i}", "Artist", "Album", "2024", str(seconds)])
        for i in range(1, count + 1)
    ]


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
        # The session normally opens this in _arm_deck; tests drive _poll()
        # directly, so give them the same already-open connection.
        dialog._deck = record_module.mdrem.MDRemClient("COM_TEST")
    return dialog


# --- preflight -------------------------------------------------------------


def test_the_playlist_is_listed_with_its_total_time(qt_app, monkeypatch, no_hardware):
    dialog = _dialog(FakeClient(_items(3, seconds=200)), monkeypatch)

    assert dialog.tree.topLevelItemCount() == 3
    assert "10:00" in dialog.summary_label.text()
    assert dialog.start_btn.isEnabled()


def test_an_empty_playlist_cannot_be_recorded(qt_app, monkeypatch, no_hardware):
    dialog = _dialog(FakeClient([]), monkeypatch)
    assert not dialog.start_btn.isEnabled()


def test_an_unreachable_foobar_explains_itself_instead_of_raising(qt_app, monkeypatch, no_hardware):
    dialog = _dialog(FakeClient(error=foobar.FoobarError("connection refused")), monkeypatch)

    assert not dialog.start_btn.isEnabled()
    assert "foo_beefweb" in dialog.summary_label.text()


def test_an_album_too_long_for_the_disc_is_flagged_before_anything_starts(qt_app, monkeypatch, no_hardware):
    """Finding out at minute 80 that it didn't fit is the failure this
    avoids -- the track times are known up front, so use them."""
    dialog = _dialog(FakeClient(_items(30, seconds=200)), monkeypatch)  # 100 minutes
    assert dialog.warning_label.isVisible() or not dialog.warning_label.isHidden()
    assert "LP2" in dialog.warning_label.text()


def test_an_album_that_fits_is_not_flagged(qt_app, monkeypatch, no_hardware):
    dialog = _dialog(FakeClient(_items(10, seconds=200)), monkeypatch)  # 33 minutes
    assert dialog.warning_label.isHidden()


# --- end detection ---------------------------------------------------------


def test_stopped_before_playback_ever_started_is_not_the_end_of_the_album(qt_app, monkeypatch, no_hardware):
    """There is a gap between asking foobar to play and it actually
    running; treating that as "finished" would stop the recording
    immediately and then offer to title an empty disc."""
    client = FakeClient(_items(3))
    dialog = _dialog(client, monkeypatch)
    dialog._recording = True
    dialog._started = False

    dialog._poll()

    assert dialog._recording, "the session must still be running"
    assert "SEND STOP" not in no_hardware


def test_the_album_ending_stops_the_deck(qt_app, monkeypatch, no_hardware):
    client = FakeClient(_items(3))
    dialog = _dialog(client, monkeypatch)
    dialog._recording = True
    dialog._started = True
    dialog._highest_index = 2
    monkeypatch.setattr(record_module.QMessageBox, "question", lambda *a, **k: record_module.QMessageBox.StandardButton.No)

    dialog._poll()

    assert not dialog._recording
    assert "SEND STOP" in no_hardware


def test_a_recording_cut_short_is_not_offered_for_titling(qt_app, monkeypatch, no_hardware):
    """Titles would name tracks that never made it onto the disc."""
    client = FakeClient(_items(5))
    dialog = _dialog(client, monkeypatch)
    dialog._recording = True
    dialog._started = True
    dialog._highest_index = 1  # stopped during track 2 of 5
    monkeypatch.setattr(
        record_module.QMessageBox,
        "question",
        lambda *a, **k: pytest.fail("must not offer to title an incomplete recording"),
    )

    dialog._poll()

    assert "incomplete" in dialog.status_label.text().lower()


def test_progress_follows_the_position_within_the_whole_album(qt_app, monkeypatch, no_hardware):
    client = FakeClient(_items(4, seconds=100))
    dialog = _dialog(client, monkeypatch)
    dialog._recording = True

    client.state = foobar.PlayerState(foobar.PLAYING, "p1", 0, 50.0, 100.0)
    dialog._poll()
    early = dialog.progress.value()

    client.state = foobar.PlayerState(foobar.PLAYING, "p1", 2, 50.0, 100.0)
    dialog._poll()

    assert dialog.progress.value() > early
    assert "Track 3" in dialog.status_label.text()


# --- track marking ---------------------------------------------------------


def test_a_track_change_sends_a_mark(qt_app, monkeypatch, no_hardware):
    """The deck's own silence detection cannot split a gapless album --
    there is no silence at the boundary to find. Marking on foobar's own
    track change is what makes it work."""
    client = FakeClient(_items(3))
    dialog = _dialog(client, monkeypatch)
    dialog._recording = True

    client.state = foobar.PlayerState(foobar.PLAYING, "p1", 0, 5.0, 200.0)
    dialog._poll()
    assert record_module.TRACK_MARK_KEY not in no_hardware, "the first track needs no mark"

    client.state = foobar.PlayerState(foobar.PLAYING, "p1", 1, 1.0, 200.0)
    dialog._poll()

    assert no_hardware.count(record_module.TRACK_MARK_KEY) == 1


def test_staying_on_the_same_track_does_not_keep_marking(qt_app, monkeypatch, no_hardware):
    client = FakeClient(_items(3))
    dialog = _dialog(client, monkeypatch)
    dialog._recording = True

    for position in (5.0, 10.0, 15.0):
        client.state = foobar.PlayerState(foobar.PLAYING, "p1", 0, position, 200.0)
        dialog._poll()
    client.state = foobar.PlayerState(foobar.PLAYING, "p1", 1, 1.0, 200.0)
    dialog._poll()
    client.state = foobar.PlayerState(foobar.PLAYING, "p1", 1, 6.0, 200.0)
    dialog._poll()

    assert no_hardware.count(record_module.TRACK_MARK_KEY) == 1


def test_marking_can_be_turned_off_for_a_deck_doing_its_own_level_sync(qt_app, monkeypatch, no_hardware):
    """Both marking the same boundary leaves a stray sliver of a track
    between the two marks."""
    client = FakeClient(_items(3))
    dialog = _dialog(client, monkeypatch)
    dialog.mark_check.setChecked(False)
    dialog._recording = True

    client.state = foobar.PlayerState(foobar.PLAYING, "p1", 0, 5.0, 200.0)
    dialog._poll()
    client.state = foobar.PlayerState(foobar.PLAYING, "p1", 1, 1.0, 200.0)
    dialog._poll()

    assert record_module.TRACK_MARK_KEY not in no_hardware


# --- adopting what was recorded --------------------------------------------


@pytest.fixture
def no_lookup(monkeypatch):
    """No network, and no cover found -- the plain case."""
    monkeypatch.setattr(record_module, "find_cover", lambda *a, **k: (None, None))


def _finish_recording(dialog, monkeypatch) -> None:
    dialog._recording = True
    dialog._started = True
    dialog._highest_index = len(dialog._items) - 1
    monkeypatch.setattr(
        record_module.QMessageBox, "question", lambda *a, **k: record_module.QMessageBox.StandardButton.No
    )
    dialog._poll()


def test_a_finished_recording_is_adopted_as_the_projects_metadata(qt_app, monkeypatch, no_hardware, no_lookup):
    """Otherwise the user has just recorded an album and still has to type
    its name into Project > Metadata... by hand."""
    dialog = _dialog(FakeClient(_items(3)), monkeypatch)
    _finish_recording(dialog, monkeypatch)

    assert dialog.result_metadata is not None
    assert dialog.result_metadata.album == "Album"
    assert [track.title for track in dialog.result_metadata.tracks] == ["Track 1", "Track 2", "Track 3"]


def test_cover_art_is_looked_up_for_what_was_recorded(qt_app, monkeypatch, no_hardware, tmp_path):
    found = AlbumCandidate(
        collection_id=1,
        artist_name="Artist",
        collection_name="Album",
        year=1999,
        track_count=3,
        artwork_url="http://example/600x600bb.jpg",
    )
    monkeypatch.setattr(record_module, "find_cover", lambda *a, **k: (b"JPEGBYTES", found))
    monkeypatch.setattr(record_module, "save_downloaded_cover", lambda *a, **k: tmp_path / "c.jpg")

    dialog = _dialog(FakeClient(_items(3)), monkeypatch)
    _finish_recording(dialog, monkeypatch)

    assert dialog.result_metadata.cover_art == b"JPEGBYTES"


def test_a_failed_cover_lookup_still_keeps_the_metadata(qt_app, monkeypatch, no_hardware):
    """Cover art is a bonus on top of the capture, exactly as it is in
    MetadataDialog -- losing it must not lose the track list too."""
    def boom(*args, **kwargs):
        raise record_module.MetadataLookupError("no network")

    monkeypatch.setattr(record_module, "find_cover", boom)

    dialog = _dialog(FakeClient(_items(3)), monkeypatch)
    _finish_recording(dialog, monkeypatch)

    assert dialog.result_metadata is not None
    assert len(dialog.result_metadata.tracks) == 3
    assert dialog.result_metadata.cover_art is None


def test_an_incomplete_recording_is_not_adopted(qt_app, monkeypatch, no_hardware, no_lookup):
    dialog = _dialog(FakeClient(_items(5)), monkeypatch)
    dialog._recording = True
    dialog._started = True
    dialog._highest_index = 1
    monkeypatch.setattr(record_module.QMessageBox, "question", lambda *a, **k: None)

    dialog._poll()

    assert dialog.result_metadata is None


# --- cancelling ------------------------------------------------------------


def test_stopping_mid_recording_stops_both_ends(qt_app, monkeypatch, no_hardware):
    """Leaving the deck recording after foobar stopped would append a long
    silent track to the disc."""
    client = FakeClient(_items(3))
    dialog = _dialog(client, monkeypatch)
    dialog._recording = True

    dialog.reject()

    assert client.stopped, "foobar must be stopped"
    assert "SEND STOP" in no_hardware, "the deck must be stopped too"
