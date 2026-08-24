"""audio_engine.py -- pyflac/mutagen decode+encode, soxr resampling, the
verified noise-shaped dither, and playback/device-selection with
sounddevice faked out (no real audio hardware needed to run this suite).

Nothing in this file exercises decode.py's or cdrip.py's own SoX/flac.exe
paths -- audio_engine is not wired into either yet; this only tests the
new module in isolation.
"""

from __future__ import annotations

import numpy as np
import pytest
import soundfile as sf

from mdtools import audio_engine


# --- decode / encode (real pyflac + mutagen, small real files) -----------


def test_encoding_and_decoding_a_flac_file_round_trips_losslessly(tmp_path):
    rng = np.random.default_rng(0)
    samples = (rng.random((4410, 2)) * 2 - 1).astype(np.float32)
    samples_i16 = np.round(samples * 32767).astype(np.int16)

    src_wav = tmp_path / "src.wav"
    sf.write(src_wav, samples_i16, 44100, subtype="PCM_16")

    flac_path = tmp_path / "out.flac"
    audio_engine.encode_wav_to_flac(src_wav, flac_path)
    assert flac_path.exists()

    decoded_wav = tmp_path / "decoded.wav"
    audio_engine.decode_flac_to_wav(flac_path, decoded_wav)

    decoded, rate = sf.read(decoded_wav, dtype="int16")
    assert rate == 44100
    assert np.array_equal(decoded, samples_i16)


def test_encoding_writes_tags_pyflac_itself_cannot(tmp_path):
    """pyFLAC's own encoder has no tag support at all (confirmed against
    its docs) -- encode_wav_to_flac() has to reach for mutagen as a
    second pass, and this is what proves that second pass actually ran."""
    import mutagen.flac

    samples_i16 = np.zeros((100, 2), dtype=np.int16)
    src_wav = tmp_path / "silence.wav"
    sf.write(src_wav, samples_i16, 44100, subtype="PCM_16")

    flac_path = tmp_path / "tagged.flac"
    audio_engine.encode_wav_to_flac(
        src_wav, flac_path, tags={"TITLE": "Feel Invincible", "ARTIST": "Skillet"}
    )

    tags = mutagen.flac.FLAC(str(flac_path))
    assert tags["title"][0] == "Feel Invincible"
    assert tags["artist"][0] == "Skillet"


def test_encoding_with_no_tags_writes_none_at_all(tmp_path):
    import mutagen.flac

    samples_i16 = np.zeros((100, 2), dtype=np.int16)
    src_wav = tmp_path / "silence.wav"
    sf.write(src_wav, samples_i16, 44100, subtype="PCM_16")
    flac_path = tmp_path / "untagged.flac"

    audio_engine.encode_wav_to_flac(src_wav, flac_path)

    tags = mutagen.flac.FLAC(str(flac_path))
    assert len(tags.tags or []) == 0


def test_decoding_something_that_is_not_flac_reports_rather_than_crashing(tmp_path):
    not_flac = tmp_path / "not_flac.flac"
    not_flac.write_bytes(b"this is not a flac file")

    with pytest.raises(audio_engine.AudioEngineError):
        audio_engine.decode_flac_to_wav(not_flac, tmp_path / "out.wav")


# --- resampling ------------------------------------------------------------


def test_resample_changes_the_sample_count_proportionally():
    samples = np.zeros(48000, dtype=np.float64)
    result = audio_engine.resample(samples, 48000, 44100)
    assert result.shape[0] == 44100


def test_resample_is_a_no_op_when_rates_already_match():
    samples = np.array([0.1, 0.2, -0.3], dtype=np.float64)
    result = audio_engine.resample(samples, 44100, 44100)
    assert result is samples


# --- dithering: verified against an independent reference implementation --


def _reference_dither(samples_lsb: np.ndarray, order: int, tpdf: np.ndarray) -> np.ndarray:
    """A from-scratch reference, deliberately not sharing any code with
    audio_engine._dither_loop -- if both have the same bug, this wouldn't
    catch it, but it does catch the numba port disagreeing with the plain
    Python algorithm the earlier prototype independently verified against
    the theoretical noise transfer function."""
    from math import comb

    coeffs = [comb(order, k) * (-1) ** (k + 1) for k in range(1, order + 1)]
    x = samples_lsb + tpdf
    err_hist = [0.0] * order
    y = np.empty(len(x), dtype=np.int64)
    for i in range(len(x)):
        feedback = sum(c * e for c, e in zip(coeffs, err_hist))
        w = x[i] + feedback
        yi = round(w)
        y[i] = yi
        e = w - yi
        err_hist = [e] + err_hist[:-1]
    return np.clip(y, -32768, 32767).astype(np.int16)


@pytest.mark.parametrize("order", [0, 1, 2, 3, 4])
def test_dither_matches_an_independent_reference_implementation(order):
    rng = np.random.default_rng(123)
    samples = rng.random(2000) * 2 - 1

    # audio_engine.dither_to_16bit draws its own TPDF internally; to
    # compare against the reference bit-for-bit, seed both from a fresh
    # generator with the same state and let each draw its own TPDF in the
    # same order the real function does.
    rng_a = np.random.default_rng(7)
    result = audio_engine.dither_to_16bit(samples, order=order, rng=rng_a)

    rng_b = np.random.default_rng(7)
    scaled = samples * 32767.0
    n = len(scaled)
    tpdf = rng_b.random(n) - rng_b.random(n)
    expected = _reference_dither(scaled, order, tpdf)

    assert np.array_equal(result, expected)


def test_dither_output_is_int16_and_the_right_length():
    samples = np.zeros(500, dtype=np.float64)
    result = audio_engine.dither_to_16bit(samples)
    assert result.dtype == np.int16
    assert len(result) == 500


def test_dither_never_exceeds_16_bit_range_even_on_full_scale_input():
    samples = np.ones(10000, dtype=np.float64)  # full-scale +1.0 throughout
    result = audio_engine.dither_to_16bit(samples, order=3)
    assert result.max() <= 32767
    assert result.min() >= -32768


def test_dither_is_numerically_stable_at_realistic_album_length():
    """The whole reason the dither loop is numba-compiled rather than
    reformulated as cumsum/diff: that vectorised shortcut loses so much
    float64 precision over a real track's length that it stops rounding
    correctly at all (confirmed separately by measuring the actual
    resolution at the resulting magnitudes). This is a regression guard
    for *that* failure mode -- a few million samples of near-full-scale
    noise should still dither to something with a sane, bounded noise
    floor, not silently degenerate."""
    rng = np.random.default_rng(0)
    n = 2_000_000
    samples = (rng.random(n) - 0.5)  # -0.5..0.5, far from all zero/all full-scale
    result = audio_engine.dither_to_16bit(samples, order=3, rng=np.random.default_rng(1))
    # a real signal at this level should behave like the signal it is --
    # nowhere near saturating 16-bit range, and not collapsed to zero
    assert 1000 < np.std(result) < 20000


# --- device listing / resolution (sounddevice faked, no hardware needed) --


class _FakeSoundDevice:
    def __init__(self, devices):
        self._devices = devices

    def query_devices(self):
        return self._devices


def test_list_output_devices_only_returns_ones_with_output_channels(monkeypatch):
    fake = _FakeSoundDevice(
        [
            {"name": "Microphone", "max_output_channels": 0, "default_samplerate": 44100.0},
            {"name": "Speakers (Realtek)", "max_output_channels": 2, "default_samplerate": 44100.0},
        ]
    )
    monkeypatch.setattr(audio_engine, "sd", fake)

    devices = audio_engine.list_output_devices()

    assert [d.name for d in devices] == ["Speakers (Realtek)"]
    assert devices[0].index == 1  # the real, un-filtered PortAudio index


def test_resolving_an_empty_saved_name_means_the_os_default(monkeypatch):
    assert audio_engine.resolve_output_device("") is None


def test_resolving_a_saved_name_finds_it_by_substring(monkeypatch):
    fake = _FakeSoundDevice(
        [{"name": "Speakers (Realtek(R) Audio)", "max_output_channels": 2, "default_samplerate": 44100.0}]
    )
    monkeypatch.setattr(audio_engine, "sd", fake)

    assert audio_engine.resolve_output_device("realtek") == 0


def test_resolving_a_saved_name_that_no_longer_matches_falls_back_to_default(monkeypatch):
    """Same "never silently replaced, but never refuse to play either"
    rule mdrem's saved port already follows -- a device that isn't
    plugged in right now degrades to the OS default rather than raising."""
    fake = _FakeSoundDevice([{"name": "Speakers", "max_output_channels": 2, "default_samplerate": 44100.0}])
    monkeypatch.setattr(audio_engine, "sd", fake)

    assert audio_engine.resolve_output_device("some usb dac that is unplugged") is None


# --- AudioPlayer: track-boundary firing, no hardware needed ---------------


class _FakeOutputStream:
    """Stands in for sd.OutputStream -- .start()/.stop()/.close() are
    no-ops, and the test itself drives the callback directly, the same
    way the real PortAudio thread would."""

    instances: list["_FakeOutputStream"] = []

    def __init__(self, samplerate, channels, dtype, device, callback):
        self.samplerate = samplerate
        self.channels = channels
        self.dtype = dtype
        self.device = device
        self.callback = callback
        self.started = False
        self.closed = False
        _FakeOutputStream.instances.append(self)

    def start(self):
        self.started = True

    def stop(self):
        self.started = False

    def close(self):
        self.closed = True


@pytest.fixture
def fake_sd(monkeypatch):
    _FakeOutputStream.instances = []
    fake = type("FakeSD", (), {"OutputStream": _FakeOutputStream})()
    monkeypatch.setattr(audio_engine, "sd", fake)
    return fake


def _pull(stream: _FakeOutputStream, frames: int) -> np.ndarray:
    outdata = np.zeros((frames, stream.channels), dtype=np.float32)
    stream.callback(outdata, frames, None, None)
    return outdata


def test_play_streams_one_buffer_then_reports_finished(fake_sd):
    finished = []
    player = audio_engine.AudioPlayer(device=None, samplerate=44100, channels=2)
    track = np.full(10, 0.5, dtype=np.float32)

    player.play([track], on_finished=lambda: finished.append(True))
    stream = _FakeOutputStream.instances[-1]
    assert stream.started

    out = _pull(stream, 10)
    assert np.allclose(out, 0.5)
    assert finished == []  # not yet -- the callback that empties the queue reports it

    _pull(stream, 5)  # queue is now empty; callback should signal finished
    assert finished == [True]


def test_play_fires_track_boundary_at_the_exact_sample(fake_sd):
    boundaries = []
    player = audio_engine.AudioPlayer(device=None, samplerate=44100, channels=2)
    track_a = np.full(10, 0.1, dtype=np.float32)
    track_b = np.full(10, 0.9, dtype=np.float32)

    player.play([track_a, track_b], on_track_boundary=lambda i: boundaries.append(i))
    stream = _FakeOutputStream.instances[-1]

    # pull frames that straddle the boundary within a single callback --
    # this is the whole point: no polling latency, the boundary is known
    # the instant it's crossed, mid-callback if necessary
    out = _pull(stream, 15)
    assert boundaries == [1]
    assert np.allclose(out[:10], 0.1)
    assert np.allclose(out[10:15], 0.9)


def test_stop_closes_the_stream_and_clears_the_queue(fake_sd):
    player = audio_engine.AudioPlayer(device=None, samplerate=44100, channels=2)
    player.play([np.zeros(10, dtype=np.float32)])
    stream = _FakeOutputStream.instances[-1]

    player.stop()

    assert stream.closed
    assert not stream.started


def test_recording_and_preview_sinks_are_independent_players(fake_sd):
    """Confirms the API shape the settings/device-picker design leans on:
    a "recording sink" pinned to an explicit device and a "preview sink"
    always on the OS default are just two AudioPlayer instances, not a
    single player juggling two devices."""
    recording_sink = audio_engine.AudioPlayer(device=3)
    preview_sink = audio_engine.AudioPlayer(device=None)

    recording_sink.play([np.zeros(10, dtype=np.float32)])
    preview_sink.play([np.zeros(10, dtype=np.float32)])

    assert _FakeOutputStream.instances[-2].device == 3
    assert _FakeOutputStream.instances[-1].device is None
