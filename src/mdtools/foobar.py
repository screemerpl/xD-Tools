"""Talking to a running foobar2000 through its Beefweb Remote Control
component (foo_beefweb), which exposes a small REST API on localhost.

Used by "Record to MiniDisc from foobar2000...": foobar plays the album
into the deck over S/PDIF while MDTools watches which track is playing and,
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
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from mdtools.project import ProjectMetadata, Track

DEFAULT_BASE_URL = "http://localhost:8880"
DEFAULT_TIMEOUT_S = 5.0

# One column set shared by the playlist listing and the now-playing query, so
# an item always reports the same fields wherever it is read from.
# "album artist" rather than "artist" on purpose: a guest feature credits a
# different artist per track, which is right for a track title and wrong for
# the disc title.
_COLUMNS = ["%tracknumber%", "%title%", "%album artist%", "%album%", "%date%", "%length_seconds%"]
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
        )


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

    def prepare_for_recording(self) -> None:
        """Forces the one playback order that records an album correctly:
        straight through, once. Shuffle or repeat would put tracks on the
        disc in an order the titles then wouldn't match -- and a repeat
        would keep recording past the end of the album.

        Note the flat keys: Beefweb answers 400 to a nested
        {"options": {...}} body."""
        self._request("/api/player", body={"playbackMode": 0, "stopAfterCurrentTrack": False})


def total_seconds(items: list[PlaylistItem]) -> int:
    return sum(item.length_seconds for item in items)


def album_title(items: list[PlaylistItem]) -> str:
    return items[0].album if items else ""


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
    whereas a lookup returns whatever release the search matched."""
    return ProjectMetadata(
        album=album_title(items),
        artist=album_artist(items),
        year=album_year(items),
        tracks=[Track(title=item.title, time_seconds=item.length_seconds or None) for item in items],
    )


def album_year(items: list[PlaylistItem]) -> int | None:
    """foobar's %date% is whatever the tag holds -- often a bare year, but
    also "2024-06-14" or worse, so only the leading four digits are used."""
    for item in items:
        text = item.date.strip()
        if len(text) >= 4 and text[:4].isdigit():
            return int(text[:4])
    return None
