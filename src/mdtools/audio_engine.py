"""xD-Tools' own audio engine: FLAC decode/encode, resampling, dithering
and real-time playback -- replacing flac.exe, SoX and foobar2000's own
playback role with `soundfile` (libsndfile) + soxr + a verified
noise-shaped dither + sounddevice, respectively.

This module is the *foundation* only -- decode.py's SoX-backed conversion
and cdrip.py's flac.exe encode still run as they always have, and every
recording dialog still drives foobar2000. Nothing here is wired into any
of those yet; this is the self-contained engine those call sites will be
switched over to, one at a time, once each swap has its own test coverage
in place. No Qt here either, matching cdrip.py/decode.py/mdrem.py's own
"plain module, testable without a QApplication" rule.

Several design decisions came out of real measurement, not assumption --
worth keeping in mind before touching any of this:

**`soundfile` (libsndfile), not `pyflac`, for FLAC encode/decode -- and
that was a correction partway through, not the original plan.** pyFLAC
looked like the obvious choice at first (a dedicated FLAC binding), but
its decoder turns out to have a hard limitation, confirmed directly: every
one of its decoder classes shares one low-level C write-callback that
raises `ValueError('Only int16/int32 data type is supported')` the moment
a FLAC frame's bits-per-sample is anything but 16 or 32 -- 24-bit is
neither, and a 24-bit download is the common real-world case this whole
conversion path exists for. `soundfile.read()` on the same file decodes
it bit-exactly regardless of depth (libsndfile has its own complete FLAC
codec with no such restriction), and `soundfile` also encodes FLAC
directly -- writing the same Vorbis-comment tags in one pass, verified via
an independent read-back through `mutagen`, and producing byte-identical
output to pyFLAC's own encoder for the same audio (both wrap the same
libFLAC underneath). It covers everything pyFLAC was doing here, with
none of its limitations, so pyFLAC and mutagen's own FLAC-writing support
are no longer dependencies of this module at all.

**FLAC and WAV only, for now, even though this build of libsndfile can
read and write MP3 and OGG Vorbis too (confirmed directly: a real
encode-then-decode round trip through both formats came back with
correlation 1.0 against the source).** Widening format support is a
deliberate, separate decision -- this project has documented MP3 as
unsupported everywhere for a long time (SoX's bundled build lacks
`libmad-0.dll`), and lifting that changes burn-dialog verdicts and
several docstrings that explain *why* it was unsupported, not just this
module. It also needs re-confirming against the actual frozen-build
wheel, not just a dev venv -- libsndfile's MP3/OGG support depends on
which codecs that specific wheel was compiled with.

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

from mdtools.decode import RED_BOOK_CHANNELS, RED_BOOK_RATE

try:
    import soundfile as sf
except ImportError:  # pragma: no cover -- wraps libsndfile via cffi, same class of risk as sounddevice below
    sf = None

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
    to tell "SoX is missing" from "this engine can't read that file"
    during the period where both paths still exist side by side."""


def _require_soundfile() -> None:
    if sf is None:
        raise AudioEngineError("soundfile is not installed")


# --- decoding / encoding (libsndfile via soundfile) -----------------------

# Both directions go through `soundfile` (libsndfile), not `pyflac`, and
# that was a real correction, not the original design: pyflac's decoder
# cannot read a 24-bit FLAC at all (confirmed directly -- every one of
# its decoder classes shares one low-level C write-callback that raises
# `ValueError('Only int16/int32 data type is supported')` the moment a
# frame's bits-per-sample is anything but 16 or 32, and 24-bit is
# neither), which is exactly the common case a real-world download is.
# `soundfile.read()` on the same file decodes it bit-exactly regardless
# of depth -- libsndfile has its own complete FLAC codec with no such
# restriction, confirmed directly against a real 24-bit FLAC made by the
# bundled flac.exe. It also encodes FLAC directly, writes the same
# Vorbis-comment tags (confirmed via an independent read-back through
# mutagen), and produces byte-identical output to pyflac's own encoder
# for the same audio (both wrap the same libFLAC underneath) -- so it
# covers everything pyflac was doing here, with none of its limitations,
# and mutagen's own FLAC support is no longer needed for tags either.


def decode_flac_to_wav(source: Path | str, destination: Path | str) -> None:
    """A lossless FLAC -> WAV unpack, at the FLAC's own bit depth -- for
    decode.py's "already Red Book, nothing to resample or dither, just
    unwrap the container" fast path. Reading as int16 is exact rather
    than lossy for that case specifically: Red Book is 16-bit by
    definition, so there is no precision to lose."""
    _require_soundfile()
    source, destination = Path(source), Path(destination)
    try:
        data, rate = sf.read(str(source), dtype="int16", always_2d=True)
        sf.write(str(destination), data, rate, subtype="PCM_16")
    except Exception as exc:
        raise AudioEngineError(f"{source.name} could not be decoded: {exc}") from exc
    if not destination.exists() or destination.stat().st_size == 0:
        raise AudioEngineError(f"{source.name} could not be decoded -- it may not be a valid FLAC file")


def encode_wav_to_flac(
    source: Path | str,
    destination: Path | str,
    tags: dict[str, str] | None = None,
) -> None:
    """cdrip.py's own `encode_command()` (flac.exe with one
    `--tag=name=value` per tag), replaced: libsndfile writes the FLAC
    *and* the tags in one pass -- unlike pyflac, which has no tag support
    at all and needed a second pass through mutagen for that half.

    No `compression_level` parameter: `SoundFile.compression_level` is a
    read-only property in this soundfile version (confirmed directly --
    assigning it raises `AttributeError`), so there is nothing here to
    set it through; libFLAC's own default (level 5) applies, the same
    default flac.exe's own command line used (no `--compression-level`
    flag was ever passed)."""
    _require_soundfile()
    source, destination = Path(source), Path(destination)
    try:
        data, rate = sf.read(str(source), dtype="int16", always_2d=True)
        with sf.SoundFile(
            str(destination),
            mode="w",
            samplerate=rate,
            channels=data.shape[1],
            subtype="PCM_16",
            format="FLAC",
        ) as out:
            for name, value in (tags or {}).items():
                setattr(out, name.lower(), str(value))
            out.write(data)
    except Exception as exc:
        raise AudioEngineError(f"{source.name} could not be encoded: {exc}") from exc
    if not destination.exists() or destination.stat().st_size == 0:
        raise AudioEngineError(f"{source.name} could not be encoded -- it may not be a valid WAV file")


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


def resample_and_dither_to_red_book(source: Path | str, destination: Path | str) -> None:
    """A FLAC or WAV source, at any sample rate/bit depth, mono or
    stereo, to a Red Book (44.1kHz/16-bit/stereo) PCM WAV -- decode.py's
    own SoX-backed conversion for this case, replaced in full: `sf.read()`
    decodes either format directly (including a 24-bit FLAC -- see
    decode_flac_to_wav()'s own note on why that needs libsndfile rather
    than a dedicated FLAC decoder), `resample()` (soxr) handles the
    sample rate, and `dither_to_16bit()` replaces SoX's own `dither`
    effect for the bit depth. Mono is duplicated to two identical
    channels, matching what SoX's own `-c 2` does to a mono source.

    Deliberately scoped to mono/stereo input only -- decode.py's own
    dispatcher routes anything with more than two channels (real-world
    surround audio) to SoX instead, which does genuine channel mixing;
    naively keeping only the first two channels here would silently drop
    the rest, exactly the kind of silent-wrong-answer this app avoids
    elsewhere (see cdrip.py/decode.py's own "never quietly misreport"
    rules)."""
    _require_soundfile()
    source, destination = Path(source), Path(destination)

    try:
        samples, rate = sf.read(str(source), dtype="float64", always_2d=True)
    except Exception as exc:
        raise AudioEngineError(f"{source.name} could not be read: {exc}") from exc
    if samples.shape[1] > RED_BOOK_CHANNELS:
        # Enforced here too, not just left to the caller's own dispatch
        # logic -- a >2-channel source silently proceeding would produce
        # a WAV with the wrong channel count instead of a clear error.
        raise AudioEngineError(
            f"{source.name} has {samples.shape[1]} channels; only mono and stereo are supported here"
        )

    resampled = resample(samples, rate, RED_BOOK_RATE)
    if resampled.shape[1] == 1:
        resampled = np.repeat(resampled, RED_BOOK_CHANNELS, axis=1)

    rng = np.random.default_rng()
    channels_16 = [dither_to_16bit(resampled[:, c], rng=rng) for c in range(resampled.shape[1])]
    interleaved = np.stack(channels_16, axis=-1)

    try:
        sf.write(str(destination), interleaved, RED_BOOK_RATE, subtype="PCM_16")
    except Exception as exc:
        raise AudioEngineError(f"{destination.name} could not be written: {exc}") from exc


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

    `gain_db` is the recording sink's own headroom setting (explicit user
    request; see app_settings.recording_gain_db(), default -5 dB) --
    previously a hardcoded `RECORDING_VOLUME_DB` constant duplicated in
    record_dialog.py/tape_record_dialog.py and applied via foobar2000's
    own set_volume(). A *preview* sink should stay at the default 0 dB
    (full digital level, since nothing downstream of it needs headroom --
    it's just being listened to), so this is a constructor argument, not
    a module-level constant every player shares.
    """

    def __init__(
        self,
        device: int | None,
        samplerate: int = RED_BOOK_RATE,
        channels: int = RED_BOOK_CHANNELS,
        gain_db: float = 0.0,
    ):
        if sd is None:
            raise AudioEngineError("sounddevice is not installed")
        self._device = device
        self._samplerate = samplerate
        self._channels = channels
        self._gain = 10 ** (gain_db / 20)
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
        # Applied unconditionally (gain 1.0 is a no-op multiply) rather
        # than guarded by an `if`, which would need a floating-point
        # equality check to skip -- and applied once here, per buffer,
        # rather than per-callback: this runs at play()-time, off the
        # real-time audio thread, so it costs nothing where it would
        # actually matter.
        return (data * self._gain).astype(np.float32)

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
