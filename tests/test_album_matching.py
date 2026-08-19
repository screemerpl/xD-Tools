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


# --- when nothing is actually a match ---------------------------------
#
# The real failure this floor exists for: a folder of Falling In Reverse's
# "Popular Monster" -- an album iTunes does not carry at all -- came back
# with a one-track cover version of the title track by an unrelated artist,
# and its sleeve was shown as though it belonged to the disc. These four are
# what the live search actually returned, scores included.


COVER_VERSIONS = [
    _candidate("Alex Krotz", "Popular Monster - Single", 1, cid=10),
    _candidate("Way of the Future", "Popular Monster - Single", 1, cid=11),
    _candidate("TruthBound AKA Daqtrrican", "Popular Monster - Single", 1, cid=12),
    _candidate("WetNLoud", "Popular Monster - Single", 1, cid=13),
]


def test_the_right_title_by_the_wrong_artist_is_not_a_match():
    """A wrong edition of the right record is a nuisance; a wrong record is
    a different album's artwork printed on this disc."""
    assert best_match(COVER_VERSIONS, ARTIST, TITLE, 12) is None


def test_the_right_title_and_the_right_track_count_are_still_not_enough():
    """The blended score alone cannot carry this, which is worth pinning
    because it looks as though it should: title (0.55) plus a track count
    that happens to agree (0.15) reaches the floor exactly, with the artist
    contributing nothing. So the artist is checked on its own terms too."""
    title_only = _candidate("Somebody Else Entirely", TITLE, 11)

    assert match_confidence(title_only, ARTIST, TITLE, 11) >= 0.70, "the blend alone lets it through"
    assert best_match([title_only], ARTIST, TITLE, 11) is None


def test_with_no_artist_to_compare_the_artist_check_does_not_apply():
    """Somebody who only knows the album name gets the blended score's
    answer -- there is nothing to judge the artist against."""
    assert best_match([TRIBUTE], "", TITLE, 11) is TRIBUTE


def test_a_real_match_is_comfortably_above_the_floor():
    """The gap has to be wide enough that ordinary hits are never refused --
    including one found without knowing the track count, which costs 0.15
    of the total on its own."""
    from mdtools.metadata_lookup import MIN_MATCH_CONFIDENCE

    assert match_confidence(ALBUM, ARTIST, TITLE, 11) > MIN_MATCH_CONFIDENCE
    assert match_confidence(ALBUM, ARTIST, TITLE, None) > MIN_MATCH_CONFIDENCE
    assert match_confidence(DELUXE, ARTIST, TITLE, 15) > MIN_MATCH_CONFIDENCE
    assert best_match([SINGLE, ALBUM], ARTIST, TITLE) is ALBUM


def test_a_guest_credit_on_the_release_still_matches():
    """Common enough to be worth pinning: the artist string is not always
    the bare band name."""
    featured = _candidate("Falling In Reverse & Jelly Roll", TITLE, 11)
    assert best_match([featured], ARTIST, TITLE, 11) is featured

