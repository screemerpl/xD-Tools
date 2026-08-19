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


# --- untagged files --------------------------------------------------------
#
# What Record Folder exists for: somebody's own folder of files, which may
# carry no tags at all. foobar substitutes the filename for a missing
# %title% itself, but a disc full of blank track names is not a risk worth
# taking on behaviour that is nowhere pinned down, so %path% is asked for
# and the fallback is made here as well.


def test_a_file_with_no_title_tag_is_named_after_its_file():
    item = foobar.PlaylistItem.from_columns(
        ["", "", "", "", "", "212", "", r"C:\Music\Skillet\03 Feel Invincible.flac"]
    )
    assert item.display_title() == "03 Feel Invincible"


def test_a_real_title_always_wins_over_the_filename():
    item = foobar.PlaylistItem.from_columns(
        ["3", "Feel Invincible", "Skillet", "Unleashed", "2016", "212", "Skillet", r"C:\Music\track03.flac"]
    )
    assert item.display_title() == "Feel Invincible"


def test_no_title_and_no_path_is_still_just_empty():
    """%path% is appended to the column set, so an older or unexpected
    response simply pads to "" -- which has to stay the answer it was
    before, not raise."""
    assert foobar.PlaylistItem.from_columns(["1", ""]).display_title() == ""


def test_the_filename_fallback_reaches_the_track_list():
    """The point of it: this is what gets written onto the disc."""
    items = [
        foobar.PlaylistItem.from_columns(["", "", "", "", "", "100", "", "/music/mix/01 Unknown Song.mp3"]),
        foobar.PlaylistItem.from_columns(["", "", "", "", "", "100", "", "/music/mix/02 Another.mp3"]),
    ]
    titles = [track.title for track in foobar.metadata_from_playlist(items).tracks]
    assert titles == ["01 Unknown Song", "02 Another"]


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


def test_set_volume_posts_a_flat_body():
    sent: list = []
    _client({}, sent).set_volume(-5.0)

    path, body = sent[0]
    assert path == "/api/player"
    assert body == {"volume": -5.0}


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


def _reordering_client(landings: list[list[str]], recorder: list | None = None) -> foobar.FoobarClient:
    """A client whose playlist reports a different order each time it is
    read -- one entry of `landings` per read, which is how foobar2000
    re-sorting an incoming batch is modelled here."""
    client = _client({"/api/playlists": PLAYLISTS}, recorder)
    reads = iter(landings)

    def playlist_items(playlist_id, limit=500):
        return [
            foobar.PlaylistItem.from_columns(["", path, "", "", "", "0", "", path])
            for path in next(reads)
        ]

    client.playlist_items = playlist_items
    return client


def test_replacing_the_current_playlist_clears_it_then_adds(monkeypatch):
    """Deliberately the *current* playlist rather than a new one: the record
    flow reads whatever is current, so this keeps one meaning of "what is
    about to be recorded"."""
    sent: list = []
    client = _reordering_client([["01.flac", "02.flac"]], sent)
    added: list = []
    monkeypatch.setattr(foobar, "add_files_via_cli", lambda exe, paths, **kw: added.append((exe, list(paths))))

    playlist = foobar.replace_current_playlist(client, "fb2k.exe", ["01.flac", "02.flac"], wait=lambda *a, **k: 2)

    assert playlist.id == "p1"
    assert ("/api/playlists/p1/clear", {}) in sent
    assert added == [("fb2k.exe", ["01.flac", "02.flac"])], "one call while the order holds"


def test_a_batch_foobar_re_sorts_is_added_one_file_at_a_time(monkeypatch):
    """Verified against the live foobar2000: handed 11, 01, 02 in one /add
    call it appends them sorted by filename -- 01, 02, 11 -- and the caller
    that trusted the order recorded the wrong track onto a MiniDisc. Adding
    them one at a time keeps the order, because a batch of one has nothing
    to sort against."""
    wanted = ["11.flac", "01.flac", "02.flac"]
    client = _reordering_client([sorted(wanted), wanted])
    added: list = []
    monkeypatch.setattr(foobar, "add_files_via_cli", lambda exe, paths, **kw: added.append(list(paths)))

    foobar.replace_current_playlist(client, "fb2k.exe", wanted, wait=lambda c, p, expected: expected)

    assert added == [wanted, ["11.flac"], ["01.flac"], ["02.flac"]]


def test_an_order_foobar_will_not_keep_raises_rather_than_being_recorded(monkeypatch):
    """A wrong order found afterwards is a disc that cannot be un-recorded,
    so this is one of the few places that would rather fail than proceed."""
    wanted = ["11.flac", "01.flac"]
    client = _reordering_client([sorted(wanted), sorted(wanted)])
    monkeypatch.setattr(foobar, "add_files_via_cli", lambda exe, paths, **kw: None)

    with pytest.raises(foobar.FoobarError):
        foobar.replace_current_playlist(client, "fb2k.exe", wanted, wait=lambda c, p, expected: expected)


def test_a_file_that_never_lands_is_named_rather_than_waited_on_forever(monkeypatch):
    """One file per call means one wait per call, and a file foobar quietly
    refuses would otherwise cost that wait once per remaining track."""
    wanted = ["11.flac", "01.flac", "02.flac"]
    client = _reordering_client([sorted(wanted)])
    monkeypatch.setattr(foobar, "add_files_via_cli", lambda exe, paths, **kw: None)

    with pytest.raises(foobar.FoobarError, match="01.flac"):
        foobar.replace_current_playlist(client, "fb2k.exe", wanted, wait=lambda c, p, expected: 1)


def test_the_order_check_ignores_how_a_path_is_spelled(monkeypatch):
    """The path we ask with and the path %path% reports come from different
    sides of the same filesystem."""
    client = _reordering_client([[r"C:\Music\01.flac", r"C:\Music\02.flac"]])
    monkeypatch.setattr(foobar, "add_files_via_cli", lambda exe, paths, **kw: None)

    foobar.replace_current_playlist(
        client, "fb2k.exe", ["c:/music/01.flac", "c:/music/02.flac"], wait=lambda *a, **k: 2
    )


# --- reordering a playlist in place ----------------------------------------


class _MovablePlaylist:
    """A client whose playlist can actually be moved about, so the moves
    themselves are what the test checks rather than the calls."""

    def __init__(self, paths: list[str]):
        self.paths = list(paths)
        self.moves: list[tuple[list[int], int]] = []

    def playlist_items(self, playlist_id, limit=500):
        return [
            foobar.PlaylistItem.from_columns(["", path, "", "", "", "0", "", path, ""])
            for path in self.paths
        ]

    def move_playlist_items(self, playlist_id, indexes, target):
        self.moves.append((list(indexes), target))
        for offset, index in enumerate(sorted(indexes)):
            self.paths.insert(target + offset, self.paths.pop(index))


def test_a_playlist_is_reordered_by_moving_its_items():
    """Verified against the live Beefweb: items/move inserts before
    targetIndex and leaves everything else in its relative order."""
    client = _MovablePlaylist(["b.flac", "c.flac", "a.flac"])

    assert foobar.reorder_playlist(client, "p1", ["a.flac", "b.flac", "c.flac"])
    assert client.paths == ["a.flac", "b.flac", "c.flac"]
    assert client.moves == [([2], 0)], "one move, not a rebuild"


def test_a_playlist_already_in_order_is_not_touched_at_all():
    client = _MovablePlaylist(["a.flac", "b.flac"])
    assert foobar.reorder_playlist(client, "p1", ["a.flac", "b.flac"])
    assert client.moves == []


def test_reordering_declines_a_playlist_holding_different_tracks():
    """Not something moving items can fix, and the caller has another way
    to deal with it -- so this says no rather than raising."""
    client = _MovablePlaylist(["a.flac", "b.flac"])
    assert not foobar.reorder_playlist(client, "p1", ["a.flac", "z.flac"])
    assert client.moves == []


def test_reordering_declines_entries_that_are_not_files():
    """Every empty path normalises to the same string, so the check at the
    end would report success having moved nothing at all."""
    client = _MovablePlaylist(["", ""])
    assert not foobar.reorder_playlist(client, "p1", ["", ""])
    assert client.moves == []


def test_reordering_does_not_care_how_a_path_is_spelled():
    client = _MovablePlaylist([r"C:\Music\b.flac", r"C:\Music\a.flac"])
    assert foobar.reorder_playlist(client, "p1", ["c:/music/a.flac", "c:/music/b.flac"])


# --- the album's own order -------------------------------------------------


def _tagged(disc: str, track: str, name: str = "") -> foobar.PlaylistItem:
    return foobar.PlaylistItem.from_columns(
        [track, name or f"{disc}-{track}", "", "", "", "0", "", f"{name or disc + track}.flac", disc]
    )


def test_a_double_album_is_put_back_into_disc_then_track_order():
    """Observed live: a two-disc album dropped into foobar2000 as one folder
    arrives interleaved -- 2, 1, 2, 1 -- because foobar sorts by filename
    and both discs number their tracks from one."""
    interleaved = [_tagged("2", "01"), _tagged("1", "01"), _tagged("2", "02"), _tagged("1", "02")]

    ordered = foobar.sort_by_disc_and_track(interleaved)

    assert [(i.disc_number, i.track_number) for i in ordered] == [
        ("1", "01"), ("1", "02"), ("2", "01"), ("2", "02"),
    ]


def test_tags_written_as_one_of_two_sort_the_same_as_a_bare_number():
    ordered = foobar.sort_by_disc_and_track([_tagged("2/2", "1/12"), _tagged("1/2", "3/12")])
    assert [i.disc_number for i in ordered] == ["1/2", "2/2"]


def test_a_playlist_with_no_numbers_at_all_is_left_exactly_as_it_is():
    """No tags means no opinion -- and the order somebody assembled by hand
    beats one invented here."""
    untagged = [
        foobar.PlaylistItem.from_columns(["", "b", "", "", "", "0", "", "b.flac", ""]),
        foobar.PlaylistItem.from_columns(["", "a", "", "", "", "0", "", "a.flac", ""]),
    ]

    assert [i.title for i in foobar.sort_by_disc_and_track(untagged)] == ["b", "a"]


def test_a_file_missing_its_track_number_sinks_rather_than_displacing_the_album():
    stray = foobar.PlaylistItem.from_columns(["", "stray", "", "", "", "0", "", "stray.flac", "1"])
    ordered = foobar.sort_by_disc_and_track([stray, _tagged("1", "01"), _tagged("1", "02")])

    assert [i.title for i in ordered] == ["1-01", "1-02", "stray"]


def test_a_missing_disc_number_counts_as_disc_one():
    """Which is what every single-disc album's files look like."""
    plain = foobar.PlaylistItem.from_columns(["02", "second", "", "", "", "0", "", "2.flac", ""])
    first = foobar.PlaylistItem.from_columns(["01", "first", "", "", "", "0", "", "1.flac", ""])

    assert [i.title for i in foobar.sort_by_disc_and_track([plain, first])] == ["first", "second"]


def test_where_the_files_say_one_disc_ends():
    items = [_tagged("1", "01"), _tagged("1", "02"), _tagged("2", "01")]
    assert foobar.disc_breaks(items) == [2]


def test_a_single_disc_album_declares_no_breaks():
    assert foobar.disc_breaks([_tagged("1", "01"), _tagged("1", "02")]) == []
    assert foobar.disc_breaks([]) == []


def test_replacing_a_playlist_when_foobar_has_none_open_is_an_error():
    client = _client({"/api/playlists": {"playlists": []}})
    with pytest.raises(foobar.FoobarError):
        foobar.replace_current_playlist(client, "fb2k.exe", ["01.flac"])
