"""The picture inside an audio file.

A last resort for cover art, behind the iTunes search: a folder of FLACs
ripped from somebody's own CD collection routinely carries the sleeve in
the files themselves, and that sleeve is certainly the right one for *this*
release, where a search result is a guess about it.

It is nonetheless the fallback rather than the first choice, deliberately.
Embedded art is whatever the ripper happened to attach -- often a 300px
scan, sometimes a photograph of the disc, occasionally a logo -- while
iTunes returns a clean 600x600 of the front cover, which is what a printed
label wants. So: search first, open the file only if that came back with
nothing.

**No tag library.** Parsing FLAC's PICTURE block is a page of struct
unpacking against a format that has not changed since 2007, which is a far
smaller thing to own than a dependency -- the same call already made for
the MusicBrainz disc id and for cdparanoia's output. Only FLAC is read:
ID3v2's APIC frame is a genuinely messier format (three frame layouts,
unsynchronisation, optional compression) and is not attempted rather than
attempted badly.

No Qt in here, matching audio_folder.py and cdrip.py -- and no image
decoding either. What comes out is the bytes as they were stored; whoever
displays them finds out whether they can be drawn (see
panels/cover_preview.py).
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Iterable

# FLAC metadata block types.
_PICTURE_BLOCK = 6

# From the PICTURE block's own "picture type" field (it borrows the ID3v2
# APIC list). 3 is the front cover, which is what a label is built around;
# 1 and 2 are the 32x32 file icons, which are never worth printing.
FRONT_COVER = 3
_ICON_TYPES = (1, 2)

_MAGIC = b"fLaC"

# A sanity bound on a length read out of the file, so a corrupt block
# cannot ask for a gigabyte. No real cover art is anywhere near this.
_MAX_PICTURE_BYTES = 32 * 1024 * 1024


def flac_pictures(path: Path | str) -> list[tuple[int, bytes]]:
    """Every PICTURE block in a FLAC file, as (picture type, bytes).

    An unreadable, truncated or non-FLAC file is not an error worth
    reporting -- it simply has no picture in it, which is the same answer
    the caller acts on either way."""
    found: list[tuple[int, bytes]] = []
    try:
        with open(path, "rb") as handle:
            if handle.read(4) != _MAGIC:
                return []
            while True:
                header = handle.read(4)
                if len(header) < 4:
                    return found
                is_last = bool(header[0] & 0x80)
                block_type = header[0] & 0x7F
                length = int.from_bytes(header[1:4], "big")
                if block_type == _PICTURE_BLOCK and length <= _MAX_PICTURE_BYTES:
                    picture = _parse_picture(handle.read(length))
                    if picture is not None:
                        found.append(picture)
                else:
                    handle.seek(length, 1)
                if is_last:
                    return found
    except OSError:
        return found


def _parse_picture(block: bytes) -> tuple[int, bytes] | None:
    """One PICTURE block: type, MIME, description, four dimensions, data --
    each length a big-endian uint32 in front of what it measures."""
    try:
        offset = 0
        (picture_type,) = struct.unpack_from(">I", block, offset)
        offset += 4
        for _ in range(2):  # the MIME string, then the description
            (length,) = struct.unpack_from(">I", block, offset)
            offset += 4 + length
        offset += 16  # width, height, colour depth, number of colours
        (data_length,) = struct.unpack_from(">I", block, offset)
        offset += 4
    except struct.error:
        return None
    data = block[offset : offset + data_length]
    if len(data) != data_length or not data:
        return None
    return picture_type, data


def cover_from_file(path: Path | str) -> bytes | None:
    """The best picture in one file: the front cover if it says which one
    that is, otherwise the first that is not a file icon."""
    if Path(path).suffix.lower() != ".flac":
        return None
    pictures = flac_pictures(path)
    for picture_type, data in pictures:
        if picture_type == FRONT_COVER:
            return data
    for picture_type, data in pictures:
        if picture_type not in _ICON_TYPES:
            return data
    return None


def cover_from_files(paths: Iterable[Path | str]) -> bytes | None:
    """The first cover found across these files.

    Stops at the first hit rather than comparing them: an album's files
    normally carry the same picture, and where they differ there is nothing
    here that could tell which is better. Reading a file that has none
    costs a few block headers, not the audio."""
    for path in paths:
        data = cover_from_file(path)
        if data:
            return data
    return None
