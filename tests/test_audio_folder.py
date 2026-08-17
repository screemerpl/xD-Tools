"""Finding an album in a folder of files.

Two things this module decides and nothing else does: which files are part
of the album, and what order they play in. Everything after that -- titles,
artists, lengths -- comes out of foobar2000, which has already read the
tags, so there is nothing here to test about metadata.

No Qt in any of these: audio_folder.py imports none.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mdtools import audio_folder


def _make(folder: Path, *names: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    for name in names:
        path = folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"not really audio")
    return folder


# --- which files ------------------------------------------------------


def test_the_usual_formats_are_all_recognised(tmp_path):
    _make(tmp_path, "a.flac", "b.mp3", "c.m4a", "d.ogg", "e.opus", "f.wav", "g.wma")
    assert len(audio_folder.list_audio_files(tmp_path)) == 7


def test_an_extension_in_capitals_still_counts(tmp_path):
    _make(tmp_path, "TRACK01.FLAC", "TRACK02.Mp3")
    assert len(audio_folder.list_audio_files(tmp_path)) == 2


def test_everything_that_is_not_audio_is_left_out(tmp_path):
    """An album folder routinely holds a cue sheet, a log, artwork and a
    text file. None of them are tracks."""
    _make(tmp_path, "01 Song.flac", "album.cue", "rip.log", "cover.jpg", "notes.txt", "playlist.m3u")
    assert [path.name for path in audio_folder.list_audio_files(tmp_path)] == ["01 Song.flac"]


def test_a_folder_with_no_audio_at_all_gives_nothing_rather_than_raising(tmp_path):
    _make(tmp_path, "cover.jpg")
    assert audio_folder.list_audio_files(tmp_path) == []


def test_a_path_that_is_not_a_folder_gives_nothing(tmp_path):
    missing = tmp_path / "nope"
    assert audio_folder.list_audio_files(missing) == []
    assert audio_folder.list_audio_files(_make(tmp_path, "x.flac") / "x.flac") == []


# --- what order -------------------------------------------------------


def test_tracks_come_back_in_numeric_order_not_alphabetical(tmp_path):
    """The bug a plain sorted() has: "10" sorts before "2", so an album
    would be recorded 1, 10, 11, 2, 3 ... and titled to match."""
    _make(tmp_path, *(f"{n} Song.flac" for n in (1, 2, 3, 9, 10, 11, 12)))
    numbers = [int(path.name.split()[0]) for path in audio_folder.list_audio_files(tmp_path)]
    assert numbers == [1, 2, 3, 9, 10, 11, 12]


def test_zero_padded_and_unpadded_numbers_sort_together(tmp_path):
    _make(tmp_path, "01 A.flac", "2 B.flac", "003 C.flac")
    assert [p.name for p in audio_folder.list_audio_files(tmp_path)] == ["01 A.flac", "2 B.flac", "003 C.flac"]


def test_names_with_and_without_a_leading_number_do_not_raise(tmp_path):
    """Mixing the two is what makes a naive natural-sort key raise
    TypeError, by comparing an int against a str."""
    _make(tmp_path, "01 Numbered.flac", "Intro.flac", "99 Last.flac", "bonus.flac")
    assert len(audio_folder.list_audio_files(tmp_path)) == 4


def test_unnumbered_names_fall_back_to_alphabetical(tmp_path):
    _make(tmp_path, "Zoo.flac", "apple.flac", "Mango.flac")
    assert [p.name for p in audio_folder.list_audio_files(tmp_path)] == ["apple.flac", "Mango.flac", "Zoo.flac"]


# --- subfolders -------------------------------------------------------


def test_a_two_disc_album_kept_in_subfolders_comes_back_in_disc_order(tmp_path):
    _make(tmp_path / "CD1", "01 A.flac", "02 B.flac")
    _make(tmp_path / "CD2", "01 C.flac", "02 D.flac")

    found = audio_folder.list_audio_files(tmp_path)

    assert [p.name for p in found] == ["01 A.flac", "02 B.flac", "01 C.flac", "02 D.flac"]


def test_subfolders_are_ignored_when_the_folder_itself_holds_the_album(tmp_path):
    """The rule that stops a folder of albums quietly becoming one giant
    recording: a folder with tracks in it *is* the album, and whatever is
    below it (scans, a bonus disc, an alternate mix) is not part of the
    running order."""
    _make(tmp_path, "01 A.flac", "02 B.flac")
    _make(tmp_path / "bonus", "outtake.flac")

    assert [p.name for p in audio_folder.list_audio_files(tmp_path)] == ["01 A.flac", "02 B.flac"]


def test_ten_or_more_discs_still_sort_numerically(tmp_path):
    for disc in (1, 2, 10):
        _make(tmp_path / f"CD{disc}", "01 A.flac")
    order = [p.parent.name for p in audio_folder.list_audio_files(tmp_path)]
    assert order == ["CD1", "CD2", "CD10"]


# --- guessing an album from the folder's own name ---------------------
#
# Only ever a suggestion, shown in editable fields. It exists because an
# untagged folder otherwise produces a disc with twelve titles and no name:
# nothing else on the machine knows what the album is.


@pytest.mark.parametrize(
    "name,expected",
    [
        ("Skillet - Unleashed (2016)", ("Skillet", "Unleashed", 2016)),
        ("Skillet - Unleashed", ("Skillet", "Unleashed", None)),
        ("Skillet - Unleashed [2016]", ("Skillet", "Unleashed", 2016)),
        ("Unleashed", ("", "Unleashed", None)),
        ("Unleashed (2016)", ("", "Unleashed", 2016)),
        # A year in front is a sorting prefix in a per-artist library, not
        # somebody called "2016".
        ("2016 - Unleashed", ("", "Unleashed", 2016)),
        # An en dash is what a lot of taggers actually write.
        ("Kult – Ostateczny Krach", ("Kult", "Ostateczny Krach", None)),
    ],
)
def test_a_folder_name_is_read_the_way_mdtools_writes_one(name, expected):
    assert audio_folder.guess_from_folder_name(name) == expected


def test_only_the_first_separator_splits_so_a_dash_in_the_title_survives():
    artist, album, _ = audio_folder.guess_from_folder_name("AC-DC - Rock - Or Bust")
    assert (artist, album) == ("AC-DC", "Rock - Or Bust")


def test_a_hyphen_with_no_spaces_is_part_of_a_word_not_a_separator():
    assert audio_folder.guess_from_folder_name("Jay-Z")[1] == "Jay-Z"


def test_a_number_that_is_not_a_year_is_left_in_the_title():
    assert audio_folder.guess_from_folder_name("Blink 182")[1] == "Blink 182"


def test_an_empty_name_does_not_raise():
    assert audio_folder.guess_from_folder_name("") == ("", "", None)
