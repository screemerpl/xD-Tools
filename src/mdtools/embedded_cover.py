"""The picture -- and, as of album_sort.py's needs, the tags -- inside a
FLAC file.

The picture is a last resort for cover art, behind the iTunes search: a
folder of FLACs ripped from somebody's own CD collection routinely carries
the sleeve in the files themselves, and that sleeve is certainly the right
one for *this* release, where a search result is a guess about it.

It is nonetheless the fallback rather than the first choice, deliberately.
Embedded art is whatever the ripper happened to attach -- often a 300px
scan, sometimes a photograph of the disc, occasionally a logo -- while
iTunes returns a clean 600x600 of the front cover, which is what a printed
label wants. So: search first, open the file only if that came back with
nothing.

**No tag library.** Parsing FLAC's metadata blocks is a page of struct
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
from typing import Iterable, Iterator

# FLAC metadata block types.
_PICTURE_BLOCK = 6
_VORBIS_COMMENT_BLOCK = 4

# From the PICTURE block's own "picture type" field (it borrows the ID3v2
# APIC list). 3 is the front cover, which is what a label is built around;
# 1 and 2 are the 32x32 file icons, which are never worth printing.
FRONT_COVER = 3
_ICON_TYPES = (1, 2)

_MAGIC = b"fLaC"

# A sanity bound on a length read out of the file, so a corrupt block
# cannot ask for a gigabyte. No real cover art is anywhere near this.
_MAX_PICTURE_BYTES = 32 * 1024 * 1024

# Real tag data is at most a few KB; this is purely a corrupt-length
# backstop, same reasoning as _MAX_PICTURE_BYTES above.
_MAX_TAG_BYTES = 1024 * 1024


def _iter_flac_blocks(path: Path | str, wanted_types: set[int], max_bytes: int) -> Iterator[tuple[int, bytes]]:
    """Every metadata block whose type is in `wanted_types`, as (type, raw
    bytes) -- shared by flac_pictures() and flac_tags() so the actual
    binary walk (magic check, block header, length) exists exactly once.

    Anything not in `wanted_types` is skipped via seek, never read into
    memory; a *wanted* block longer than `max_bytes` is skipped the same
    way rather than read -- a corrupt length claiming a gigabyte should
    not try to allocate one.

    An unreadable, truncated, or non-FLAC file simply yields nothing --
    not an error, the same answer every caller here already treats a
    missing block as. A mid-file OSError still leaves whatever was already
    yielded intact in the caller (it ends the generator normally, it does
    not raise out of it)."""
    try:
        with open(path, "rb") as handle:
            if handle.read(4) != _MAGIC:
                return
            while True:
                header = handle.read(4)
                if len(header) < 4:
                    return
                is_last = bool(header[0] & 0x80)
                block_type = header[0] & 0x7F
                length = int.from_bytes(header[1:4], "big")
                if block_type in wanted_types and length <= max_bytes:
                    yield block_type, handle.read(length)
                else:
                    handle.seek(length, 1)
                if is_last:
                    return
    except OSError:
        return


def flac_pictures(path: Path | str) -> list[tuple[int, bytes]]:
    """Every PICTURE block in a FLAC file, as (picture type, bytes)."""
    found: list[tuple[int, bytes]] = []
    for _, body in _iter_flac_blocks(path, {_PICTURE_BLOCK}, _MAX_PICTURE_BYTES):
        picture = _parse_picture(body)
        if picture is not None:
            found.append(picture)
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


def flac_tags(path: Path | str) -> dict[str, str]:
    """The VORBIS_COMMENT block's fields, keyed upper-case (Vorbis comment
    field names are case-insensitive by spec -- ``Album``/``ALBUM``/``album``
    all mean the same tag). Empty if the file has no such block, or is not
    a FLAC at all.

    Used by album_sort.py to group a folder of downloaded tracks by their
    own ALBUM tag -- the same "read the file directly, no tag library"
    approach this module already takes for cover art."""
    for _, body in _iter_flac_blocks(path, {_VORBIS_COMMENT_BLOCK}, _MAX_TAG_BYTES):
        return _parse_vorbis_comments(body)
    return {}


def _parse_vorbis_comments(block: bytes) -> dict[str, str]:
    """A VORBIS_COMMENT block's fields.

    **Load-bearing detail, easy to get wrong by analogy with PICTURE's own
    big-endian shape**: every length *inside* this block is little-endian
    -- it is Ogg Vorbis's own comment format, embedded byte-for-byte inside
    an otherwise big-endian FLAC metadata block. Vendor string length +
    string, then a comment count, then each comment as a length-prefixed
    ``"FIELD=value"`` UTF-8 string -- all of those lengths are u32 LE."""
    tags: dict[str, str] = {}
    try:
        offset = 0
        (vendor_length,) = struct.unpack_from("<I", block, offset)
        offset += 4 + vendor_length
        (count,) = struct.unpack_from("<I", block, offset)
        offset += 4
        for _ in range(count):
            (length,) = struct.unpack_from("<I", block, offset)
            offset += 4
            comment = block[offset : offset + length].decode("utf-8", errors="replace")
            offset += length
            key, sep, value = comment.partition("=")
            if sep:
                tags[key.strip().upper()] = value
    except struct.error:
        pass
    return tags


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
