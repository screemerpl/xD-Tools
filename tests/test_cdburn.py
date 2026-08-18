"""Planning and writing an audio CD-R.

Everything here runs without a burner: the planning half needs nothing at
all, and `burn()` is driven through a fake process that writes into the
same log file the real one would. What cannot be faked -- the spelling
cdrdao wants for a Windows device, and the exact wording of its progress
output -- is marked as an assumption in cdburn.py itself and has to be
pinned against real hardware; the tests here cover the parsers being
tolerant when it does not match, which is the part that decides whether a
surprise costs a disc.
"""

import wave

import pytest

from mdtools import cdburn, decode


def _write_wav(path, *, seconds=10.0, rate=44100, bits=16, channels=2):
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(bits // 8)
        handle.setframerate(rate)
        handle.writeframes(b"\x00" * int(rate * seconds) * channels * (bits // 8))
    return path


def _sources(tmp_path, count=3, **kwargs):
    return [
        (_write_wav(tmp_path / f"{i}.wav", **kwargs), f"Track {i}", "Artist")
        for i in range(1, count + 1)
    ]


# -- the plan ------------------------------------------------------------


def test_a_plain_album_plans_cleanly(tmp_path):
    plan = cdburn.build_burn_plan(_sources(tmp_path), album="Album", artist="Artist")

    assert plan.can_burn is True
    assert plan.problems == []
    assert len(plan.tracks) == 3
    # 10s a track, plus the 2s lead-in that comes out of the disc as well
    assert plan.total_seconds == pytest.approx(32.0, abs=0.1)


def test_a_track_costs_whole_sectors_even_when_it_does_not_fill_the_last_one(tmp_path):
    """A track ends on a sector boundary, so rounding down would let a plan
    claim a disc holds slightly more than it does."""
    source = _write_wav(tmp_path / "odd.wav", seconds=5)
    plan = cdburn.build_burn_plan([(source, "T", "A")])
    properties = decode.analyze(source)

    exact = properties.frames / cdburn.SAMPLES_PER_SECTOR
    assert plan.tracks[0].sectors == int(exact) + (1 if exact % 1 else 0)


def test_a_hi_res_track_is_a_problem_naming_that_track(tmp_path):
    sources = _sources(tmp_path, 2)
    sources.append((_write_wav(tmp_path / "hi.wav", rate=48000), "Hi-res", "Artist"))

    plan = cdburn.build_burn_plan(sources)

    assert plan.can_burn is False
    problems = plan.problems_for(3)
    assert [problem.code for problem in problems] == [cdburn.NOT_RED_BOOK]
    assert "48000" in problems[0].detail


def test_a_track_under_four_seconds_is_refused(tmp_path):
    """Red Book's own minimum -- a shorter track is not a small track, it is
    a disc some players will not play."""
    plan = cdburn.build_burn_plan([(_write_wav(tmp_path / "blip.wav", seconds=2), "Blip", "A")])

    assert [problem.code for problem in plan.problems] == [cdburn.TOO_SHORT]


def test_an_unreadable_file_becomes_a_problem_rather_than_an_exception(tmp_path):
    broken = tmp_path / "broken.wav"
    broken.write_bytes(b"RIFFjunk")
    sources = _sources(tmp_path, 1) + [(broken, "Broken", "A")]

    plan = cdburn.build_burn_plan(sources)

    assert [problem.code for problem in plan.problems] == [cdburn.UNREADABLE]
    # still listed, so the dialog can show it in place rather than silently
    # dropping a track the user chose
    assert len(plan.tracks) == 2
    assert plan.tracks[1].sectors == 0


def test_every_problem_is_collected_not_just_the_first(tmp_path):
    """The dialog shows them all at once: stopping at the first would make
    fixing an album a matter of one failed attempt per bad file."""
    sources = [
        (_write_wav(tmp_path / "short.wav", seconds=1), "Short", "A"),
        (_write_wav(tmp_path / "hi.wav", rate=48000), "Hi", "A"),
    ]

    codes = {problem.code for problem in cdburn.build_burn_plan(sources).problems}

    assert codes == {cdburn.TOO_SHORT, cdburn.NOT_RED_BOOK}


def test_an_album_longer_than_the_disc_says_by_how_much(tmp_path):
    source = _write_wav(tmp_path / "long.wav", seconds=10)
    plan = cdburn.build_burn_plan(
        [(source, "T", "A")],
        capacity_sectors=5 * cdburn.SECTORS_PER_SECOND,
    )

    problem = next(p for p in plan.problems if p.code == cdburn.TOO_LONG_FOR_DISC)
    assert problem.detail.endswith("s")


def test_more_than_ninety_nine_tracks_is_a_problem(tmp_path):
    source = _write_wav(tmp_path / "one.wav", seconds=5)
    plan = cdburn.build_burn_plan([(source, f"T{i}", "A") for i in range(100)])

    assert any(problem.code == cdburn.TOO_MANY_TRACKS for problem in plan.problems)


def test_an_empty_plan_cannot_be_burned(tmp_path):
    plan = cdburn.build_burn_plan([])

    assert plan.can_burn is False
    assert [problem.code for problem in plan.problems] == [cdburn.NO_TRACKS]


# -- CD-Text -------------------------------------------------------------


def test_cd_text_strips_accents_the_way_the_minidisc_titles_do(tmp_path):
    result = cdburn.cd_text("Zażółć gęślą jaźń")

    assert result.text == "Zazolc gesla jazn"
    assert result.dropped == []


def test_cd_text_reports_what_it_could_not_carry(tmp_path):
    """A Japanese title comes back empty -- which the user needs to see
    before the disc is written, not after."""
    result = cdburn.cd_text("君の名は")

    assert result.text == ""
    assert result.dropped


# -- the toc file --------------------------------------------------------


def test_the_toc_describes_the_disc_and_every_track(tmp_path):
    plan = cdburn.build_burn_plan(_sources(tmp_path, 2), album="Album", artist="Artist")
    names = [cdburn.wav_name_for(1), cdburn.wav_name_for(2)]

    toc = cdburn.toc_text(plan, names)

    assert toc.startswith("CD_DA")
    assert toc.count("TRACK AUDIO") == 2
    assert 'TITLE "Album"' in toc
    assert 'PERFORMER "Artist"' in toc
    assert 'TITLE "Track 1"' in toc
    assert 'FILE "01.wav" 0' in toc


def test_the_toc_refers_to_bare_filenames_so_there_is_no_path_to_escape(tmp_path):
    plan = cdburn.build_burn_plan(_sources(tmp_path, 1))

    toc = cdburn.toc_text(plan, [cdburn.wav_name_for(1)])

    assert "\\" not in toc, "a Windows path in a format that escapes with backslash is a trap"
    assert str(tmp_path) not in toc


def test_a_quote_in_a_title_is_escaped(tmp_path):
    source = _write_wav(tmp_path / "a.wav")
    plan = cdburn.build_burn_plan([(source, 'The "Best" Song', "A")], album="A", artist="B")

    toc = cdburn.toc_text(plan, ["01.wav"])

    assert r'TITLE "The \"Best\" Song"' in toc


def test_the_toc_file_lands_beside_the_wavs(tmp_path):
    plan = cdburn.build_burn_plan(_sources(tmp_path, 1))

    path = cdburn.write_toc(plan, tmp_path, ["01.wav"])

    assert path.parent == tmp_path
    assert path.read_text(encoding="ascii").startswith("CD_DA")


def test_preparing_wavs_names_them_in_disc_order(tmp_path):
    plan = cdburn.build_burn_plan(_sources(tmp_path, 3))
    out = tmp_path / "burn"

    names = cdburn.prepare_wavs(plan, out)

    assert names == ["01.wav", "02.wav", "03.wav"]
    assert all((out / name).exists() for name in names)


def test_preparing_wavs_stops_at_the_first_failure(tmp_path):
    sources = _sources(tmp_path, 1) + [(_write_wav(tmp_path / "hi.wav", rate=48000), "Hi", "A")]
    plan = cdburn.build_burn_plan(sources)

    with pytest.raises(cdburn.BurnError):
        cdburn.prepare_wavs(plan, tmp_path / "burn")


# -- talking to cdrdao ---------------------------------------------------


def test_scanbus_output_is_read_for_device_names():
    text = (
        "cdrdao version 1.2.3 - (C) Andreas Mueller\n"
        "0,1,0 : HL-DT-ST, DVDRAM GP60NB60, 1.00\n"
        "1,0,0 : ASUS, BW-16D1HT, 3.02\n"
    )

    burners = cdburn.parse_scanbus(text)

    assert [b.device for b in burners] == ["0,1,0", "1,0,0"]
    assert "DVDRAM" in burners[0].description
    assert burners[1].display().startswith("1,0,0 - ")


def test_a_drive_letter_is_accepted_as_a_device_too():
    """Windows builds have been seen spelling devices both ways, and which
    one this cdrdao uses is exactly what is not being assumed."""
    assert [b.device for b in cdburn.parse_scanbus("D: : SOME, DRIVE, 1.0")] == ["D:"]


def test_scanbus_noise_is_not_mistaken_for_a_drive():
    assert cdburn.parse_scanbus("cdrdao version 1.2.3\nUsing libscg version 'schily-0.9'\n") == []


def test_disc_info_reads_blank_and_capacity():
    text = "CD-RW                : no\nCD-R empty           : yes\nTotal Capacity       : 79:59:74\n"

    info = cdburn.parse_disc_info(text)

    assert info.empty is True
    assert info.usable is True
    assert info.capacity_sectors == (79 * 60 + 59) * 75 + 74


def test_an_unrecognised_disc_info_is_unknown_rather_than_an_error():
    info = cdburn.parse_disc_info("something else entirely")

    assert info.empty is False
    assert info.capacity_sectors is None


def test_a_written_disc_is_not_usable_for_a_fresh_burn():
    info = cdburn.parse_disc_info("CD-R empty : no\n")

    assert info.usable is False


def test_the_burn_command_carries_speed_and_the_toc(tmp_path):
    command = cdburn.burn_command("cdrdao", "1,0,0", tmp_path / "disc.toc", speed=4)

    assert command[:2] == ["cdrdao", "write"]
    assert "--device" in command and "1,0,0" in command
    assert command[command.index("--speed") + 1] == "4"
    assert command[-1] == str(tmp_path / "disc.toc")
    assert "--simulate" not in command


def test_simulating_is_a_flag_on_the_same_command(tmp_path):
    command = cdburn.burn_command("cdrdao", "1,0,0", tmp_path / "disc.toc", simulate=True, eject=False)

    assert "--simulate" in command
    assert "--eject" not in command


def test_progress_is_read_from_the_latest_line_only():
    assert cdburn.parse_progress("Wrote 10 of 100 MB\nWrote 60 of 100 MB\n") == pytest.approx(0.6)


def test_unrecognised_output_means_no_progress_information_not_a_failure():
    """A burn that finishes correctly with a motionless bar is a cosmetic
    problem; one that stops because the output read differently would be a
    wasted disc."""
    assert cdburn.parse_progress("Starting write at speed 4...") is None
    assert cdburn.parse_progress("") is None


# -- driving the burn ----------------------------------------------------


@pytest.fixture
def pretend_cdrdao_exists(monkeypatch):
    """There is no cdrdao on this machine yet (the binary is bundled once it
    has been tried against a real burner), and these tests are about the
    driving loop rather than about finding the tool."""
    monkeypatch.setattr(cdburn, "cdrdao_path", lambda: "cdrdao")


class _FakeProcess:
    """A cdrdao that writes the given chunks into the log, one per poll."""

    def __init__(self, chunks, returncode=0, never_ends=False):
        self._chunks = list(chunks)
        self._returncode = returncode
        self._never_ends = never_ends
        self.killed = False
        self.log = None

    def __call__(self, command, stdout=None, stderr=None, creationflags=0):
        self.command = command
        self.log = stdout
        return self

    def poll(self):
        if self._chunks:
            self.log.write(self._chunks.pop(0))
            self.log.flush()
            return None
        if self._never_ends:
            return None
        return self._returncode

    def kill(self):
        self.killed = True

    def wait(self):
        return self._returncode

    @property
    def returncode(self):
        return self._returncode


def test_a_successful_burn_reports_progress_and_removes_its_log(tmp_path, pretend_cdrdao_exists):
    toc = tmp_path / "disc.toc"
    toc.write_text("CD_DA\n", encoding="ascii")
    process = _FakeProcess(["Wrote 25 of 100 MB\n", "Wrote 100 of 100 MB\n"])
    seen = []

    cdburn.burn(
        "1,0,0",
        toc,
        on_progress=seen.append,
        popen=process,
        sleep=lambda _s: None,
    )

    assert seen[-1] == 1.0
    assert max(seen) == 1.0 and any(0 < value < 1 for value in seen)
    assert not (tmp_path / "disc.log").exists()


def test_a_failed_burn_keeps_its_log_and_reports_the_reason(tmp_path, pretend_cdrdao_exists):
    toc = tmp_path / "disc.toc"
    toc.write_text("CD_DA\n", encoding="ascii")
    process = _FakeProcess(["Wrote 10 of 100 MB\n", "ERROR: Cannot open SCSI device\n"], returncode=1)

    with pytest.raises(cdburn.BurnError) as error:
        cdburn.burn("1,0,0", toc, popen=process, sleep=lambda _s: None)

    assert "Cannot open SCSI device" in str(error.value)
    # the only account of what went wrong on a disc nothing can read back
    assert (tmp_path / "disc.log").exists()


def test_cancelling_kills_the_burner(tmp_path, pretend_cdrdao_exists):
    toc = tmp_path / "disc.toc"
    toc.write_text("CD_DA\n", encoding="ascii")
    process = _FakeProcess(["Wrote 1 of 100 MB\n"], never_ends=True)

    with pytest.raises(cdburn.BurnCancelled):
        cdburn.burn(
            "1,0,0",
            toc,
            should_cancel=lambda: True,
            popen=process,
            sleep=lambda _s: None,
        )

    assert process.killed is True


def test_burning_without_the_tool_says_which_tool(monkeypatch, tmp_path):
    monkeypatch.setattr(cdburn, "cdrdao_path", lambda: None)

    with pytest.raises(cdburn.BurnError) as error:
        cdburn.burn("1,0,0", tmp_path / "disc.toc")

    assert "cdrdao" in str(error.value)


def test_missing_tools_names_cdrdao_when_it_is_absent(monkeypatch):
    monkeypatch.setattr(cdburn, "cdrdao_path", lambda: None)

    assert "cdrdao" in cdburn.missing_tools()
