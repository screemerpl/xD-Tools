"""Planning and writing an audio CD-R.

Everything here runs without a burner: the planning half needs nothing at
all, and `burn()` is driven through a fake process that writes into the
same log file the real one would.

Two fixtures below are *real* output, captured from the bundled
cdrecord 3.02a10 on a machine with an HL-DT-ST DVDRAM GP20N attached --
the same reason test_cdrip.py keeps `REAL_TOC_OUTPUT`: a hand-written
sample can agree with the parser perfectly and still not match what the
binary actually prints.
"""

import wave

import pytest

from mdtools import cdburn, decode

# `cdrecord -scanbus`, verbatim (stdout; the privilege warnings it also
# prints go to stderr).
REAL_SCANBUS_OUTPUT = """Cdrecord-ProDVD-ProBD-Clone 3.02a10 2021/07/23 (i686-pc-cygwin) Copyright (C) 1995-2019 Joerg Schilling
Using libscg version 'schily-0.9'.
scsibus0:
\t0,0,0\t  0) 'HL-DT-ST' 'DVDRAM GP20N    ' '1.02' Removable CD-ROM
\t0,1,0\t  1) *
\t0,2,0\t  2) *
\t0,3,0\t  3) *
\t0,4,0\t  4) *
\t0,5,0\t  5) *
\t0,6,0\t  6) *
\t0,7,0\t  7) HOST ADAPTOR
"""

# `cdrecord dev=0,0,0 -minfo` with nothing in the drive: exit status 255.
REAL_NO_DISC_OUTPUT = """cdrecord: Input/output error. test unit ready: scsi sendcmd: no error
CDB:  00 00 00 00 00 00
status: 0x2 (CHECK CONDITION)
Sense Bytes: 70 00 02 00 00 00 00 0E 00 00 00 00 3A 01 00 00 00 00
Sense Key: 0x2 Not Ready, Segment 0
Sense Code: 0x3A Qual 0x01 (medium not present - tray closed) Fru 0x0
Sense flags: Blk 0 (not valid)
cmd finished after 0.000s timeout 40s
cdrecord: No disk / Wrong disk!
"""


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


def test_a_hi_res_track_is_a_problem_naming_that_track(tmp_path, monkeypatch):
    # with no resampler available; with one it becomes a note instead, see
    # further down
    monkeypatch.setattr(decode, "can_convert", lambda: False)
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


def test_every_problem_is_collected_not_just_the_first(tmp_path, monkeypatch):
    """The dialog shows them all at once: stopping at the first would make
    fixing an album a matter of one failed attempt per bad file."""
    monkeypatch.setattr(decode, "can_convert", lambda: False)
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


def test_cd_text_strips_accents_the_way_the_minidisc_titles_do():
    result = cdburn.cd_text("Zażółć gęślą jaźń")

    assert result.text == "Zazolc gesla jazn"
    assert result.dropped == []


def test_cd_text_reports_what_it_could_not_carry():
    """A Japanese title comes back empty -- which the user needs to see
    before the disc is written, not after."""
    result = cdburn.cd_text("君の名は")

    assert result.text == ""
    assert result.dropped


# -- the *.inf files cdrecord reads CD-Text from -------------------------


def test_each_track_gets_an_inf_file_beside_its_wav(tmp_path):
    plan = cdburn.build_burn_plan(_sources(tmp_path, 2), album="Album", artist="Artist")
    out = tmp_path / "burn"
    out.mkdir()

    names = cdburn.write_inf_files(plan, out)

    assert names == ["01.inf", "02.inf"]
    # cdrecord matches an .inf to its audio file by the shared prefix, so
    # these two namings must stay in step
    assert [cdburn.wav_name_for(1), cdburn.wav_name_for(2)] == ["01.wav", "02.wav"]
    assert (out / "01.inf").exists()


def test_the_inf_file_carries_the_album_and_the_track(tmp_path):
    plan = cdburn.build_burn_plan(
        [(_write_wav(tmp_path / "a.wav"), "Feel Invincible", "Skillet")],
        album="Unleashed",
        artist="Skillet",
    )

    text = cdburn.inf_text(plan, 1)

    assert "Albumtitle=\t'Unleashed'" in text
    assert "Albumperformer=\t'Skillet'" in text
    assert "Tracktitle=\t'Feel Invincible'" in text
    assert "Performer=\t'Skillet'" in text
    assert "Tracknumber=\t1" in text


def test_a_track_with_no_artist_of_its_own_is_credited_to_the_album(tmp_path):
    plan = cdburn.build_burn_plan(
        [(_write_wav(tmp_path / "a.wav"), "Song", "")], album="Album", artist="Skillet"
    )

    assert "Performer=\t'Skillet'" in cdburn.inf_text(plan, 1)


def test_an_apostrophe_inside_a_title_is_left_alone(tmp_path):
    """cdrecord's own rule: the value runs from the first quote on the line
    to the last, and needs no escaping in between. Escaping it would put a
    backslash on the disc."""
    plan = cdburn.build_burn_plan(
        [(_write_wav(tmp_path / "a.wav"), "Rock 'n' Roll", "A")], album="Album", artist="A"
    )

    assert "Tracktitle=\t'Rock 'n' Roll'" in cdburn.inf_text(plan, 1)


def test_a_trailing_apostrophe_is_dropped_rather_than_escaped(tmp_path):
    """One at the very end would swallow the closing quote, and there is no
    escape sequence to reach for."""
    plan = cdburn.build_burn_plan(
        [(_write_wav(tmp_path / "a.wav"), "Nothin'", "A")], album="Album", artist="A"
    )

    assert "Tracktitle=\t'Nothin'" in cdburn.inf_text(plan, 1)
    assert "Nothin''" not in cdburn.inf_text(plan, 1)


def test_a_japanese_title_reaches_the_inf_file_empty_rather_than_broken(tmp_path):
    plan = cdburn.build_burn_plan(
        [(_write_wav(tmp_path / "a.wav"), "君の名は", "A")], album="Album", artist="A"
    )

    text = cdburn.inf_text(plan, 1)
    assert "Tracktitle=\t''" in text
    text.encode("ascii")  # must not raise: CD-Text carries nothing else


def test_preparing_wavs_names_them_in_disc_order(tmp_path):
    plan = cdburn.build_burn_plan(_sources(tmp_path, 3))
    out = tmp_path / "burn"

    names = cdburn.prepare_wavs(plan, out)

    assert names == ["01.wav", "02.wav", "03.wav"]
    assert all((out / name).exists() for name in names)


def test_preparing_wavs_stops_at_the_first_failure(tmp_path):
    """A file nothing can read, rather than one that merely needs
    resampling -- that one is converted now."""
    broken = tmp_path / "broken.wav"
    broken.write_bytes(b"RIFFjunk")
    sources = _sources(tmp_path, 1) + [(broken, "Broken", "A")]
    plan = cdburn.build_burn_plan(sources)

    with pytest.raises(cdburn.BurnError):
        cdburn.prepare_wavs(plan, tmp_path / "burn")


# -- talking to cdrecord -------------------------------------------------


def test_the_real_scanbus_output_yields_exactly_the_one_drive():
    burners = cdburn.parse_scanbus(REAL_SCANBUS_OUTPUT)

    assert [b.device for b in burners] == ["0,0,0"]
    assert burners[0].description == "HL-DT-ST DVDRAM GP20N 1.02"
    assert burners[0].display() == "0,0,0 - HL-DT-ST DVDRAM GP20N 1.02"


def test_empty_slots_and_the_host_adaptor_are_not_drives():
    """Every scsibus line looks like a device; seven of the nine in the real
    output are not one."""
    text = "\t0,1,0\t  1) *\n\t0,7,0\t  7) HOST ADAPTOR\n"

    assert cdburn.parse_scanbus(text) == []


def test_scanbus_banner_lines_are_not_mistaken_for_a_drive():
    assert cdburn.parse_scanbus("Using libscg version 'schily-0.9'.\nscsibus0:\n") == []


def test_an_empty_drive_is_read_as_having_no_disc():
    """Captured from the bundled binary with the tray closed and empty --
    it also exits 255, but the message is what this reads."""
    info = cdburn.parse_disc_info(REAL_NO_DISC_OUTPUT)

    assert info.present is False
    assert info.usable is False


def test_a_blank_disc_reports_its_capacity():
    text = "Mounted media type: CD-R\ndisk status: empty\nATIP start of lead out: 359849 (79:57/74)\n"

    info = cdburn.parse_disc_info(text)

    assert info.present is True
    assert info.empty is True
    assert info.usable is True
    assert info.capacity_sectors == 359849


def test_a_disc_that_already_holds_something_is_not_usable():
    info = cdburn.parse_disc_info("Mounted media type: CD-R\ndisk status: complete\n")

    assert info.present is True
    assert info.usable is False


def test_unrecognised_disc_info_does_not_block_a_burn():
    """The drive is the last word; refusing on the strength of a line that
    read differently would be worse than letting the burn report itself."""
    info = cdburn.parse_disc_info("something else entirely")

    assert info.present is True
    assert info.usable is True
    assert info.capacity_sectors is None


def test_the_burn_command_writes_disc_at_once_audio_with_cd_text():
    command = cdburn.burn_command("cdrecord", "0,0,0", ["01.wav", "02.wav"], speed=4)

    assert command[0] == "cdrecord"
    assert "dev=0,0,0" in command
    assert "speed=4" in command
    # -dao is the mode CD-Text is written in; -text -useinfo is what makes
    # cdrecord read the .inf beside each track
    for flag in ("-dao", "-audio", "-pad", "-text", "-useinfo"):
        assert flag in command
    assert command[-2:] == ["01.wav", "02.wav"]
    assert "-dummy" not in command


def test_simulating_is_a_flag_on_the_same_command():
    command = cdburn.burn_command("cdrecord", "0,0,0", ["01.wav"], simulate=True, eject=False)

    assert "-dummy" in command
    assert "-eject" not in command


def test_progress_is_read_from_the_latest_track_line():
    text = "Track 01:   10 of   45 MB written (fifo 100%) [buf  97%]  8.0x.\n"

    assert cdburn.parse_progress(text) == pytest.approx(10 / 45)


def test_progress_across_the_disc_counts_the_tracks_already_written():
    """cdrecord counts within a track; the bar is about the disc."""
    text = "Track 02:   5 of   10 MB written\n"

    assert cdburn.parse_progress(text, [10.0, 10.0]) == pytest.approx(0.75)


def test_unrecognised_output_means_no_progress_information_not_a_failure():
    """A burn that finishes correctly with a motionless bar is a cosmetic
    problem; one that stops because the output read differently would be a
    wasted disc."""
    assert cdburn.parse_progress("Starting new track at sector: 0") is None
    assert cdburn.parse_progress("") is None


def test_track_sizes_come_from_the_plan(tmp_path):
    plan = cdburn.build_burn_plan(_sources(tmp_path, 2))

    sizes = cdburn.track_megabytes(plan)

    assert len(sizes) == 2
    # 10 seconds of Red Book audio is a little over 1.7 MB
    assert sizes[0] == pytest.approx(1.76, abs=0.05)


# -- driving the burn ----------------------------------------------------


class _FakeProcess:
    """A cdrecord that writes the given chunks into the log, one per poll."""

    def __init__(self, chunks, returncode=0, never_ends=False):
        self._chunks = list(chunks)
        self._returncode = returncode
        self._never_ends = never_ends
        self.killed = False
        self.log = None
        self.cwd = None

    def __call__(self, command, stdout=None, stderr=None, cwd=None, creationflags=0):
        self.command = command
        self.log = stdout
        self.cwd = cwd
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


@pytest.fixture
def cdrecord_at(monkeypatch):
    monkeypatch.setattr(cdburn, "cdrecord_path", lambda: "cdrecord")


def test_a_successful_burn_reports_progress_and_removes_its_log(tmp_path, cdrecord_at):
    process = _FakeProcess(
        ["Track 01:   1 of   10 MB written\n", "Track 01:   10 of   10 MB written\n"]
    )
    seen = []

    cdburn.burn(
        "0,0,0",
        tmp_path,
        ["01.wav"],
        megabytes=[10.0],
        on_progress=seen.append,
        popen=process,
        sleep=lambda _s: None,
    )

    assert seen[-1] == 1.0
    assert any(0 < value < 1 for value in seen)
    assert not (tmp_path / "burn.log").exists()


def test_the_burner_runs_in_the_folder_holding_the_audio(tmp_path, cdrecord_at):
    """It is given bare filenames: the bundled Windows build is a Cygwin
    one, and each .inf has to sit beside its WAV regardless."""
    process = _FakeProcess([])

    cdburn.burn("0,0,0", tmp_path, ["01.wav", "02.wav"], popen=process, sleep=lambda _s: None)

    assert process.cwd == str(tmp_path)
    assert process.command[-2:] == ["01.wav", "02.wav"]


def test_a_failed_burn_keeps_its_log_and_reports_the_reason(tmp_path, cdrecord_at):
    process = _FakeProcess(
        ["Track 01:   1 of   10 MB written\n", "cdrecord: Cannot open SCSI driver.\n"], returncode=1
    )

    with pytest.raises(cdburn.BurnError) as error:
        cdburn.burn("0,0,0", tmp_path, ["01.wav"], popen=process, sleep=lambda _s: None)

    assert "Cannot open SCSI driver" in str(error.value)
    # the only account of what went wrong on a disc nothing can read back
    assert (tmp_path / "burn.log").exists()


def test_the_privilege_warnings_are_not_reported_as_the_failure(tmp_path, cdrecord_at):
    """cdrecord prints six of those on every run on this machine, where it
    nonetheless talks to the drive perfectly well -- blaming one of them
    would send the user chasing a permissions problem they do not have."""
    process = _FakeProcess(
        [
            "cdrecord: Cannot load media.\n",
            "cdrecord: Insufficient 'device' privileges. You may not be able to send all needed SCSI commands\n",
        ],
        returncode=1,
    )

    with pytest.raises(cdburn.BurnError) as error:
        cdburn.burn("0,0,0", tmp_path, ["01.wav"], popen=process, sleep=lambda _s: None)

    assert "Cannot load media" in str(error.value)


def test_cancelling_kills_the_burner(tmp_path, cdrecord_at):
    process = _FakeProcess(["Track 01:   1 of  10 MB written\n"], never_ends=True)

    with pytest.raises(cdburn.BurnCancelled):
        cdburn.burn(
            "0,0,0",
            tmp_path,
            ["01.wav"],
            should_cancel=lambda: True,
            popen=process,
            sleep=lambda _s: None,
        )

    assert process.killed is True


def test_burning_without_the_tool_says_which_tool(monkeypatch, tmp_path):
    monkeypatch.setattr(cdburn, "cdrecord_path", lambda: None)

    with pytest.raises(cdburn.BurnError) as error:
        cdburn.burn("0,0,0", tmp_path, ["01.wav"])

    assert "cdrecord" in str(error.value)


def test_missing_tools_names_cdrecord_when_it_is_absent(monkeypatch):
    monkeypatch.setattr(cdburn, "cdrecord_path", lambda: None)

    assert "cdrecord" in cdburn.missing_tools()


# -- the bundled binary itself -------------------------------------------


def test_the_bundled_cdrecord_runs_and_identifies_itself():
    """The same rigour as test_cdrip.py's bundled-encoder tests: a binary
    that is present but will not start is worse than one that is missing,
    because everything above it looks fine until a disc is at stake."""
    import subprocess

    tool = cdburn.cdrecord_path()
    if tool is None:
        pytest.skip("cdrecord is not bundled on this platform")

    result = subprocess.run([tool, "-version"], capture_output=True, text=True)

    assert result.returncode == 0
    assert "Cdrecord" in result.stdout


def test_only_the_burn_command_can_eject_a_disc():
    """Found by running a dry run with -eject: cdrecord opens the tray even
    when the run fails. On an inspection command that would mean looking at
    the drive spat the disc out."""
    assert "-eject" not in cdburn.scan_command("cdrecord")
    assert "-eject" not in cdburn.disc_info_command("cdrecord", "0,0,0")
    assert "-eject" in cdburn.burn_command("cdrecord", "0,0,0", ["01.wav"], eject=True)


# `cdrecord dev=0,0,0 -minfo` with a blank CD-R in the drive, exit 0.
REAL_BLANK_DISC_OUTPUT = """Mounted media class:      CD
Mounted media type:       CD-R
Disk Is not erasable
data type:                standard
disk status:              empty
session status:           empty
first track:              1
last start of lead in: -11634
last start of lead out: 359846
Track  Sess Type   Start Addr End Addr   Size
==============================================
    1     1 Blank  0          359843     359844
Next writable address:              0
Remaining writable size:            359844
"""

# From a real `-dummy` run of the burn command this module builds. Note the
# first line of each track carries no fifo/buf suffix at all.
REAL_PROGRESS_OUTPUT = """Starting new track at sector: 0
Track 01:    0 of    3 MB written.
Track 01:    1 of    3 MB written (fifo 100%)   9.7x.
Track 01:    2 of    3 MB written (fifo 100%) [buf  90%]  10.3x.
Track 01: Total bytes read/written: 3528000/3528000 (1500 sectors).
Starting new track at sector: 1500
Track 02:    1 of    3 MB written (fifo 100%)   9.7x.
"""


def test_a_real_blank_disc_reports_itself_empty_and_writable():
    info = cdburn.parse_disc_info(REAL_BLANK_DISC_OUTPUT)

    assert info.present is True
    assert info.empty is True
    assert info.usable is True
    # what the drive says can actually be written, not the lead-out address
    # two sectors above it
    assert info.capacity_sectors == 359844


def test_capacity_falls_back_to_the_lead_out_when_nothing_better_is_offered():
    info = cdburn.parse_disc_info("disk status: empty\nlast start of lead out: 359846\n")

    assert info.capacity_sectors == 359846


def test_the_real_progress_output_is_read_as_a_fraction_of_the_disc():
    """Two 3 MB tracks: the last line seen is track 2 at 1 of 3 MB, so four
    of the disc's six megabytes are done."""
    assert cdburn.parse_progress(REAL_PROGRESS_OUTPUT, [3.0, 3.0]) == pytest.approx(4 / 6)


def test_the_lines_around_the_progress_lines_are_not_mistaken_for_progress():
    text = "Starting new track at sector: 1500\nTrack 01: Total bytes read/written: 3528000/3528000\n"

    assert cdburn.parse_progress(text) is None


# -- a wrong sample rate: a problem, or a step on the way? ---------------


def test_a_hi_res_track_is_only_a_problem_when_nothing_can_resample(tmp_path, monkeypatch):
    monkeypatch.setattr(decode, "can_convert", lambda: False)
    sources = [(_write_wav(tmp_path / "hi.wav", rate=48000), "Hi-res", "A")]

    plan = cdburn.build_burn_plan(sources)

    assert [p.code for p in plan.problems] == [cdburn.NOT_RED_BOOK]
    assert plan.can_burn is False


def test_with_a_resampler_the_same_track_is_a_note_and_the_disc_can_still_be_burned(tmp_path, monkeypatch):
    """The whole point of bundling SoX: a 48 kHz / 24-bit album is what a
    download normally is, and it is converted on the way to the disc."""
    monkeypatch.setattr(decode, "can_convert", lambda: True)
    sources = [(_write_wav(tmp_path / "hi.wav", rate=48000), "Hi-res", "A")]

    plan = cdburn.build_burn_plan(sources)

    assert plan.problems == []
    assert plan.can_burn is True
    assert [note.code for note in plan.notes_for(1)] == [cdburn.RESAMPLED]
    assert "48000" in plan.notes_for(1)[0].detail


def test_a_note_never_disables_the_burn_button(tmp_path, monkeypatch):
    monkeypatch.setattr(decode, "can_convert", lambda: True)
    sources = _sources(tmp_path, 1) + [(_write_wav(tmp_path / "hi.wav", rate=48000), "Hi", "A")]

    plan = cdburn.build_burn_plan(sources)

    assert plan.notes and plan.can_burn is True


def test_a_hi_res_track_takes_the_disc_space_it_will_take_after_conversion(tmp_path):
    """Found by comparing a real burn with the dialog that planned it: the
    plan said 45:29 for twelve tracks that came off the disc as 41:45 --
    exactly 48000/44100. Sectors were being counted as frames/588, which
    only holds at 44.1 kHz; what reaches the CD is the resampled audio."""
    source = _write_wav(tmp_path / "hi.wav", seconds=60, rate=48000)
    plan = cdburn.build_burn_plan([(source, "Hi-res", "A")])

    # a minute of audio is a minute of disc, whatever it was sampled at
    assert plan.tracks[0].sectors == 60 * cdburn.SECTORS_PER_SECOND
    assert plan.total_seconds == pytest.approx(62.0, abs=0.1)  # plus the lead-in


def test_a_44100_track_is_unaffected_by_that(tmp_path):
    """The two ways of counting agree exactly at 44.1 kHz, which is why the
    error hid until a hi-res album turned up."""
    source = _write_wav(tmp_path / "ok.wav", seconds=10)
    plan = cdburn.build_burn_plan([(source, "T", "A")])
    properties = decode.analyze(source)

    assert plan.tracks[0].sectors == properties.frames // cdburn.SAMPLES_PER_SECTOR
