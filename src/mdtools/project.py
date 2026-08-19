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

# The physical medium a project is for. Chosen once, when the project is
# created, and it decides which templates File > New offers and which
# recording/burning flow applies to it.
MEDIUM_MD = "md"
MEDIUM_CD = "cd"
MEDIUM_TAPE = "tape"

PAGE_DISC = "disc"
PAGE_COVER = "cover"
# A cassette carries a label on each face, and they are different pages
# rather than one page printed twice: side B is not side A, and the whole
# point of the object is which half is facing you.
PAGE_SIDE_A = "side_a"
PAGE_SIDE_B = "side_b"
# Not built yet -- the planned CD back insert (a jewel case tray card).
# Listed here so the shape of "a page kind" is visible, and so nothing
# below has to change when it arrives.
PAGE_BACK = "back"


@dataclass(frozen=True)
class PageKind:
    """What one page of a project is.

    A project used to be exactly a disc page plus a cover page, and that
    assumption was written into every layer of the app -- the page
    dropdown, the template picker, saving, printing. Adding a third page
    (a CD's case back) meant touching all of it, so the pair became this
    list instead: a page kind is *data*, and a new one is an entry here
    rather than a change everywhere.

    `template_kind` is which family of templates fits this page, matching
    DiscTemplate.kind / CoverTemplate.kind. Several pages can share one:
    a CD's front insert and its case back are both "cover" shapes.
    """

    key: str
    template_kind: str


PAGE_KINDS: dict[str, PageKind] = {
    PAGE_DISC: PageKind(PAGE_DISC, "disc"),
    PAGE_COVER: PageKind(PAGE_COVER, "cover"),
    PAGE_BACK: PageKind(PAGE_BACK, "cover"),
    # Their own family, not "cover": a J-card and a shell sticker are both
    # rectangles, and offering one where the other belongs is how a
    # cassette project ended up able to hold three J-cards.
    PAGE_SIDE_A: PageKind(PAGE_SIDE_A, "label"),
    PAGE_SIDE_B: PageKind(PAGE_SIDE_B, "label"),
}

# The order pages are offered in, for any project that has them. A project
# carries only the pages it actually uses; this decides how they are
# listed.
PAGE_ORDER = (PAGE_DISC, PAGE_COVER, PAGE_BACK, PAGE_SIDE_A, PAGE_SIDE_B)


@dataclass(frozen=True)
class MediumPage:
    """One page a medium has, and whether a project must have it.

    This is what stopped the app assuming a disc: a MiniDisc project has a
    disc label and a J-card, a CD project may add a case back, and a
    cassette has no disc at all -- a J-card and one label per side. Which
    pages File > New offers, and which of them can be left out, is read
    from here rather than written into the dialog.
    """

    page: str
    optional: bool = False


MEDIUM_PAGES: dict[str, tuple[MediumPage, ...]] = {
    MEDIUM_MD: (MediumPage(PAGE_DISC), MediumPage(PAGE_COVER)),
    MEDIUM_CD: (MediumPage(PAGE_DISC), MediumPage(PAGE_COVER), MediumPage(PAGE_BACK, optional=True)),
    MEDIUM_TAPE: (MediumPage(PAGE_COVER), MediumPage(PAGE_SIDE_A), MediumPage(PAGE_SIDE_B)),
}


def medium_pages(medium: str) -> tuple[MediumPage, ...]:
    return MEDIUM_PAGES.get(medium, MEDIUM_PAGES[MEDIUM_MD])


def medium_name(medium: str) -> str:
    """What to call a medium on screen.

    One function, because the Recording menu, the rip dialog and the folder
    dialog all name the thing being recorded onto and none of them may
    disagree with the others -- a window headed "Record CD to MiniDisc"
    while the project is a cassette is exactly the report this exists to
    answer.

    QCoreApplication.translate with a fixed context rather than tr(): this
    is a plain function, the same rule page_title() above follows.
    """
    if medium == MEDIUM_CD:
        return QCoreApplication.translate("Media", "CD")
    if medium == MEDIUM_TAPE:
        return QCoreApplication.translate("Media", "Cassette")
    return QCoreApplication.translate("Media", "MiniDisc")


def page_template_kind(page: str) -> str:
    """Which template family a page takes. Unknown pages are treated as
    covers, which is the safe answer: every non-disc page so far is one."""
    kind = PAGE_KINDS.get(page)
    return kind.template_kind if kind else "cover"


def page_title(page: str, medium: str = "md") -> str:
    """What to call a page on screen.

    Depends on the medium as well as the page: a MiniDisc's second page is
    a J-card, a CD's is a case insert, and calling either by the other's
    name describes a part the project does not have.

    QCoreApplication.translate with a fixed context rather than tr(): this
    is a plain function, the same rule metadata_menu_entries() below
    follows.
    """
    if page == PAGE_DISC:
        return QCoreApplication.translate("Pages", "Disc Label")
    if page == PAGE_COVER:
        if medium == MEDIUM_CD:
            return QCoreApplication.translate("Pages", "Case Insert")
        if medium == MEDIUM_TAPE:
            return QCoreApplication.translate("Pages", "J-Card")
        return QCoreApplication.translate("Pages", "Cover / J-Card")
    if page == PAGE_BACK:
        return QCoreApplication.translate("Pages", "Case Back")
    if page == PAGE_SIDE_A:
        return QCoreApplication.translate("Pages", "Side A label")
    if page == PAGE_SIDE_B:
        return QCoreApplication.translate("Pages", "Side B label")
    return page


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
    # Keyed by page (PAGE_DISC, PAGE_COVER, ...). A project carries only
    # the pages it uses -- two today, more once the CD case back lands --
    # so nothing may assume a particular set. Use ordered_pages() to list
    # them.
    pages: dict[str, DesignScene]
    default_text_style: TextStyle = field(default_factory=TextStyle)
    grayscale_adjustment: GrayscaleAdjustment = field(default_factory=GrayscaleAdjustment)
    # MEDIUM_MD for every project saved before CD-R support existed -- they
    # were MiniDisc projects, so loading them as such is not a default, it
    # is the truth about them.
    medium: str = MEDIUM_MD
    # Which cassette this project is for, in minutes across both sides. It
    # decides where the side break falls, so the shell labels and the
    # recording have to agree about it -- which is why it lives on the
    # project rather than being asked for twice. Meaningless for a disc,
    # and simply ignored there.
    tape_total_minutes: float = 90.0

    def ordered_pages(self) -> list[str]:
        """This project's pages, in the order they are shown.

        PAGE_ORDER decides the order; anything not listed there follows, in
        whatever order the project itself holds it, so an unknown page is
        never silently dropped from the dropdown.
        """
        known = [page for page in PAGE_ORDER if page in self.pages]
        return known + [page for page in self.pages if page not in PAGE_ORDER]


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


def track_list_columns(metadata: ProjectMetadata, count: int = 2) -> list[str]:
    """The numbered track list dealt into `count` side-by-side columns.

    Filled column by column, not row by row, so the numbering still reads
    downwards -- the first column holds the first tracks, and each one
    continues where the last left off.

    More than two is for a panel that is much wider than it is tall: a
    cassette inlay's tuck-in flap is 102mm across and 24mm deep, where two
    columns of six leave the type at the smallest size that still prints.
    Returns [] if there are no tracks.
    """
    if not metadata.tracks:
        return []
    count = max(1, count)
    lines = numbered_track_lines(metadata)
    per_column = math.ceil(len(lines) / count)
    return ["\n".join(lines[start : start + per_column]) for start in range(0, len(lines), per_column)]


def track_list_two_columns(metadata: ProjectMetadata) -> list[str]:
    """The two-column form, which is what the Metadata menu inserts."""
    return track_list_columns(metadata, 2)


def metadata_column_entries(metadata: ProjectMetadata) -> list[tuple[str, list[str]]]:
    """(menu label, column texts) pairs for "insert as N side-by-side text
    layers" -- currently just the two-column track list, omitted if there
    are no tracks yet."""
    entries: list[tuple[str, list[str]]] = []
    columns = track_list_two_columns(metadata)
    if columns:
        entries.append((QCoreApplication.translate("MetadataMenu", "Full Track List (2 Columns)"), columns))
    return entries
