"""Recording > "Record Folder to MiniDisc..." -- finding an album that is
already sitting on disk as files.

The third source of a recording, after a CD and whatever foobar2000 happens
to have open. Its job is the same as cdrip.py's: put the right files, in the
right order, into foobar's playlist, and then get out of the way so the
existing record flow can do the rest.

Two things it deliberately does not do:

**The recording path never reads a tag.** There is no tag library in this
project and adding one for that would be a dependency for something
foobar2000 already does perfectly -- the files go into the playlist first,
and every title, artist, album and length is then read back out of foobar
through Beefweb. `list_audio_files()` therefore only ever decides *which*
files and in *what order*.

`album_from_folder()`, added for burning a CD-R, is the exception and needs
to be: a burn hands the files straight to cdrdao, so foobar is not in the
loop at all and there is nothing else to ask what a track is called. It
reads FLAC's own comment block through embedded_cover.flac_tags() -- the
parser this project already owns, no library -- and falls back to the
filename for anything else. That is the whole difference: not a change of
mind about tags, but a path where no player is involved.

**It never renames, moves or rewrites anything.** These are the user's own
music files, not the disposable rip folder cdrip.py owns.

`metadata_from_folder()`, added for the Metadata dialog's "Import from
Folder..." (replacing what used to be "Load from foobar2000" there,
explicit user request), is a second exception to the "never reads a tag"
rule above, for the same reason `album_from_folder()` already is: filling
in the metadata editor by hand should not require foobar2000 to be
running with the album already loaded first, any more than burning one
should.

Order comes from the filename, because a filename is the only ordering
signal available before foobar has seen the files -- and it is a good one:
essentially every ripper and download names tracks with the number in front.
Compared naturally (digit runs as numbers), so "10" sorts after "2" rather
than after "1".

No Qt in here, matching cdrip.py/foobar.py/mdrem.py -- the panel imports
this, never the other way round.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import mutagen

from mdtools.embedded_cover import flac_tags
from mdtools.foobar import PlaylistItem, metadata_from_playlist
from mdtools.multidisc import (
    breaks_from_disc_numbers,
    leading_number,
    order_by_disc_and_track,
)
from mdtools.project import ProjectMetadata

# What foobar2000 plays out of the box, plus the common lossless oddities.
# A generous list rather than a strict one: a file it turns out not to
# support simply fails to add, which foobar reports itself, whereas a format
# missing from here is silently left out of the album.
AUDIO_EXTENSIONS = frozenset(
    {
        ".flac", ".mp3", ".m4a", ".mp4", ".aac", ".ogg", ".oga", ".opus",
        ".wav", ".wma", ".ape", ".wv", ".mpc", ".aiff", ".aif", ".alac",
        ".tta", ".dsf", ".dff", ".spx", ".ac3", ".dts",
    }
)

_DIGITS = re.compile(r"(\d+)")

# "Artist - Album", the shape xD-Tools itself proposes when saving a project
# (see user_paths.project_start_path), and the shape essentially every
# download and ripper uses for a folder name.
_SEPARATOR = re.compile(r"\s+-\s+|\s+–\s+|\s+—\s+")

# A trailing "(2016)" or "[2016]", which the same convention appends.
_TRAILING_YEAR = re.compile(r"[\s._-]*[\[(]?((?:19|20)\d{2})[\])]?\s*$")


def natural_key(text: str) -> tuple:
    """Sort key that compares digit runs as numbers.

    Every element is a uniform 3-tuple so keys of different shapes stay
    comparable -- mixing a bare int and a bare str in one key raises
    TypeError the moment two names differ in whether they start with a
    digit, which is exactly the case this exists for."""
    parts = _DIGITS.split(text)
    key = []
    for index, part in enumerate(parts):
        if index % 2:  # the captured digit run
            key.append((0, int(part), ""))
        elif part:
            key.append((1, 0, part.casefold()))
    return tuple(key)


def _is_audio(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS


def _sort_key(path: Path, root: Path) -> tuple:
    """Folder by folder, then filename -- so a two-disc album split into
    CD1/CD2 subfolders comes back in disc order rather than interleaved."""
    try:
        parts = path.relative_to(root).parts
    except ValueError:  # pragma: no cover -- rglob cannot produce this
        parts = (path.name,)
    return tuple(natural_key(part) for part in parts)


def list_audio_files(folder: Path | str) -> list[Path]:
    """The album in `folder`, in the order it should be recorded.

    Looks in the folder itself first and only recurses if it holds no audio
    at all. That is what handles a multi-disc album kept as CD1/CD2
    subfolders, while still making it impossible to pick a folder of albums
    and quietly get every one of them: a folder that has tracks in it *is*
    the album, and its subfolders (scans, artwork, a "bonus" directory) are
    not part of the running order."""
    root = Path(folder)
    if not root.is_dir():
        return []
    top = [path for path in root.iterdir() if _is_audio(path)]
    if top:
        return sorted(top, key=lambda path: _sort_key(path, root))
    nested = [path for path in root.rglob("*") if _is_audio(path)]
    return sorted(nested, key=lambda path: _sort_key(path, root))


def guess_from_folder_name(name: str) -> tuple[str, str, int | None]:
    """(artist, album, year) read out of a folder name like
    "Skillet - Unleashed (2016)".

    Only ever a suggestion, and only used when the files carry no tags to
    contradict it -- it is shown in editable fields, so a wrong guess costs
    a correction rather than a mislabelled disc. Without it an untagged
    folder produces a disc with twelve titles and no name at all, since
    there is nothing else on the machine that knows what the album is.

    Note this is the inverse of the filename xD-Tools proposes for a project
    (user_paths.project_start_path, via mdrem.disc_title) -- the same
    convention read in the other direction."""
    text = name.strip()
    year: int | None = None
    match = _TRAILING_YEAR.search(text)
    if match:
        year = int(match.group(1))
        text = text[: match.start()].strip(" .-_")

    parts = _SEPARATOR.split(text, maxsplit=1)
    if len(parts) == 2 and parts[0].strip() and parts[1].strip():
        left, right = parts[0].strip(), parts[1].strip()
        # "2016 - Unleashed": a year in front is a sorting prefix, not an
        # artist. Common enough in a per-artist library to be worth knowing.
        if len(left) == 4 and left.isdigit():
            return "", right, year or int(left)
        return left, right, year
    return "", text, year


@dataclass(frozen=True)
class FolderTrack:
    """One file, with whatever the file itself says it is called."""

    path: Path
    title: str
    artist: str


@dataclass(frozen=True)
class FolderAlbum:
    """A folder read as an album: its files in disc order, plus the album's
    own name, artist and year where the files carry them.

    Deliberately built without foobar2000, unlike the recording flows: a CD
    burn works from the files directly, so making it wait on a running
    player would be asking for a dependency the job does not have. FLAC
    tags are read the same way album_sort.py reads them, and anything
    untagged (a WAV, an MP3 stripped of tags) falls back to the filename
    stem -- a disc of blank track names is a worse outcome than a filename.
    """

    tracks: list[FolderTrack]
    album: str
    artist: str
    year: int | None


def album_from_folder(folder: Path | str) -> FolderAlbum:
    """Everything a burn needs to know about a folder of audio files.

    The album/artist/year fall back to guess_from_folder_name(), the same
    source FolderRecordDialog prefills its fields from -- and, as there,
    tags beat the folder name whenever the files carry them.
    """
    folder = Path(folder)
    paths = list_audio_files(folder)

    tracks: list[FolderTrack] = []
    albums: list[str] = []
    artists: list[str] = []
    years: list[str] = []
    for path in paths:
        tags = flac_tags(path) if path.suffix.lower() == ".flac" else {}
        tracks.append(
            FolderTrack(
                path=path,
                title=tags.get("TITLE", "").strip() or path.stem,
                artist=(tags.get("ARTIST", "") or tags.get("ALBUMARTIST", "")).strip(),
            )
        )
        if tags.get("ALBUM", "").strip():
            albums.append(tags["ALBUM"].strip())
        credited = (tags.get("ALBUMARTIST", "") or tags.get("ARTIST", "")).strip()
        if credited:
            artists.append(credited)
        if tags.get("DATE", "").strip():
            years.append(tags["DATE"].strip())

    guessed_artist, guessed_album, guessed_year = guess_from_folder_name(folder.name)
    return FolderAlbum(
        tracks=tracks,
        # weighed only against the files that actually carry the tag: counting
        # untagged files as votes against would strip the name off a
        # half-tagged record (the same rule foobar.album_title() follows)
        album=_commonest(albums) or guessed_album,
        artist=_commonest(artists) or guessed_artist,
        year=_year_from(_commonest(years)) or guessed_year,
    )


def metadata_from_folder(folder: Path | str) -> ProjectMetadata:
    """A folder's own tags as project metadata -- the Metadata dialog's
    "Import from Folder..." button, standing in for what used to be "Load
    from foobar2000" there.

    Builds the same `foobar.PlaylistItem` records the live-playlist path
    builds, then hands them to `foobar.metadata_from_playlist()`
    unchanged -- so the album/artist/year majority-vote and
    compilation-naming logic (`foobar.album_title()`/`album_artist()`/
    `apply_compilation_naming()`) is exactly the same code either way,
    fed from files instead of a running player, not a second copy of it
    that could drift from the original.

    Reads tags with `mutagen`'s "easy" interface rather than
    `embedded_cover.flac_tags()` (the hand-rolled, FLAC-only parser
    `album_from_folder()` above uses): this button's whole point is
    reading whatever is actually in the tags, and mutagen reads whatever
    format it recognises -- FLAC, WAV's own RIFF INFO chunk, MP3, and
    more -- under one common set of field names, where the hand-rolled
    parser only ever understood FLAC."""
    paths = list_audio_files(Path(folder))
    items = [_playlist_item_from_file(path, number) for number, path in enumerate(paths, start=1)]
    return metadata_from_playlist(items)


def _playlist_item_from_file(path: Path, track_number: int) -> PlaylistItem:
    """One file read as though foobar2000 had reported it -- the same
    fields `PlaylistItem.from_columns()` builds from Beefweb's columns,
    just read directly off the file instead."""
    try:
        audio = mutagen.File(str(path), easy=True)
    except mutagen.MutagenError:
        audio = None
    tags = audio.tags if audio is not None and audio.tags is not None else {}

    def tag(name: str) -> str:
        value = tags.get(name)
        return value[0].strip() if value else ""

    length = int(audio.info.length) if audio is not None and audio.info is not None else 0
    return PlaylistItem(
        track_number=tag("tracknumber") or str(track_number),
        title=tag("title") or path.stem,
        album_artist=tag("albumartist"),
        album=tag("album"),
        date=tag("date"),
        length_seconds=length,
        artist=tag("artist"),
        path=str(path),
        disc_number=tag("discnumber"),
    )


def _commonest(values: list[str]) -> str:
    """The value most of the files agree on -- so one guest-credited track
    cannot rename the album (see album_sort._group_display_name, which
    solves the same problem for folder names)."""
    if not values:
        return ""
    return Counter(values).most_common(1)[0][0]


def _year_from(value: str) -> int | None:
    match = re.search(r"(\d{4})", value or "")
    return int(match.group(1)) if match else None


def disc_numbers(paths: list[Path | str]) -> list[int | None]:
    """The disc each file says it belongs to, or None where it says nothing.

    Only FLAC is read -- the same limit album_from_folder() already works
    under, and for the same reason: this project owns a FLAC comment parser
    and no tag library, so anything else honestly reports nothing rather
    than being read badly."""
    numbers: list[int | None] = []
    for path in paths:
        path = Path(path)
        tags = flac_tags(path) if path.suffix.lower() == ".flac" else {}
        numbers.append(leading_number(tags.get("DISCNUMBER", "")))
    return numbers


def disc_and_track_order(paths: list[Path | str]) -> list[int]:
    """The album's own order for these files, as indices into `paths`.

    The same rule the playlist side follows (multidisc.order_by_disc_and_track)
    over the same two tags, read straight out of the files. It matters most
    where a two-disc set was downloaded into one folder: both discs number
    their tracks from one, so by filename they arrive interleaved -- and a
    disc break worked out from *that* order falls on nearly every track,
    which is exactly what a 34-track album offered as 26 discs turned out to
    be.
    """
    numbers = disc_numbers(paths)
    tracks = _track_numbers(paths)
    return order_by_disc_and_track(list(zip(numbers, tracks)))


def _track_numbers(paths: list[Path | str]) -> list[int | None]:
    result: list[int | None] = []
    for path in paths:
        path = Path(path)
        tags = flac_tags(path) if path.suffix.lower() == ".flac" else {}
        result.append(leading_number(tags.get("TRACKNUMBER", "")))
    return result


def disc_breaks(paths: list[Path | str]) -> list[int]:
    """Where these files say one disc ends and the next begins.

    Empty for a single-disc album and for anything untagged, so a caller
    can use it without asking whether it applies.

    **Assumes the files are already in disc order** -- see
    disc_and_track_order(), which is what puts them there. A break is simply
    where the number changes, so an interleaved folder produces one at
    almost every track."""
    return breaks_from_disc_numbers(disc_numbers(paths))


def total_bytes(paths: list[Path]) -> int:
    """Only ever shown to the user -- a folder's size says nothing about how
    long it plays, which is what actually has to fit on the disc, and that
    is not knowable until foobar has read the files."""
    total = 0
    for path in paths:
        try:
            total += path.stat().st_size
        except OSError:
            continue
    return total
