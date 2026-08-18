"""The picture inside a FLAC file.

The last resort for cover art, behind the iTunes search. Two kinds of test
here and both matter: hand-built blocks pin down the parsing (including the
malformed cases, which a real encoder will never produce), and one test runs
the **bundled flac.exe** and reads back what it actually wrote -- because
the whole point of this module is understanding a real file, and a fixture
written from the specification can agree with itself while disagreeing with
the encoder.
"""

from __future__ import annotations

import struct
import subprocess

import pytest

from mdtools import cdrip, embedded_cover


def _picture_block(data: bytes, picture_type: int = 3, mime: bytes = b"image/png") -> bytes:
    """A PICTURE block body, as the format specifies it: each variable part
    preceded by its big-endian uint32 length."""
    description = b""
    return b"".join(
        [
            struct.pack(">I", picture_type),
            struct.pack(">I", len(mime)),
            mime,
            struct.pack(">I", len(description)),
            description,
            struct.pack(">IIII", 100, 100, 24, 0),  # width, height, depth, colours
            struct.pack(">I", len(data)),
            data,
        ]
    )


def _flac(*blocks: tuple[int, bytes]) -> bytes:
    """A file that is nothing but a header and metadata blocks -- enough for
    a parser that never looks at the audio."""
    out = [b"fLaC"]
    for index, (block_type, body) in enumerate(blocks):
        last = 0x80 if index == len(blocks) - 1 else 0
        out.append(bytes([last | block_type]) + len(body).to_bytes(3, "big"))
        out.append(body)
    return b"".join(out)


def _write(tmp_path, name: str, data: bytes):
    path = tmp_path / name
    path.write_bytes(data)
    return path


def _vorbis_comment_block(comments: dict[str, str], vendor: bytes = b"test vendor") -> bytes:
    """A VORBIS_COMMENT block body -- unlike PICTURE's, every length here
    is little-endian (Ogg Vorbis's own comment format, carried as-is
    inside FLAC's otherwise big-endian metadata blocks)."""
    out = [struct.pack("<I", len(vendor)), vendor, struct.pack("<I", len(comments))]
    for key, value in comments.items():
        entry = f"{key}={value}".encode("utf-8")
        out.append(struct.pack("<I", len(entry)))
        out.append(entry)
    return b"".join(out)


# --- reading the block ------------------------------------------------


def test_a_front_cover_is_found(tmp_path):
    path = _write(tmp_path, "a.flac", _flac((6, _picture_block(b"IMAGEBYTES"))))
    assert embedded_cover.cover_from_file(path) == b"IMAGEBYTES"


def test_the_front_cover_wins_over_a_back_cover(tmp_path):
    """A file can hold several. Type 3 is the front, and the front is what a
    label is built around."""
    path = _write(
        tmp_path,
        "a.flac",
        _flac((6, _picture_block(b"BACK", picture_type=4)), (6, _picture_block(b"FRONT", picture_type=3))),
    )
    assert embedded_cover.cover_from_file(path) == b"FRONT"


def test_a_picture_of_no_stated_kind_is_still_used(tmp_path):
    path = _write(tmp_path, "a.flac", _flac((6, _picture_block(b"SOMETHING", picture_type=0))))
    assert embedded_cover.cover_from_file(path) == b"SOMETHING"


def test_a_32x32_file_icon_is_not_a_cover(tmp_path):
    """Types 1 and 2 are the little icons some taggers attach. Printing one
    on a J-card would be worse than printing nothing."""
    path = _write(tmp_path, "a.flac", _flac((6, _picture_block(b"ICON", picture_type=1))))
    assert embedded_cover.cover_from_file(path) is None


def test_picture_blocks_are_found_after_other_blocks(tmp_path):
    """STREAMINFO always comes first, and a real file has several more."""
    path = _write(
        tmp_path,
        "a.flac",
        _flac((0, b"\x00" * 34), (4, b"vorbis comment goes here"), (6, _picture_block(b"LATE"))),
    )
    assert embedded_cover.cover_from_file(path) == b"LATE"


def test_a_file_with_no_picture_says_so(tmp_path):
    path = _write(tmp_path, "a.flac", _flac((0, b"\x00" * 34)))
    assert embedded_cover.cover_from_file(path) is None


# --- the cases a real encoder never produces --------------------------


def test_something_that_is_not_a_flac_file_is_not_an_error(tmp_path):
    assert embedded_cover.cover_from_file(_write(tmp_path, "a.flac", b"ID3\x03nonsense")) is None


def test_an_empty_file_is_not_an_error(tmp_path):
    assert embedded_cover.cover_from_file(_write(tmp_path, "a.flac", b"")) is None


def test_a_truncated_picture_block_is_not_an_error(tmp_path):
    body = _picture_block(b"IMAGEBYTES")[:20]
    assert embedded_cover.cover_from_file(_write(tmp_path, "a.flac", _flac((6, body)))) is None


def test_a_block_claiming_more_data_than_it_holds_is_refused(tmp_path):
    """A length field is just four bytes off a disk -- it does not have to
    be true."""
    body = _picture_block(b"SHORT")[:-3]
    assert embedded_cover.cover_from_file(_write(tmp_path, "a.flac", _flac((6, body)))) is None


def test_a_file_that_is_not_there_is_not_an_error(tmp_path):
    assert embedded_cover.cover_from_file(tmp_path / "absent.flac") is None


def test_only_flac_is_read(tmp_path):
    """ID3's APIC frame is a messier format and is not attempted rather than
    attempted badly -- an MP3 simply reports nothing."""
    path = _write(tmp_path, "a.mp3", _flac((6, _picture_block(b"IMAGEBYTES"))))
    assert embedded_cover.cover_from_file(path) is None


# --- across a folder --------------------------------------------------


def test_the_first_cover_in_the_album_is_the_one_used(tmp_path):
    plain = _write(tmp_path, "01.flac", _flac((0, b"\x00" * 34)))
    with_art = _write(tmp_path, "02.flac", _flac((6, _picture_block(b"SLEEVE"))))
    later = _write(tmp_path, "03.flac", _flac((6, _picture_block(b"OTHER"))))

    assert embedded_cover.cover_from_files([plain, with_art, later]) == b"SLEEVE"


def test_an_album_with_no_art_anywhere_reports_nothing(tmp_path):
    files = [_write(tmp_path, f"{n}.flac", _flac((0, b"\x00" * 34))) for n in range(3)]
    assert embedded_cover.cover_from_files(files) is None


def test_no_files_at_all_is_not_an_error():
    assert embedded_cover.cover_from_files([]) is None


# --- tags (VORBIS_COMMENT) ---------------------------------------------


def test_album_and_artist_tags_are_read(tmp_path):
    body = _vorbis_comment_block({"ALBUM": "Lost Souls", "ARTIST": "Caskets"})
    path = _write(tmp_path, "a.flac", _flac((4, body)))

    assert embedded_cover.flac_tags(path) == {"ALBUM": "Lost Souls", "ARTIST": "Caskets"}


def test_tag_field_names_are_upper_cased_on_the_way_in(tmp_path):
    """Vorbis comment field names are case-insensitive by spec -- a real
    encoder is not guaranteed to write them upper-case."""
    body = _vorbis_comment_block({"Album": "Unleashed"})
    path = _write(tmp_path, "a.flac", _flac((4, body)))

    assert embedded_cover.flac_tags(path) == {"ALBUM": "Unleashed"}


def test_a_value_containing_an_equals_sign_keeps_the_rest_after_the_first(tmp_path):
    body = _vorbis_comment_block({"ALBUM": "Him = Her"})
    path = _write(tmp_path, "a.flac", _flac((4, body)))

    assert embedded_cover.flac_tags(path) == {"ALBUM": "Him = Her"}


def test_a_file_with_no_vorbis_comment_block_reports_no_tags(tmp_path):
    path = _write(tmp_path, "a.flac", _flac((6, _picture_block(b"IMAGEBYTES"))))
    assert embedded_cover.flac_tags(path) == {}


def test_content_that_is_not_actually_flac_reports_no_tags(tmp_path):
    """flac_tags(), like flac_pictures(), reads the file's own magic bytes
    rather than trusting its extension -- album_sort.py is what checks the
    extension before ever calling this, same layering as cover_from_file()
    does for flac_pictures()."""
    path = _write(tmp_path, "a.flac", b"ID3\x03nonsense")
    assert embedded_cover.flac_tags(path) == {}


def test_a_truncated_vorbis_comment_block_is_not_an_error(tmp_path):
    body = _vorbis_comment_block({"ALBUM": "Lost Souls", "ARTIST": "Caskets"})[:10]
    path = _write(tmp_path, "a.flac", _flac((4, body)))

    assert embedded_cover.flac_tags(path) == {}


def test_tags_are_found_after_other_blocks(tmp_path):
    body = _vorbis_comment_block({"ALBUM": "Lost Souls"})
    path = _write(tmp_path, "a.flac", _flac((6, _picture_block(b"IMAGEBYTES")), (4, body)))

    assert embedded_cover.flac_tags(path) == {"ALBUM": "Lost Souls"}


def test_reading_tags_does_not_disturb_reading_pictures_from_the_same_file(tmp_path):
    """Both walk the same block structure via the shared _iter_flac_blocks
    -- a regression here would likely mean one broke the other."""
    picture_body = _picture_block(b"SLEEVE")
    tag_body = _vorbis_comment_block({"ALBUM": "Lost Souls"})
    path = _write(tmp_path, "a.flac", _flac((6, picture_body), (4, tag_body)))

    assert embedded_cover.cover_from_file(path) == b"SLEEVE"
    assert embedded_cover.flac_tags(path) == {"ALBUM": "Lost Souls"}


# --- against the real encoder -----------------------------------------


@pytest.mark.skipif(cdrip.find_tool("flac") is None, reason="the bundled flac.exe is not present")
def test_a_cover_embedded_by_the_bundled_encoder_reads_back_out(tmp_path):
    """The one test here that could disagree with the specification: a
    fixture written from the spec can agree with itself perfectly and still
    misread what flac.exe actually writes."""
    from PySide6.QtCore import QBuffer
    from PySide6.QtGui import QColor, QImage

    image = QImage(8, 8, QImage.Format.Format_ARGB32)
    image.fill(QColor("red"))
    buffer = QBuffer()
    buffer.open(QBuffer.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    art = tmp_path / "cover.png"
    art.write_bytes(bytes(buffer.data()))

    # A second of silence is enough to encode; the audio is irrelevant here.
    wav = tmp_path / "track.wav"
    frames = 44100
    pcm = b"\x00\x00\x00\x00" * frames
    wav.write_bytes(
        b"RIFF"
        + (36 + len(pcm)).to_bytes(4, "little")
        + b"WAVEfmt "
        + (16).to_bytes(4, "little")
        + (1).to_bytes(2, "little")
        + (2).to_bytes(2, "little")
        + (44100).to_bytes(4, "little")
        + (44100 * 4).to_bytes(4, "little")
        + (4).to_bytes(2, "little")
        + (16).to_bytes(2, "little")
        + b"data"
        + len(pcm).to_bytes(4, "little")
        + pcm
    )

    flac_path = tmp_path / "track.flac"
    completed = subprocess.run(
        [
            cdrip.find_tool("flac"),
            "-s",
            "-f",
            f"--picture={art}",
            "-o",
            str(flac_path),
            str(wav),
        ],
        capture_output=True,
        text=True,
        errors="replace",
    )
    assert completed.returncode == 0, completed.stderr

    assert embedded_cover.cover_from_file(flac_path) == art.read_bytes()


@pytest.mark.skipif(cdrip.find_tool("flac") is None, reason="the bundled flac.exe is not present")
def test_tags_embedded_by_the_bundled_encoder_read_back_out(tmp_path):
    """The little-endian-lengths detail is exactly the kind of thing a
    fixture built from the specification could get right while still
    disagreeing with what a real encoder produces -- this is the test that
    would catch that."""
    wav = tmp_path / "track.wav"
    frames = 44100
    pcm = b"\x00\x00\x00\x00" * frames
    wav.write_bytes(
        b"RIFF"
        + (36 + len(pcm)).to_bytes(4, "little")
        + b"WAVEfmt "
        + (16).to_bytes(4, "little")
        + (1).to_bytes(2, "little")
        + (2).to_bytes(2, "little")
        + (44100).to_bytes(4, "little")
        + (44100 * 4).to_bytes(4, "little")
        + (4).to_bytes(2, "little")
        + (16).to_bytes(2, "little")
        + b"data"
        + len(pcm).to_bytes(4, "little")
        + pcm
    )

    flac_path = tmp_path / "track.flac"
    completed = subprocess.run(
        [
            cdrip.find_tool("flac"),
            "-s",
            "-f",
            "--tag=ALBUM=Lost Souls",
            "--tag=ARTIST=Caskets",
            "-o",
            str(flac_path),
            str(wav),
        ],
        capture_output=True,
        text=True,
        errors="replace",
    )
    assert completed.returncode == 0, completed.stderr

    tags = embedded_cover.flac_tags(flac_path)
    assert tags["ALBUM"] == "Lost Souls"
    assert tags["ARTIST"] == "Caskets"
