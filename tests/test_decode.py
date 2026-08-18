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


def test_a_file_that_is_not_red_book_goes_through_the_resampler(tmp_path):
    """It used to be refused outright here. That was right while nothing
    could resample; with SoX bundled, refusing an ordinary 48 kHz download
    would be refusing the common case."""
    launched = []
    source = _write_wav(tmp_path / "hires.wav", rate=48000)

    def record(command, **kwargs):
        launched.append(command)

        class Result:
            returncode = 0
            stdout = stderr = ""

        (tmp_path / "out.wav").write_bytes(b"")
        return Result()

    decode.to_wav(source, tmp_path / "out.wav", run=record)

    assert launched and "rate" in launched[0]


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


# -- resampling with SoX -------------------------------------------------


def _sox_or_skip():
    if decode.sox_path() is None:
        pytest.skip("SoX is not bundled on this platform")


def test_a_hi_res_flac_is_converted_rather_than_refused(tmp_path):
    """The case that started this: a 48 kHz / 24-bit album, which is what
    a modern download normally is."""
    _sox_or_skip()
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


def test_a_file_that_is_already_red_book_is_not_run_through_the_resampler(tmp_path):
    _sox_or_skip()
    source = _write_wav(tmp_path / "ok.wav")

    def fail_if_run(*args, **kwargs):
        raise AssertionError("nothing to convert")

    decode.to_wav(source, tmp_path / "out.wav", run=fail_if_run)


def test_without_sox_a_hi_res_file_is_refused_and_says_why(tmp_path, monkeypatch):
    monkeypatch.setattr(decode, "sox_path", lambda: None)
    source = _write_wav(tmp_path / "hires.wav", rate=48000)

    with pytest.raises(decode.DecodeError) as error:
        decode.to_wav(source, tmp_path / "out.wav")

    assert "48000" in str(error.value)
    assert "SoX" in str(error.value)


def test_the_convert_command_resamples_dithers_and_sets_the_depth():
    command = decode.convert_command("sox", tmp_pathlike("in.flac"), tmp_pathlike("out.wav"))

    assert command[0] == "sox"
    assert command[command.index("-b") + 1] == "16"
    assert command[command.index("-c") + 1] == "2"
    # effects come after the output file -- SoX's own argument order
    assert command[-4:] == ["rate", "-v", "44100", "dither"]


def tmp_pathlike(name):
    from pathlib import Path

    return Path(name)


def test_a_format_sox_reads_but_this_module_cannot_parse_itself(tmp_path):
    """Ogg Vorbis has no header this project knows how to read, so its
    length comes from SoX -- and the length is what decides how much of the
    disc a track takes."""
    _sox_or_skip()
    ogg = tmp_path / "tone.ogg"
    subprocess.run(
        [decode.sox_path(), "-n", "-r", "44100", "-c", "2", str(ogg), "synth", "3", "sine", "440"],
        capture_output=True,
        check=True,
    )

    properties = decode.analyze(ogg)

    assert properties.sample_rate == 44100
    assert properties.channels == 2
    assert properties.duration_seconds == pytest.approx(3.0, abs=0.05)


def test_mp3_is_not_offered_because_this_build_of_sox_cannot_read_one():
    """Its format list says mp3, but decoding needs libmad loaded at
    runtime and the official package does not ship it -- promising it here
    would turn a clear "unsupported" into a failure half way through a
    burn."""
    assert ".mp3" not in decode.CONVERTIBLE_SUFFIXES
    assert decode.is_supported("album.mp3") is False


def test_sox_is_kept_apart_from_the_64_bit_tools():
    """Its DLLs are 32-bit and share names with the ones cd-paranoia and
    flac need -- unpacking it alongside them overwrote libwinpthread-1.dll
    once already."""
    sox = decode.sox_path()
    if sox is None:
        pytest.skip("SoX is not bundled on this platform")

    from pathlib import Path

    from mdtools import cdrip

    assert Path(sox).parent == cdrip.tools_dir() / "sox"
    assert not (cdrip.tools_dir() / "libsox-3.dll").exists()
