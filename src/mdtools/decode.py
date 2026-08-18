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
- Anything at a different rate or bit depth -- a 48 kHz / 24-bit download
  is the normal case, not an exotic one -- goes through **SoX**, which is
  the only piece here that can resample. `_ensure_pcm()` is the single
  place that decides, so nothing above this module knows which tool ran.

**SoX rather than ffmpeg, and the reason was measured rather than
assumed.** ffmpeg was the first choice (it would have brought MP3, M4A and
Opus with it), but the Windows builds are 128 MB of DLLs -- `avcodec`
alone is 68 MB, past the size GitHub warns about, and every clone would
carry it. SoX does the one thing actually needed, resampling, in 6 MB.
What it costs is breadth: this build reads FLAC, WAV, Ogg Vorbis, WavPack
and AIFF, and **not MP3** -- the format is in its list, but decoding one
needs `libmad-0.dll` loaded at runtime and the official package does not
ship it (verified by running it: writing an MP3 fails with "Unable to load
LAME encoder library"). Dropping a 32-bit `libmad-0.dll` beside `sox.exe`
would enable it without any change here.

**Without a resampler, a file that is not already 44.1 kHz / 16-bit /
stereo is reported rather than converted**, and that is deliberate rather
than a limitation to route around: `flac.exe` cannot resample, so the
alternative would be writing something onto a CD that is not what the user
chose -- exactly the class of mistake this module exists to prevent. With
SoX present the same file is converted, and the plan says so before
anything is written (see cdburn.RESAMPLED).

No Qt here: this is a plain module, like cdrip.py and mdrem.py, so all of
it is testable without a QApplication.
"""

from __future__ import annotations

import re
import shutil
import struct
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path

import sys

from mdtools import cdrip
from mdtools.cdrip import find_tool, flac_path
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

# Read only when SoX is available, and only what the bundled build can
# actually open without extra libraries -- MP3 is deliberately absent, see
# this module's header.
CONVERTIBLE_SUFFIXES = (".ogg", ".oga", ".wv", ".aiff", ".aif", ".au")

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


def sox_path() -> str | None:
    """The bundled SoX if there is one, otherwise whatever is on PATH.

    **In a folder of its own**, unlike every other bundled tool, and that
    is not tidiness: the official SoX package is 32-bit, while cd-paranoia
    and flac are 64-bit builds from MSYS2. Unpacking it beside them
    overwrote `libwinpthread-1.dll` with a 32-bit copy of the same name --
    which happened not to break cd-paranoia, purely because it does not
    import that DLL directly. `zlib1.dll` and `libpng16-16.dll` are just as
    common, and the next tool added might not be so lucky. One folder per
    architecture is the fix; Windows resolves an exe's DLLs from its own
    directory first, so each set stays with its own binary.
    """
    bundled = cdrip.tools_dir() / "sox" / ("sox.exe" if sys.platform == "win32" else "sox")
    if bundled.is_file():
        return str(bundled)
    return find_tool("sox")


def can_convert() -> bool:
    """Whether anything can be resampled at all, i.e. whether SoX is there.
    The burn plan asks this before deciding that a 48 kHz album is a
    problem rather than a conversion."""
    return sox_path() is not None


def is_supported(path: Path | str) -> bool:
    suffix = Path(path).suffix.lower()
    if suffix in NATIVE_SUFFIXES:
        return True
    return suffix in CONVERTIBLE_SUFFIXES and can_convert()


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
    if suffix in CONVERTIBLE_SUFFIXES and can_convert():
        return sox_properties(path)
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


_INFO_FIELD = re.compile(r"^(Channels|Sample Rate|Precision|Duration)\s*:\s*(.+)$", re.MULTILINE)
_SAMPLES = re.compile(r"=\s*(\d+)\s+samples")
_PRECISION = re.compile(r"(\d+)")


def sox_properties(path: Path | str, *, run=subprocess.run) -> AudioProperties:
    """What SoX says a file is, from its own `--i` header.

    Only used for formats this module cannot read itself; WAV and FLAC are
    parsed directly, which needs no subprocess at all. The duration matters
    most -- it decides how much of the disc a track takes -- and SoX gives
    it as an exact sample count rather than a rounded time, which is why
    that is what gets read.
    """
    tool = sox_path()
    if tool is None:
        raise DecodeError("SoX is not available")
    result = run([tool, "--i", str(path)], capture_output=True, text=True)
    text = (result.stdout or "") + (result.stderr or "")

    fields = {name: value.strip() for name, value in _INFO_FIELD.findall(text)}
    samples = _SAMPLES.search(fields.get("Duration", ""))
    if "Sample Rate" not in fields or samples is None:
        raise DecodeError(f"SoX could not read {Path(path).name}: {_first_line(result.stderr)}")

    precision = _PRECISION.search(fields.get("Precision", "16"))
    return AudioProperties(
        sample_rate=int(fields["Sample Rate"]),
        bits_per_sample=int(precision.group(1)) if precision else 16,
        channels=int(fields.get("Channels", "2")),
        frames=int(samples.group(1)),
    )


def decode_command(tool: str, source: Path, destination: Path) -> list[str]:
    """flac.exe decoding one file to WAV. `-f` overwrites a leftover from an
    earlier, failed attempt rather than stopping to ask about it; `-s` keeps
    it from drawing a progress bar nobody is watching."""
    return [tool, "-d", "-f", "-s", "-o", str(destination), str(source)]


def convert_command(tool: str, source: Path, destination: Path) -> list[str]:
    """SoX turning anything it can read into Red Book PCM.

    `-b 16 -c 2` on the *output* set the depth and channel count; `rate -v`
    is the resampler (very high quality, which is the whole reason for
    having SoX here at all), and `dither` is what makes reducing 24 bits to
    16 sound like the recording rather than like quantisation noise. Effects
    come after the output file, which is SoX's own argument order and not a
    mistake.
    """
    return [
        tool,
        str(source),
        "-b",
        str(RED_BOOK_BITS),
        "-c",
        str(RED_BOOK_CHANNELS),
        str(destination),
        "rate",
        "-v",
        str(RED_BOOK_RATE),
        "dither",
    ]


def to_wav(source: Path | str, destination: Path | str, *, run=subprocess.run) -> Path:
    """`source` as a Red Book WAV at `destination`.

    A WAV that is already Red Book is copied rather than run through
    anything: there is nothing to convert, and re-encoding audio that is
    already exactly right can only lose to it. Anything else goes through
    SoX, which resamples -- and without SoX it is refused outright rather
    than written to a disc at the wrong rate.
    """
    source, destination = Path(source), Path(destination)
    properties = analyze(source)
    if not properties.is_red_book and not can_convert():
        raise DecodeError(
            f"{source.name} is {properties.sample_rate} Hz / {properties.bits_per_sample}-bit / "
            f"{properties.channels}ch, and a CD needs {RED_BOOK_RATE} / {RED_BOOK_BITS} / "
            f"{RED_BOOK_CHANNELS}. SoX is missing, so it cannot be converted."
        )
    return _ensure_pcm(source, destination, run=run)


def _ensure_pcm(source: Path, destination: Path, *, run) -> Path:
    """The one place that turns a supported file into a WAV on disk.

    A bundled ffmpeg, if this ever grows one, belongs here and nowhere
    else: every caller above already thinks in terms of "a path to Red Book
    WAV", and none of them would need changing.
    """
    suffix = source.suffix.lower()
    properties = analyze(source)

    if not properties.is_red_book or suffix not in NATIVE_SUFFIXES:
        tool = sox_path()
        if tool is None:
            raise DecodeError(f"{source.name} needs SoX to be converted, and it was not found")
        result = run(convert_command(tool, source, destination), capture_output=True, text=True)
        if result.returncode != 0:
            raise DecodeError(f"converting {source.name} failed: {_first_line(result.stderr)}")
        if not destination.exists():
            raise DecodeError(f"converting {source.name} produced no file")
        return destination

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
