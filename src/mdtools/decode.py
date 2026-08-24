"""What is in an audio file, and how to get Red Book PCM out of it.

A CD-R holds 44.1 kHz, 16-bit, stereo PCM and nothing else, so before a
single sector is written every source file has to be measured against that
-- which is why reading a file's properties is separate from decoding it.
A rate or depth mismatch is then something the burn dialog can show per
track, before the disc is committed, rather than a failure discovered by a
burner half way through a disc it cannot un-burn.

**Only WAV and FLAC, mono or stereo, at any rate or bit depth -- and
getting Red Book PCM out of either needs no external tool at all any
more.** An already-Red-Book FLAC decodes losslessly through
`audio_engine.decode_flac_to_wav()`; anything else goes through
`audio_engine.resample_and_dither_to_red_book()` (soxr for the rate,
the project's own verified noise-shaped dither for the bit depth). Both
are backed by `soundfile` (libsndfile), which decodes FLAC directly at
any bit depth, including 24-bit -- where `flac.exe` used to be needed for
the decode half and SoX for the resample+dither half of the very same
file. `_ensure_pcm()` is the single place that decides.

**Explicit scope decision, not a limitation being routed around: nothing
except WAV and FLAC is supported, and a source with more than two
channels (real-world surround audio) is refused rather than mixed down.**
Earlier versions of this module used SoX for Ogg Vorbis, WavPack, AIFF
and AU, and for channel mixing -- SoX has been dropped entirely rather
than kept around for those, since none of them are formats this project
actually needs to support. A future MP3/Ogg Vorbis *decode* is expected
to go through `soundfile`/libsndfile directly (confirmed to read both),
not by reviving SoX.

No Qt here: this is a plain module, like cdrip.py and mdrem.py, so all of
it is testable without a QApplication.
"""

from __future__ import annotations

import shutil
import struct
import wave
from dataclasses import dataclass
from pathlib import Path

from mdtools.embedded_cover import iter_flac_blocks

# Red Book audio, as fixed as physical constants get: 44.1 kHz, 16-bit,
# stereo, and 75 sectors of 2352 bytes to the second.
RED_BOOK_RATE = 44100
RED_BOOK_BITS = 16
RED_BOOK_CHANNELS = 2
BYTES_PER_FRAME = 2352
FRAMES_PER_SECOND = 75

# Read without any help: stdlib for WAV, this project's own parser for
# FLAC's STREAMINFO.
NATIVE_SUFFIXES = (".wav", ".flac")

SUPPORTED_SUFFIXES = NATIVE_SUFFIXES  # kept: callers ask "can I read this?"

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
    return Path(path).suffix.lower() in NATIVE_SUFFIXES


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


def to_wav(source: Path | str, destination: Path | str) -> Path:
    """`source` as a Red Book WAV at `destination`.

    A WAV that is already Red Book is copied rather than run through
    anything: there is nothing to convert, and re-encoding audio that is
    already exactly right can only lose to it. Anything else -- any
    rate/bit-depth mismatch, mono or stereo -- goes through audio_engine,
    which needs no external tool at all. More than two channels is refused
    outright: see this module's own header for why that is a scope
    decision, not a limitation being routed around.
    """
    source, destination = Path(source), Path(destination)
    properties = analyze(source)
    if properties.channels > RED_BOOK_CHANNELS:
        raise DecodeError(
            f"{source.name} has {properties.channels} channels, and only mono and stereo are supported"
        )
    return _ensure_pcm(source, destination, properties)


def _ensure_pcm(source: Path, destination: Path, properties: AudioProperties) -> Path:
    """WAV or FLAC, mono or stereo -- handled entirely by audio_engine, with
    no external tool involved at all. Imported here rather than at module
    level: audio_engine.py itself imports this module for the RED_BOOK_*
    constants, so a module-level import here would be a straight import
    cycle (see cdrip.py's own identical note on encode_track())."""
    from mdtools import audio_engine

    suffix = source.suffix.lower()
    try:
        if properties.is_red_book:
            if suffix == ".wav":
                shutil.copyfile(source, destination)
            else:
                audio_engine.decode_flac_to_wav(source, destination)
        else:
            audio_engine.resample_and_dither_to_red_book(source, destination)
    except audio_engine.AudioEngineError as exc:
        raise DecodeError(str(exc)) from exc
    return destination
