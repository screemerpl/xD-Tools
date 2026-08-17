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


# --- filling the playlist for a CD rip --------------------------------------
#
# The awkward half of Record CD to MiniDisc: Beefweb makes the playlist and
# reads it back, but cannot be handed the files (see add_files_via_cli).


def test_clearing_a_playlist_posts_to_its_clear_endpoint():
    sent: list = []
    _client({}, sent).clear_playlist("p1")
    assert sent[0][0] == "/api/playlists/p1/clear"


def test_browser_roots_is_usually_empty_which_is_why_files_go_in_by_cli():
    """Captured from the live component on a normal install: no music
    directories configured, so every path is refused by items/add."""
    client = _client({"/api/browser/roots": {"pathSeparator": "\\", "roots": []}})
    assert client.browser_roots() == []


def test_add_files_via_cli_sends_one_command_in_playlist_order():
    """One call with every file, not one per file: foobar adds a batch in
    the order it receives it."""
    calls: list = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    foobar.add_files_via_cli("fb2k.exe", ["01.flac", "02.flac"], run=fake_run)

    assert calls == [["fb2k.exe", "/add", "01.flac", "02.flac"]]


def test_adding_no_files_does_not_launch_anything():
    def explode(*args, **kwargs):
        raise AssertionError("should not have run foobar2000")

    foobar.add_files_via_cli("fb2k.exe", [], run=explode)


def test_a_failing_command_line_becomes_a_foobar_error():
    def fake_run(command, **kwargs):
        return type("R", (), {"returncode": 1, "stdout": "", "stderr": ""})()

    with pytest.raises(foobar.FoobarError):
        foobar.add_files_via_cli("fb2k.exe", ["01.flac"], run=fake_run)


def test_waiting_for_the_add_polls_until_the_count_settles():
    """The command line returns as soon as foobar has accepted the files;
    reading and tagging them happens afterwards, so the count climbs for a
    moment. Asking once would see a half-filled playlist."""
    counts = iter([0, 1, 3])
    client = foobar.FoobarClient()
    client.playlists = lambda: [foobar.Playlist("p1", "Default", next(counts), True)]

    settled = foobar.wait_for_item_count(client, "p1", 3, sleep=lambda _: None)

    assert settled == 3


def test_waiting_gives_up_at_the_deadline_rather_than_looping_forever():
    client = foobar.FoobarClient()
    client.playlists = lambda: [foobar.Playlist("p1", "Default", 1, True)]
    clock = iter([0.0, 0.0, 99.0])

    settled = foobar.wait_for_item_count(client, "p1", 3, sleep=lambda _: None, now=lambda: next(clock))

    assert settled == 1


def test_replacing_the_current_playlist_clears_it_then_adds(monkeypatch):
    """Deliberately the *current* playlist rather than a new one: the record
    flow reads whatever is current, so this keeps one meaning of "what is
    about to be recorded"."""
    sent: list = []
    client = _client({"/api/playlists": PLAYLISTS}, sent)
    added: list = []
    monkeypatch.setattr(foobar, "add_files_via_cli", lambda exe, paths, **kw: added.append((exe, list(paths))))

    playlist = foobar.replace_current_playlist(client, "fb2k.exe", ["01.flac", "02.flac"], wait=lambda *a, **k: 2)

    assert playlist.id == "p1"
    assert ("/api/playlists/p1/clear", {}) in sent
    assert added == [("fb2k.exe", ["01.flac", "02.flac"])]


def test_replacing_a_playlist_when_foobar_has_none_open_is_an_error():
    client = _client({"/api/playlists": {"playlists": []}})
    with pytest.raises(foobar.FoobarError):
        foobar.replace_current_playlist(client, "fb2k.exe", ["01.flac"])
