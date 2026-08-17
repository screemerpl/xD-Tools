"""Picking the right release out of an iTunes search without asking the
user -- used by the automated record flow, which cannot stop and offer a
picker the way MetadataDialog does.

The cases here are the ones that actually go wrong in practice: a remix
single sharing the album's title, a deluxe reissue, and a tribute-album
cover version by a different artist.
"""

from mdtools.metadata_lookup import AlbumCandidate, best_match, match_confidence


def _candidate(artist: str, album: str, tracks: int, cid: int = 0) -> AlbumCandidate:
    return AlbumCandidate(
        collection_id=cid, artist_name=artist, collection_name=album, year=2024, track_count=tracks
    )


ALBUM = _candidate("Falling In Reverse", "Popular Monster", 11, cid=2)
SINGLE = _candidate("Falling In Reverse", "Popular Monster - Single", 1, cid=1)
DELUXE = _candidate("Falling In Reverse", "Popular Monster (Deluxe Edition)", 15, cid=3)
TRIBUTE = _candidate("Tribute Players", "Popular Monster", 11, cid=4)

ARTIST, TITLE = "Falling In Reverse", "Popular Monster"


def test_an_exact_match_scores_perfectly():
    assert match_confidence(ALBUM, ARTIST, TITLE, 11) == 1.0


def test_the_right_album_beats_its_single_its_deluxe_and_a_cover_version():
    assert best_match([SINGLE, ALBUM, DELUXE, TRIBUTE], ARTIST, TITLE, 11) is ALBUM


def test_a_different_artist_loses_even_with_an_identical_title():
    assert match_confidence(TRIBUTE, ARTIST, TITLE, 11) < match_confidence(ALBUM, ARTIST, TITLE, 11)


def test_knowing_the_track_count_is_what_separates_an_album_from_its_deluxe():
    """The titles differ only by edition noise, which normalisation strips
    on purpose -- so the count is what is left to tell them apart."""
    assert match_confidence(ALBUM, ARTIST, TITLE, 11) > match_confidence(DELUXE, ARTIST, TITLE, 11)
    assert match_confidence(DELUXE, ARTIST, TITLE, 15) > match_confidence(ALBUM, ARTIST, TITLE, 15)


def test_a_single_never_wins_a_tie_against_a_full_album():
    """Stripping "single" as edition noise makes the two titles score
    identically, so the tiebreaker has to carry this."""
    assert best_match([SINGLE, ALBUM], ARTIST, TITLE) is ALBUM
    assert best_match([ALBUM, SINGLE], ARTIST, TITLE) is ALBUM


def test_punctuation_case_and_accents_do_not_matter():
    messy = _candidate("bjork", "homogenic", 10)
    assert match_confidence(messy, "Björk", "Homogénic!", 10) == 1.0


def test_reordered_names_still_match_closely():
    reordered = _candidate("Bowie, David", "Low", 11)
    natural = _candidate("Nirvana", "Nevermind", 12)
    assert match_confidence(reordered, "David Bowie", "Low", 11) > match_confidence(natural, "David Bowie", "Low", 11)


def test_nothing_to_choose_from_is_not_an_error():
    assert best_match([], ARTIST, TITLE, 11) is None


def test_a_completely_unrelated_result_scores_low():
    unrelated = _candidate("Some Other Band", "A Totally Different Record", 9)
    assert match_confidence(unrelated, ARTIST, TITLE, 11) < 0.35
