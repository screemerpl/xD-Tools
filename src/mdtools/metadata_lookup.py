"""Looks up a release's track listing and year from the iTunes Search API,
given an album title and artist name. No API key/signup required -- see
https://performance-partners.apple.com/search-api for the (undocumented but
long-stable) endpoints used here.

Two-step, by design: search_albums() returns candidates for the user to
disambiguate between (album search terms are ambiguous enough -- a single
or remix sharing the album's title, a deluxe reissue, a "best of" -- that
silently auto-picking "the best match" regularly picks the wrong release),
then fetch_tracks() gets the actual track listing for whichever candidate
was chosen.
"""

from __future__ import annotations

import difflib
import json
import re
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

SEARCH_URL = "https://itunes.apple.com/search"
LOOKUP_URL = "https://itunes.apple.com/lookup"
REQUEST_TIMEOUT_SECONDS = 10
USER_AGENT = "xD-Tools (https://github.com/) metadata lookup"

# Deezer's public search API -- like iTunes, no key/signup, and unlike
# iTunes it actually carries artist photos (iTunes' own API has no artist
# image field at all). Used only for a picture of the *artist*, never for
# album/track data -- that stays iTunes, which is what everything else here
# is built around.
ARTIST_SEARCH_URL = "https://api.deezer.com/search/artist"


class MetadataLookupError(Exception):
    """No matching album could be found, or the request itself failed."""


ARTWORK_SIZE = 600  # iTunes serves any size via the URL -- 100x100bb is the
# thumbnail iTunes itself defaults to; swapped for a size actually usable as
# print/cover artwork, not just a UI thumbnail.


@dataclass
class AlbumCandidate:
    collection_id: int
    artist_name: str
    collection_name: str
    year: int | None
    track_count: int
    artwork_url: str | None = None


@dataclass
class LookupTrack:
    title: str
    time_seconds: int | None


@dataclass
class LookupResult:
    year: int | None
    tracks: list[LookupTrack]


@dataclass
class ArtistCandidate:
    id: int
    name: str
    nb_fan: int
    picture_url: str | None


def search_albums(artist: str, album: str) -> list[AlbumCandidate]:
    """Candidates ranked best-match-first (see _match_score) -- ties (e.g.
    a single sharing its title with the album) are broken in favor of
    whichever has more tracks, since a single/remix/EP reliably has far
    fewer than a full album."""
    query = urllib.parse.urlencode({"term": f"{artist} {album}", "entity": "album", "limit": 25})
    data = _get_json(f"{SEARCH_URL}?{query}")

    candidates = [
        AlbumCandidate(
            collection_id=entry["collectionId"],
            artist_name=entry.get("artistName", ""),
            collection_name=entry.get("collectionName", ""),
            year=_year_from_release_date(entry.get("releaseDate")),
            track_count=entry.get("trackCount") or 0,
            artwork_url=_upsized_artwork_url(entry.get("artworkUrl100")),
        )
        for entry in data.get("results", [])
        if entry.get("collectionId") is not None
    ]
    candidates.sort(key=lambda c: _match_score(c, artist, album), reverse=True)
    return candidates


def fetch_tracks(collection_id: int, fallback_year: int | None = None) -> LookupResult:
    query = urllib.parse.urlencode({"id": collection_id, "entity": "song"})
    data = _get_json(f"{LOOKUP_URL}?{query}")
    results = data.get("results", [])

    year = fallback_year
    for entry in results:
        if entry.get("wrapperType") == "collection":
            year = _year_from_release_date(entry.get("releaseDate")) or fallback_year
            break

    songs = [entry for entry in results if entry.get("wrapperType") == "track"]
    songs.sort(key=lambda entry: (entry.get("discNumber", 1), entry.get("trackNumber", 0)))

    tracks = [
        LookupTrack(
            title=entry.get("trackName", "").strip(),
            time_seconds=_seconds_from_millis(entry.get("trackTimeMillis")),
        )
        for entry in songs
        if entry.get("trackName")
    ]
    return LookupResult(year=year, tracks=tracks)


def lookup_album(artist: str, album: str) -> LookupResult:
    """Convenience one-shot lookup that auto-picks the top-ranked
    candidate -- for callers that can't offer the user a picker. Raises
    MetadataLookupError if no matching album is found or a request fails
    (network error, bad response, etc.)."""
    candidates = search_albums(artist, album)
    if not candidates:
        raise MetadataLookupError(f'No album matching "{album}" by "{artist}" was found.')
    best = candidates[0]
    return fetch_tracks(best.collection_id, fallback_year=best.year)


def find_cover(artist: str, album: str, track_count: int | None = None) -> tuple[bytes | None, AlbumCandidate | None]:
    """Best-matching release's cover art, without asking the user anything.

    Returns (image bytes or None, the candidate it came from or None) --
    the candidate is worth having even when there is no artwork, since it
    also carries a release year the caller may be missing. Raises
    MetadataLookupError only if the *search* fails; a missing or
    undownloadable cover is reported as None, because artwork is a bonus on
    top of whatever the caller was really after."""
    chosen = best_match(search_albums(artist, album), artist, album, track_count)
    if chosen is None or not chosen.artwork_url:
        return None, chosen
    try:
        return fetch_artwork(chosen.artwork_url), chosen
    except MetadataLookupError:
        return None, chosen


def fetch_artwork(url: str) -> bytes:
    """Raises MetadataLookupError on failure -- callers that treat cover
    art as an optional bonus (rather than the point of the call, unlike
    search_albums/fetch_tracks) should catch and ignore it themselves.

    Named for cover art, but there is nothing album-specific about it --
    it is a plain "download this URL or raise" helper, which is exactly
    what find_artist_photo() below reuses it for."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return response.read()
    except (urllib.error.URLError, TimeoutError) as exc:
        raise MetadataLookupError(f"Could not download the cover art: {exc}") from exc


def search_artists(artist: str) -> list[ArtistCandidate]:
    """Candidates for `artist`'s own name, from Deezer's public artist
    search -- ranked by name similarity first, and *popularity* (nb_fan)
    second, not track count (Deezer's artist search has no such thing).

    The popularity tiebreaker matters more here than the equivalent one
    does for an album: verified live against "Taylor Swift" -- the real
    one and a same-named unrelated act both score a perfect 1.0 name
    match, so name similarity alone cannot tell them apart at all, and
    nb_fan (12.6M vs 11, in that live search) is what actually
    distinguishes "who somebody means" from "who happens to share a name".
    """
    query = urllib.parse.urlencode({"q": artist})
    data = _get_json(f"{ARTIST_SEARCH_URL}?{query}")
    candidates = [
        ArtistCandidate(
            id=entry["id"],
            name=entry.get("name", ""),
            nb_fan=entry.get("nb_fan") or 0,
            picture_url=entry.get("picture_xl") or entry.get("picture_big") or None,
        )
        for entry in data.get("data", [])
        if entry.get("id") is not None
    ]
    candidates.sort(key=lambda c: (_similarity(artist, c.name), c.nb_fan), reverse=True)
    return candidates


# A photo is of one specific person, not an edition of a release -- there
# is no equivalent of "close enough, the user can still tell it's the right
# album from the cover". Stricter than MIN_ARTIST_SIMILARITY (0.40) above,
# which only ever has to rule out an unrelated act attached to someone
# else's album.
MIN_ARTIST_PHOTO_SIMILARITY = 0.75


def find_artist_photo(artist: str) -> bytes | None:
    """A photo of `artist`, or None if nothing good enough was found.

    Silent on every kind of failure -- no match, no picture on the best
    match, a network error either during search or download -- the same
    "bonus, not the point of the call" contract find_cover() already
    follows for album art: a missing photo means an empty spot on the
    page, not a warning dialog interrupting whatever the caller was doing.
    """
    if not artist.strip():
        return None
    try:
        candidates = search_artists(artist)
    except MetadataLookupError:
        return None
    matching = [c for c in candidates if _similarity(artist, c.name) >= MIN_ARTIST_PHOTO_SIMILARITY]
    if not matching or not matching[0].picture_url:
        return None
    try:
        return fetch_artwork(matching[0].picture_url)
    except MetadataLookupError:
        return None


# Words iTunes routinely appends to a release title that say nothing about
# which album it is -- left in, they drag the similarity of an otherwise
# perfect match down and can let a worse candidate win.
_EDITION_NOISE = {
    "deluxe", "edition", "remaster", "remastered", "explicit", "clean",
    "bonus", "track", "version", "special", "anniversary", "expanded",
    "reissue", "single", "ep", "the",
}

_PUNCTUATION = re.compile(r"[^\w\s]", re.UNICODE)
_WHITESPACE = re.compile(r"\s+")


def _normalize(text: str) -> str:
    """Casefolded, unaccented, punctuation-free, edition-noise-free."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    words = _WHITESPACE.sub(" ", _PUNCTUATION.sub(" ", stripped.casefold())).split()
    meaningful = [word for word in words if word not in _EDITION_NOISE]
    return " ".join(meaningful or words)


def _similarity(left: str, right: str) -> float:
    """0..1, blending whole-string closeness with word overlap.

    SequenceMatcher alone punishes reordering ("Bowie, David" vs "David
    Bowie") harshly; token overlap alone ignores word order entirely and
    calls "Love Songs" and "Songs Love" identical. Averaging the two is
    steadier than either."""
    a, b = _normalize(left), _normalize(right)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    sequence = difflib.SequenceMatcher(None, a, b).ratio()
    left_words, right_words = set(a.split()), set(b.split())
    overlap = len(left_words & right_words) / len(left_words | right_words)
    return (sequence + overlap) / 2


def _track_count_closeness(candidate: AlbumCandidate, expected: int | None) -> float:
    if not expected or candidate.track_count <= 0:
        return 0.0
    return max(0.0, 1.0 - abs(candidate.track_count - expected) / expected)


def match_confidence(candidate: AlbumCandidate, artist: str, album: str, track_count: int | None = None) -> float:
    """How well a candidate matches what we asked for, 0..1.

    Deliberately our own statistic rather than iTunes' result order, which
    regularly puts a remix single or a tribute-album cover version above the
    actual release. The album title carries the most weight, the artist name
    nearly as much, and -- when the caller knows how many tracks it is
    actually holding, as it does when recording a playlist -- the track
    count settles what would otherwise be close calls between an album and
    its own deluxe reissue."""
    album_score = _similarity(album, candidate.collection_name)
    artist_score = _similarity(artist, candidate.artist_name)
    return 0.55 * album_score + 0.30 * artist_score + 0.15 * _track_count_closeness(candidate, track_count)


# Below this, "the best of these" is not the same as "a match". Chosen
# against a real failure: a folder of Falling In Reverse's "Popular
# Monster", an album iTunes does not carry at all, matched a one-track cover
# version of the title track by an unrelated artist at 0.605 -- a perfect
# album title (0.55) plus almost nothing else -- and its sleeve was shown as
# though it belonged to the disc. A genuine hit scores 0.85 without a known
# track count and past 0.90 with one, so the gap is wide and this sits in
# the middle of it.
MIN_MATCH_CONFIDENCE = 0.70

# The blended score alone is not enough, which is worth stating plainly
# because it looks as though it should be: title (0.55) plus a track count
# that happens to agree (0.15) already reaches 0.70 with the artist
# contributing nothing, and "right title, wrong artist" is precisely the
# failure above. So the artist is checked on its own terms as well -- but
# only when the caller supplied one, since with no artist to compare there
# is nothing to judge. A real variant lands well clear of this: "Falling In
# Reverse & Jelly Roll" against "Falling In Reverse" scores about 0.70,
# "Bowie, David" against "David Bowie" about 0.77, while the unrelated
# artists in the failing search all came in under 0.25.
MIN_ARTIST_SIMILARITY = 0.40


def best_match(
    candidates: list[AlbumCandidate], artist: str, album: str, track_count: int | None = None
) -> AlbumCandidate | None:
    """The single best candidate, for flows that cannot stop and ask -- or
    None when none of them is good enough to be called a match.

    MetadataDialog still shows a picker; a person choosing beats any
    heuristic, and it deliberately does not go through here. This exists for
    the automated flows, where interrupting a finished recording to ask
    about cover art would be worse than occasionally picking a wrong edition
    of the right album.

    A wrong edition is one thing; a wrong *record* is another, and returning
    one is worse than returning nothing -- the caller has other places to
    look (the picture inside the files, see embedded_cover) and, failing
    that, no cover at all is an honest answer where somebody else's sleeve
    printed on this disc is not."""
    if not candidates:
        return None
    # Track count breaks ties, never overrides a better name match -- the
    # same rule the interactive ranking uses. It matters because stripping
    # edition noise makes "Popular Monster - Single" score identically to
    # "Popular Monster", and among equals the fuller release is the album.
    chosen = max(candidates, key=lambda c: (match_confidence(c, artist, album, track_count), c.track_count))
    if match_confidence(chosen, artist, album, track_count) < MIN_MATCH_CONFIDENCE:
        return None
    if artist.strip() and _similarity(artist, chosen.artist_name) < MIN_ARTIST_SIMILARITY:
        return None
    return chosen


def _upsized_artwork_url(url: str | None) -> str | None:
    """iTunes serves whatever pixel size is encoded in the URL itself
    (".../100x100bb.jpg") -- swap in a size usable as real artwork instead
    of the tiny default thumbnail."""
    if not url:
        return None
    return url.replace("100x100bb", f"{ARTWORK_SIZE}x{ARTWORK_SIZE}bb")


def _match_score(candidate: AlbumCandidate, artist: str, album: str) -> tuple[int, int]:
    artist_lower, album_lower = artist.strip().lower(), album.strip().lower()
    entry_artist = candidate.artist_name.lower()
    entry_album = candidate.collection_name.lower()
    name_score = (artist_lower in entry_artist or entry_artist in artist_lower) + (
        album_lower in entry_album or entry_album in album_lower
    )
    # tiebreaker only -- never lets a higher track count outrank a better
    # name match, just picks the likelier "real album" among equal matches
    return (name_score, candidate.track_count)


def _year_from_release_date(release_date: str | None) -> int | None:
    if not release_date or len(release_date) < 4:
        return None
    try:
        return int(release_date[:4])
    except ValueError:
        return None


def _seconds_from_millis(millis) -> int | None:
    return round(millis / 1000) if isinstance(millis, (int, float)) else None


def _get_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError) as exc:
        raise MetadataLookupError(f"Could not reach the lookup service: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise MetadataLookupError("The lookup service returned an unexpected response.") from exc
