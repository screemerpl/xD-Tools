"""A project pairs one disc-label design with one cover/J-card design,
plus the release metadata (album/artist/year/track list) that's useful to
have next to the artwork while designing it.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field

from PySide6.QtCore import QCoreApplication

from mdtools.canvas.scene import DesignScene

PAGE_DISC = "disc"
PAGE_COVER = "cover"


@dataclass
class Track:
    title: str
    time_seconds: int | None = None  # optional; None means "not set"
    # Who performs *this* track, which is only ever interesting when it
    # differs from the album's own artist -- on a compilation. Empty means
    # "not known", which is the normal case for a metadata lookup or a
    # hand-typed track list.
    artist: str = ""


@dataclass
class ProjectMetadata:
    album: str = ""
    artist: str = ""
    year: int | None = None
    tracks: list[Track] = field(default_factory=list)
    # Raw image bytes (whatever format metadata_lookup.fetch_artwork()
    # returned, typically JPEG) fetched via the Metadata dialog's "Lookup
    # Track List..." -- saved with the project so reopening the Metadata
    # dialog later still shows it, not just a same-session preview.
    cover_art: bytes | None = None

    def is_compilation(self) -> bool:
        """Whether this is a mixtape rather than one artist's album.

        It matters because almost everything downstream assumes an album:
        a cover art lookup keyed on "artist + album" returns whatever
        release happens to match those words, the J-card credits one
        performer for twelve, and the disc title names a band that plays on
        one track of it.

        The test is not "do the track artists differ" -- that would call
        every album with a guest feature a compilation, which is exactly
        the mistake foobar.album_artist() already exists to avoid. It is
        "can most of these tracks be attributed to one artist": the album's
        own artist if it has one, otherwise the commonest track artist. A
        release credited to Various Artists says so outright and is taken
        at its word."""
        if _looks_like_various(self.artist):
            return True
        credited = [track.artist.strip() for track in self.tracks if track.artist.strip()]
        if len(credited) < 2:
            # Nothing to compare -- an untagged or hand-typed track list is
            # an ordinary album until something says otherwise.
            return False
        anchor = self.artist.strip() or Counter(credited).most_common(1)[0][0]
        attributable = sum(1 for name in credited if _same_artist(name, anchor))
        return attributable * 2 <= len(credited)


# What a compilation calls itself, in the tags this app is likely to meet.
_VARIOUS_NAMES = {"various", "various artists", "va", "v.a.", "różni wykonawcy", "rozni wykonawcy"}


def _looks_like_various(name: str) -> bool:
    return name.strip().casefold() in _VARIOUS_NAMES


def _same_artist(name: str, anchor: str) -> bool:
    """Substring either way, casefolded -- so "Falling In Reverse" matches
    the track credited to "Falling In Reverse, Jelly Roll". Crude, and
    deliberately so: this only has to tell a guest feature apart from a
    genuinely different act."""
    left, right = name.casefold(), anchor.casefold()
    return left in right or right in left


@dataclass
class TextStyle:
    """The project-wide default font/color for newly created text layers.

    Each field is None until the user has actually set that aspect via the
    Properties panel -- an unset field means "leave whatever a freshly
    constructed text item already has," rather than forcing some arbitrary
    hardcoded look before the user has expressed a preference.

    `font_spec` is a full `QFont.toString()` (family, point size, weight,
    italic, underline, strikeout, stretch, ...) rather than separate
    family/size fields -- storing just family+size silently dropped every
    other style the Font... dialog lets you set (bold, italic, strikeout,
    ...) both here and on the item itself. Construct/inspect it via
    `QFont()` + `.fromString(style.font_spec)`, not by hand.
    """

    font_spec: str | None = None
    color: str | None = None

    def is_set(self) -> bool:
        return self.font_spec is not None or self.color is not None


@dataclass
class GrayscaleAdjustment:
    """Brightness/contrast (-100..100 each, 0 = unchanged) for Export Print
    PNG (Grayscale) -- also mirrored live by the canvas's own grayscale
    preview toolbar sliders while that preview is active. Saved with the
    project (see io/project_io.py) so a look dialed in once doesn't need
    re-adjusting on every future export."""

    brightness: int = 0
    contrast: int = 0


@dataclass
class Project:
    metadata: ProjectMetadata
    pages: dict[str, DesignScene]  # keys: PAGE_DISC, PAGE_COVER
    default_text_style: TextStyle = field(default_factory=TextStyle)
    grayscale_adjustment: GrayscaleAdjustment = field(default_factory=GrayscaleAdjustment)


# What a mixtape is called when its own tags do not name it. Deliberately
# not translated: this is written into file tags and onto the MiniDisc
# itself, where the deck can only show ASCII anyway (see mdrem.transliterate),
# and it is a name rather than UI text.
MIXTAPE_ALBUM = "Mixtape"
VARIOUS_ARTISTS = "Various Artists"


def apply_compilation_naming(metadata: ProjectMetadata) -> ProjectMetadata:
    """Gives a compilation a name that is true, in place.

    A mix assembled from twelve unrelated files takes its album and artist
    from whichever track happened to be first, which then goes on the disc
    and the J-card as though the whole thing were that record. "Various
    Artists" is simply the accurate answer.

    A released compilation keeps its own album title -- "Now That's What I
    Call Music 50" is the name of the thing, and only the artist needed
    correcting. `MIXTAPE_ALBUM` is the fallback for a pile of files that
    never had a shared album name to begin with."""
    if not metadata.is_compilation():
        return metadata
    metadata.artist = VARIOUS_ARTISTS
    if not metadata.album.strip():
        metadata.album = MIXTAPE_ALBUM
    return metadata


def format_time(seconds: int | None) -> str:
    if seconds is None:
        return ""
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes}:{secs:02d}"


def parse_time(text: str) -> int | None:
    text = text.strip()
    if not text:
        return None
    parts = text.split(":")
    try:
        if len(parts) == 1:
            return int(parts[0])
        minutes, secs = int(parts[0]), int(parts[1])
        return minutes * 60 + secs
    except ValueError:
        return None


def _track_line(index: int, track: Track, with_artist: bool = False) -> str:
    line = f"{index}. "
    if with_artist and track.artist.strip():
        line += f"{track.artist.strip()} - "
    line += track.title
    if track.time_seconds is not None:
        line += f" ({format_time(track.time_seconds)})"
    return line


def numbered_track_lines(metadata: ProjectMetadata) -> list[str]:
    """["1. Title (3:54)", ...] -- the one place this format lives, shared
    by the metadata-insert menu, the two-column split, and the J-card's
    back panel.

    On a compilation each line names its performer as well ("1. Artist -
    Title (3:54)"), because there the artist is per-track information and
    the card's own heading cannot carry it. On an ordinary album it is left
    out: every line would repeat the name already printed at the top."""
    with_artist = metadata.is_compilation()
    return [_track_line(index, track, with_artist) for index, track in enumerate(metadata.tracks, start=1)]


def metadata_menu_entries(metadata: ProjectMetadata) -> list[tuple[str, str]]:
    """(menu label, text to insert) pairs for "insert text from metadata",
    skipping any field that hasn't been filled in yet.

    Uses QCoreApplication.translate(context, text) rather than `self.tr()`
    since this is a plain function, not a QObject method -- still a literal
    call pyside6-lupdate recognizes for string extraction."""
    entries: list[tuple[str, str]] = []
    if metadata.album:
        entries.append((QCoreApplication.translate("MetadataMenu", "Album Title"), metadata.album))
    if metadata.artist:
        entries.append((QCoreApplication.translate("MetadataMenu", "Artist"), metadata.artist))
    if metadata.year:
        entries.append((QCoreApplication.translate("MetadataMenu", "Year"), str(metadata.year)))
    if metadata.tracks:
        entries.append(
            (
                QCoreApplication.translate("MetadataMenu", "Full Track List"),
                "\n".join(numbered_track_lines(metadata)),
            )
        )
    return entries


def track_list_two_columns(metadata: ProjectMetadata) -> list[str]:
    """Splits the numbered track list into two side-by-side columns -- the
    first half of tracks in the first column, continuing the same numbering
    into the second -- handy for a J-card layout where one long list would
    run too tall. Returns [] if there are no tracks to split."""
    if not metadata.tracks:
        return []
    midpoint = math.ceil(len(metadata.tracks) / 2)
    lines = numbered_track_lines(metadata)
    return ["\n".join(lines[:midpoint]), "\n".join(lines[midpoint:])]


def metadata_column_entries(metadata: ProjectMetadata) -> list[tuple[str, list[str]]]:
    """(menu label, column texts) pairs for "insert as N side-by-side text
    layers" -- currently just the two-column track list, omitted if there
    are no tracks yet."""
    entries: list[tuple[str, list[str]]] = []
    columns = track_list_two_columns(metadata)
    if columns:
        entries.append((QCoreApplication.translate("MetadataMenu", "Full Track List (2 Columns)"), columns))
    return entries
