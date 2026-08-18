"""What is in an audio file, and how to get Red Book PCM out of it.

A CD-R holds 44.1 kHz, 16-bit, stereo PCM and nothing else, so before a
single sector is written every source file has to be measured against that
-- which is why reading a file's properties is separate from decoding it.
A rate or depth mismatch is then something the burn dialog can show per
track, before the disc is committed, rather than a failure discovered by a
burner half way through a disc it cannot un-burn.

Only WAV and FLAC are read, and deliberately:

- WAV needs nothing at all (stdlib `wave`).
- FLAC is decoded by the `flac.exe` this project already bundles for
  ripping, so supporting it costs no new dependency and no new megabytes.
- Everything else (MP3, M4A, Opus) needs a decoder this project does not
  ship. `_ensure_pcm()` is the single place a bundled ffmpeg would slot in
  if that changes; nothing else here or above would need to know.

`flac.exe` cannot resample, so a 96 kHz or 24-bit file is *reported*, never
silently converted -- the fix belongs in whatever produced the file (or in
that future ffmpeg step), and quietly writing something onto a CD that is
not what the user chose is exactly the class of mistake this module exists
to prevent.

No Qt here: this is a plain module, like cdrip.py and mdrem.py, so all of
it is testable without a QApplication.
"""

from __future__ import annotations

import shutil
import struct
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path

from mdtools.cdrip import flac_path
from mdtools.embedded_cover import iter_flac_blocks

# Red Book audio, as fixed as physical constants get: 44.1 kHz, 16-bit,
# stereo, and 75 sectors of 2352 bytes to the second.
RED_BOOK_RATE = 44100
RED_BOOK_BITS = 16
RED_BOOK_CHANNELS = 2
BYTES_PER_FRAME = 2352
FRAMES_PER_SECOND = 75

SUPPORTED_SUFFIXES = (".wav", ".flac")

_STREAMINFO_BLOCK = 0
_STREAMINFO_BYTES = 34


class DecodeError(Exception):
    """A file that cannot be read, or cannot be turned into Red Book PCM."""


@dataclass(frozen=True)
class AudioProperties:
    """What a source file actually is, in the only four terms a CD cares
    about."""

    sample_rate: int
    bits_per_sample: int
    channels: int
    frames: int  # sample frames, not CD sectors

    @property
    def duration_seconds(self) -> float:
        if self.sample_rate <= 0:
            return 0.0
        return self.frames / self.sample_rate

    @property
    def is_red_book(self) -> bool:
        return (
            self.sample_rate == RED_BOOK_RATE
            and self.bits_per_sample == RED_BOOK_BITS
            and self.channels == RED_BOOK_CHANNELS
        )

    def mismatches(self) -> list[str]:
        """Which of the three Red Book properties this file does not meet,
        as bare field names.

        Deliberately not a sentence: the wording belongs to the dialog,
        which has to translate it, and this module has no Qt in it.
        """
        wrong = []
        if self.sample_rate != RED_BOOK_RATE:
            wrong.append("sample_rate")
        if self.bits_per_sample != RED_BOOK_BITS:
            wrong.append("bits_per_sample")
        if self.channels != RED_BOOK_CHANNELS:
            wrong.append("channels")
        return wrong


def is_supported(path: Path | str) -> bool:
    return Path(path).suffix.lower() in SUPPORTED_SUFFIXES


def analyze(path: Path | str) -> AudioProperties:
    """The file's own sample rate, depth, channel count and length.

    Raises DecodeError for anything unreadable or unsupported -- a burn
    plan that silently skipped a file it could not measure would produce a
    disc missing a track.
    """
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".wav":
        return wav_properties(path)
    if suffix == ".flac":
        return flac_properties(path)
    raise DecodeError(f"unsupported audio format: {path.suffix or path.name}")


def wav_properties(path: Path | str) -> AudioProperties:
    try:
        with wave.open(str(path), "rb") as handle:
            return AudioProperties(
                sample_rate=handle.getframerate(),
                bits_per_sample=handle.getsampwidth() * 8,
                channels=handle.getnchannels(),
                frames=handle.getnframes(),
            )
    except (OSError, wave.Error) as exc:
        raise DecodeError(f"could not read {Path(path).name}: {exc}") from exc


def flac_properties(path: Path | str) -> AudioProperties:
    """FLAC's STREAMINFO block, parsed directly.

    The same call already made for the MiniDisc disc id and for embedded
    cover art: a fixed-layout header frozen since 2007 is a smaller thing
    to own than a tag library. The bit packing is the part worth naming --
    sample rate (20 bits), channels - 1 (3), bits per sample - 1 (5) and
    total samples (36) share one 64-bit big-endian field with no byte
    boundaries between them, so it is read whole and shifted apart. Note
    this is big-endian, unlike the little-endian lengths inside the
    VORBIS_COMMENT block right next to it (see embedded_cover.flac_tags).
    """
    for _, body in iter_flac_blocks(path, {_STREAMINFO_BLOCK}, _STREAMINFO_BYTES):
        if len(body) < _STREAMINFO_BYTES:
            break
        # bytes 0..9 are min/max block and frame sizes, which say nothing
        # about the audio itself
        (packed,) = struct.unpack_from(">Q", body, 10)
        return AudioProperties(
            sample_rate=(packed >> 44) & 0xFFFFF,
            channels=((packed >> 41) & 0x07) + 1,
            bits_per_sample=((packed >> 36) & 0x1F) + 1,
            frames=packed & 0xFFFFFFFFF,
        )
    raise DecodeError(f"no FLAC stream info in {Path(path).name}")


def decode_command(tool: str, source: Path, destination: Path) -> list[str]:
    """flac.exe decoding one file to WAV. `-f` overwrites a leftover from an
    earlier, failed attempt rather than stopping to ask about it; `-s` keeps
    it from drawing a progress bar nobody is watching."""
    return [tool, "-d", "-f", "-s", "-o", str(destination), str(source)]


def to_wav(source: Path | str, destination: Path | str, *, run=subprocess.run) -> Path:
    """`source` as a Red Book WAV at `destination`.

    A WAV that is already Red Book is copied rather than run through
    anything: there is nothing to convert, and re-encoding audio that is
    already exactly right can only lose to it.
    """
    source, destination = Path(source), Path(destination)
    properties = analyze(source)
    if not properties.is_red_book:
        raise DecodeError(
            f"{source.name} is {properties.sample_rate} Hz / {properties.bits_per_sample}-bit / "
            f"{properties.channels}ch, and a CD needs {RED_BOOK_RATE} / {RED_BOOK_BITS} / {RED_BOOK_CHANNELS}"
        )
    return _ensure_pcm(source, destination, run=run)


def _ensure_pcm(source: Path, destination: Path, *, run) -> Path:
    """The one place that turns a supported file into a WAV on disk.

    A bundled ffmpeg, if this ever grows one, belongs here and nowhere
    else: every caller above already thinks in terms of "a path to Red Book
    WAV", and none of them would need changing.
    """
    suffix = source.suffix.lower()
    if suffix == ".wav":
        shutil.copyfile(source, destination)
        return destination

    if suffix == ".flac":
        tool = flac_path()
        if tool is None:
            raise DecodeError("the FLAC decoder is missing (bin/win64/flac.exe, or flac on PATH)")
        result = run(decode_command(tool, source, destination), capture_output=True, text=True)
        if result.returncode != 0:
            raise DecodeError(f"decoding {source.name} failed: {_first_line(result.stderr)}")
        if not destination.exists():
            raise DecodeError(f"decoding {source.name} produced no file")
        return destination

    raise DecodeError(f"unsupported audio format: {source.suffix or source.name}")


def _first_line(text: str | None) -> str:
    for line in (text or "").splitlines():
        line = line.strip()
        if line:
            return line
    return "no output"
