"""Recording > "Record Folder to MiniDisc..." -- finding an album that is
already sitting on disk as files.

The third source of a recording, after a CD and whatever foobar2000 happens
to have open. Its job is the same as cdrip.py's: put the right files, in the
right order, into foobar's playlist, and then get out of the way so the
existing record flow can do the rest.

Two things it deliberately does not do:

**It never reads a tag.** There is no tag library in this project and adding
one for this would be a dependency for something foobar2000 already does
perfectly -- the files go into the playlist first, and every title, artist,
album and length is then read back out of foobar through Beefweb. So this
module only ever decides *which* files and in *what order*.

**It never renames, moves or rewrites anything.** These are the user's own
music files, not the disposable rip folder cdrip.py owns.

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
from pathlib import Path

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

# "Artist - Album", the shape MDTools itself proposes when saving a project
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

    Note this is the inverse of the filename MDTools proposes for a project
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
