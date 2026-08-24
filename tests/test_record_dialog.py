"""Record to MiniDisc -- the preflight checks and the end-of-album
detection, with the adapter and AudioPlayer both faked out.

Nothing here touches a real serial port or real audio hardware: an
accidental send would arm a deck for recording, which is destructive.

Track lists are built directly as `tracks.PlaylistItem`s (bypassing
`tracks.playlist_items_from_paths()`'s real mutagen tag reading, which is
tested on its own in test_tracks.py) via the `_dialog()` helper below,
which stubs `record_module.tracks.playlist_items_from_paths`.
"""

from pathlib import Path

import pytest

from mdtools import tracks
from mdtools.metadata_lookup import AlbumCandidate
from mdtools.panels import record_dialog as record_module
from mdtools.panels.record_dialog import RecordDialog


class _FakePlayer:
    """Stands in for audio_engine.AudioPlayer -- captures the callbacks
    `play()` is given so a test can fire them directly, the same way
    test_audio_engine.py's _FakeOutputStream lets a test drive the real
    callback."""

    def __init__(self, device=None, gain_db=0.0, samplerate=44100, channels=2):
        self.device = device
        self.gain_db = gain_db
        self.samplerate = samplerate
        self.channels = channels
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


def _png() -> bytes:
    """A real one-pixel image, since these bytes go through a QPixmap."""
    from PySide6.QtCore import QBuffer
    from PySide6.QtGui import QColor, QImage

    image = QImage(1, 1, QImage.Format.Format_ARGB32)
    image.fill(QColor("red"))
    buffer = QBuffer()
    buffer.open(QBuffer.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(buffer.data())


@pytest.fixture(autouse=True)
def no_cover_lookup(monkeypatch):
    """The dialog looks a cover up as soon as the tracks load, so every
    construction in this file would otherwise reach iTunes. Tests that care
    about the lookup override this with their own stand-in."""
    monkeypatch.setattr(record_module, "fetch_into", lambda *a, **k: None)


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


@pytest.fixture
def fake_player(monkeypatch):
    """Never let a test reach sounddevice -- AudioPlayer construction and
    playback are both faked out."""
    monkeypatch.setattr(record_module.audio_engine, "AudioPlayer", _FakePlayer)
    monkeypatch.setattr(record_module.audio_engine, "resolve_output_device", lambda name: None)


def _dialog(items: list[tracks.PlaylistItem], monkeypatch, connected: bool = True) -> RecordDialog:
    monkeypatch.setattr(record_module.tracks, "playlist_items_from_paths", lambda paths: items)
    dialog = RecordDialog("COM_TEST", [item.path for item in items] or [])
    if connected:
        dialog._deck = record_module.mdrem.MDRemClient("COM_TEST")
    return dialog


# --- preflight -------------------------------------------------------------


def test_the_album_is_listed_with_its_total_time(qt_app, monkeypatch, no_hardware):
    dialog = _dialog(_items(3, seconds=200), monkeypatch)

    assert dialog.tree.topLevelItemCount() == 3
    assert "10:00" in dialog.summary_label.text()
    assert dialog.start_btn.isEnabled()


def test_no_tracks_cannot_be_recorded(qt_app, monkeypatch, no_hardware):
    dialog = _dialog([], monkeypatch)
    assert not dialog.start_btn.isEnabled()


def test_an_album_too_long_for_the_disc_is_flagged_before_anything_starts(qt_app, monkeypatch, no_hardware):
    """Finding out at minute 80 that it didn't fit is the failure this
    avoids -- the track times are known up front, so use them."""
    dialog = _dialog(_items(30, seconds=200), monkeypatch)  # 100 minutes
    assert dialog.warning_label.isVisible() or not dialog.warning_label.isHidden()
    assert "LP2" in dialog.warning_label.text()


def test_an_album_that_fits_is_not_flagged(qt_app, monkeypatch, no_hardware):
    dialog = _dialog(_items(10, seconds=200), monkeypatch)  # 33 minutes
    assert dialog.warning_label.isHidden()


# --- track marking -----------------------------------------------------
#
# AudioPlayer itself guarantees on_track_boundary never fires for the first
# buffer in a queue (see test_audio_engine.py's
# test_play_fires_track_boundary_at_the_exact_sample) -- that is what
# replaces the old poll loop's "never mark the first track" special case,
# so there is nothing left to test for that here.


def test_a_track_boundary_sends_a_mark(qt_app, monkeypatch, no_hardware):
    """The deck's own silence detection cannot split a gapless album --
    there is no silence at the boundary to find. A track-boundary callback
    is what makes it work."""
    dialog = _dialog(_items(3), monkeypatch)
    dialog._recording = True

    dialog._on_track_boundary(1)

    assert no_hardware.count(record_module.TRACK_MARK_KEY) == 1


def test_marking_can_be_turned_off_for_a_deck_doing_its_own_level_sync(qt_app, monkeypatch, no_hardware):
    """Both marking the same boundary leaves a stray sliver of a track
    between the two marks."""
    dialog = _dialog(_items(3), monkeypatch)
    dialog.mark_check.setChecked(False)
    dialog._recording = True

    dialog._on_track_boundary(1)

    assert record_module.TRACK_MARK_KEY not in no_hardware


# --- progress ------------------------------------------------------------


def test_progress_follows_the_position_within_the_whole_album(qt_app, monkeypatch, no_hardware):
    dialog = _dialog(_items(4, seconds=100), monkeypatch)
    dialog._recording = True
    dialog._player = _FakePlayer()

    dialog._current_local_index = 0
    dialog._player.position_seconds = 50.0
    dialog._refresh_progress()
    early = dialog.progress.value()

    dialog._current_local_index = 2
    dialog._player.position_seconds = 50.0
    dialog._refresh_progress()

    assert dialog.progress.value() > early
    assert "Track 3" in dialog.status_label.text()


# --- end of the disc -------------------------------------------------------


def test_the_album_ending_stops_the_deck(qt_app, monkeypatch, no_hardware):
    dialog = _dialog(_items(3), monkeypatch)
    dialog._recording = True
    monkeypatch.setattr(record_module.QMessageBox, "question", lambda *a, **k: record_module.QMessageBox.StandardButton.No)

    dialog._on_disc_finished()

    assert not dialog._recording
    assert "SEND STOP" in no_hardware


# --- adopting what was recorded --------------------------------------------


@pytest.fixture
def no_lookup(no_cover_lookup):
    """No network, and no cover found -- the plain case. The autouse guard
    above already does it; this name stays because it says so at the call
    site."""


def _finish_recording(dialog, monkeypatch) -> None:
    dialog._recording = True
    dialog._current_local_index = len(dialog._items) - 1
    monkeypatch.setattr(
        record_module.QMessageBox, "question", lambda *a, **k: record_module.QMessageBox.StandardButton.No
    )
    dialog._on_disc_finished()


def test_a_finished_recording_is_adopted_as_the_projects_metadata(qt_app, monkeypatch, no_hardware, no_lookup):
    """Otherwise the user has just recorded an album and still has to type
    its name into the Tools panel's Metadata dialog by hand."""
    dialog = _dialog(_items(3), monkeypatch)
    _finish_recording(dialog, monkeypatch)

    assert dialog.result_metadata is not None
    assert dialog.result_metadata.album == "Album"
    assert [track.title for track in dialog.result_metadata.tracks] == ["Track 1", "Track 2", "Track 3"]


def test_cover_art_is_looked_up_before_recording_not_after(qt_app, monkeypatch, no_hardware):
    """It used to happen once the album had finished playing, which is the
    worst moment to find out the search matched the wrong release. Now it is
    on screen while the album name can still be corrected."""
    calls: list = []

    def fake_fetch(preview, artist, album, track_count=None):
        calls.append((artist, album, track_count))
        preview.set_cover(_png())
        return AlbumCandidate(
            collection_id=1,
            artist_name="Artist",
            collection_name="Album",
            year=1999,
            track_count=3,
            artwork_url="http://example/600x600bb.jpg",
        )

    monkeypatch.setattr(record_module, "fetch_into", fake_fetch)

    dialog = _dialog(_items(3), monkeypatch)

    assert calls == [("Artist", "Album", 3)], "looked up as the tracks loaded"
    _finish_recording(dialog, monkeypatch)
    assert dialog.result_metadata.cover_art == _png()


def test_a_year_the_tags_did_not_have_comes_from_the_cover_lookup(qt_app, monkeypatch, no_hardware):
    def fake_fetch(preview, artist, album, track_count=None):
        return AlbumCandidate(
            collection_id=1, artist_name="Artist", collection_name="Album", year=1999, track_count=3
        )

    monkeypatch.setattr(record_module, "fetch_into", fake_fetch)
    items = [
        tracks.PlaylistItem(
            track_number=str(n), title=f"Track {n}", album_artist="Artist", album="Album", date="", length_seconds=200
        )
        for n in range(1, 4)
    ]

    dialog = _dialog(items, monkeypatch)

    assert dialog.year_spin.value() == 1999


def test_a_failed_cover_lookup_still_keeps_the_metadata(qt_app, monkeypatch, no_hardware):
    """Cover art is a bonus on top of the capture, exactly as it is in
    MetadataDialog -- losing it must not lose the track list too.
    cover_preview.fetch_into swallows the error itself and answers None."""
    monkeypatch.setattr(record_module, "fetch_into", lambda *a, **k: None)

    dialog = _dialog(_items(3), monkeypatch)
    _finish_recording(dialog, monkeypatch)

    assert dialog.result_metadata is not None
    assert len(dialog.result_metadata.tracks) == 3
    assert dialog.result_metadata.cover_art is None


# --- cancelling ------------------------------------------------------------


def test_stopping_mid_recording_stops_both_ends(qt_app, monkeypatch, no_hardware):
    """Leaving the deck recording after playback stopped would append a
    long silent track to the disc."""
    dialog = _dialog(_items(3), monkeypatch)
    dialog._recording = True
    dialog._player = _FakePlayer()

    dialog.reject()

    assert dialog._player.stopped, "playback must be stopped"
    assert "SEND STOP" in no_hardware, "the deck must be stopped too"


# --- metadata handed in by the caller ---------------------------------------
#
# Record Folder passes what its own dialog settled on, because a folder holds
# somebody else's files and nothing rewrites them -- an album name corrected
# there reaches the disc no other way. The CD flow deliberately does not: it
# wrote its titles into the files it created, so the tags already carry them.


def test_metadata_handed_in_is_what_the_disc_is_titled_from(qt_app, monkeypatch, no_hardware, no_lookup):
    from mdtools.project import ProjectMetadata, Track

    given = ProjectMetadata(album="Posluchaj", artist="Kult", tracks=[Track("Arahja")])
    monkeypatch.setattr(record_module.tracks, "playlist_items_from_paths", lambda paths: _items(3))
    dialog = RecordDialog("COM_TEST", ["a", "b", "c"], metadata=given)
    dialog._deck = record_module.mdrem.MDRemClient("COM_TEST")
    _finish_recording(dialog, monkeypatch)

    # A copy, not the same object: the dialog reads its own widgets back, so
    # a correction made in it is what comes out.
    assert dialog.result_metadata is not given
    assert (dialog.result_metadata.album, dialog.result_metadata.artist) == ("Posluchaj", "Kult")


def test_a_cover_that_came_with_it_is_not_looked_up_again(qt_app, monkeypatch, no_hardware):
    """Record Folder looks one up before recording, while the user can
    still correct the album name. A second search could only answer the
    same question worse."""
    from mdtools.project import ProjectMetadata, Track

    monkeypatch.setattr(
        record_module, "fetch_into", lambda *a, **k: pytest.fail("must not search for a second cover")
    )
    given = ProjectMetadata(album="Unleashed", artist="Skillet", tracks=[Track("A")], cover_art=_png())
    monkeypatch.setattr(record_module.tracks, "playlist_items_from_paths", lambda paths: _items(3))
    dialog = RecordDialog("COM_TEST", ["a", "b", "c"], metadata=given)
    dialog._deck = record_module.mdrem.MDRemClient("COM_TEST")
    _finish_recording(dialog, monkeypatch)

    assert dialog.result_metadata.cover_art == _png()


def test_without_any_the_tracks_are_still_the_source(qt_app, monkeypatch, no_hardware, no_lookup):
    """The ordinary path, unchanged: every other entry point passes
    nothing."""
    dialog = _dialog(_items(3), monkeypatch)
    _finish_recording(dialog, monkeypatch)

    assert dialog.result_metadata.album == "Album"


def test_the_titles_written_onto_the_disc_are_the_ones_on_screen(qt_app, monkeypatch, no_hardware, no_lookup):
    """_offer_titling used to rebuild the metadata from the tracks all over
    again, which would have thrown away every edit made here."""
    uploaded: list = []

    class _FakeUpload:
        def __init__(self, metadata, port, parent=None, clear_default=True):
            uploaded.append(metadata)

        def exec(self):
            return 0

    monkeypatch.setattr(record_module, "MDRemUploadDialog", _FakeUpload)
    monkeypatch.setattr(
        record_module.QMessageBox, "question", lambda *a, **k: record_module.QMessageBox.StandardButton.Yes
    )
    dialog = _dialog(_items(3), monkeypatch)
    dialog.album_edit.setText("Posluchaj")
    dialog.artist_edit.setText("Kult")
    dialog.tree.topLevelItem(0).setText(record_module.COL_TITLE, "Arahja")
    dialog._recording = True
    dialog._current_local_index = len(dialog._items) - 1

    dialog._on_disc_finished()

    assert uploaded == [dialog.result_metadata]
    assert (uploaded[0].album, uploaded[0].artist) == ("Posluchaj", "Kult")
    assert uploaded[0].tracks[0].title == "Arahja"


def test_an_edited_track_artist_keeps_a_mixtape_a_mixtape(qt_app, monkeypatch, no_hardware, no_lookup):
    """Rebuilding tracks from the Title column alone would drop every
    performer, and with them the only thing that makes a compilation one --
    exactly the bug MetadataDialog had before it grew an Artist column."""
    dialog = _dialog(_items(3), monkeypatch)
    dialog.artist_edit.clear()
    dialog.album_edit.clear()
    for index, performer in enumerate(("New Order", "The Cure", "Depeche Mode")):
        dialog.tree.topLevelItem(index).setText(record_module.COL_ARTIST, performer)

    _finish_recording(dialog, monkeypatch)

    assert [track.artist for track in dialog.result_metadata.tracks] == [
        "New Order",
        "The Cure",
        "Depeche Mode",
    ]
    assert dialog.result_metadata.is_compilation()


# --- starting -----------------------------------------------------------


def test_starting_builds_the_player_with_the_configured_gain(qt_app, monkeypatch, no_hardware, fake_player):
    """Explicit user request: every recording backs off the output volume
    first, so a digital transfer at 0dB never risks clipping."""
    monkeypatch.setattr(record_module.app_settings, "recording_gain_db", lambda: -5.0)
    dialog = _dialog(_items(3), monkeypatch)
    monkeypatch.setattr(
        record_module.QMessageBox, "warning", lambda *a, **k: record_module.QMessageBox.StandardButton.Ok
    )
    monkeypatch.setattr(
        record_module.QMessageBox, "question", lambda *a, **k: record_module.QMessageBox.StandardButton.Yes
    )

    dialog._start()

    assert dialog._player.gain_db == -5.0


def test_the_track_list_is_frozen_once_recording_starts(qt_app, monkeypatch, no_hardware, no_lookup, fake_player):
    """What is on screen when the deck starts is what gets written when it
    stops; renaming the album halfway through would only make the two
    disagree."""
    dialog = _dialog(_items(3), monkeypatch)
    monkeypatch.setattr(
        record_module.QMessageBox, "warning", lambda *a, **k: record_module.QMessageBox.StandardButton.Ok
    )
    monkeypatch.setattr(
        record_module.QMessageBox, "question", lambda *a, **k: record_module.QMessageBox.StandardButton.Yes
    )
    # Decoding now happens synchronously inside _start() (see _begin_disc),
    # before the deliberate lead-in -- these items carry no real paths, so
    # without this the decode itself would fail and _fail() would undo the
    # very freeze this test is checking.
    monkeypatch.setattr(record_module.audio_engine, "load_for_playback", lambda paths, **kwargs: [])

    dialog._start()

    assert not dialog.tree.isEnabled()
    assert not dialog.album_edit.isEnabled()
    assert not dialog.cover_label.isEnabled()


def test_decode_progress_updates_the_status_label(qt_app, monkeypatch, no_hardware, no_lookup, fake_player):
    """Decoding a whole disc up front (see _begin_disc) can take a few real
    seconds -- without this, that gap reads as the dialog having hung."""
    dialog = _dialog(_items(3), monkeypatch)

    dialog._report_decode_progress(2, 5, Path("some/dir/03 Track.flac"))

    text = dialog.status_label.text()
    assert "2" in text
    assert "5" in text
    assert "03 Track" in text


def test_the_dialog_opens_on_what_the_disc_will_be_called(qt_app, monkeypatch, no_hardware, no_lookup):
    """Not just a list of paths: the album, the artist and the artwork are
    what actually gets written onto the MiniDisc."""
    dialog = _dialog(_items(3), monkeypatch)

    assert dialog.artist_edit.text() == "Artist"
    assert dialog.album_edit.text() == "Album"
    assert dialog.year_spin.value() == 2024


def test_artwork_that_came_with_the_metadata_is_shown_straight_away(qt_app, monkeypatch, no_hardware):
    from mdtools.project import ProjectMetadata, Track

    monkeypatch.setattr(
        record_module, "fetch_into", lambda *a, **k: pytest.fail("nothing to look up, it already has one")
    )
    given = ProjectMetadata(album="Unleashed", artist="Skillet", tracks=[Track("A")], cover_art=_png())
    monkeypatch.setattr(record_module.tracks, "playlist_items_from_paths", lambda paths: _items(3))

    dialog = RecordDialog("COM_TEST", ["a", "b", "c"], metadata=given)

    assert dialog.cover_label.data == _png()


def test_a_cover_inside_the_albums_own_files_is_the_last_resort(qt_app, monkeypatch, no_hardware):
    monkeypatch.setattr(record_module, "fetch_into", lambda *a, **k: None)
    seen: list = []

    def fake_embedded(paths):
        seen.extend(paths)
        return _png()

    monkeypatch.setattr(record_module.embedded_cover, "cover_from_files", fake_embedded)
    items = [
        tracks.PlaylistItem(
            track_number=str(n),
            title=f"Track {n}",
            album_artist="Artist",
            album="Album",
            date="2024",
            length_seconds=200,
            path=f"/music/{n}.flac",
        )
        for n in range(1, 4)
    ]

    dialog = _dialog(items, monkeypatch)

    assert dialog.cover_label.data == _png()
    assert seen == ["/music/1.flac", "/music/2.flac", "/music/3.flac"]
