"""Telling a mixtape apart from an album, and what follows from it.

Half of these tests exist to pin down the *negative* case. Getting a
compilation wrong in the interesting direction is merely a wrong-looking
cover; getting an ordinary album wrongly flagged renames it to "Various
Artists", strips its sleeve and rewrites its J-card -- so the ordinary path
has to be provably untouched.
"""

from __future__ import annotations

from mdtools import foobar
from mdtools.project import (
    MIXTAPE_ALBUM,
    VARIOUS_ARTISTS,
    ProjectMetadata,
    Track,
    apply_compilation_naming,
    numbered_track_lines,
)


def _album() -> ProjectMetadata:
    """An ordinary album, credited to one band, with a guest feature on it
    -- the case that must never be read as a compilation."""
    return ProjectMetadata(
        album="Popular Monster",
        artist="Falling In Reverse",
        tracks=[
            Track("Prequel", 234, "Falling In Reverse"),
            Track("Popular Monster", 221, "Falling In Reverse"),
            Track("All My Life", 190, "Falling In Reverse, Jelly Roll"),
            Track("Watch The World Burn", 202, "Falling In Reverse"),
        ],
    )


def _mixtape() -> ProjectMetadata:
    return ProjectMetadata(
        tracks=[
            Track("Blue Monday", 434, "New Order"),
            Track("Just Like Heaven", 213, "The Cure"),
            Track("Enjoy the Silence", 373, "Depeche Mode"),
            Track("Tainted Love", 160, "Soft Cell"),
        ],
    )


# --- the negative case, which matters most ----------------------------


def test_an_ordinary_album_is_not_a_compilation():
    assert _album().is_compilation() is False


def test_a_guest_feature_does_not_make_an_album_a_compilation():
    """"Falling In Reverse, Jelly Roll" is the same record's own track. This
    is the exact distinction foobar.album_artist() was already written to
    respect, and it must not be undone here."""
    album = _album()
    assert len({track.artist for track in album.tracks}) > 1, "precondition: the credits do differ"
    assert album.is_compilation() is False


def test_an_album_with_no_per_track_artists_at_all_is_not_a_compilation():
    """A hand-typed track list, or one from a metadata lookup, carries no
    performers. Absence of evidence is not evidence of a mixtape."""
    metadata = ProjectMetadata(album="Nevermind", artist="Nirvana", tracks=[Track("Breed"), Track("Lithium")])
    assert metadata.is_compilation() is False


def test_naming_leaves_an_ordinary_album_completely_alone():
    before = _album()
    after = apply_compilation_naming(_album())
    assert (after.album, after.artist) == (before.album, before.artist)


def test_an_ordinary_albums_track_lines_are_unchanged_by_the_artist_field():
    """The J-card, the insert menu and the two-column split all read this.
    An album's every line naming the same band would be twelve redundant
    repetitions of the heading directly above them."""
    assert numbered_track_lines(_album())[0] == "1. Prequel (3:54)"


# --- the positive case ------------------------------------------------


def test_unrelated_artists_make_a_compilation():
    assert _mixtape().is_compilation() is True


def test_a_release_credited_to_various_artists_is_taken_at_its_word():
    metadata = ProjectMetadata(album="Now 50", artist="Various Artists", tracks=[Track("A"), Track("B")])
    assert metadata.is_compilation() is True


def test_naming_a_mixtape_gives_it_both_a_name_and_an_honest_credit():
    named = apply_compilation_naming(_mixtape())
    assert named.artist == VARIOUS_ARTISTS
    assert named.album == MIXTAPE_ALBUM


def test_a_released_compilation_keeps_its_own_album_title():
    """"Now That's What I Call Music 50" is the name of the thing; only the
    artist needed correcting."""
    named = apply_compilation_naming(
        ProjectMetadata(album="Now 50", artist="Various", tracks=[Track("A", 10, "Blur"), Track("B", 10, "Oasis")])
    )
    assert named.album == "Now 50"
    assert named.artist == VARIOUS_ARTISTS


def test_a_mixtapes_track_lines_name_who_plays_on_each_one():
    lines = numbered_track_lines(apply_compilation_naming(_mixtape()))
    assert lines[0] == "1. New Order - Blue Monday (7:14)"


# --- through foobar ---------------------------------------------------


def _items(rows: list[tuple[str, str, str, str]]) -> list[foobar.PlaylistItem]:
    """rows of (title, album artist, album, artist)."""
    return [
        foobar.PlaylistItem(
            track_number=str(index),
            title=title,
            album_artist=album_artist,
            album=album,
            date="2001",
            length_seconds=200,
            artist=artist,
        )
        for index, (title, album_artist, album, artist) in enumerate(rows, start=1)
    ]


def test_a_playlist_of_one_album_still_becomes_that_album():
    items = _items(
        [
            ("Prequel", "Falling In Reverse", "Popular Monster", "Falling In Reverse"),
            ("All My Life", "Falling In Reverse", "Popular Monster", "Falling In Reverse, Jelly Roll"),
        ]
    )
    metadata = foobar.metadata_from_playlist(items)

    assert metadata.album == "Popular Monster"
    assert metadata.artist == "Falling In Reverse"
    assert metadata.is_compilation() is False


def test_a_playlist_of_unrelated_tracks_becomes_a_mixtape():
    """Each track's own album would otherwise be printed as the disc's --
    whichever one happened to be first."""
    items = _items(
        [
            ("Blue Monday", "New Order", "Power, Corruption & Lies", "New Order"),
            ("Just Like Heaven", "The Cure", "Kiss Me", "The Cure"),
            ("Tainted Love", "Soft Cell", "Non-Stop Erotic Cabaret", "Soft Cell"),
        ]
    )
    metadata = foobar.metadata_from_playlist(items)

    assert metadata.is_compilation() is True
    assert metadata.artist == VARIOUS_ARTISTS
    assert metadata.album == MIXTAPE_ALBUM
    assert [track.artist for track in metadata.tracks] == ["New Order", "The Cure", "Soft Cell"]


def test_a_half_tagged_album_keeps_its_name():
    """Untagged tracks are not votes against the album's title -- counting
    them as such would strip the name off an ordinary record."""
    items = _items(
        [
            ("One", "Metallica", "...And Justice for All", "Metallica"),
            ("Blackened", "Metallica", "", "Metallica"),
            ("Harvester of Sorrow", "Metallica", "", "Metallica"),
        ]
    )
    assert foobar.album_title(items) == "...And Justice for All"


def test_an_album_shared_by_nobody_reports_no_album_at_all():
    items = _items([("A", "X", "Album X", "X"), ("B", "Y", "Album Y", "Y")])
    assert foobar.album_title(items) == ""


def test_the_playlist_columns_ask_for_both_artist_fields():
    """The difference between them is the entire signal. Losing either one
    would make every compilation look like an album, or every guest feature
    look like a compilation."""
    assert "%artist%" in foobar._COLUMNS
    assert "%album artist%" in foobar._COLUMNS


def test_an_item_from_a_short_column_list_still_has_an_artist_field():
    """Beefweb returning fewer columns than asked for must not raise -- the
    existing padding behaviour has to cover the new column too."""
    item = foobar.PlaylistItem.from_columns(["01", "Title"])
    assert item.artist == ""


# --- through the Metadata dialog --------------------------------------


def test_the_metadata_dialog_does_not_lose_per_track_artists(qt_app):
    """Opening Project > Metadata... on a mixtape and pressing OK rebuilds
    the track list out of the table. Before the artist column existed that
    silently dropped every performer, and the project stopped being a
    compilation just for having been looked at."""
    from mdtools.panels.metadata_dialog import MetadataDialog

    dialog = MetadataDialog(apply_compilation_naming(_mixtape()))
    result = dialog._current_metadata()

    assert [track.artist for track in result.tracks] == ["New Order", "The Cure", "Depeche Mode", "Soft Cell"]
    assert result.is_compilation() is True


def test_an_ordinary_album_round_trips_through_the_dialog_unchanged(qt_app):
    from mdtools.panels.metadata_dialog import MetadataDialog

    before = _album()
    result = MetadataDialog(before)._current_metadata()

    assert result.album == before.album
    assert result.artist == before.artist
    assert [t.title for t in result.tracks] == [t.title for t in before.tracks]
    assert result.is_compilation() is False


def test_per_track_artists_survive_a_save_and_reload(tmp_path, qt_app):
    """The field is written into .mdproj, and a project saved before it
    existed loads as an ordinary album -- which is what it was."""
    from mdtools.io.project_io import _metadata_from_dict, _metadata_to_dict

    restored = _metadata_from_dict(_metadata_to_dict(apply_compilation_naming(_mixtape())))
    assert [track.artist for track in restored.tracks] == ["New Order", "The Cure", "Depeche Mode", "Soft Cell"]
    assert restored.is_compilation() is True

    older = _metadata_from_dict({"album": "A", "artist": "B", "tracks": [{"title": "T"}]})
    assert older.tracks[0].artist == ""
    assert older.is_compilation() is False
