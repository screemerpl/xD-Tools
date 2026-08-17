"""Identifying a CD from its TOC.

The payload below is the real shape musicbrainz.org returns, trimmed to the
fields this app reads -- captured from a live query for the TOC of Nirvana's
Nevermind, which is also what test_cdrip.py's disc id is checked against.
"""

from __future__ import annotations

import io
import json
import urllib.error

import pytest

from mdtools import cdrip, musicbrainz


def _release(title, artist, date, country, track_titles, extra_medium=None):
    media = [{"tracks": [{"title": t} for t in track_titles]}]
    if extra_medium is not None:
        media.insert(0, {"tracks": [{"title": t} for t in extra_medium]})
    return {
        "id": f"id-{title}-{date}",
        "title": title,
        "date": date,
        "country": country,
        "artist-credit": [{"name": artist, "joinphrase": ""}],
        "media": media,
    }


PAYLOAD = {
    "releases": [
        _release("Nevermind", "Nirvana", "2011-09-20", "US", ["Smells Like Teen Spirit", "In Bloom", "Bonus"]),
        _release("Nevermind", "Nirvana", "1991-09-24", "US", ["Smells Like Teen Spirit", "In Bloom"]),
    ]
}


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def _opener(payload, *, recorder=None, error=None):
    def open_url(request, timeout=None):
        if recorder is not None:
            recorder.append(request.full_url)
        if error is not None:
            raise error
        return _Response(json.dumps(payload).encode())

    return open_url


def _toc(tracks=2):
    return cdrip.DiscToc(
        tracks=[cdrip.TocTrack(n + 1, n * 10000, 10000) for n in range(tracks)],
        leadout_lba=tracks * 10000,
    )


# --- parsing ----------------------------------------------------------


def test_a_release_carries_artist_album_year_and_titles():
    releases = musicbrainz.parse_releases(PAYLOAD, expected_tracks=2)
    best = releases[0]
    assert best.artist == "Nirvana"
    assert best.title == "Nevermind"
    assert best.year == 1991
    assert best.track_titles == ["Smells Like Teen Spirit", "In Bloom"]


def test_a_release_whose_track_count_matches_the_disc_outranks_one_that_does_not():
    """A reissue with a bonus track is the wrong answer even when it is the
    right album -- the disc in the drive has the track count it has."""
    releases = musicbrainz.parse_releases(PAYLOAD, expected_tracks=2)
    assert len(releases[0].track_titles) == 2
    assert len(releases[1].track_titles) == 3


def test_among_equally_good_matches_the_earliest_release_wins():
    payload = {
        "releases": [
            _release("A", "B", "2015", "US", ["x"]),
            _release("A", "B", "1979", "GB", ["x"]),
        ]
    }
    assert musicbrainz.parse_releases(payload, expected_tracks=1)[0].year == 1979


def test_the_right_disc_of_a_box_set_is_picked_by_track_count():
    """A multi-disc release lists every disc, and a TOC search does not
    narrow that down at all."""
    payload = {"releases": [_release("Set", "B", "1999", "US", ["d2a", "d2b"], extra_medium=["d1a"])]}
    assert musicbrainz.parse_releases(payload, expected_tracks=2)[0].track_titles == ["d2a", "d2b"]


def test_a_collaboration_is_reassembled_with_its_join_phrases():
    payload = {
        "releases": [
            {
                "id": "x",
                "title": "T",
                "artist-credit": [
                    {"name": "Bowie", "joinphrase": " & "},
                    {"name": "Queen", "joinphrase": ""},
                ],
                "media": [{"tracks": [{"title": "Under Pressure"}]}],
            }
        ]
    }
    assert musicbrainz.parse_releases(payload, 1)[0].artist == "Bowie & Queen"


def test_a_missing_or_partial_date_does_not_raise():
    payload = {"releases": [_release("A", "B", "", "US", ["x"]), _release("C", "D", "1988", "US", ["y"])]}
    years = {r.year for r in musicbrainz.parse_releases(payload, 1)}
    assert years == {None, 1988}


def test_the_label_says_enough_to_tell_two_pressings_apart():
    label = musicbrainz.parse_releases(PAYLOAD, 2)[0].label()
    assert "Nirvana" in label and "Nevermind" in label and "1991" in label and "2 tracks" in label


# --- the two queries --------------------------------------------------


def test_the_exact_disc_id_is_tried_first_and_ends_it_when_it_hits():
    urls: list[str] = []
    releases = musicbrainz.lookup_disc(_toc(), opener=_opener(PAYLOAD, recorder=urls))

    assert len(urls) == 1
    assert _toc().musicbrainz_disc_id() in urls[0]
    assert releases[0].title == "Nevermind"


def test_a_disc_nobody_has_submitted_falls_back_to_the_fuzzy_toc_search():
    """The two queries fail in opposite directions: the disc id is exact but
    only hits if somebody submitted this pressing, while the TOC search
    finds releases nobody ever submitted an id for."""
    urls: list[str] = []
    payloads = iter([{"releases": []}, PAYLOAD])

    def open_url(request, timeout=None):
        urls.append(request.full_url)
        return _Response(json.dumps(next(payloads)).encode())

    releases = musicbrainz.lookup_disc(_toc(), opener=open_url)

    assert len(urls) == 2
    assert "toc=" in urls[1]
    assert releases[0].title == "Nevermind"


def test_a_404_from_the_disc_id_lookup_is_an_ordinary_miss_not_a_failure():
    """Plenty of discs are in neither index. The caller is meant to let the
    user type the titles instead."""
    def open_url(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 404, "Not Found", {}, None)

    assert musicbrainz.lookup_disc(_toc(), opener=open_url) == []


def test_a_refused_request_is_reported_rather_than_swallowed():
    def open_url(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 503, "Service Unavailable", {}, None)

    with pytest.raises(musicbrainz.MusicBrainzError):
        musicbrainz.lookup_disc(_toc(), opener=open_url)


def test_an_unreachable_service_is_reported_rather_than_swallowed():
    with pytest.raises(musicbrainz.MusicBrainzError):
        musicbrainz.lookup_disc(_toc(), opener=_opener(None, error=urllib.error.URLError("offline")))


def test_every_request_identifies_the_application():
    """MusicBrainz refuses anonymous clients outright, so this is not
    politeness -- without it nothing here works at all."""
    seen: list = []

    def open_url(request, timeout=None):
        seen.append(request.get_header("User-agent"))
        return _Response(json.dumps(PAYLOAD).encode())

    musicbrainz.lookup_disc(_toc(), opener=open_url)
    assert "MDTools" in seen[0]
