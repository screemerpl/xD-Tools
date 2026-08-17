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
