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

    def fail_if_run(*args, **kwargs):
        raise AssertionError("a file that is already Red Book must not be run through anything")

    decode.to_wav(source, destination, run=fail_if_run)

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


def test_a_file_that_is_not_red_book_is_refused_before_anything_runs(tmp_path):
    source = _write_wav(tmp_path / "hires.wav", rate=48000)

    def fail_if_run(*args, **kwargs):
        raise AssertionError("nothing should be launched for a file that cannot go on a CD as it is")

    with pytest.raises(decode.DecodeError) as error:
        decode.to_wav(source, tmp_path / "out.wav", run=fail_if_run)

    assert "48000" in str(error.value)


def test_a_failed_decode_reports_the_tools_own_first_line(tmp_path):
    wav = _write_wav(tmp_path / "a.wav", seconds=0.2)
    flac = _encode_flac(wav, tmp_path / "a.flac")

    class Result:
        returncode = 1
        stdout = ""
        stderr = "\n\nERROR: not a valid stream\n"

    with pytest.raises(decode.DecodeError) as error:
        decode.to_wav(flac, tmp_path / "out.wav", run=lambda *a, **k: Result())

    assert "not a valid stream" in str(error.value)


def test_the_decode_command_overwrites_quietly(tmp_path):
    command = decode.decode_command("flac", tmp_path / "in.flac", tmp_path / "out.wav")

    assert command[:4] == ["flac", "-d", "-f", "-s"]
    assert str(tmp_path / "out.wav") in command
    assert str(tmp_path / "in.flac") == command[-1]
