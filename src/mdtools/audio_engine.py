"""xD-Tools' own audio engine: FLAC decode/encode, resampling, dithering
and real-time playback -- replacing flac.exe, SoX and foobar2000's own
playback role with pyflac + mutagen + soxr + a verified noise-shaped
dither + sounddevice, respectively.

This module is the *foundation* only -- decode.py's SoX-backed conversion
and cdrip.py's flac.exe encode still run as they always have, and every
recording dialog still drives foobar2000. Nothing here is wired into any
of those yet; this is the self-contained engine those call sites will be
switched over to, one at a time, once each swap has its own test coverage
in place. No Qt here either, matching cdrip.py/decode.py/mdrem.py's own
"plain module, testable without a QApplication" rule.

Three design decisions came out of real measurement, not assumption --
worth keeping in mind before touching any of this:

**FLAC only, for now.** pyFLAC covers FLAC encode/decode; WAV needs
nothing beyond `soundfile` (already a dependency of pyflac's own file
I/O). Anything else (MP3 especially) is deliberately out of scope --
mirrors decode.py's own "SoX cannot read MP3, and that's fine" stance,
just drawn one format earlier. A file this can't handle should be
reported, never silently misread.

**pyFLAC has no tag support at all** ("FLAC metadata handling is not
implemented", per its own docs) -- confirmed directly, not assumed.
`encode_wav_to_flac()` therefore always writes tags as a second pass
through `mutagen`, exactly the way cdrip.py's own `encode_command()`
passes `--tag=` arguments to flac.exe today; this is what makes the swap
a drop-in for that call site later.

**The noise-shaped dither's inner loop is JIT-compiled with numba, not
plain Python, and not a "vectorise the recursion away" trick either --
both alternatives were tried and rejected by measurement.** A pure Python
per-sample loop measured ~0.5M samples/sec, which is ~6.5 minutes of
dithering alone for one 40-minute stereo album -- not viable. The
tempting fix, reformulating the recursive error-feedback filter as
`diff(round(cumsum(...)))` (a genuine, verified-bit-exact identity for
short buffers), turns out to be numerically unsafe at real album lengths:
the repeated cumulative sum grows unboundedly, and at 10M samples an
order-3 shaper's running sum reaches ~3e20, where float64's resolution
(~7.6e4) is nowhere near fine enough to round correctly any more --
confirmed by measuring the actual float64 resolution at that magnitude,
not assumed. The recursive, bounded-state loop (each step only ever
depends on `order` recent, small error values, never an unbounded running
sum) has no such ceiling regardless of length, which is exactly why it's
the correct algorithm to keep -- it just needed compiling, not
rewriting. `numba.njit(cache=True)` gets that same bounded-state loop to
~130M samples/sec (~1.6s for a 40-minute stereo album), verified bit-exact
against the plain Python loop first.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import comb
from pathlib import Path
from typing import Callable

import numpy as np
import soxr

from mdtools.decode import DecodeError, RED_BOOK_CHANNELS, RED_BOOK_RATE

try:
    import pyflac
except ImportError:  # pragma: no cover -- exercised only if the dependency is genuinely missing
    pyflac = None

try:
    import mutagen.flac
except ImportError:  # pragma: no cover
    mutagen = None

try:
    import sounddevice as sd
except ImportError:  # pragma: no cover -- e.g. no PortAudio backend on a given machine
    sd = None

import numba


class AudioEngineError(Exception):
    """A decode/encode/playback operation this engine cannot carry out --
    a missing dependency, an unreadable file, or no matching output
    device. Deliberately a separate class from decode.DecodeError (which
    stays what SoX-backed conversion raises until that call site is
    actually switched over): merging them now would make a caller unable
    to tell "SoX is missing" from "pyflac is missing" during the period
    where both paths still exist side by side."""


# --- decoding / encoding (pyflac + mutagen) -------------------------------


def decode_flac_to_wav(source: Path | str, destination: Path | str) -> None:
    """pyflac's own equivalent of flac.exe's `-d -f -s -o dest src` decode
    (see decode.py's `flac_decode_command()`) -- writes a WAV file rather
    than returning an array, deliberately: every decode path in this app
    already reads its PCM by reading a file afterwards, and matching that
    shape is what keeps this a drop-in for decode.py's own dispatcher
    later, rather than a parallel decode path with different semantics.

    **`decoder.process()` does not raise on a garbage/non-FLAC input, and
    `decoder.state` cannot tell success from failure either** -- confirmed
    directly, not assumed: it silently returns, having logged an error
    through its own callback, and `.state` lands on `UNINITIALIZED`
    either way, since `.process()` calls `finish()` internally regardless
    of outcome. The only reliable signal is whether the destination file
    actually landed on disk -- the same "a clean-looking return is not
    evidence, only the actual output is" lesson cdrip.py already learned
    from cdparanoia's own exit code.

    **Failure can also come out of `FileDecoder()`'s own constructor, not
    just `.process()`** -- confirmed directly: a missing source file
    raises `pyflac.DecoderInitException` right there, before `.process()`
    is ever reached. A broad `except Exception` around both the
    construction and the process() call is deliberate, not laziness --
    this function's whole contract is "always AudioEngineError, never a
    third-party exception leaking past it," and pyflac alone already has
    four differently-named exception classes across init/process for
    encode/decode, with `soundfile.LibsndfileError` (a *different*
    library's exception, since pyflac's own file I/O goes through it)
    on top of those."""
    if pyflac is None:
        raise AudioEngineError("pyflac is not installed")
    source, destination = Path(source), Path(destination)
    try:
        decoder = pyflac.FileDecoder(input_file=str(source), output_file=str(destination))
        decoder.process()
    except Exception as exc:
        raise AudioEngineError(f"{source.name} could not be decoded: {exc}") from exc
    if not destination.exists() or destination.stat().st_size == 0:
        raise AudioEngineError(f"{source.name} could not be decoded -- it may not be a valid FLAC file")


def encode_wav_to_flac(
    source: Path | str,
    destination: Path | str,
    tags: dict[str, str] | None = None,
    *,
    compression_level: int = 5,
) -> None:
    """pyflac + mutagen's equivalent of cdrip.py's `encode_command()`
    (flac.exe with one `--tag=name=value` per tag). Two separate steps
    because pyflac's encoder cannot write tags at all -- see this module's
    own docstring.

    Checks the destination file actually landed, same reasoning as
    decode_flac_to_wav()'s own note above -- `.process()`/`.state` cannot
    be trusted alone, and neither can catching only pyflac's own
    exception classes: `FileEncoder()`'s constructor calls `soundfile.info()`
    on the source to read its format, so a missing/unreadable source
    raises a raw `soundfile.LibsndfileError` right there, before
    `.process()` is ever reached -- confirmed directly, not assumed (see
    decode_flac_to_wav()'s matching note)."""
    if pyflac is None:
        raise AudioEngineError("pyflac is not installed")
    source, destination = Path(source), Path(destination)
    try:
        encoder = pyflac.FileEncoder(
            input_file=str(source),
            output_file=str(destination),
            compression_level=compression_level,
        )
        encoder.process()
    except Exception as exc:
        raise AudioEngineError(f"{source.name} could not be encoded: {exc}") from exc
    if not destination.exists() or destination.stat().st_size == 0:
        raise AudioEngineError(f"{source.name} could not be encoded -- it may not be a valid WAV file")

    if tags:
        if mutagen is None:
            raise AudioEngineError("mutagen is not installed")
        audio = mutagen.flac.FLAC(str(destination))
        for name, value in tags.items():
            audio[name] = str(value)
        audio.save()


# --- resampling -----------------------------------------------------------


def resample(samples: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    """soxr's "VHQ" (very high quality) resampler -- SoX's own `rate -v`
    at a fraction of the dependency weight. A no-op when the rates
    already match, same as SoX itself would effectively be."""
    if source_rate == target_rate:
        return samples
    return soxr.resample(samples, source_rate, target_rate, quality="VHQ")


# --- dithering: verified noise-shaped error feedback ----------------------

# A safe, bounded middle ground -- confirmed against a real bundled
# sox.exe: order 2-3 tracks plain TPDF's THD closely with a modest,
# genuine shift of noise energy toward high frequencies, and the peak
# dither excursion this order actually reaches (a handful of LSBs) never
# approached clipping on real program-level material in testing. Higher
# orders close in further on SoX's own `dither -s` noise floor and tilt,
# but their peak excursion grows fast enough (order 6 alone reaches ~28
# LSB peak on silence) that matching `-s` exactly would need a proper
# tabulated FIR shaping filter instead of just raising this order -- not
# attempted here.
DEFAULT_DITHER_ORDER = 2


def _noise_shaping_coefficients(order: int) -> np.ndarray:
    """Feedback coefficients for an order-`p` error-feedback quantizer
    whose noise transfer function is (1-z^-1)^p. Verified against the
    theoretical NTF magnitude via direct FFT of injected noise on a
    white-noise test signal before ever being trusted here -- the other
    sign convention for the fed-back error (`y-w` instead of `w-y`)
    silently produces a perfectly flat spectrum, not merely a
    phase-flipped one, which is exactly the bug that was caught this way."""
    if order == 0:
        return np.zeros(0, dtype=np.float64)
    return np.array([comb(order, k) * (-1) ** (k + 1) for k in range(1, order + 1)], dtype=np.float64)


@numba.njit(cache=True)
def _dither_loop(x: np.ndarray, coeffs: np.ndarray, order: int) -> np.ndarray:
    """The actual recursive, bounded-state error-feedback quantizer --
    each step depends only on `order` recent (small) error values, never
    an unbounded running sum, which is what keeps this numerically exact
    regardless of how long the input is (see this module's own docstring
    for the vectorised alternative that does NOT have that property)."""
    n = len(x)
    err_hist = np.zeros(order)
    y = np.empty(n, dtype=np.int64)
    for i in range(n):
        feedback = 0.0
        for k in range(order):
            feedback += coeffs[k] * err_hist[k]
        w = x[i] + feedback
        yi = np.round(w)
        y[i] = np.int64(yi)
        e = w - yi
        for k in range(order - 1, 0, -1):
            err_hist[k] = err_hist[k - 1]
        if order > 0:
            err_hist[0] = e
    return y


def dither_to_16bit(
    samples: np.ndarray,
    *,
    order: int = DEFAULT_DITHER_ORDER,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """`samples` in [-1, 1] float -> int16, via TPDF dither (for
    decorrelation) plus an order-`order` noise-shaping feedback loop on
    top (for pushing the residual noise toward the less-audible high end)
    -- what actually turns quantising 24 bits down to 16 into something
    that sounds like the recording rather than like quantisation noise,
    same reasoning as decode.py's own note on SoX's `dither` effect, just
    with an audible shift toward high frequencies added on top."""
    scaled = np.asarray(samples, dtype=np.float64) * 32767.0
    if rng is None:
        rng = np.random.default_rng()
    n = len(scaled)
    tpdf = rng.random(n) - rng.random(n)
    coeffs = _noise_shaping_coefficients(order)
    y = _dither_loop(scaled + tpdf, coeffs, order)
    return np.clip(y, -32768, 32767).astype(np.int16)


# --- playback / device selection (sounddevice) -----------------------------


@dataclass(frozen=True)
class OutputDevice:
    """One PortAudio-visible output-capable device. `index` is only valid
    for the lifetime of the current process -- see resolve_output_device()
    for why a *name* is what gets saved, never this."""

    index: int
    name: str
    max_output_channels: int
    default_samplerate: float


def list_output_devices() -> list[OutputDevice]:
    if sd is None:
        raise AudioEngineError("sounddevice is not installed")
    devices = []
    for index, info in enumerate(sd.query_devices()):
        if info["max_output_channels"] > 0:
            devices.append(
                OutputDevice(
                    index=index,
                    name=info["name"],
                    max_output_channels=info["max_output_channels"],
                    default_samplerate=info["default_samplerate"],
                )
            )
    return devices


def resolve_output_device(name: str) -> int | None:
    """A saved device name -> its current PortAudio index, or None.

    None means "the OS default output device" -- both when `name` is
    empty (nothing chosen yet) and when a previously-saved name no longer
    matches anything currently plugged in. Same "never silently replaced,
    but never refuse to play either" balance app_settings.audio_output_device()
    documents: a saved index would be meaningless after a reboot or a USB
    replug, so this is resolved by name every time playback actually
    starts, not cached."""
    if not name:
        return None
    needle = name.lower()
    for device in list_output_devices():
        if needle in device.name.lower():
            return device.index
    return None


class AudioPlayer:
    """Plays a queue of already-decoded PCM buffers to one output device,
    firing a callback at the exact sample position each buffer ends --
    not polled, unlike foobar2000's now-playing index (which this project
    has so far only ever been able to check every POLL_MS): the boundary
    is known the instant this player's own callback crosses it, because
    this player is the thing doing the playing.

    Two independent players are what a "recording sink" (whatever device
    Settings has configured) and an always-on-the-OS-default "preview
    sink" are -- both just `AudioPlayer(device=...)` with a different
    `device` argument, verified to run concurrently with no PortAudio
    contention in the prototype this module is built from.
    """

    def __init__(self, device: int | None, samplerate: int = RED_BOOK_RATE, channels: int = RED_BOOK_CHANNELS):
        if sd is None:
            raise AudioEngineError("sounddevice is not installed")
        self._device = device
        self._samplerate = samplerate
        self._channels = channels
        self._stream: "sd.OutputStream | None" = None
        self._queue: list[np.ndarray] = []
        self._queue_index = 0
        self._position_in_current = 0
        self._on_track_boundary: Callable[[int], None] | None = None
        self._on_finished: Callable[[], None] | None = None

    def play(
        self,
        buffers: list[np.ndarray],
        *,
        on_track_boundary: Callable[[int], None] | None = None,
        on_finished: Callable[[], None] | None = None,
    ) -> None:
        """`buffers` is one array per track, mono or already the right
        channel count, float32 in [-1, 1]. `on_track_boundary(index)` -- if
        given -- fires from the audio callback thread the instant playback
        crosses from track `index-1` into track `index`; `on_finished()`
        fires once the whole queue has played out."""
        self.stop()
        self._queue = [self._as_stereo(b) for b in buffers]
        self._queue_index = 0
        self._position_in_current = 0
        self._on_track_boundary = on_track_boundary
        self._on_finished = on_finished
        self._stream = sd.OutputStream(
            samplerate=self._samplerate,
            channels=self._channels,
            dtype="float32",
            device=self._device,
            callback=self._callback,
        )
        self._stream.start()

    def stop(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        self._queue = []

    def _as_stereo(self, data: np.ndarray) -> np.ndarray:
        data = np.asarray(data, dtype=np.float32)
        if data.ndim == 1:
            data = np.stack([data] * self._channels, axis=-1)
        return data

    def _callback(self, outdata, frames, time_info, status) -> None:
        written = 0
        while written < frames:
            if self._queue_index >= len(self._queue):
                outdata[written:] = 0
                if self._on_finished is not None:
                    self._on_finished()
                return
            current = self._queue[self._queue_index]
            remaining_in_track = len(current) - self._position_in_current
            take = min(frames - written, remaining_in_track)
            outdata[written: written + take] = current[
                self._position_in_current: self._position_in_current + take
            ]
            written += take
            self._position_in_current += take
            if self._position_in_current >= len(current):
                self._queue_index += 1
                self._position_in_current = 0
                if self._queue_index < len(self._queue) and self._on_track_boundary is not None:
                    self._on_track_boundary(self._queue_index)
