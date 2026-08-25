"""Reading what an audio file is, and getting Red Book PCM out of it.

The FLAC half runs against the *bundled encoder*, not against fixtures
written from the specification -- a hand-built STREAMINFO block can agree
with itself perfectly and still misread what flac.exe actually produces,
which is the same reason test_embedded_cover.py encodes a real file before
reading its picture block back.
"""

import subprocess
import wave

import pytest

from mdtools import decode
from mdtools.cdrip import flac_path


def _write_wav(path, *, rate=44100, bits=16, channels=2, seconds=1.0):
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(bits // 8)
        handle.setframerate(rate)
        handle.writeframes(b"\x00" * int(rate * seconds) * channels * (bits // 8))
    return path


def _encode_flac(wav_path, flac_out):
    tool = flac_path()
    if tool is None:
        pytest.skip("the bundled FLAC encoder is not available")
    result = subprocess.run([tool, "-s", "-f", "-o", str(flac_out), str(wav_path)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return flac_out


# -- reading properties --------------------------------------------------


def test_a_red_book_wav_reads_back_exactly(tmp_path):
    properties = decode.analyze(_write_wav(tmp_path / "a.wav"))

    assert (properties.sample_rate, properties.bits_per_sample, properties.channels) == (44100, 16, 2)
    assert properties.frames == 44100
    assert properties.duration_seconds == pytest.approx(1.0)
    assert properties.is_red_book is True
    assert properties.mismatches() == []


def test_a_flac_encoded_by_the_bundled_tool_reports_the_same_properties(tmp_path):
    wav = _write_wav(tmp_path / "a.wav", seconds=0.5)
    flac = _encode_flac(wav, tmp_path / "a.flac")

    assert decode.analyze(flac) == decode.analyze(wav)


def test_a_hi_res_file_is_reported_rather_than_quietly_accepted(tmp_path):
    """The bundled decoder cannot resample, so this has to surface as a
    verdict the burn dialog can show -- not as something fixed silently."""
    properties = decode.analyze(_write_wav(tmp_path / "hires.wav", rate=96000))

    assert properties.is_red_book is False
    assert properties.mismatches() == ["sample_rate"]


def test_mono_and_bit_depth_are_each_reported_on_their_own(tmp_path):
    mono = decode.analyze(_write_wav(tmp_path / "mono.wav", channels=1))
    assert mono.mismatches() == ["channels"]

    deep = decode.analyze(_write_wav(tmp_path / "deep.wav", bits=24))
    assert deep.mismatches() == ["bits_per_sample"]


def test_a_24_bit_flac_is_read_as_24_bit(tmp_path):
    """The depth lives in a 5-bit field packed against the sample rate and
    the channel count, so an off-by-one shift would still look plausible on
    a 16-bit file."""
    wav = _write_wav(tmp_path / "deep.wav", bits=24, seconds=0.2)
    flac = _encode_flac(wav, tmp_path / "deep.flac")

    properties = decode.analyze(flac)
    assert properties.bits_per_sample == 24
    assert properties.sample_rate == 44100
    assert properties.channels == 2


def test_an_unsupported_format_says_so(tmp_path):
    mp3 = tmp_path / "song.mp3"
    mp3.write_bytes(b"not really an mp3")

    with pytest.raises(decode.DecodeError):
        decode.analyze(mp3)
    assert decode.is_supported(mp3) is False


def test_an_unreadable_file_raises_rather_than_reporting_zeroes(tmp_path):
    broken = tmp_path / "broken.wav"
    broken.write_bytes(b"RIFF____WAVEjunk")

    with pytest.raises(decode.DecodeError):
        decode.analyze(broken)


def test_a_truncated_flac_raises(tmp_path):
    truncated = tmp_path / "cut.flac"
    truncated.write_bytes(b"fLaC")

    with pytest.raises(decode.DecodeError):
        decode.analyze(truncated)


# -- producing PCM -------------------------------------------------------


def test_a_red_book_wav_is_copied_not_re_encoded(tmp_path):
    source = _write_wav(tmp_path / "a.wav")
    destination = tmp_path / "out.wav"

    decode.to_wav(source, destination)

    assert destination.read_bytes() == source.read_bytes()


def test_a_flac_is_decoded_by_the_real_bundled_tool(tmp_path):
    wav = _write_wav(tmp_path / "a.wav", seconds=0.5)
    flac = _encode_flac(wav, tmp_path / "a.flac")
    destination = tmp_path / "out.wav"

    decode.to_wav(flac, destination)

    assert decode.analyze(destination) == decode.analyze(wav)
    # lossless all the way round: the samples themselves survived
    with wave.open(str(destination), "rb") as out, wave.open(str(wav), "rb") as original:
        assert out.readframes(out.getnframes()) == original.readframes(original.getnframes())


def test_a_file_that_is_not_red_book_goes_through_audio_engine(tmp_path):
    """It used to be refused outright here, then went through SoX. Now a
    mono/stereo WAV/FLAC needing conversion goes through audio_engine
    instead, with no external tool involved at all."""
    source = _write_wav(tmp_path / "hires.wav", rate=48000, seconds=0.5)

    out = decode.to_wav(source, tmp_path / "out.wav")

    properties = decode.analyze(out)
    assert properties.is_red_book is True
    assert properties.duration_seconds == pytest.approx(0.5, abs=0.01)


def test_a_genuinely_corrupt_flac_reports_audio_engines_own_message(tmp_path):
    """STREAMINFO alone (what analyze() reads) can look perfectly valid
    while the actual audio frames after it are garbage -- this is what
    that looks like, and it has to surface as DecodeError, not an
    unhandled exception from soundfile."""
    wav = _write_wav(tmp_path / "a.wav", seconds=0.2)
    flac = _encode_flac(wav, tmp_path / "a.flac")
    # truncate well past STREAMINFO, into the actual audio frames
    data = flac.read_bytes()
    flac.write_bytes(data[: len(data) // 2])

    with pytest.raises(decode.DecodeError):
        decode.to_wav(flac, tmp_path / "out.wav")


# -- resampling and dithering, via audio_engine --------------------------


def test_a_hi_res_flac_is_converted_rather_than_refused(tmp_path):
    """The case that started this: a 48 kHz / 24-bit album, which is what
    a modern download normally is."""
    wav = tmp_path / "hires.wav"
    with wave.open(str(wav), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(3)
        handle.setframerate(48000)
        handle.writeframes(bytes(48000 * 2 * 3 * 2))
    flac = _encode_flac(wav, tmp_path / "hires.flac")
    assert decode.analyze(flac).is_red_book is False

    out = decode.to_wav(flac, tmp_path / "out.wav")

    properties = decode.analyze(out)
    assert properties.is_red_book is True
    # two seconds in, two seconds out -- a resampler that dropped or
    # invented audio would show up here before it showed up on a disc
    assert properties.duration_seconds == pytest.approx(2.0, abs=0.01)


def test_a_file_that_is_already_red_book_is_not_re_encoded(tmp_path):
    source = _write_wav(tmp_path / "ok.wav")
    destination = tmp_path / "out.wav"

    decode.to_wav(source, destination)

    assert destination.read_bytes() == source.read_bytes()


def test_a_surround_file_is_refused_and_says_why(tmp_path):
    """More than two channels is the one case audio_engine deliberately
    doesn't attempt -- see decode.py's own header for why that is a scope
    decision, not a limitation being routed around."""
    source = _write_wav(tmp_path / "surround.wav", rate=48000, channels=6)

    with pytest.raises(decode.DecodeError) as error:
        decode.to_wav(source, tmp_path / "out.wav")

    assert "6" in str(error.value)


def test_mp3_is_not_a_supported_format():
    assert decode.is_supported("album.mp3") is False


def test_an_unsupported_extension_is_not_offered():
    """Ogg Vorbis, WavPack, AIFF and AU used to go through SoX; nothing
    reads them any more, and that is a scope decision, not a gap."""
    assert decode.is_supported("track.ogg") is False
    assert decode.is_supported("track.wv") is False
    assert decode.is_supported("track.aiff") is False
