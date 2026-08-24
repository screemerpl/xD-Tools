"""A track list read off files directly, with no external player involved.

This is the metadata half of retiring foobar2000: `PlaylistItem` and the
functions below used to live in `foobar.py`, reading their fields out of
Beefweb's `%columns%`. They never actually depended on foobar2000 being
there -- `audio_folder.py` was already building the exact same records by
reading tags with `mutagen` for the burn/"Import from Folder" paths, which
foobar2000 was never in the loop for. `playlist_items_from_paths()`
generalises that reading (previously `audio_folder._playlist_item_from_file`,
called once per file) into the one place every recording source -- CD rip,
folder record, and a running-order table the user reordered by hand --
now gets its `PlaylistItem`s from.

No Qt here, matching cdrip.py/decode.py/mdrem.py's own "plain module,
testable without a QApplication" rule.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import mutagen

from mdtools.multidisc import breaks_from_disc_numbers, leading_number, order_by_disc_and_track
from mdtools.project import ProjectMetadata, Track, apply_compilation_naming


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

    def display_title(self) -> str:
        """The title to record, falling back to the filename.

        A folder of untagged files is precisely the case Record Folder
        exists to handle, and a disc full of blank track names is not a
        failure worth risking on tags nobody wrote. Falls back to the
        empty string when there is no path either, which is what it was
        before."""
        if self.title.strip():
            return self.title
        stem = Path(self.path).stem if self.path else ""
        return stem or self.title


def playlist_items_from_paths(paths: list[Path | str]) -> list[PlaylistItem]:
    """One file read as a `PlaylistItem`, for every path given -- the same
    fields foobar2000's Beefweb columns used to fill, read directly off
    the file instead via `mutagen`'s "easy" tag interface, which reads
    whatever format it recognises (FLAC, WAV's own RIFF INFO chunk, MP3,
    and more) under one common set of field names."""
    return [_playlist_item_from_file(Path(path), number) for number, path in enumerate(paths, start=1)]


def _playlist_item_from_file(path: Path, track_number: int) -> PlaylistItem:
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


def sort_by_disc_and_track(items: list[PlaylistItem]) -> list[PlaylistItem]:
    """The album's own order: disc first, then track.

    A folder or playlist holding a double album routinely arrives with the
    two discs interleaved, because both discs number their tracks from
    one and whatever assembled the list sorted by filename. The files
    themselves know better, so this asks them.

    Two rules keep it from doing harm where it has nothing to go on:
    - **A list where nothing carries either number is returned untouched.**
      No tags means no opinion, and the order somebody put the list in by
      hand is a better answer than one invented here.
    - **Anything missing a track number sinks to the end of its disc rather
      than to the front**, and ties keep the order they arrived in (the sort
      is stable), so an untagged odd file out never displaces the album.

    A missing disc number counts as disc 1, which is what a single-disc
    album's files look like."""
    numbers = [(leading_number(item.disc_number), leading_number(item.track_number)) for item in items]
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
    # against the whole list. A half-tagged album is still that album --
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


def album_year(items: list[PlaylistItem]) -> int | None:
    """The tagged date is whatever the tag holds -- often a bare year, but
    also "2024-06-14" or worse, so only the leading four digits are used."""
    for item in items:
        text = item.date.strip()
        if len(text) >= 4 and text[:4].isdigit():
            return int(text[:4])
    return None


def metadata_from_playlist(items: list[PlaylistItem]) -> ProjectMetadata:
    """A track list as project metadata.

    A track list is not necessarily an album, though -- it is just as
    likely to be a mixtape somebody assembled -- so the result is passed
    through the compilation check before being handed back."""
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
