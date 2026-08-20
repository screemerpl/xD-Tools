"""Talking to a running foobar2000 through its Beefweb Remote Control
component (foo_beefweb), which exposes a small REST API on localhost.

Used by "Record to MiniDisc from foobar2000...": foobar plays the album
into the deck over S/PDIF while xD-Tools watches which track is playing and,
when the playlist ends, titles the disc through MDRem.

Plain stdlib urllib rather than QtNetwork or a client library, for the same
reasons metadata_lookup.py gives: the calls are small, local, and driven by
a poll loop that already lives on a worker thread, so there is nothing an
async client would buy -- and no dependency is added to pyproject.toml.

No Qt anywhere in here, matching mdrem.py: the panels import this, never
the other way round, and every function is testable without a QApplication.

Verified against foobar2000 2.25.10 with foo_beefweb 0.10:
  GET  /api/player[?columns=...]     -> playbackState, activeItem{...}
  GET  /api/playlists                -> id, title, itemCount, isCurrent
  GET  /api/playlists/{id}/items/{offset}:{count}?columns=...
  POST /api/player/play/{id}/{index} -> 204, starts playback
  POST /api/player/stop              -> 204
  POST /api/player  {flat keys}      -> 204 (nested {"options":{...}} is a 400)
  POST /api/playlists/{id}/clear     -> 204
  POST /api/playlists/{id}/items/add -> 403 unless the path is under a
                                        configured music directory (!)
  GET  /api/browser/roots            -> those directories, often none
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from mdtools.multidisc import breaks_from_disc_numbers, leading_number, order_by_disc_and_track
from mdtools.project import ProjectMetadata, Track, apply_compilation_naming

DEFAULT_BASE_URL = "http://localhost:8880"
DEFAULT_TIMEOUT_S = 5.0

# One column set shared by the playlist listing and the now-playing query, so
# an item always reports the same fields wherever it is read from.
# "album artist" rather than "artist" for the disc's own title: a guest
# feature credits a different artist per track, which is right for a track
# title and wrong for the disc title.
#
# Both are asked for, because the difference between them is the entire
# signal a compilation gives off -- see ProjectMetadata.is_compilation().
# %artist% is appended at the end rather than slotted in beside %album
# artist%, so every positional index below keeps meaning what it meant --
# and %path% after it for the same reason.
_COLUMNS = [
    "%tracknumber%",
    "%title%",
    "%album artist%",
    "%album%",
    "%date%",
    "%length_seconds%",
    "%artist%",
    "%path%",
    # Appended, like every column before it -- see the note on _COLUMNS'
    # order in PlaylistItem.from_columns. A double album's files carry the
    # disc they belong to, and a playlist assembled by dropping a folder in
    # routinely arrives with the two interleaved.
    "%discnumber%",
]
_COLUMNS_PARAM = ",".join(_COLUMNS)

PLAYING = "playing"
PAUSED = "paused"
STOPPED = "stopped"


class FoobarError(Exception):
    """foobar2000 unreachable, Beefweb not installed/enabled, or an
    unexpected response."""


@dataclass
class PlaylistItem:
    track_number: str
    title: str
    album_artist: str
    album: str
    date: str
    length_seconds: int
    artist: str = ""
    path: str = ""
    disc_number: str = ""

    @classmethod
    def from_columns(cls, columns: list[str]) -> PlaylistItem:
        padded = list(columns) + [""] * (len(_COLUMNS) - len(columns))
        try:
            length = int(padded[5] or 0)
        except ValueError:
            length = 0
        return cls(
            track_number=padded[0],
            title=padded[1],
            album_artist=padded[2],
            album=padded[3],
            date=padded[4],
            length_seconds=length,
            artist=padded[6],
            path=padded[7],
            disc_number=padded[8],
        )

    def display_title(self) -> str:
        """The title to record, falling back to the filename.

        foobar2000 substitutes the filename for a missing %title% itself, so
        on a live install this is usually belt and braces -- but a folder of
        untagged files is precisely the case Record Folder exists to handle,
        and a disc full of blank track names is not a failure worth risking
        on behaviour nobody here can pin down. Falls back to the empty
        string when there is no path either, which is what it was before."""
        if self.title.strip():
            return self.title
        stem = Path(self.path).stem if self.path else ""
        return stem or self.title


@dataclass
class Playlist:
    id: str
    title: str
    item_count: int
    is_current: bool


@dataclass
class PlayerState:
    playback_state: str
    playlist_id: str
    item_index: int  # -1 when nothing is active
    position: float
    duration: float

    @property
    def is_playing(self) -> bool:
        return self.playback_state == PLAYING

    @property
    def is_stopped(self) -> bool:
        return self.playback_state == STOPPED


class FoobarClient:
    def __init__(self, base_url: str = DEFAULT_BASE_URL, timeout: float = DEFAULT_TIMEOUT_S):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    # --- transport ----------------------------------------------------

    def _request(self, path: str, *, params: dict | None = None, body: dict | None = None):
        url = f"{self.base_url}{path}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        data = None
        headers = {}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            raise FoobarError(f"{path}: HTTP {exc.code}") from exc
        except (urllib.error.URLError, OSError) as exc:
            raise FoobarError(f"cannot reach foobar2000 at {self.base_url}: {exc}") from exc
        if not raw:
            return None
        try:
            return json.loads(raw)
        except ValueError as exc:
            raise FoobarError(f"{path}: unreadable response") from exc

    # --- reading ------------------------------------------------------

    def player_state(self) -> PlayerState:
        payload = self._request("/api/player", params={"columns": _COLUMNS_PARAM}) or {}
        try:
            player = payload["player"]
            active = player["activeItem"]
            return PlayerState(
                playback_state=player["playbackState"],
                playlist_id=active.get("playlistId", ""),
                item_index=int(active.get("index", -1)),
                position=float(active.get("position") or 0.0),
                duration=float(active.get("duration") or 0.0),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise FoobarError("unexpected player state response") from exc

    def playlists(self) -> list[Playlist]:
        payload = self._request("/api/playlists") or {}
        try:
            return [
                Playlist(
                    id=entry["id"],
                    title=entry.get("title", ""),
                    item_count=int(entry.get("itemCount", 0)),
                    is_current=bool(entry.get("isCurrent")),
                )
                for entry in payload["playlists"]
            ]
        except (KeyError, TypeError, ValueError) as exc:
            raise FoobarError("unexpected playlists response") from exc

    def current_playlist(self) -> Playlist | None:
        for playlist in self.playlists():
            if playlist.is_current:
                return playlist
        return None

    def playlist_items(self, playlist_id: str, limit: int = 500) -> list[PlaylistItem]:
        payload = (
            self._request(f"/api/playlists/{playlist_id}/items/0:{limit}", params={"columns": _COLUMNS_PARAM}) or {}
        )
        try:
            return [PlaylistItem.from_columns(entry["columns"]) for entry in payload["playlistItems"]["items"]]
        except (KeyError, TypeError) as exc:
            raise FoobarError("unexpected playlist items response") from exc

    # --- control ------------------------------------------------------

    def play(self, playlist_id: str, index: int) -> None:
        self._request(f"/api/player/play/{playlist_id}/{index}", body={})

    def stop(self) -> None:
        self._request("/api/player/stop", body={})

    def clear_playlist(self, playlist_id: str) -> None:
        self._request(f"/api/playlists/{playlist_id}/clear", body={})

    def move_playlist_items(self, playlist_id: str, indexes: list[int], target: int) -> None:
        """Moves the items at these positions so they sit at `target`.

        Beefweb's own endpoint, and the only way to reorder a playlist that
        does not go anywhere near the files: nothing is cleared, nothing is
        re-added, and a track whose file has since moved or been locked is
        reordered just the same."""
        self._request(
            f"/api/playlists/{playlist_id}/items/move",
            body={"items": list(indexes), "targetIndex": int(target)},
        )

    def browser_roots(self) -> list[str]:
        """The directories Beefweb is allowed to serve files from.

        Read only to explain a failure, never to decide anything: it is
        routinely empty (it is opt-in configuration in foobar's own
        preferences), which is exactly why files go in through the command
        line instead -- see add_files_via_cli."""
        payload = self._request("/api/browser/roots") or {}
        roots = payload.get("roots") or []
        return [str(entry.get("path", "")) for entry in roots if isinstance(entry, dict)]

    def prepare_for_recording(self) -> None:
        """Forces the one playback order that records an album correctly:
        straight through, once. Shuffle or repeat would put tracks on the
        disc in an order the titles then wouldn't match -- and a repeat
        would keep recording past the end of the album.

        Note the flat keys: Beefweb answers 400 to a nested
        {"options": {...}} body."""
        self._request("/api/player", body={"playbackMode": 0, "stopAfterCurrentTrack": False})

    def set_stop_after_current_track(self, stop: bool) -> None:
        """Makes foobar2000 stop when the playing track ends, instead of
        going on to the next one.

        This is how a cassette's side break is made clean. The alternative
        -- watching for the playlist to move past the last track of the side
        and stopping then -- always records the first fraction of a second
        of the next track onto the end of the side, because a poll can only
        notice a change after it has happened. Handing the boundary to
        foobar2000 itself means playback simply ends where the side does.

        Flat key, like prepare_for_recording()'s -- which is also what
        clears it again at the start of every recording, so a side left
        armed can never affect the next one."""
        self._request("/api/player", body={"stopAfterCurrentTrack": bool(stop)})

    def set_volume(self, db: float) -> None:
        """Sets foobar's output volume, in dB -- confirmed live against a
        running foobar2000 2.25.10/foo_beefweb 0.10: GET /api/player's own
        "volume" object reports {"isMuted", "max": 0.0, "min": -100.0,
        "type": "db", "value"}, and POSTing a flat {"volume": db} body (same
        convention as prepare_for_recording()'s own flat keys) updates
        "value" to exactly that, read back and verified. Does not touch
        isMuted -- a muted player staying muted is not this call's
        business."""
        self._request("/api/player", body={"volume": db})


# --- putting files into foobar ----------------------------------------
#
# Beefweb has an endpoint for this (POST /api/playlists/{id}/items/add) and
# it cannot be used: it answers 403 "item is not under allowed path" for
# anything outside the music directories configured in foobar's own
# preferences, and that list starts out -- and on a normal install stays --
# completely empty. Confirmed against the live component: GET
# /api/browser/roots returned {"roots": []}, and adding a real file from the
# user's own Music folder was refused.
#
# foobar2000's command line has no such notion, so that is what carries the
# files, while Beefweb still does everything else (making the playlist, and
# reading back what landed in it). Splitting one operation across two
# transports is not elegant; requiring every user to go and configure a
# whitelist before a CD could be recorded is worse.

# Windows registers the install path here; the fixed paths cover an install
# that somehow did not.
_APP_PATHS_KEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\foobar2000.exe"

# foobar2000 forwards a command line to the already-running instance and
# exits immediately, so this is fast -- but not instant, and the add itself
# is asynchronous inside foobar (see wait_for_item_count).
_CLI_TIMEOUT_S = 30.0


def find_foobar_exe() -> str | None:
    """Where foobar2000 is installed, or None."""
    if sys.platform == "win32":
        import winreg

        for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                with winreg.OpenKey(root, _APP_PATHS_KEY) as key:
                    path = str(winreg.QueryValueEx(key, "")[0])
            except OSError:
                continue
            if path and Path(path).is_file():
                return path
        for base in (os.environ.get("ProgramFiles", ""), os.environ.get("ProgramFiles(x86)", "")):
            if not base:
                continue
            candidate = Path(base) / "foobar2000" / "foobar2000.exe"
            if candidate.is_file():
                return str(candidate)
        return None
    import shutil

    return shutil.which("foobar2000")


def add_files_via_cli(exe: str, paths: list[Path | str], *, run=subprocess.run) -> None:
    """Adds files to foobar2000's *current* playlist.

    One call with every file rather than one call per file, because spawning
    a process per track multiplies the wait.

    **It does not follow that they land in the order they were given.** This
    used to say they did, and a user recording an album whose tracks he had
    reordered got the wrong track on the disc: foobar2000 sorts an incoming
    batch by its own rule (by filename, normally), so a batch handed over in
    one order can arrive in another. Nothing here can turn that off, so
    order is something to *check* afterwards, never to assume -- see
    replace_current_playlist(), which does the checking and knows what to do
    when the answer is no."""
    if not paths:
        return
    command = [exe, "/add"] + [str(path) for path in paths]
    try:
        completed = run(
            command,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=_CLI_TIMEOUT_S,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired as exc:
        raise FoobarError("foobar2000 did not respond to the command line") from exc
    except OSError as exc:
        raise FoobarError(f"could not run foobar2000: {exc}") from exc
    if completed.returncode != 0:
        raise FoobarError(f"foobar2000 refused the files (exit {completed.returncode})")


def wait_for_item_count(
    client: FoobarClient,
    playlist_id: str,
    expected: int,
    *,
    timeout: float = 30.0,
    sleep=time.sleep,
    now=time.monotonic,
) -> int:
    """Waits for foobar to finish adding.

    The command line returns as soon as foobar has *accepted* the files;
    reading and tagging them happens afterwards, so asking for the playlist
    immediately reports a count that is still climbing. Returns whatever
    count it settled on -- short is the caller's problem to report, not an
    exception here, since a partially added album is still a real state the
    user may want to see."""
    deadline = now() + timeout
    count = 0
    while True:
        for playlist in client.playlists():
            if playlist.id == playlist_id:
                count = playlist.item_count
        if count >= expected or now() >= deadline:
            return count
        sleep(0.25)


def _same_order(client: FoobarClient, playlist_id: str, paths: list[Path | str]) -> bool:
    """Whether the playlist really holds these files, in this order.

    Compared by path rather than by title, because the title is whatever
    foobar read out of the tags and two tracks can share one. Normalised
    for case and separators, since the path we asked with and the path
    %path% reports come from different sides of the same filesystem."""

    try:
        landed = client.playlist_items(playlist_id)
    except FoobarError:
        return False
    return [_normalise_path(item.path) for item in landed] == [_normalise_path(p) for p in paths]


def _normalise_path(value) -> str:
    return os.path.normcase(os.path.normpath(str(value)))


def reorder_playlist(client: FoobarClient, playlist_id: str, paths: list[Path | str]) -> bool:
    """Puts a playlist into this order by *moving* its items.

    The right way round, and the one to try first: it never clears the
    playlist, never re-adds a file, and does not care whether the files are
    still where they were -- so nothing is lost if it fails halfway, unlike
    rebuilding through the command line (which additionally has to fight
    foobar2000's own habit of sorting whatever it is handed).

    Verified against the live Beefweb: `items/move` with `targetIndex`
    inserts the moved items *before* that position and leaves everything
    else in its relative order, so pulling each track forward in turn ends
    with exactly the order asked for. Each step is simulated locally as
    well, because a playlist's indices shift under every move.

    Returns whether the playlist now holds that order; False (rather than
    an exception) when it holds different tracks altogether, which is not
    something reordering can fix and the caller has another way to handle.
    """
    items = client.playlist_items(playlist_id)
    if not all(str(path).strip() for path in paths) or not all(item.path.strip() for item in items):
        # Without a path there is nothing to tell one entry from another --
        # every empty one normalises to the same string, so the comparison
        # below would report success having moved nothing at all. A stream
        # or anything else that is not a file is simply not reorderable
        # this way, and saying so is what sends the caller to the fallback.
        return False

    wanted = [_normalise_path(path) for path in paths]
    current = [_normalise_path(item.path) for item in items]
    if current == wanted:
        return True
    if sorted(current) != sorted(wanted):
        return False

    for target, path in enumerate(wanted):
        if current[target] == path:
            continue
        source = current.index(path, target)
        client.move_playlist_items(playlist_id, [source], target)
        current.insert(target, current.pop(source))

    landed = [_normalise_path(item.path) for item in client.playlist_items(playlist_id)]
    return landed == wanted


def replace_current_playlist(
    client: FoobarClient,
    exe: str,
    paths: list[Path | str],
    *,
    wait=wait_for_item_count,
) -> Playlist:
    """Empties the playlist foobar is on and fills it with these files, in
    this order -- and makes sure that is what actually happened.

    Deliberately the *current* playlist rather than a new one made for the
    occasion: the record flow reads whatever playlist is current, so this
    keeps one meaning of "what is about to be recorded" instead of two.

    **The order is verified rather than assumed, and that is the whole
    point of this function.** Reported live, mid-recording: an album whose
    tracks had been reordered in xD-Tools was recorded from foobar's own
    order, so the disc got the wrong track -- foobar2000 sorts an incoming
    batch by filename before appending it, which silently undoes the very
    thing the caller asked for. Adding the files one at a time is what
    survives that (a batch of one has nothing to sort against, and each
    lands after the last), at the cost of one process per track, so it is
    the fallback and not the first move.

    If even that does not produce the order asked for, this raises rather
    than returning: every caller is about to record or burn what is in this
    playlist, and a wrong order discovered afterwards is a wasted disc."""
    playlist = client.current_playlist()
    if playlist is None:
        raise FoobarError("foobar2000 has no playlist open")

    client.clear_playlist(playlist.id)
    add_files_via_cli(exe, paths)
    wait(client, playlist.id, len(paths))
    if _same_order(client, playlist.id, paths):
        return playlist

    client.clear_playlist(playlist.id)
    for index, path in enumerate(paths, start=1):
        add_files_via_cli(exe, [path])
        if wait(client, playlist.id, index) < index:
            raise FoobarError(f"foobar2000 did not take {path}")
    if _same_order(client, playlist.id, paths):
        return playlist

    raise FoobarError("foobar2000 would not keep the tracks in the order they were given")


def sort_by_disc_and_track(items: list[PlaylistItem]) -> list[PlaylistItem]:
    """The album's own order: disc first, then track.

    A playlist assembled by dropping a folder of a double album into
    foobar2000 routinely arrives with the two discs interleaved -- observed
    directly, `2, 1, 2, 1, 1...` -- because foobar sorts what it is given by
    filename, and both discs number their tracks from one. The files
    themselves know better, so this asks them.

    Two rules keep it from doing harm where it has nothing to go on:
    - **A list where nothing carries either number is returned untouched.**
      No tags means no opinion, and the order somebody put the playlist in
      by hand is a better answer than one invented here.
    - **Anything missing a track number sinks to the end of its disc rather
      than to the front**, and ties keep the order they arrived in (the sort
      is stable), so an untagged odd file out never displaces the album.

    A missing disc number counts as disc 1, which is what a single-disc
    album's files look like."""
    numbers = [
        (leading_number(item.disc_number), leading_number(item.track_number)) for item in items
    ]
    return [items[index] for index in order_by_disc_and_track(numbers)]


def disc_breaks(items: list[PlaylistItem]) -> list[int]:
    """Where the files themselves say one disc ends and the next begins --
    indices into `items`, in the form multidisc.plan_from_breaks() takes.

    Assumes the list is already in disc order (see sort_by_disc_and_track);
    the rule itself is multidisc's, since the same question is asked of
    files on disk by the burning side."""
    return breaks_from_disc_numbers([leading_number(item.disc_number) for item in items])


def total_seconds(items: list[PlaylistItem]) -> int:
    return sum(item.length_seconds for item in items)


def album_title(items: list[PlaylistItem]) -> str:
    """The album these tracks are all from, or "" if they are not all from
    one.

    Taking `items[0].album` was enough while a playlist was assumed to be an
    album: every item agreed. A mixtape's first track carries the name of
    whatever record *it* came from, and that name would then be printed on
    the J-card and written onto the disc as though it described all twelve.
    An empty answer is the honest one, and is what
    project.apply_compilation_naming() then turns into a real name."""
    named = [item.album.strip() for item in items if item.album.strip()]
    if not named:
        return ""
    most_common, count = Counter(named).most_common(1)[0]
    # Weighed against the tracks that actually carry an album tag, not
    # against the whole playlist. A half-tagged album is still that album --
    # counting the untagged ones as votes against would strip the name off
    # a perfectly ordinary record, which is a regression on the normal path
    # for the sake of the unusual one.
    return most_common if count * 2 > len(named) else ""


def album_artist(items: list[PlaylistItem]) -> str:
    """The album's own artist, not whoever is credited on track one -- a
    compilation or a guest feature makes those differ."""
    for item in items:
        if item.album_artist:
            return item.album_artist
    return ""


def metadata_from_playlist(items: list[PlaylistItem]) -> ProjectMetadata:
    """The playlist as project metadata.

    Taken from foobar rather than iTunes on purpose when recording: this is
    exactly what will end up on the disc, in the order it will be recorded,
    whereas a lookup returns whatever release the search matched.

    A playlist is not necessarily an album, though -- it is just as likely
    to be a mixtape somebody assembled -- so the result is passed through
    the compilation check before being handed back."""
    metadata = ProjectMetadata(
        album=album_title(items),
        artist=album_artist(items),
        year=album_year(items),
        tracks=[
            Track(title=item.display_title(), time_seconds=item.length_seconds or None, artist=item.artist)
            for item in items
        ],
    )
    return apply_compilation_naming(metadata)


def album_year(items: list[PlaylistItem]) -> int | None:
    """foobar's %date% is whatever the tag holds -- often a bare year, but
    also "2024-06-14" or worse, so only the leading four digits are used."""
    for item in items:
        text = item.date.strip()
        if len(text) >= 4 and text[:4].isdigit():
            return int(text[:4])
    return None
