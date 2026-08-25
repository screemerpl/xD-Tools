"""Identifying an audio CD from its table of contents, via MusicBrainz.

A bare audio CD carries no text at all -- no album, no artist, no track
titles, just a table of contents. What it does carry is a TOC unique enough
to serve as a fingerprint, and MusicBrainz will trade one for the other.

Chosen over the iTunes Search API that `metadata_lookup.py` already uses for
one reason: iTunes has nothing to search *with* here. Its endpoint takes an
artist and album name, which is precisely what a CD does not tell us. Once
this module has supplied those names, cover art still comes from
`metadata_lookup.find_cover()` -- MusicBrainz's own artwork lives in a
separate service, and the existing one already caches what it fetches into
the asset gallery.

Like metadata_lookup.py: plain stdlib urllib, synchronous, no key and no
signup. Unlike it, MusicBrainz *requires* an identifying User-Agent and
will refuse a request without one, so `_USER_AGENT` is not decoration.

No Qt in here -- the dialog imports this, never the other way round.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

from mdtools.cdrip import DiscToc

BASE_URL = "https://musicbrainz.org/ws/2"
TIMEOUT_S = 20.0

# MusicBrainz blocks requests that do not identify themselves. Their policy
# asks for an application name, a version, and a way to make contact.
_USER_AGENT = "xD-Tools/1.0 ( https://github.com/screemerpl/xD-Tools )"

_INCLUDES = "artist-credits+recordings"


class MusicBrainzError(Exception):
    """Unreachable, refused, or an unreadable response. One exception type
    for every failure, so the UI has one place to handle it -- the same
    shape metadata_lookup.MetadataLookupError has."""


@dataclass
class DiscRelease:
    release_id: str
    title: str
    artist: str
    year: int | None = None
    country: str = ""
    track_titles: list[str] = field(default_factory=list)
    # Per-track performers, parallel to track_titles and "" where unknown.
    # Only interesting on a compilation, which is exactly the case where a
    # release's own artist ("Various Artists") says nothing useful about
    # what is actually on the disc.
    track_artists: list[str] = field(default_factory=list)

    def label(self) -> str:
        """Enough to tell two pressings apart at a glance, which is the
        whole reason the user is shown a list rather than a guess."""
        bits = [str(self.year)] if self.year else []
        if self.country:
            bits.append(self.country)
        bits.append(f"{len(self.track_titles)} tracks")
        return f"{self.artist} - {self.title} ({', '.join(bits)})"


def lookup_disc(toc: DiscToc, *, opener=None) -> list[DiscRelease]:
    """Every release this disc might be, best first.

    Two queries, deliberately, because they fail in opposite directions.
    The exact disc id matches this pressing and nothing else -- when it hits
    it is right -- but it only hits if somebody has submitted this disc's id
    before. The TOC search matches on the shape of the disc instead, so it
    finds releases nobody has ever submitted an id for, at the cost of
    returning every other pressing that happens to have the same track
    lengths. Exact first, fall back to fuzzy.

    An empty list is a normal answer -- plenty of discs are in neither --
    and the caller is expected to let the user type the titles instead,
    rather than treat it as an error."""
    disc_id = toc.musicbrainz_disc_id()
    payload = _get(f"/discid/{urllib.parse.quote(disc_id)}", {"inc": _INCLUDES}, opener=opener, allow_404=True)
    if payload:
        releases = parse_releases(payload, len(toc.tracks))
        if releases:
            return releases

    payload = _get(
        "/discid/-",
        {"toc": toc.musicbrainz_toc_param(), "inc": _INCLUDES, "media-format": "all"},
        opener=opener,
        allow_404=True,
    )
    return parse_releases(payload or {}, len(toc.tracks))


def parse_releases(payload: dict, expected_tracks: int) -> list[DiscRelease]:
    """The releases out of either query's response -- both return the same
    shape, a discid lookup simply wrapping it in one more level.

    Ranked by how well they actually fit the disc in the drive: a medium
    whose track count matches wins outright (a box set's other disc, or a
    reissue with bonus tracks, is the wrong answer even when the release is
    the right one), and among equals the earliest release wins, which is
    the original pressing rather than whichever reissue was catalogued
    first."""
    releases = []
    for entry in payload.get("releases", []) or []:
        tracks = _tracks_for(entry, expected_tracks)
        releases.append(
            DiscRelease(
                release_id=entry.get("id", ""),
                title=entry.get("title", ""),
                artist=_artist_credit(entry),
                year=_year(entry.get("date")),
                country=entry.get("country") or "",
                track_titles=[title for title, _ in tracks],
                track_artists=[artist for _, artist in tracks],
            )
        )
    releases.sort(key=lambda r: (len(r.track_titles) != expected_tracks, r.year or 9999))
    return releases


def _tracks_for(release: dict, expected_tracks: int) -> list[tuple[str, str]]:
    """(title, artist) off whichever medium is the disc we are holding.

    A multi-disc release lists every disc in `media`, and the fuzzy TOC
    search does not narrow that down at all, so matching on track count is
    what picks disc 2 of a set instead of always taking disc 1.

    A track's performer is credited on the track itself, or failing that on
    the recording behind it -- MusicBrainz puts it in either place
    depending on whether the release overrides the recording's credit,
    which a compilation routinely does."""
    media = release.get("media") or []
    best = None
    for medium in media:
        tracks = medium.get("tracks") or []
        if len(tracks) == expected_tracks:
            best = tracks
            break
        if best is None and tracks:
            best = tracks
    return [(track.get("title", ""), _track_artist(track)) for track in (best or [])]


def _track_artist(track: dict) -> str:
    credited = _artist_credit(track)
    if credited:
        return credited
    return _artist_credit(track.get("recording") or {})


def _artist_credit(release: dict) -> str:
    """MusicBrainz spells a collaboration out as credited -- separate
    artists with the join phrases ("feat. ", " & ") that go between them --
    so the parts are reassembled rather than just taking the first."""
    credits = release.get("artist-credit") or []
    text = "".join(str(part.get("name", "")) + str(part.get("joinphrase", "")) for part in credits)
    return text.strip() or str(release.get("artist", "") or "")


def _year(date: str | None) -> int | None:
    if not date:
        return None
    head = str(date)[:4]
    return int(head) if head.isdigit() else None


def _get(path: str, params: dict, *, opener=None, allow_404: bool = False) -> dict | None:
    query = urllib.parse.urlencode({**params, "fmt": "json"})
    request = urllib.request.Request(f"{BASE_URL}{path}?{query}", headers={"User-Agent": _USER_AGENT})
    open_url = opener or urllib.request.urlopen
    try:
        with open_url(request, timeout=TIMEOUT_S) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        # A disc nobody has catalogued is the ordinary case, not a failure.
        if allow_404 and exc.code == 404:
            return None
        raise MusicBrainzError(f"MusicBrainz returned HTTP {exc.code}") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise MusicBrainzError(f"could not reach MusicBrainz: {exc}") from exc
    try:
        return json.loads(raw)
    except ValueError as exc:
        raise MusicBrainzError("unreadable response from MusicBrainz") from exc
