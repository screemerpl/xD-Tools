"""Recording > Record Folder to MiniDisc.

The third source of a recording, and the one with the least of its own
machinery: it reads each file's own tags directly (via
tracks.playlist_items_from_paths, mutagen underneath) and reconciles them
with what the user typed. So most of what is worth pinning down here is
about the boundary between "what the files say" and "what the user typed".
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QDialog

from mdtools import app_settings, tracks
from mdtools.panels import folder_record_dialog as module
from mdtools.panels.folder_record_dialog import FolderRecordDialog
from mdtools.project import ProjectMetadata


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """The cover lookup reaches iTunes. Every test here either overrides it
    or must not be making the call at all."""
    monkeypatch.setattr(
        module, "fetch_into", lambda *a, **k: pytest.fail("cover lookup was not expected here")
    )


@pytest.fixture(autouse=True)
def no_auto_load(monkeypatch):
    """Choosing a folder now reads its files' tags straight away, which
    would touch real (garbage, zero-byte) test fixtures via mutagen. Yields
    the real method, for the tests that do want it."""
    real = FolderRecordDialog._load
    monkeypatch.setattr(FolderRecordDialog, "_load", lambda self: None)
    return real


def _png() -> bytes:
    """A real one-pixel image: these bytes go through a QPixmap."""
    from PySide6.QtCore import QBuffer
    from PySide6.QtGui import QColor, QImage

    image = QImage(1, 1, QImage.Format.Format_ARGB32)
    image.fill(QColor("red"))
    buffer = QBuffer()
    buffer.open(QBuffer.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(buffer.data())


def _album(folder: Path, *names: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    for name in names:
        (folder / name).write_bytes(b"x")
    return folder


def _item(number="", title="", album_artist="", album="", date="", length="200", artist="", path=""):
    return tracks.PlaylistItem(
        track_number=number,
        title=title,
        album_artist=album_artist,
        album=album,
        date=date,
        length_seconds=int(length or 0),
        artist=artist,
        path=path,
    )


def _tagged_items():
    return [
        _item("1", "Feel Invincible", "Skillet", "Unleashed", "2016", "212", "Skillet", "/m/01.flac"),
        _item("2", "Back From The Dead", "Skillet", "Unleashed", "2016", "200", "Skillet", "/m/02.flac"),
    ]


# --- choosing a folder ------------------------------------------------


def test_picking_a_folder_lists_its_tracks_in_playing_order(qt_app, tmp_path):
    dialog = FolderRecordDialog()
    dialog.set_folder(_album(tmp_path / "album", "02 B.flac", "10 J.flac", "01 A.flac"))

    shown = [dialog.tree.topLevelItem(i).text(1) for i in range(dialog.tree.topLevelItemCount())]
    assert shown == ["01 A", "02 B", "10 J"]


def test_choosing_a_folder_loads_it_straight_away(qt_app, tmp_path, monkeypatch):
    """Picking a folder in this dialog *is* the decision -- asking the user
    to then press "Load Folder" was asking them to confirm something they
    had just done."""
    loads: list = []
    monkeypatch.setattr(FolderRecordDialog, "_load", lambda self: loads.append(True))
    dialog = FolderRecordDialog()

    dialog.set_folder(_album(tmp_path / "album", "01 A.flac"))

    assert loads == [True]


def test_a_folder_with_nothing_in_it_is_not_sent_anywhere(qt_app, tmp_path, monkeypatch):
    monkeypatch.setattr(
        FolderRecordDialog, "_load", lambda self: pytest.fail("nothing to load")
    )
    dialog = FolderRecordDialog()
    (tmp_path / "empty").mkdir()

    dialog.set_folder(tmp_path / "empty")


def test_a_folder_with_no_audio_cannot_be_recorded(qt_app, tmp_path):
    dialog = FolderRecordDialog()
    (tmp_path / "empty").mkdir()
    dialog.set_folder(tmp_path / "empty")

    assert dialog.record_btn.isEnabled() is False


def test_the_album_is_guessed_from_the_folder_name(qt_app, tmp_path):
    """Not authoritative -- it fills editable fields, and the tags win over
    it as soon as they have been read. Without it an untagged folder has no
    name at all."""
    dialog = FolderRecordDialog()
    dialog.set_folder(_album(tmp_path / "Skillet - Unleashed (2016)", "01 A.flac"))

    assert dialog.artist_edit.text() == "Skillet"
    assert dialog.album_edit.text() == "Unleashed"
    assert dialog.year_spin.value() == 2016


def test_an_absurd_number_of_tracks_is_flagged_but_not_refused(qt_app, tmp_path):
    """Picking a whole library's root produces exactly this. It is the
    user's call, but it is worth saying out loud."""
    folder = _album(tmp_path / "library", *(f"{n:03d}.flac" for n in range(module.UNLIKELY_TRACK_COUNT + 5)))
    dialog = FolderRecordDialog()
    dialog.set_folder(folder)

    # isHidden(), not isVisible(): nothing in an unshown dialog is visible,
    # so isVisible() would pass whatever the code did.
    assert not dialog.warning_label.isHidden()
    assert dialog.warning_label.text()


def test_the_picker_comes_back_to_where_the_last_album_was(qt_app, tmp_path):
    """The parent, not the album itself: the next one is far more likely to
    be its sibling than inside it."""
    dialog = FolderRecordDialog()
    dialog.set_folder(_album(tmp_path / "Music" / "Skillet - Unleashed", "01 A.flac"))

    assert app_settings.music_folder() == str(tmp_path / "Music")
    assert FolderRecordDialog()._start_directory() == str(tmp_path / "Music")


# --- reading the tags ---------------------------------------------------


def test_a_real_load_reads_tags_directly_with_no_external_player(qt_app, tmp_path, monkeypatch, no_auto_load):
    """End to end through the real _load(), not _on_loaded() -- proving the
    swap from foobar2000 to tracks.playlist_items_from_paths actually
    happened."""
    monkeypatch.setattr(module, "fetch_into", lambda *a, **k: None)
    monkeypatch.setattr(module.tracks, "playlist_items_from_paths", lambda paths: _tagged_items())
    dialog = FolderRecordDialog()
    dialog.set_folder(_album(tmp_path / "Skillet - Unleashed", "01 A.flac", "02 B.flac"))

    no_auto_load(dialog)  # the real _load, which the fixture stubbed out

    shown = [dialog.tree.topLevelItem(i).text(1) for i in range(dialog.tree.topLevelItemCount())]
    assert shown == ["Feel Invincible", "Back From The Dead"]
    assert dialog.record_btn.isEnabled()


def test_loading_shows_the_files_without_closing(qt_app, tmp_path, monkeypatch):
    """Two presses, not one: what was found has to be on screen before the
    recording window opens over it."""
    monkeypatch.setattr(module, "fetch_into", lambda *a, **k: None)
    dialog = FolderRecordDialog()
    dialog.set_folder(_album(tmp_path / "Skillet - Unleashed", "01 A.flac", "02 B.flac"))

    dialog._on_loaded(_tagged_items())

    shown = [dialog.tree.topLevelItem(i).text(1) for i in range(dialog.tree.topLevelItemCount())]
    assert shown == ["Feel Invincible", "Back From The Dead"]
    assert dialog.result() != QDialog.DialogCode.Accepted, "still open to be looked at"
    assert dialog.record_btn.isEnabled()

    dialog._on_record()

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.result_metadata.album == "Unleashed"
    assert dialog.result_paths == dialog._paths


def test_a_cover_chosen_by_hand_survives_the_hand_over(qt_app, tmp_path, monkeypatch):
    """The preview is clickable, so a corrected sleeve has to reach the
    recording rather than being overwritten by the captured one."""
    monkeypatch.setattr(module, "fetch_into", lambda *a, **k: None)
    dialog = FolderRecordDialog()
    dialog.set_folder(_album(tmp_path / "Skillet - Unleashed", "01 A.flac"))
    dialog._on_loaded(_tagged_items())
    dialog.cover_label.set_cover(_png())

    dialog._on_record()

    assert dialog.result_metadata.cover_art == _png()


def test_recording_before_anything_is_loaded_does_nothing(qt_app, tmp_path):
    dialog = FolderRecordDialog()
    dialog.set_folder(_album(tmp_path / "album", "01 A.flac"))

    dialog._on_record()

    assert dialog.result_metadata is None
    assert dialog.result() != QDialog.DialogCode.Accepted


# --- what the disc gets titled from -----------------------------------


def test_the_tags_are_what_the_titles_come_from(qt_app, tmp_path, monkeypatch):
    monkeypatch.setattr(module, "fetch_into", lambda *a, **k: None)
    dialog = FolderRecordDialog()
    dialog.set_folder(_album(tmp_path / "whatever", "01 A.flac"))

    metadata = dialog._capture_metadata(_tagged_items())

    assert [track.title for track in metadata.tracks] == ["Feel Invincible", "Back From The Dead"]
    assert (metadata.artist, metadata.album) == ("Skillet", "Unleashed")


def test_an_untagged_folder_is_titled_from_its_filenames(qt_app, tmp_path, monkeypatch):
    """The case this whole feature has to cope with. The album name comes
    from the folder, the track names from the files."""
    monkeypatch.setattr(module, "fetch_into", lambda *a, **k: None)
    dialog = FolderRecordDialog()
    dialog.set_folder(_album(tmp_path / "Kult - Posluchaj", "01 Arahja.flac"))

    metadata = dialog._capture_metadata(
        [_item(length="100", path="/m/01 Arahja.flac"), _item(length="90", path="/m/02 Dziewczyna.flac")]
    )

    assert [track.title for track in metadata.tracks] == ["01 Arahja", "02 Dziewczyna"]
    assert (metadata.artist, metadata.album) == ("Kult", "Posluchaj")


def test_what_the_user_typed_beats_what_the_tags_say(qt_app, tmp_path, monkeypatch):
    """Nothing here rewrites the user's files, so a correction made in this
    dialog reaches the disc only by being carried forward."""
    monkeypatch.setattr(module, "fetch_into", lambda *a, **k: None)
    dialog = FolderRecordDialog()
    dialog.set_folder(_album(tmp_path / "album", "01 A.flac"))
    dialog.artist_edit.setText("Skillet")
    dialog.album_edit.setText("Unleashed Beyond")
    dialog.year_spin.setValue(2017)

    metadata = dialog._capture_metadata(_tagged_items())

    assert (metadata.artist, metadata.album, metadata.year) == ("Skillet", "Unleashed Beyond", 2017)


def test_the_folder_name_never_renames_a_properly_tagged_album(qt_app, tmp_path, monkeypatch):
    """The bug the three-way precedence exists to stop. The fields are
    prefilled from the folder name before a single tag has been read, so
    treating whatever is in them as the user's word let a folder called
    "Disc 1" rename a tagged record to "Disc 1"."""
    monkeypatch.setattr(module, "fetch_into", lambda *a, **k: None)
    dialog = FolderRecordDialog()
    dialog.set_folder(_album(tmp_path / "Disc 1", "01 A.flac"))
    assert dialog.album_edit.text() == "Disc 1", "precondition: the guess is in the field"

    metadata = dialog._capture_metadata(_tagged_items())

    assert metadata.album == "Unleashed"


def test_a_blank_field_leaves_the_tags_alone(qt_app, tmp_path, monkeypatch):
    monkeypatch.setattr(module, "fetch_into", lambda *a, **k: None)
    dialog = FolderRecordDialog()
    dialog.set_folder(_album(tmp_path / "album", "01 A.flac"))
    dialog.artist_edit.clear()
    dialog.album_edit.clear()
    dialog.year_spin.setValue(0)

    metadata = dialog._capture_metadata(_tagged_items())

    assert (metadata.artist, metadata.album, metadata.year) == ("Skillet", "Unleashed", 2016)


def test_a_cover_is_fetched_for_an_ordinary_album(qt_app, tmp_path, monkeypatch):
    class _Chosen:
        artist_name, collection_name, year = "Skillet", "Unleashed", 2016

    def fake_fetch(preview, artist, album, track_count=None):
        preview.set_cover(_png())
        return _Chosen()

    monkeypatch.setattr(module, "fetch_into", fake_fetch)
    dialog = FolderRecordDialog()
    dialog.set_folder(_album(tmp_path / "album", "01 A.flac"))

    metadata = dialog._capture_metadata(_tagged_items())

    assert metadata.cover_art == _png()


def test_a_compilation_gets_a_drawn_cover_and_no_search(qt_app, tmp_path):
    """Searching for "Various Artists" returns some unrelated record's
    sleeve, which would then be printed on this disc as though it belonged
    to it. The autouse fixture fails the test if a search happens."""
    dialog = FolderRecordDialog()
    dialog.set_folder(_album(tmp_path / "mixtape", "01 A.flac"))
    dialog.artist_edit.clear()
    dialog.album_edit.clear()

    metadata = dialog._capture_metadata(
        [
            _item(title="Blue Monday", artist="New Order", length="100", path="/m/1.flac"),
            _item(title="A Forest", artist="The Cure", length="100", path="/m/2.flac"),
            _item(title="Enjoy The Silence", artist="Depeche Mode", length="100", path="/m/3.flac"),
        ]
    )

    assert metadata.is_compilation()
    assert metadata.cover_art, "one is drawn from the track list instead"


def test_a_failed_lookup_still_leaves_usable_metadata(qt_app, tmp_path, monkeypatch):
    """Artwork is a bonus on top of a capture that has already succeeded --
    the same rule MetadataDialog follows. cover_preview.fetch_into swallows
    the network error itself and answers None, which is what this sees."""
    monkeypatch.setattr(module, "fetch_into", lambda *a, **k: None)
    dialog = FolderRecordDialog()
    dialog.set_folder(_album(tmp_path / "album", "01 A.flac"))

    metadata = dialog._capture_metadata(_tagged_items())

    assert len(metadata.tracks) == 2
    assert metadata.cover_art is None


def test_a_year_the_tags_did_not_have_is_taken_from_the_lookup(qt_app, tmp_path, monkeypatch):
    class _Chosen:
        artist_name, collection_name, year = "Skillet", "Unleashed", 2016

    monkeypatch.setattr(module, "fetch_into", lambda *a, **k: _Chosen())
    dialog = FolderRecordDialog()
    dialog.set_folder(_album(tmp_path / "album", "01 A.flac"))
    dialog.year_spin.setValue(0)

    untagged_year = [_item(title="A", album_artist="Skillet", album="Unleashed", length="100")]
    assert dialog._capture_metadata(untagged_year).year == 2016


def test_nothing_at_all_to_search_by_is_not_a_lookup(qt_app, tmp_path):
    """The autouse fixture fails on a search: with no artist and no album
    there is nothing to search for."""
    dialog = FolderRecordDialog()
    (tmp_path / "  ").mkdir(exist_ok=True)
    dialog.artist_edit.clear()
    dialog.album_edit.clear()

    metadata = dialog._capture_metadata([_item(title="Something", length="100")])

    assert isinstance(metadata, ProjectMetadata)
    assert metadata.cover_art is None


def test_a_cover_inside_the_files_is_used_when_the_search_finds_none(qt_app, tmp_path, monkeypatch):
    """Last resort, and a good one: a folder ripped from somebody's own CDs
    routinely carries the sleeve, and it is certainly the right one for
    this release."""
    monkeypatch.setattr(module, "fetch_into", lambda *a, **k: None)
    monkeypatch.setattr(module.embedded_cover, "cover_from_files", lambda paths: _png())
    dialog = FolderRecordDialog()
    dialog.set_folder(_album(tmp_path / "Skillet - Unleashed", "01 A.flac"))

    metadata = dialog._capture_metadata(_tagged_items())

    assert metadata.cover_art == _png()


def test_the_search_still_wins_over_what_is_in_the_files(qt_app, tmp_path, monkeypatch):
    """Embedded art is whatever the ripper attached -- often a 300px scan;
    iTunes returns a clean 600x600, which is what a printed label wants."""
    def fake_fetch(preview, artist, album, track_count=None):
        preview.set_cover(_png())
        return None

    monkeypatch.setattr(module, "fetch_into", fake_fetch)
    monkeypatch.setattr(
        module.embedded_cover,
        "cover_from_files",
        lambda paths: pytest.fail("must not open the files when the search answered"),
    )
    dialog = FolderRecordDialog()
    dialog.set_folder(_album(tmp_path / "Skillet - Unleashed", "01 A.flac"))

    assert dialog._capture_metadata(_tagged_items()).cover_art == _png()
