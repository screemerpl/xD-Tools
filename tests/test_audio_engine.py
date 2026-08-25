"""audio_engine.py -- FLAC decode+encode via soundfile (libsndfile), soxr
resampling, the verified noise-shaped dither, and playback/device-
selection with sounddevice faked out (no real audio hardware needed to
run this suite).

Nothing in this file exercises decode.py's or cdrip.py's own SoX/flac.exe
paths -- audio_engine is not wired into either yet; this only tests the
new module in isolation.
"""

from __future__ import annotations

import subprocess

import numpy as np
import pytest
import soundfile as sf

from mdtools import audio_engine, cdrip


# --- decode / encode (real libsndfile, small real files) ------------------


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


def test_encoding_writes_tags_in_one_pass(tmp_path):
    """Verified through mutagen -- a library that had no part in writing
    them -- rather than trusting soundfile's own read-back, the same
    "don't test with the tool that wrote it" reasoning the rest of this
    codebase's tag tests already follow."""
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


def test_a_genuine_24_bit_flac_can_be_resampled_and_dithered(tmp_path):
    """The actual regression guard for the bug that made this module use
    soundfile instead of pyflac in the first place: pyflac's decoder
    cannot read a 24-bit FLAC at all (confirmed directly against every
    one of its decoder classes), which is exactly the common case a
    "needs conversion" source -- what resample_and_dither_to_red_book()
    is for -- actually is. The fixture is made by the bundled flac.exe
    (not soundfile itself), so this proves compatibility with a real
    24-bit FLAC, not just a round trip through soundfile's own encoder.

    Deliberately does NOT go through decode_flac_to_wav() here: that
    function reads as int16 by design (correct only for its own "already
    Red Book, nothing to dither" fast-path use), so calling it on a
    24-bit source would silently truncate without any dithering at all --
    exactly the case resample_and_dither_to_red_book() exists to handle
    properly instead."""
    tool = cdrip.flac_path()
    if tool is None:
        pytest.skip("the bundled flac encoder is not present")

    rng = np.random.default_rng(0)
    t = np.arange(48000) / 48000
    sig = 0.3 * np.sin(2 * np.pi * 440 * t)
    samples_24 = np.stack([sig, sig], axis=-1)
    src_wav = tmp_path / "src24.wav"
    sf.write(src_wav, samples_24, 48000, subtype="PCM_24")

    flac_path = tmp_path / "src24.flac"
    result = subprocess.run(
        [tool, "-s", "-f", "-o", str(flac_path), str(src_wav)], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    assert sf.info(str(flac_path)).subtype == "PCM_24"

    out_wav = tmp_path / "out.wav"
    audio_engine.resample_and_dither_to_red_book(flac_path, out_wav)

    decoded, rate = sf.read(str(out_wav), dtype="float64", always_2d=True)
    assert rate == 44100
    assert decoded.shape == (44100, 2)
    # resampled from 48k -> 44.1k, so lengths differ -- compare the
    # signals' own correlation instead of a sample-for-sample equality
    resampled_original = audio_engine.resample(sig, 48000, 44100)
    correlation = np.corrcoef(decoded[:, 0], resampled_original[: len(decoded)])[0, 1]
    assert correlation > 0.99


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


# --- resample_and_dither_to_red_book (the "needs conversion" path) --------


def test_a_wav_is_resampled_and_bit_reduced_to_red_book(tmp_path):
    samples = np.zeros((48000 * 2, 2), dtype=np.float64)
    src = tmp_path / "src.wav"
    sf.write(src, samples, 48000, subtype="PCM_24")

    out = tmp_path / "out.wav"
    audio_engine.resample_and_dither_to_red_book(src, out)

    info = sf.info(str(out))
    assert info.samplerate == 44100
    assert info.channels == 2
    assert info.subtype == "PCM_16"


def test_a_mono_source_is_duplicated_to_stereo(tmp_path):
    """Duplicated *before* dithering, not after -- each channel then gets
    its own independent dither noise (the correct behaviour: correlated
    noise between channels would colour the stereo image), so the two
    channels end up nearly but not bit-exactly identical, differing only
    by up to a couple of LSBs of independent dither."""
    samples = np.full((44100,), 0.5, dtype=np.float64)
    src = tmp_path / "mono.wav"
    sf.write(src, samples, 48000, subtype="PCM_24")

    out = tmp_path / "out.wav"
    audio_engine.resample_and_dither_to_red_book(src, out)

    data, _ = sf.read(str(out), dtype="int16")
    assert data.ndim == 2 and data.shape[1] == 2
    assert np.max(np.abs(data[:, 0].astype(int) - data[:, 1].astype(int))) <= 4


def test_a_surround_source_is_refused_rather_than_silently_folded(tmp_path):
    samples = np.zeros((44100, 6), dtype=np.float64)
    src = tmp_path / "surround.wav"
    sf.write(src, samples, 48000, subtype="PCM_24")

    with pytest.raises(audio_engine.AudioEngineError, match="6 channels"):
        audio_engine.resample_and_dither_to_red_book(src, tmp_path / "out.wav")


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
    """`hostapis` defaults to a single "Windows WDM-KS" entry at index 0,
    and every device fixture below is already tagged `hostapi: 0` -- so by
    default the new host-API filter in list_output_devices() is a no-op
    against these older fixtures, matching every physical device the way
    it always did. The filtering itself is tested separately below, with
    fixtures that deliberately set up more than one host API."""

    def __init__(self, devices, hostapis=None):
        self._devices = devices
        self._hostapis = hostapis if hostapis is not None else [{"name": "Windows WDM-KS"}]

    def query_devices(self):
        return self._devices

    def query_hostapis(self):
        return self._hostapis


def test_list_output_devices_only_returns_ones_with_output_channels(monkeypatch):
    fake = _FakeSoundDevice(
        [
            {"name": "Microphone", "max_output_channels": 0, "default_samplerate": 44100.0, "hostapi": 0},
            {"name": "Speakers (Realtek)", "max_output_channels": 2, "default_samplerate": 44100.0, "hostapi": 0},
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
        [
            {
                "name": "Speakers (Realtek(R) Audio)",
                "max_output_channels": 2,
                "default_samplerate": 44100.0,
                "hostapi": 0,
            }
        ]
    )
    monkeypatch.setattr(audio_engine, "sd", fake)

    assert audio_engine.resolve_output_device("realtek") == 0


def test_resolving_a_saved_name_that_no_longer_matches_falls_back_to_default(monkeypatch):
    """Same "never silently replaced, but never refuse to play either"
    rule mdrem's saved port already follows -- a device that isn't
    plugged in right now degrades to the OS default rather than raising."""
    fake = _FakeSoundDevice(
        [{"name": "Speakers", "max_output_channels": 2, "default_samplerate": 44100.0, "hostapi": 0}]
    )
    monkeypatch.setattr(audio_engine, "sd", fake)

    assert audio_engine.resolve_output_device("some usb dac that is unplugged") is None


# --- device listing: restricted to one host API (#28) ----------------------


def test_list_output_devices_keeps_only_the_wdm_ks_host_api(monkeypatch):
    """PortAudio enumerates the same physical device once per Windows host
    API it can reach it through -- MME, DirectSound, WASAPI and WDM-KS each
    listing every output device again, which is what made this list
    implausibly long. Filtering to one host API is meant to collapse that
    back down to one entry per real device."""
    fake = _FakeSoundDevice(
        [
            {"name": "Speakers (MME)", "max_output_channels": 2, "default_samplerate": 44100.0, "hostapi": 0},
            {
                "name": "Speakers (DirectSound)",
                "max_output_channels": 2,
                "default_samplerate": 44100.0,
                "hostapi": 1,
            },
            {"name": "Speakers (WASAPI)", "max_output_channels": 2, "default_samplerate": 44100.0, "hostapi": 2},
            {"name": "Speakers (WDM-KS)", "max_output_channels": 2, "default_samplerate": 44100.0, "hostapi": 3},
        ],
        hostapis=[
            {"name": "MME"},
            {"name": "Windows DirectSound"},
            {"name": "Windows WASAPI"},
            {"name": "Windows WDM-KS"},
        ],
    )
    monkeypatch.setattr(audio_engine, "sd", fake)

    devices = audio_engine.list_output_devices()

    assert [d.name for d in devices] == ["Speakers (WDM-KS)"]


def test_list_output_devices_falls_back_to_everything_when_wdm_ks_is_absent(monkeypatch):
    """Not every platform/build reports a "Windows WDM-KS" host API (this is
    a Windows-only kernel streaming layer) -- when it's missing, filtering
    must not silently return an empty list. Fall back to every output
    device PortAudio reports, exactly like before this filter existed."""
    fake = _FakeSoundDevice(
        [
            {"name": "Built-in Output", "max_output_channels": 2, "default_samplerate": 44100.0, "hostapi": 0},
        ],
        hostapis=[{"name": "Core Audio"}],
    )
    monkeypatch.setattr(audio_engine, "sd", fake)

    devices = audio_engine.list_output_devices()

    assert [d.name for d in devices] == ["Built-in Output"]


def test_resolving_a_saved_device_only_matches_within_the_preferred_host_api(monkeypatch):
    """A saved device name that exists only under a filtered-out host API
    (e.g. the WASAPI-only spelling of a device whose WDM-KS name differs)
    must not resolve -- it should degrade to the OS default exactly like an
    unplugged device does, not silently pick the wrong API's index."""
    fake = _FakeSoundDevice(
        [
            {
                "name": "Realtek Digital Output (Realtek High Definition Audio)",
                "max_output_channels": 2,
                "default_samplerate": 44100.0,
                "hostapi": 2,
            },
            {
                "name": "SPDIF Out (Realtek HDA SPDIF Out)",
                "max_output_channels": 2,
                "default_samplerate": 44100.0,
                "hostapi": 3,
            },
        ],
        hostapis=[{"name": "MME"}, {"name": "Windows DirectSound"}, {"name": "Windows WASAPI"}, {"name": "Windows WDM-KS"}],
    )
    monkeypatch.setattr(audio_engine, "sd", fake)

    assert audio_engine.resolve_output_device("realtek digital output") is None
    assert audio_engine.resolve_output_device("spdif out") == 1


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


def test_on_finished_fires_only_once_even_though_the_callback_keeps_running(fake_sd):
    """Real report: a MiniDisc recording's "Upload Tracklist" window kept
    reopening in a loop after the album finished. Root cause: PortAudio
    keeps calling this callback continuously for as long as the stream
    stays open, and nothing here ever stops the stream once the queue
    empties -- so a caller that reacts to on_finished (record_dialog.py's
    _on_disc_finished, via PlaybackBridge) used to get told the disc
    finished once per audio callback, forever, each one independently
    scheduling its own titling dialog."""
    finished = []
    player = audio_engine.AudioPlayer(device=None, samplerate=44100, channels=2)
    track = np.full(10, 0.5, dtype=np.float32)

    player.play([track], on_finished=lambda: finished.append(True))
    stream = _FakeOutputStream.instances[-1]

    _pull(stream, 10)  # exhausts the track
    _pull(stream, 5)  # queue now empty -- finished fires once, here
    _pull(stream, 5)  # PortAudio keeps calling; must not fire again
    _pull(stream, 5)
    _pull(stream, 5)

    assert finished == [True]


def test_a_second_play_call_can_report_finished_again(fake_sd):
    """The guard is per play(), not a permanent one-shot latch -- a second
    recording through the same AudioPlayer instance must still report its
    own completion."""
    finished = []
    player = audio_engine.AudioPlayer(device=None, samplerate=44100, channels=2)
    track = np.full(10, 0.5, dtype=np.float32)

    player.play([track], on_finished=lambda: finished.append("first"))
    _pull(_FakeOutputStream.instances[-1], 10)
    _pull(_FakeOutputStream.instances[-1], 5)
    assert finished == ["first"]

    player.play([track], on_finished=lambda: finished.append("second"))
    _pull(_FakeOutputStream.instances[-1], 10)
    _pull(_FakeOutputStream.instances[-1], 5)
    assert finished == ["first", "second"]


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


def test_gain_db_attenuates_playback(fake_sd):
    """app_settings.recording_gain_db() (default -5 dB) reaches actual
    output samples through this constructor argument -- confirmed against
    the exact linear factor, not just "quieter than before"."""
    player = audio_engine.AudioPlayer(device=None, samplerate=44100, channels=2, gain_db=-6.0206)
    track = np.full(10, 1.0, dtype=np.float32)

    player.play([track])
    out = _pull(_FakeOutputStream.instances[-1], 10)

    # -6.0206 dB is a factor of ~0.5
    assert np.allclose(out, 0.5, atol=1e-3)


def test_zero_gain_leaves_playback_unchanged(fake_sd):
    player = audio_engine.AudioPlayer(device=None, samplerate=44100, channels=2, gain_db=0.0)
    track = np.full(10, 0.7, dtype=np.float32)

    player.play([track])
    out = _pull(_FakeOutputStream.instances[-1], 10)

    assert np.allclose(out, 0.7, atol=1e-6)


def test_a_preview_sink_defaults_to_no_gain(fake_sd):
    """The recording sink's headroom setting must not leak into a preview
    player just because both are the same class -- gain_db defaults to 0
    unless a caller explicitly passes the recording setting in."""
    preview = audio_engine.AudioPlayer(device=None)
    track = np.full(10, 0.9, dtype=np.float32)

    preview.play([track])
    out = _pull(_FakeOutputStream.instances[-1], 10)

    assert np.allclose(out, 0.9, atol=1e-6)


def test_queue_index_and_position_track_playback(fake_sd):
    player = audio_engine.AudioPlayer(device=None, samplerate=44100, channels=2)
    track_a = np.zeros(10, dtype=np.float32)
    track_b = np.zeros(10, dtype=np.float32)

    player.play([track_a, track_b])
    stream = _FakeOutputStream.instances[-1]
    assert player.queue_index == 0
    assert player.position_seconds == 0.0

    _pull(stream, 4)
    assert player.queue_index == 0
    assert player.position_seconds == pytest.approx(4 / 44100)

    _pull(stream, 10)  # crosses into track_b, 4 frames of it consumed
    assert player.queue_index == 1
    assert player.position_seconds == pytest.approx(4 / 44100)


# --- load_for_playback: decode + resample, no dithering, for AudioPlayer --


def test_load_for_playback_decodes_and_resamples_to_the_target_rate(tmp_path):
    samples = np.zeros((4800, 2), dtype=np.float32)
    src = tmp_path / "hires.wav"
    sf.write(src, samples, 48000, subtype="PCM_16")

    buffers = audio_engine.load_for_playback([src], samplerate=44100)

    assert len(buffers) == 1
    assert buffers[0].dtype == np.float32
    # 4800 samples at 48000 Hz is 0.1s, which at 44100 Hz is 4410 samples
    assert buffers[0].shape[0] == pytest.approx(4410, abs=2)


def test_load_for_playback_leaves_mono_mono(tmp_path):
    """AudioPlayer._as_stereo() already duplicates a mono buffer to every
    output channel -- doing it again here would be redundant, not wrong."""
    samples = np.zeros(100, dtype=np.float32)
    src = tmp_path / "mono.wav"
    sf.write(src, samples, 44100, subtype="PCM_16")

    buffers = audio_engine.load_for_playback([src])

    assert buffers[0].ndim == 1


def test_load_for_playback_refuses_surround(tmp_path):
    samples = np.zeros((100, 6), dtype=np.float32)
    src = tmp_path / "surround.wav"
    sf.write(src, samples, 44100, subtype="PCM_16")

    with pytest.raises(audio_engine.AudioEngineError):
        audio_engine.load_for_playback([src])
