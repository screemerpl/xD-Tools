import json

import pytest

from mdtools import metadata_lookup
from mdtools.metadata_lookup import MetadataLookupError, fetch_artwork, fetch_tracks, lookup_album, search_albums


class _FakeResponse:
    def __init__(self, payload: dict):
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return self._body


def _fake_urlopen(search_payload: dict, lookup_payload: dict):
    def urlopen(request, timeout=None):
        url = request.full_url
        if url.startswith(metadata_lookup.SEARCH_URL):
            return _FakeResponse(search_payload)
        assert url.startswith(metadata_lookup.LOOKUP_URL)
        return _FakeResponse(lookup_payload)

    return urlopen


def test_search_albums_ranks_the_full_album_above_a_same_titled_single(monkeypatch):
    search_payload = {
        "results": [
            {
                "artistName": "Test Artist",
                "collectionName": "Test Album (Remix) - Single",
                "collectionId": 1,
                "trackCount": 1,
                "releaseDate": "2005-01-01T00:00:00Z",
            },
            {
                "artistName": "Test Artist",
                "collectionName": "Test Album",
                "collectionId": 2,
                "trackCount": 12,
                "releaseDate": "1998-03-01T00:00:00Z",
            },
        ]
    }
    monkeypatch.setattr(metadata_lookup.urllib.request, "urlopen", _fake_urlopen(search_payload, {}))

    candidates = search_albums("Test Artist", "Test Album")

    # both name-match equally well (the single's name contains "Test Album"
    # too) -- the real album (more tracks) must still rank first
    assert candidates[0].collection_id == 2
    assert candidates[0].track_count == 12
    assert candidates[1].collection_id == 1


def test_search_albums_returns_empty_list_when_nothing_matches(monkeypatch):
    monkeypatch.setattr(metadata_lookup.urllib.request, "urlopen", _fake_urlopen({"results": []}, {}))

    assert search_albums("Nobody", "Nothing") == []


def test_fetch_tracks_returns_sorted_tracks_and_year(monkeypatch):
    lookup_payload = {
        "results": [
            {"wrapperType": "collection", "releaseDate": "1998-03-01T00:00:00Z"},
            {"wrapperType": "track", "trackName": "Second Song", "trackNumber": 2, "trackTimeMillis": 200000},
            {"wrapperType": "track", "trackName": "First Song", "trackNumber": 1, "trackTimeMillis": 185500},
        ]
    }
    monkeypatch.setattr(metadata_lookup.urllib.request, "urlopen", _fake_urlopen({}, lookup_payload))

    result = fetch_tracks(4242)

    assert result.year == 1998
    assert [t.title for t in result.tracks] == ["First Song", "Second Song"]
    assert result.tracks[0].time_seconds == 186  # 185500ms rounds to 186s
    assert result.tracks[1].time_seconds == 200


def test_fetch_tracks_falls_back_to_the_given_year_when_the_collection_entry_has_none(monkeypatch):
    lookup_payload = {"results": [{"wrapperType": "collection"}]}
    monkeypatch.setattr(metadata_lookup.urllib.request, "urlopen", _fake_urlopen({}, lookup_payload))

    result = fetch_tracks(4242, fallback_year=1999)

    assert result.year == 1999


def test_lookup_album_raises_when_nothing_matches(monkeypatch):
    monkeypatch.setattr(metadata_lookup.urllib.request, "urlopen", _fake_urlopen({"results": []}, {}))

    with pytest.raises(MetadataLookupError):
        lookup_album("Nobody", "Nothing")


def test_lookup_album_auto_picks_the_top_ranked_candidate(monkeypatch):
    search_payload = {
        "results": [
            {"artistName": "Test Artist", "collectionName": "Test Album", "collectionId": 7, "trackCount": 10, "releaseDate": "2001-01-01T00:00:00Z"},
        ]
    }
    lookup_payload = {"results": [{"wrapperType": "collection", "releaseDate": "2001-01-01T00:00:00Z"}]}
    monkeypatch.setattr(metadata_lookup.urllib.request, "urlopen", _fake_urlopen(search_payload, lookup_payload))

    result = lookup_album("Test Artist", "Test Album")

    assert result.year == 2001


def test_network_failure_raises_metadata_lookup_error(monkeypatch):
    import urllib.error

    def broken_urlopen(request, timeout=None):
        raise urllib.error.URLError("boom")

    monkeypatch.setattr(metadata_lookup.urllib.request, "urlopen", broken_urlopen)

    with pytest.raises(MetadataLookupError):
        search_albums("Test Artist", "Test Album")


def test_search_albums_upsizes_the_artwork_url(monkeypatch):
    search_payload = {
        "results": [
            {
                "artistName": "Test Artist",
                "collectionName": "Test Album",
                "collectionId": 1,
                "trackCount": 10,
                "artworkUrl100": "https://example.com/cover/100x100bb.jpg",
            }
        ]
    }
    monkeypatch.setattr(metadata_lookup.urllib.request, "urlopen", _fake_urlopen(search_payload, {}))

    candidates = search_albums("Test Artist", "Test Album")

    assert candidates[0].artwork_url == "https://example.com/cover/600x600bb.jpg"


def test_search_albums_leaves_artwork_url_none_when_missing(monkeypatch):
    search_payload = {
        "results": [{"artistName": "Test Artist", "collectionName": "Test Album", "collectionId": 1, "trackCount": 10}]
    }
    monkeypatch.setattr(metadata_lookup.urllib.request, "urlopen", _fake_urlopen(search_payload, {}))

    candidates = search_albums("Test Artist", "Test Album")

    assert candidates[0].artwork_url is None


def test_fetch_artwork_returns_the_raw_bytes(monkeypatch):
    class _FakeImageResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b"fake-jpeg-bytes"

    monkeypatch.setattr(metadata_lookup.urllib.request, "urlopen", lambda request, timeout=None: _FakeImageResponse())

    assert fetch_artwork("https://example.com/cover.jpg") == b"fake-jpeg-bytes"


def test_fetch_artwork_raises_metadata_lookup_error_on_network_failure(monkeypatch):
    import urllib.error

    def broken_urlopen(request, timeout=None):
        raise urllib.error.URLError("boom")

    monkeypatch.setattr(metadata_lookup.urllib.request, "urlopen", broken_urlopen)

    with pytest.raises(MetadataLookupError):
        fetch_artwork("https://example.com/cover.jpg")


# -- artist photos (search_artists / find_artist_photo) ----------------------


def _fake_artist_urlopen(search_payload: dict, image_bytes: bytes = b"fake-photo-bytes"):
    def urlopen(request, timeout=None):
        url = request.full_url
        if url.startswith(metadata_lookup.ARTIST_SEARCH_URL):
            return _FakeResponse(search_payload)
        return _FakeImageResponse(image_bytes)

    return urlopen


class _FakeImageResponse:
    def __init__(self, body: bytes):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return self._body


def test_search_artists_ranks_by_name_similarity_then_popularity(monkeypatch):
    """Verified live against the real Deezer API (2026-08-21): two acts
    both called "Taylor Swift" score an identical 1.0 name match, so
    nb_fan is what actually has to decide which one somebody means."""
    payload = {
        "data": [
            {"id": 1, "name": "Taylor Swift", "nb_fan": 11, "picture_xl": "https://example.com/obscure.jpg"},
            {"id": 2, "name": "Taylor Swift", "nb_fan": 12691966, "picture_xl": "https://example.com/real.jpg"},
        ]
    }
    monkeypatch.setattr(metadata_lookup.urllib.request, "urlopen", _fake_artist_urlopen(payload))

    candidates = metadata_lookup.search_artists("Taylor Swift")

    assert candidates[0].id == 2
    assert candidates[0].nb_fan == 12691966


def test_find_artist_photo_downloads_the_best_matches_picture(monkeypatch):
    payload = {"data": [{"id": 1, "name": "Taylor Swift", "nb_fan": 100, "picture_xl": "https://example.com/a.jpg"}]}
    monkeypatch.setattr(
        metadata_lookup.urllib.request, "urlopen", _fake_artist_urlopen(payload, b"the-actual-photo-bytes")
    )

    photo = metadata_lookup.find_artist_photo("Taylor Swift")

    assert photo == b"the-actual-photo-bytes"


def test_find_artist_photo_returns_none_when_nothing_is_found(monkeypatch):
    monkeypatch.setattr(metadata_lookup.urllib.request, "urlopen", _fake_artist_urlopen({"data": []}))

    assert metadata_lookup.find_artist_photo("Some Obscure Nobody") is None


def test_find_artist_photo_refuses_a_poorly_matching_name(monkeypatch):
    """A photo is of one specific person -- "close enough" is not good
    enough the way it can be for an album edition."""
    payload = {
        "data": [{"id": 1, "name": "Completely Unrelated Band", "nb_fan": 999999, "picture_xl": "https://x/y.jpg"}]
    }
    monkeypatch.setattr(metadata_lookup.urllib.request, "urlopen", _fake_artist_urlopen(payload))

    assert metadata_lookup.find_artist_photo("Taylor Swift") is None


def test_find_artist_photo_is_silent_on_a_search_failure(monkeypatch):
    import urllib.error

    def broken_urlopen(request, timeout=None):
        raise urllib.error.URLError("boom")

    monkeypatch.setattr(metadata_lookup.urllib.request, "urlopen", broken_urlopen)

    assert metadata_lookup.find_artist_photo("Taylor Swift") is None


def test_find_artist_photo_is_silent_on_a_download_failure(monkeypatch):
    import urllib.error

    payload = {"data": [{"id": 1, "name": "Taylor Swift", "nb_fan": 100, "picture_xl": "https://example.com/a.jpg"}]}

    def urlopen(request, timeout=None):
        if request.full_url.startswith(metadata_lookup.ARTIST_SEARCH_URL):
            return _FakeResponse(payload)
        raise urllib.error.URLError("boom")

    monkeypatch.setattr(metadata_lookup.urllib.request, "urlopen", urlopen)

    assert metadata_lookup.find_artist_photo("Taylor Swift") is None


def test_find_artist_photo_of_a_blank_name_makes_no_request(monkeypatch):
    def urlopen(request, timeout=None):
        raise AssertionError("should never be called for a blank artist")

    monkeypatch.setattr(metadata_lookup.urllib.request, "urlopen", urlopen)

    assert metadata_lookup.find_artist_photo("   ") is None
