"""tracks.py -- the metadata half of retiring foobar2000: PlaylistItem and
the pure disc/track ordering and metadata-building functions that used to
live in foobar.py, migrated verbatim (see tracks.py's own module
docstring). These tests are themselves migrated from test_foobar.py's own
coverage of the same functions.
"""

from pathlib import Path

import pytest

from mdtools import tracks


def _item(
    track_number="",
    title="",
    album_artist="",
    album="",
    date="",
    length_seconds=0,
    artist="",
    path="",
    disc_number="",
) -> tracks.PlaylistItem:
    return tracks.PlaylistItem(
        track_number=track_number,
        title=title,
        album_artist=album_artist,
        album=album,
        date=date,
        length_seconds=length_seconds,
        artist=artist,
        path=path,
        disc_number=disc_number,
    )


def _items() -> list[tracks.PlaylistItem]:
    return [
        _item("01", "Prequel", "Falling In Reverse", "Popular Monster", "2024-08-16", 234),
        _item("02", "Popular Monster", "Falling In Reverse", "Popular Monster", "2024-08-16", 221),
        _item(
            "03",
            "All My Life",
            "Falling In Reverse, Jelly Roll",
            "Popular Monster",
            "2024-08-16",
            190,
        ),
    ]


# --- album fields ------------------------------------------------------


def test_album_artist_is_the_albums_own_not_the_first_tracks_credits():
    """Track 3 credits a guest; the disc title must not inherit that."""
    assert tracks.album_artist(_items()) == "Falling In Reverse"


def test_year_is_taken_from_the_leading_digits_of_whatever_date_holds():
    assert tracks.album_year(_items()) == 2024
    assert tracks.album_year([_item(date="1998")]) == 1998
    assert tracks.album_year([_item(date="")]) is None
    assert tracks.album_year([_item(date="unknown")]) is None


def test_total_time_adds_up_the_tracks():
    assert tracks.total_seconds(_items()) == 234 + 221 + 190


def test_playlist_becomes_project_metadata():
    metadata = tracks.metadata_from_playlist(_items())
    assert (metadata.album, metadata.artist, metadata.year) == ("Popular Monster", "Falling In Reverse", 2024)
    assert [track.title for track in metadata.tracks] == ["Prequel", "Popular Monster", "All My Life"]
    assert metadata.tracks[0].time_seconds == 234


def test_metadata_from_an_empty_playlist_is_empty_not_an_error():
    metadata = tracks.metadata_from_playlist([])
    assert metadata.album == "" and metadata.tracks == []


# --- untagged files ------------------------------------------------------
#
# What Record Folder exists for: somebody's own folder of files, which may
# carry no tags at all. A disc full of blank track names is not a risk
# worth taking, so display_title() falls back to the filename.


def test_a_file_with_no_title_tag_is_named_after_its_file():
    item = _item(length_seconds=212, path=r"C:\Music\Skillet\03 Feel Invincible.flac")
    assert item.display_title() == "03 Feel Invincible"


def test_a_real_title_always_wins_over_the_filename():
    item = _item(
        "3", "Feel Invincible", "Skillet", "Unleashed", "2016", 212, "Skillet", r"C:\Music\track03.flac"
    )
    assert item.display_title() == "Feel Invincible"


def test_no_title_and_no_path_is_still_just_empty():
    assert _item().display_title() == ""


def test_the_filename_fallback_reaches_the_track_list():
    """The point of it: this is what gets written onto the disc."""
    items = [
        _item(length_seconds=100, path="/music/mix/01 Unknown Song.mp3"),
        _item(length_seconds=100, path="/music/mix/02 Another.mp3"),
    ]
    titles = [track.title for track in tracks.metadata_from_playlist(items).tracks]
    assert titles == ["01 Unknown Song", "02 Another"]


# --- the album's own order ------------------------------------------------


def _tagged(disc: str, track: str, name: str = "") -> tracks.PlaylistItem:
    return _item(
        track_number=track,
        title=name or f"{disc}-{track}",
        length_seconds=0,
        path=f"{name or disc + track}.flac",
        disc_number=disc,
    )


def test_a_double_album_is_put_back_into_disc_then_track_order():
    """Observed live: a two-disc album dropped into a folder as one arrives
    interleaved -- 2, 1, 2, 1 -- because both discs number their tracks
    from one and a plain filename sort doesn't know that."""
    interleaved = [_tagged("2", "01"), _tagged("1", "01"), _tagged("2", "02"), _tagged("1", "02")]

    ordered = tracks.sort_by_disc_and_track(interleaved)

    assert [(i.disc_number, i.track_number) for i in ordered] == [
        ("1", "01"), ("1", "02"), ("2", "01"), ("2", "02"),
    ]


def test_tags_written_as_one_of_two_sort_the_same_as_a_bare_number():
    ordered = tracks.sort_by_disc_and_track([_tagged("2/2", "1/12"), _tagged("1/2", "3/12")])
    assert [i.disc_number for i in ordered] == ["1/2", "2/2"]


def test_a_playlist_with_no_numbers_at_all_is_left_exactly_as_it_is():
    """No tags means no opinion -- and the order somebody assembled by hand
    beats one invented here."""
    untagged = [_item(title="b", path="b.flac"), _item(title="a", path="a.flac")]

    assert [i.title for i in tracks.sort_by_disc_and_track(untagged)] == ["b", "a"]


def test_a_file_missing_its_track_number_sinks_rather_than_displacing_the_album():
    stray = _item(title="stray", path="stray.flac", disc_number="1")
    ordered = tracks.sort_by_disc_and_track([stray, _tagged("1", "01"), _tagged("1", "02")])

    assert [i.title for i in ordered] == ["1-01", "1-02", "stray"]


def test_a_missing_disc_number_counts_as_disc_one():
    """Which is what every single-disc album's files look like."""
    plain = _item(track_number="02", title="second", path="2.flac")
    first = _item(track_number="01", title="first", path="1.flac")

    assert [i.title for i in tracks.sort_by_disc_and_track([plain, first])] == ["first", "second"]


def test_where_the_files_say_one_disc_ends():
    items = [_tagged("1", "01"), _tagged("1", "02"), _tagged("2", "01")]
    assert tracks.disc_breaks(items) == [2]


def test_a_single_disc_album_declares_no_breaks():
    assert tracks.disc_breaks([_tagged("1", "01"), _tagged("1", "02")]) == []
    assert tracks.disc_breaks([]) == []


# --- reading tags off real files ------------------------------------------


def test_playlist_items_from_paths_reads_real_tags(tmp_path):
    import mutagen
    import numpy as np
    import soundfile as sf

    path = tmp_path / "01.flac"
    samples = np.zeros((4410, 2), dtype=np.int16)
    with sf.SoundFile(str(path), mode="w", samplerate=44100, channels=2, subtype="PCM_16", format="FLAC") as f:
        f.title = "Feel Invincible"
        f.artist = "Skillet"
        f.write(samples)

    items = tracks.playlist_items_from_paths([path])

    assert items[0].title == "Feel Invincible"
    assert items[0].artist == "Skillet"
    assert items[0].path == str(path)


def test_playlist_items_from_paths_falls_back_on_an_unreadable_file(tmp_path):
    path = tmp_path / "broken.flac"
    path.write_bytes(b"not really a flac")

    items = tracks.playlist_items_from_paths([path])

    assert items[0].title == "broken"
    assert items[0].track_number == "1"
