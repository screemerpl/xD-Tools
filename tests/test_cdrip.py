"""Reading an audio CD: everything that can be checked without a disc.

The two functions that actually spawn cd-paranoia are exercised against a
fake process; the one that spawns flac is exercised for real, because the
bundled encoder is in the repository and what it does with a non-ASCII tag
on Windows is exactly the sort of thing that has to be proven rather than
assumed.
"""

from __future__ import annotations

import struct
import subprocess
import sys
from pathlib import Path

import pytest

from mdtools import cdrip

# The TOC of Nirvana's Nevermind, written in `cd-paranoia -Q` output format
# -- the disc whose identifier was verified against musicbrainz.org. The
# format itself is confirmed byte-for-byte against the bundled binary's real
# output; see REAL_TOC_OUTPUT below, captured from it.
NEVERMIND_TOC_OUTPUT = """
cdparanoia III release 10.2 libcdio 2.2.0 x86_64-w64-mingw32
(C) 2001 Monty <monty@xiph.org> and Xiphophorus

Table of contents (audio tracks only):
track        length               begin        copy pre ch
===========================================================
  1.    22617 [05:01.42]        0 [00:00.00]    no   no  2
  2.    19120 [04:14.70]    22617 [05:01.42]    no   no  2
  3.    16430 [03:39.05]    41737 [09:16.37]    no   no  2
  4.    13785 [03:03.60]    58167 [12:55.42]    no   no  2
  5.    19273 [04:16.73]    71952 [15:59.27]    no   no  2
  6.    13277 [02:57.02]    91225 [20:16.25]    no   no  2
  7.    10728 [02:23.03]   104502 [23:13.27]    no   no  2
  8.    16785 [03:43.60]   115230 [25:36.30]    no   no  2
  9.    11767 [02:36.67]   132015 [29:20.15]    no   no  2
 10.    15938 [03:32.38]   143782 [31:57.07]    no   no  2
 11.    14727 [03:16.27]   159720 [35:29.45]    no   no  2
 12.    92660 [20:35.35]   174447 [38:45.72]    no   no  2
TOTAL  267107 [59:21.32]    (audio only)
"""


# Captured verbatim from the bundled cd-paranoia.exe reading a real disc
# (Skillet, Unleashed) in a USB drive -- banner, blank lines, trailing space
# and all. NEVERMIND_TOC_OUTPUT above is written by hand to match this shape;
# this one proves the shape.
REAL_TOC_OUTPUT = """cdparanoia III release 10.2 libcdio 2.2.0 x86_64-w64-mingw32
(C) 2001 Monty <monty@xiph.org> and Xiphophorus
(C) 2004, 2005, 2008 Rocky Bernstein <rocky@gnu.org>
(C) 2014 Robert Kausch <robert.kausch@freac.org>

Report bugs to bug-libcdio@gnu.org


Table of contents (audio tracks only):
track        length               begin        copy pre ch
===========================================================
  1.    17245 [03:49.70]        0 [00:00.00]    no   no  2
  2.    16019 [03:33.44]    17245 [03:49.70]    no   no  2
  3.    16939 [03:45.64]    33264 [07:23.39]    no   no  2
  4.    15662 [03:28.62]    50203 [11:09.28]    no   no  2
  5.    16191 [03:35.66]    65865 [14:38.15]    no   no  2
  6.    14880 [03:18.30]    82056 [18:14.06]    no   no  2
  7.    15345 [03:24.45]    96936 [21:32.36]    no   no  2
  8.    16063 [03:34.13]   112281 [24:57.06]    no   no  2
  9.    14734 [03:16.34]   128344 [28:31.19]    no   no  2
 10.    15696 [03:29.21]   143078 [31:47.53]    no   no  2
 11.    16955 [03:46.05]   158774 [35:16.74]    no   no  2
 12.    17405 [03:52.05]   175729 [39:03.04]    no   no  2
TOTAL  193134 [42:55.09]    (audio only)

"""


def _toc() -> cdrip.DiscToc:
    return cdrip.parse_toc(NEVERMIND_TOC_OUTPUT)


def test_the_parser_handles_real_output_from_the_bundled_binary():
    """The banner, the blank lines, the ruler, the TOTAL row and a stray
    trailing space are all things the parser has to step over rather than
    trip on -- and all things a hand-written fixture could get wrong."""
    toc = cdrip.parse_toc(REAL_TOC_OUTPUT)

    assert len(toc.tracks) == 12
    assert toc.tracks[0].first_lba == 0
    assert toc.tracks[11].sectors == 17405
    # The TOTAL row is 193134 sectors, which the lead-out has to agree with.
    assert toc.leadout_lba == 193134


def test_the_real_discs_identifier_is_the_one_musicbrainz_answered_to():
    """Second live-verified vector, alongside Nevermind's: this TOC came off
    an actual disc through the bundled binary, and musicbrainz.org resolved
    this identifier to Skillet's Unleashed, 12 tracks -- matching the disc."""
    assert cdrip.parse_toc(REAL_TOC_OUTPUT).musicbrainz_disc_id() == "_dODxWGqmW9J1Ez3UiD8Z1z2JpY-"


# --- the table of contents -------------------------------------------


def test_parse_toc_reads_every_track_with_its_length_and_start():
    toc = _toc()
    assert [t.number for t in toc.tracks] == list(range(1, 13))
    assert toc.tracks[0].sectors == 22617
    assert toc.tracks[0].first_lba == 0
    assert toc.tracks[11].first_lba == 174447


def test_parse_toc_derives_the_leadout_from_the_last_track():
    """Nothing prints the lead-out as such, but it is exactly where the last
    track ends -- and every disc identifier needs it."""
    toc = _toc()
    assert toc.leadout_lba == 174447 + 92660


def test_parse_toc_rejects_output_with_no_tracks_in_it():
    with pytest.raises(cdrip.CdRipError):
        cdrip.parse_toc("Unable find or access a CD-ROM drive with an audio CD in it.")


def test_track_lengths_convert_to_seconds_at_75_sectors_each():
    toc = _toc()
    assert toc.tracks[0].seconds == pytest.approx(22617 / 75)
    assert toc.total_seconds == pytest.approx(267107 / 75)


# --- disc identity ----------------------------------------------------


def test_musicbrainz_disc_id_matches_the_value_the_live_service_returns():
    """The one hard-coded expectation in this file that came from outside
    it: this TOC was sent to musicbrainz.org, which resolved this exact
    string to Nirvana's Nevermind. If the hashing is ever "simplified", this
    is what catches it."""
    assert _toc().musicbrainz_disc_id() == "I5l9cCSFccLKFEKS.7wqSZAorPU-"


def test_disc_id_uses_msf_frame_offsets_not_raw_lbas():
    toc = _toc()
    assert toc.frame_offsets()[0] == 150  # LBA 0 is MSF 00:02.00
    assert toc.leadout_offset() == toc.leadout_lba + 150


def test_disc_id_pads_to_a_hundred_slots_so_track_count_does_not_shift_it():
    """A five-track disc and a twelve-track disc must hash over the same
    length of text -- that is what the zero-filled slots are for."""
    short = cdrip.DiscToc(tracks=[cdrip.TocTrack(1, 0, 7500)], leadout_lba=7500)
    assert len(short.musicbrainz_disc_id()) == len(_toc().musicbrainz_disc_id())


def test_toc_param_is_first_last_leadout_then_every_offset():
    param = _toc().musicbrainz_toc_param().split("+")
    assert param[0] == "1"
    assert param[1] == "12"
    assert param[2] == str(174447 + 92660 + 150)
    assert len(param) == 3 + 12


def test_identifying_a_disc_with_no_tracks_is_an_error_not_a_hash_of_nothing():
    with pytest.raises(cdrip.CdRipError):
        cdrip.DiscToc().musicbrainz_disc_id()


# --- the rip plan -----------------------------------------------------


def test_plan_names_files_with_a_padded_track_number_so_order_survives_sorting():
    plan = cdrip.build_rip_plan(_toc(), Path("/rips/x"), ["Smells Like Teen Spirit"], artist="Nirvana")
    assert plan.tasks[0].flac_path.name == "01 - Smells Like Teen Spirit.flac"
    names = [task.flac_path.name for task in plan.tasks]
    assert names == sorted(names)


def test_plan_falls_back_to_a_numbered_title_when_none_was_given():
    plan = cdrip.build_rip_plan(_toc(), Path("/rips/x"), [])
    assert plan.tasks[0].title == "Track 01"
    assert plan.tasks[0].tags["TITLE"] == "Track 01"


def test_plan_writes_both_artist_and_album_artist():
    """foobar's %album artist% is what the record flow reads for the disc
    title; %artist% is what most other things display. Missing either one
    would show up as a blank somewhere downstream."""
    plan = cdrip.build_rip_plan(_toc(), Path("/rips/x"), ["A"], artist="Nirvana", album="Nevermind", year=1991)
    tags = plan.tasks[0].tags
    assert tags["ARTIST"] == "Nirvana"
    assert tags["ALBUMARTIST"] == "Nirvana"
    assert tags["ALBUM"] == "Nevermind"
    assert tags["DATE"] == "1991"
    assert tags["TRACKNUMBER"] == "1"
    assert tags["TRACKTOTAL"] == "12"


def test_plan_keeps_a_slash_in_a_title_out_of_the_filename_but_in_the_tag():
    plan = cdrip.build_rip_plan(_toc(), Path("/rips/x"), ["AC/DC: Back?"])
    assert "/" not in plan.tasks[0].flac_path.name
    assert "?" not in plan.tasks[0].flac_path.name
    assert plan.tasks[0].tags["TITLE"] == "AC/DC: Back?"


def test_folder_name_survives_a_title_windows_would_mangle():
    """Windows silently drops a trailing dot or space from a directory
    name, which would leave us creating one folder and writing into
    another."""
    assert cdrip.rip_folder_name("Therapy?", "Troublegum.") == "Therapy_ - Troublegum"
    assert cdrip.rip_folder_name("", "") == "Unknown Artist - Unknown Album"


def test_expected_wav_bytes_is_the_toc_length_in_cdda_sectors():
    plan = cdrip.build_rip_plan(_toc(), Path("/rips/x"), [])
    assert plan.tasks[0].expected_wav_bytes == 44 + 22617 * 2352


# --- device spellings -------------------------------------------------


@pytest.mark.skipif(sys.platform != "win32", reason="drive letters are a Windows notion")
def test_windows_device_candidates_try_the_plain_letter_then_the_raw_path():
    assert cdrip.device_candidates("D:") == ["D:", r"\\.\D:"]


# --- running the tools ------------------------------------------------


class _FakeCompleted:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def test_read_toc_parses_what_the_tool_printed_to_stderr(monkeypatch):
    """cdparanoia writes everything, success included, to stderr -- stdout
    is reserved for ripped audio. Reading only stdout would find nothing."""
    monkeypatch.setattr(cdrip, "cdparanoia_path", lambda: "cd-paranoia")
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return _FakeCompleted(stderr=NEVERMIND_TOC_OUTPUT)

    toc = cdrip.read_toc("D:", run=fake_run)
    assert len(toc.tracks) == 12
    assert "-Q" in calls[0]


def test_read_toc_tries_every_device_spelling_before_giving_up(monkeypatch):
    monkeypatch.setattr(cdrip, "cdparanoia_path", lambda: "cd-paranoia")
    monkeypatch.setattr(cdrip, "device_candidates", lambda device: ["D:", r"\\.\D:"])
    tried = []

    def fake_run(command, **kwargs):
        tried.append(command[2])
        # Only the raw device path answers, which is the whole point.
        if command[2] == r"\\.\D:":
            return _FakeCompleted(stderr=NEVERMIND_TOC_OUTPUT)
        return _FakeCompleted(stderr="Unable find or access a CD-ROM drive")

    assert len(cdrip.read_toc("D:", run=fake_run).tracks) == 12
    assert tried == ["D:", r"\\.\D:"]


def test_a_clean_exit_with_no_toc_in_it_is_still_a_failure(monkeypatch):
    """`cd-paranoia -Q` exits 0 even when it found no drive at all --
    verified by running the bundled binary on a machine with none. Trusting
    the return code here would report an empty disc as a successful read."""
    monkeypatch.setattr(cdrip, "cdparanoia_path", lambda: "cd-paranoia")
    monkeypatch.setattr(cdrip, "device_candidates", lambda device: ["D:"])

    def fake_run(command, **kwargs):
        return _FakeCompleted(stderr="Unable find or access a CD-ROM drive", returncode=0)

    with pytest.raises(cdrip.CdRipError):
        cdrip.read_toc("D:", run=fake_run)


def test_read_toc_reports_the_tools_own_complaint_not_a_generic_message(monkeypatch):
    monkeypatch.setattr(cdrip, "cdparanoia_path", lambda: "cd-paranoia")
    monkeypatch.setattr(cdrip, "device_candidates", lambda device: ["D:"])

    def fake_run(command, **kwargs):
        return _FakeCompleted(
            stderr="cdparanoia III release 10.2\n(C) 2001 Monty\n\nUnable find or access a CD-ROM drive"
        )

    with pytest.raises(cdrip.CdRipError, match="Unable find or access"):
        cdrip.read_toc("D:", run=fake_run)


class _FakeProcess:
    """A cd-paranoia that grows its output file over a few poll intervals,
    which is exactly what rip_track watches -- it never reads the child's
    output at all (see rip_track's docstring for why)."""

    def __init__(self, wav_path: Path, total_bytes: int, polls: int = 4, write_bytes: int | None = None):
        self._wav = wav_path
        self._total = total_bytes if write_bytes is None else write_bytes
        self._polls = polls
        self._seen = 0
        self.killed = False
        self.returncode = None

    def poll(self):
        if self._seen >= self._polls:
            self.returncode = 0
            return 0
        self._seen += 1
        self._wav.write_bytes(b"\0" * (self._total * self._seen // self._polls))
        return None

    def kill(self):
        self.killed = True

    def wait(self):
        return 0


def _one_task(tmp_path: Path, sectors: int = 10) -> cdrip.RipTask:
    toc = cdrip.DiscToc(tracks=[cdrip.TocTrack(1, 0, sectors)], leadout_lba=sectors)
    return cdrip.build_rip_plan(toc, tmp_path, ["A Song"]).tasks[0]


def test_rip_track_reports_progress_from_the_file_it_is_growing(monkeypatch, tmp_path):
    monkeypatch.setattr(cdrip, "cdparanoia_path", lambda: "cd-paranoia")
    task = _one_task(tmp_path)
    seen: list[float] = []

    def fake_popen(command, **kwargs):
        return _FakeProcess(task.wav_path, task.expected_wav_bytes)

    cdrip.rip_track("D:", task, on_progress=seen.append, popen=fake_popen, sleep=lambda _: None)
    assert seen == sorted(seen)
    assert seen[-1] == 1.0


def test_rip_track_fails_when_the_output_is_shorter_than_the_toc_promised(monkeypatch, tmp_path):
    """A clean exit is not proof of a clean rip. The TOC says how many
    sectors the track is; anything less means audio is missing, and putting
    a truncated track on a MiniDisc is not recoverable."""
    monkeypatch.setattr(cdrip, "cdparanoia_path", lambda: "cd-paranoia")
    task = _one_task(tmp_path)

    def fake_popen(command, **kwargs):
        return _FakeProcess(task.wav_path, task.expected_wav_bytes, write_bytes=task.expected_wav_bytes // 2)

    with pytest.raises(cdrip.CdRipError, match="came up short"):
        cdrip.rip_track("D:", task, popen=fake_popen, sleep=lambda _: None)


def test_cancelling_a_rip_kills_the_reader_and_removes_the_partial_file(monkeypatch, tmp_path):
    monkeypatch.setattr(cdrip, "cdparanoia_path", lambda: "cd-paranoia")
    task = _one_task(tmp_path)
    process = _FakeProcess(task.wav_path, task.expected_wav_bytes, polls=50)

    with pytest.raises(cdrip.CdRipCancelled):
        cdrip.rip_track(
            "D:", task, should_cancel=lambda: True, popen=lambda *a, **k: process, sleep=lambda _: None
        )

    assert process.killed
    assert not task.wav_path.exists()


def test_a_successful_rip_cleans_up_its_log(monkeypatch, tmp_path):
    monkeypatch.setattr(cdrip, "cdparanoia_path", lambda: "cd-paranoia")
    task = _one_task(tmp_path)

    cdrip.rip_track(
        "D:",
        task,
        popen=lambda *a, **k: _FakeProcess(task.wav_path, task.expected_wav_bytes),
        sleep=lambda _: None,
    )

    assert list(tmp_path.glob("*.log")) == []


def test_a_failed_rip_keeps_its_log_and_reports_what_is_in_it(monkeypatch, tmp_path):
    """cdparanoia's log holds its per-sector account of what went wrong,
    which is the only diagnosis available for a disc that would not read."""
    monkeypatch.setattr(cdrip, "cdparanoia_path", lambda: "cd-paranoia")
    task = _one_task(tmp_path)

    class _Failing:
        returncode = None

        def __init__(self, log):
            self._log = log
            self._polled = False

        def poll(self):
            if not self._polled:
                self._polled = True
                return None
            self._log.write("scratch detected, giving up on sector 12345\n")
            self._log.flush()
            self.returncode = 1
            return 1

    def fake_popen(command, stderr=None, **kwargs):
        return _Failing(stderr)

    with pytest.raises(cdrip.CdRipError, match="scratch detected"):
        cdrip.rip_track("D:", task, popen=fake_popen, sleep=lambda _: None)

    assert [p.name for p in tmp_path.glob("*.log")] == ["01 - A Song.log"]


def test_rip_command_asks_for_stderr_progress_and_a_wav():
    command = cdrip.rip_command("cd-paranoia", "D:", 3, Path("/tmp/3.wav"))
    assert "-e" in command  # machine-readable progress, "for wrapper scripts"
    assert "-w" in command
    assert command[command.index("-d") + 1] == "D:"


# --- encoding, for real -----------------------------------------------


def _write_silent_wav(path: Path, frames: int = 4410) -> None:
    data = b"\0" * (frames * 4)  # 16-bit stereo
    header = b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVE"
    header += b"fmt " + struct.pack("<IHHIIHH", 16, 1, 2, 44100, 44100 * 4, 4, 16)
    header += b"data" + struct.pack("<I", len(data))
    path.write_bytes(header + data)


def _flac_vorbis_comments(path: Path) -> list[str]:
    """The Vorbis comment block out of a FLAC file, without needing
    metaflac or any third-party parser: a fLaC magic number, then metadata
    blocks with a 4-byte header each."""
    raw = path.read_bytes()
    assert raw[:4] == b"fLaC"
    offset = 4
    while offset < len(raw):
        header = raw[offset]
        last, block_type = bool(header & 0x80), header & 0x7F
        length = int.from_bytes(raw[offset + 1 : offset + 4], "big")
        body = raw[offset + 4 : offset + 4 + length]
        if block_type == 4:  # VORBIS_COMMENT
            pos = 4 + int.from_bytes(body[:4], "little")
            count = int.from_bytes(body[pos : pos + 4], "little")
            pos += 4
            out = []
            for _ in range(count):
                size = int.from_bytes(body[pos : pos + 4], "little")
                pos += 4
                out.append(body[pos : pos + size].decode("utf-8"))
                pos += size
            return out
        if last:
            break
        offset += 4 + length
    return []


def test_the_encoder_writes_non_ascii_tags_without_mangling_them(tmp_path):
    """Verified against a hand-written Vorbis-comment parser
    (_flac_vorbis_comments), not soundfile/mutagen, since those are what
    wrote/could read them back.

    Encoding now goes through audio_engine.encode_wav_to_flac()
    (soundfile/libsndfile), not flac.exe -- tags reach libsndfile as plain
    Python strings, not command-line arguments, so surviving a Polish or
    Japanese title is no longer an assumption about a tool's own argv
    handling the way it was when this ran flac.exe directly. Still worth
    proving directly rather than assuming it from the library's own docs.

    Comments are compared lowercase: libsndfile always writes the field
    *name* (not the value) lowercase regardless of the case given here --
    a real, confirmed difference from flac.exe's own behaviour (which
    preserved whatever case was passed), but not a mangling one, since
    Vorbis comment field names are case-insensitive by spec."""
    task = cdrip.RipTask(
        number=1,
        title="Zażółć gęślą jaźń",
        sectors=1,
        wav_path=tmp_path / "in.wav",
        flac_path=tmp_path / "out.flac",
        tags={"TITLE": "Zażółć gęślą jaźń", "ARTIST": "サカナクション", "ALBUM": "834.194"},
    )
    _write_silent_wav(task.wav_path)

    cdrip.encode_track(task)

    assert task.flac_path.is_file()
    comments = [c.lower() for c in _flac_vorbis_comments(task.flac_path)]
    assert "title=zażółć gęślą jaźń" in comments
    assert "artist=サカナクション" in comments


def test_encoding_removes_the_wav_it_replaced(tmp_path):
    task = cdrip.RipTask(1, "A", 1, tmp_path / "in.wav", tmp_path / "out.flac", {"TITLE": "A"})
    _write_silent_wav(task.wav_path)
    cdrip.encode_track(task)
    assert not task.wav_path.exists()
    assert task.flac_path.is_file()


def test_encoding_can_keep_the_wav_when_asked(tmp_path):
    task = cdrip.RipTask(1, "A", 1, tmp_path / "in.wav", tmp_path / "out.flac", {"TITLE": "A"})
    _write_silent_wav(task.wav_path)
    cdrip.encode_track(task, keep_wav=True)
    assert task.wav_path.exists()
    assert task.flac_path.is_file()


def test_encode_failure_is_reported_as_a_cdriperror(tmp_path):
    """No WAV was ever written at source -- audio_engine.encode_wav_to_flac()
    has nothing to encode, which is exactly the "clean-looking return is
    not evidence, check the actual output" case its own docstring
    describes."""
    task = _one_task(tmp_path)

    with pytest.raises(cdrip.CdRipError):
        cdrip.encode_track(task)


# --- bundled tools ----------------------------------------------------


def test_tools_dir_points_at_the_bundled_bin_folder():
    directory = cdrip.tools_dir()
    assert directory.parent.name == "bin"
    assert directory.parent.parent == Path(__file__).resolve().parents[1]


@pytest.mark.skipif(sys.platform != "win32", reason="only the Windows binaries are bundled")
def test_both_tools_are_bundled_and_actually_run():
    """Guards the whole download-and-commit step: a missing DLL makes these
    exit 0xC0000135 with no output, which is otherwise only discovered by a
    user with a disc in the drive."""
    assert cdrip.missing_tools() == []
    for tool, needle in ((cdrip.cdparanoia_path(), "cdparanoia"), (cdrip.flac_path(), "flac")):
        completed = subprocess.run([tool, "--version"], capture_output=True, text=True, timeout=30)
        assert needle in (completed.stdout + completed.stderr).lower()


# --- housekeeping -----------------------------------------------------


def test_stale_rip_folders_are_removed_except_the_one_in_use(tmp_path):
    old = tmp_path / "Old Artist - Old Album"
    old.mkdir()
    (old / "01 - x.flac").write_bytes(b"")
    keep = tmp_path / "New Artist - New Album"
    keep.mkdir()

    removed = cdrip.clean_stale_rip_folders(tmp_path, keep=keep)

    assert removed == [old]
    assert not old.exists()
    assert keep.exists()


def test_a_folder_holding_anything_but_rip_output_is_left_alone(tmp_path):
    """The rip folder is user-configurable, so it can be pointed somewhere
    that also holds something else. A recursive delete has no business
    guessing."""
    theirs = tmp_path / "Holiday Photos"
    theirs.mkdir()
    (theirs / "beach.jpg").write_bytes(b"")

    assert cdrip.clean_stale_rip_folders(tmp_path) == []
    assert (theirs / "beach.jpg").exists()


# --- making the rip folder --------------------------------------------
#
# The rip folder is a setting, which means it is a path somebody typed: it
# routinely names a directory that does not exist yet. That is the normal
# state before the first rip, not an error, so whoever is about to use it
# creates it.


def test_a_missing_folder_and_all_its_parents_are_created(tmp_path):
    target = tmp_path / "one" / "two" / "three"

    assert cdrip.ensure_folder(target) == target
    assert target.is_dir()


def test_creating_a_folder_that_is_already_there_is_fine(tmp_path):
    cdrip.ensure_folder(tmp_path)
    assert tmp_path.is_dir()


def test_a_folder_that_cannot_be_made_says_which_one_and_why(tmp_path):
    """A drive that is not there, or a path with no write permission --
    worth a sentence naming the folder, not an unhandled OSError."""
    blocked = tmp_path / "a-file"
    blocked.write_text("not a directory")

    with pytest.raises(cdrip.CdRipError) as error:
        cdrip.ensure_folder(blocked / "underneath")

    assert "underneath" in str(error.value)
