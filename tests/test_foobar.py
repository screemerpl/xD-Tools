"""The Beefweb client, exercised without a running foobar2000.

The JSON fixtures below are real responses captured from foobar2000 2.25.10
with foo_beefweb 0.10 -- if the component ever changes shape, these are what
notice.
"""

import json

import pytest

from mdtools import foobar

PLAYER_STOPPED = json.loads(
    """
{"player":{"activeItem":{"columns":[],"duration":0.0,"index":-1,"playlistId":"","playlistIndex":-1,
"position":0.0},"info":{"name":"foobar2000","pluginVersion":"0.10","version":"2.25.10"},
"playbackMode":0,"playbackState":"stopped","volume":{"isMuted":false,"value":-3.0}}}
"""
)

PLAYER_PLAYING = json.loads(
    """
{"player":{"activeItem":{"columns":["01","Prequel","Falling In Reverse","Popular Monster","2024-08-16","234"],
"duration":233.79310416666667,"index":0,"playlistId":"p1","playlistIndex":0,"position":0.43},
"playbackMode":0,"playbackState":"playing"}}
"""
)

PLAYLISTS = json.loads(
    """
{"playlists":[{"id":"p1","index":0,"isCurrent":true,"itemCount":11,"title":"Default Playlist","totalTime":0.0}]}
"""
)

ITEMS = json.loads(
    """
{"playlistItems":{"items":[
{"columns":["01","Prequel","Falling In Reverse","Popular Monster","2024-08-16","234"]},
{"columns":["02","Popular Monster","Falling In Reverse","Popular Monster","2024-08-16","221"]},
{"columns":["03","All My Life","Falling In Reverse, Jelly Roll","Popular Monster","2024-08-16","190"]}],
"offset":0,"totalCount":3}}
"""
)


def _client(responses: dict, recorder: list | None = None) -> foobar.FoobarClient:
    """A client whose transport is a lookup table instead of a socket."""
    client = foobar.FoobarClient()

    def fake_request(path, *, params=None, body=None):
        if recorder is not None:
            recorder.append((path, body))
        for prefix, payload in responses.items():
            if path.startswith(prefix):
                return payload
        return None

    client._request = fake_request
    return client


def _items() -> list[foobar.PlaylistItem]:
    return [foobar.PlaylistItem.from_columns(entry["columns"]) for entry in ITEMS["playlistItems"]["items"]]


# --- parsing ---------------------------------------------------------------


def test_player_state_of_a_stopped_player():
    state = _client({"/api/player": PLAYER_STOPPED}).player_state()
    assert state.is_stopped
    assert state.item_index == -1


def test_player_state_while_playing_reports_which_item_and_where():
    state = _client({"/api/player": PLAYER_PLAYING}).player_state()
    assert state.is_playing
    assert (state.playlist_id, state.item_index) == ("p1", 0)
    assert state.position == pytest.approx(0.43)


def test_playlists_and_which_one_is_current():
    client = _client({"/api/playlists": PLAYLISTS})
    assert client.current_playlist().id == "p1"
    assert client.current_playlist().item_count == 11


def test_playlist_items_carry_title_and_length():
    items = _client({"/api/playlists": ITEMS}).playlist_items("p1")
    assert [item.title for item in items] == ["Prequel", "Popular Monster", "All My Life"]
    assert items[0].length_seconds == 234


def test_a_short_or_ragged_column_list_does_not_raise():
    item = foobar.PlaylistItem.from_columns(["07", "Half A Row"])
    assert item.title == "Half A Row"
    assert item.length_seconds == 0


def test_an_unreadable_response_becomes_a_foobar_error():
    client = _client({"/api/player": {"nonsense": True}})
    with pytest.raises(foobar.FoobarError):
        client.player_state()


# --- album fields ----------------------------------------------------------


def test_album_artist_is_the_albums_own_not_the_first_tracks_credits():
    """Track 3 credits a guest; the disc title must not inherit that."""
    assert foobar.album_artist(_items()) == "Falling In Reverse"


def test_year_is_taken_from_the_leading_digits_of_whatever_date_holds():
    assert foobar.album_year(_items()) == 2024
    assert foobar.album_year([foobar.PlaylistItem.from_columns(["1", "T", "A", "Al", "1998", "10"])]) == 1998
    assert foobar.album_year([foobar.PlaylistItem.from_columns(["1", "T", "A", "Al", "", "10"])]) is None
    assert foobar.album_year([foobar.PlaylistItem.from_columns(["1", "T", "A", "Al", "unknown", "10"])]) is None


def test_total_time_adds_up_the_tracks():
    assert foobar.total_seconds(_items()) == 234 + 221 + 190


def test_playlist_becomes_project_metadata():
    metadata = foobar.metadata_from_playlist(_items())
    assert (metadata.album, metadata.artist, metadata.year) == ("Popular Monster", "Falling In Reverse", 2024)
    assert [track.title for track in metadata.tracks] == ["Prequel", "Popular Monster", "All My Life"]
    assert metadata.tracks[0].time_seconds == 234


def test_metadata_from_an_empty_playlist_is_empty_not_an_error():
    metadata = foobar.metadata_from_playlist([])
    assert metadata.album == "" and metadata.tracks == []


# --- control ---------------------------------------------------------------


def test_preparing_to_record_forces_straight_through_once():
    """Shuffle or repeat would put tracks on the disc in an order the
    titles then wouldn't match, and a repeat would record past the end."""
    sent: list = []
    _client({}, sent).prepare_for_recording()

    path, body = sent[0]
    assert path == "/api/player"
    # Flat keys, not {"options": {...}} -- Beefweb answers 400 to the latter.
    assert body == {"playbackMode": 0, "stopAfterCurrentTrack": False}


def test_play_targets_a_specific_playlist_item():
    sent: list = []
    _client({}, sent).play("p1", 0)
    assert sent[0][0] == "/api/player/play/p1/0"
