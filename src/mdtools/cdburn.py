"""Writing an audio CD-R: what will be on it, and the tool that puts it there.

The split is the one cdrip.py, mdrem.py and printing.py already use -- a
pure planning half that needs no drive and no QApplication, and a thin
executing half. Everything about what lands on the disc (track order,
lengths, whether it fits, what CD-Text will say) is decided in
`build_burn_plan()`, so all of it is testable, and the burn dialog shows
the user the same object the burner is handed.

**cdrecord (cdrtools), and the choice was forced.** cdrdao was the first
pick -- a `.toc` file describes a whole disc in one pass, which is a
pleasant fit -- but it has no maintained Windows build: the last official
win32 package is 1.1.5 from around 2004, Cygwin- and ASPI-based, sitting in
an OldFiles folder, and upstream's own Windows instructions are stale.
cdrecord 3.02a10 is built for Windows as recently as 2021 (shipped by the
cdrtfe project), does disc-at-once audio with CD-Text, and is packaged by
every Linux distribution -- so one tool covers both platforms. It is
bundled into `bin/win64` exactly like cd-paranoia and flac, and found on
PATH on Linux; `cdrip.find_tool()` already implements that rule and is
reused here rather than copied.

CD-Text goes in through a `*.inf` file beside each WAV (`-text -useinfo`),
whose field names come from cdrecord's own manual page rather than from
guesswork -- see `inf_text()`.

**What was established by running the bundled binary, not read anywhere**
(the same discipline cd-paranoia's own surprises taught this project):
`-scanbus` prints its device list on *stdout* while its warnings go to
stderr; the six "Insufficient privileges" warnings it prints on every run
are noise, since `-checkdrive` still talked to the drive; and an empty
drive answers `-atip`/`-minfo` with "medium not present" and a non-zero
exit. A full `-dummy` run on a real blank disc then pinned the rest: the
progress line's shape, the 150-sector pregap cdrecord adds itself, and that
`-dao -audio -pad -text -useinfo` is accepted as written. `burn()` still
treats unparseable progress as "no progress information" rather than as a
failure -- a motionless bar is cosmetic, a burn that stopped because the
output read differently would be a wasted disc.

**What no dry run can show** is whether the CD-Text packs actually land on
the disc: cdrecord accepted `-text -useinfo` without complaint, but reading
it back needs a real burn plus `cdrecord -vv -toc`.

Nothing here is irreversible except `burn()` itself, and `simulate=True`
makes even that a dry run -- a wasted CD-R is this feature's equivalent of
a bad cut, so the option exists at the lowest level rather than only in the
dialog.
"""

from __future__ import annotations

import math
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from mdtools import decode
from mdtools.cdrip import NO_WINDOW, find_tool
from mdtools.mdrem import transliterate

# One CD sector is 2352 bytes of audio, which at 16-bit stereo is 588
# sample frames; 75 of them make a second.
FRAMES_PER_SECTOR = BYTES_PER_SECTOR = decode.BYTES_PER_FRAME  # 2352 bytes
SAMPLES_PER_SECTOR = 588
SECTORS_PER_SECOND = decode.FRAMES_PER_SECOND  # 75

# Red Book rules that can fail a burn rather than merely look wrong.
MIN_TRACK_SECONDS = 4
MIN_TRACK_SECTORS = MIN_TRACK_SECONDS * SECTORS_PER_SECOND
MAX_TRACKS = 99

# Nominal capacities. The disc in the drive is the real authority (see
# `read_disc_info()`); these are what a plan is checked against before any
# drive has been opened, so a hopeless track list is caught while it still
# costs nothing.
CAPACITY_74_MIN_SECTORS = 74 * 60 * SECTORS_PER_SECOND
CAPACITY_80_MIN_SECTORS = 80 * 60 * SECTORS_PER_SECOND
DEFAULT_CAPACITY_SECTORS = CAPACITY_80_MIN_SECTORS

# The 2-second gap before track 1, which comes out of the disc's capacity
# like anything else. Verified on a real dummy run, which announced
# "Writing pregap for track 1 at -150" -- exactly these 150 sectors, added
# by cdrecord itself in disc-at-once mode.
LEAD_IN_SECTORS = 2 * SECTORS_PER_SECOND

# cdrecord picks the driver itself (it reported "Using generic SCSI-3/mmc
# CD-R/CD-RW driver (mmc_cdr)" for the drive tried here), so unlike cdrdao
# there is no driver to configure and none is passed.
DEFAULT_SPEED = 8

BURN_POLL_S = 0.5
_LOG_TAIL_CHARS = 4000

# Problem codes. Deliberately codes rather than sentences: the wording has
# to be translated, and this module has no Qt in it (the same rule
# decode.AudioProperties.mismatches() follows).
NOT_RED_BOOK = "not_red_book"
TOO_SHORT = "too_short"
UNREADABLE = "unreadable"
TOO_MANY_TRACKS = "too_many_tracks"
TOO_LONG_FOR_DISC = "too_long_for_disc"
NO_TRACKS = "no_tracks"


class BurnError(Exception):
    """Anything that stops a disc being written."""


class BurnCancelled(Exception):
    """The user stopped the burn."""


@dataclass(frozen=True)
class Problem:
    """One reason a plan cannot be burned as it stands.

    `track_number` is 1-based, or 0 for something about the disc as a whole.
    """

    code: str
    track_number: int = 0
    detail: str = ""


@dataclass
class BurnTrack:
    source: Path
    title: str
    artist: str
    properties: decode.AudioProperties | None  # None if the file could not be read

    @property
    def sectors(self) -> int:
        """How much of the disc this track occupies.

        Rounded *up*: a track ends on a sector boundary, so a file that
        does not fill its last sector still costs the whole thing.
        """
        if self.properties is None:
            return 0
        return math.ceil(self.properties.frames / SAMPLES_PER_SECTOR)

    @property
    def seconds(self) -> float:
        return self.properties.duration_seconds if self.properties else 0.0


@dataclass
class BurnPlan:
    album: str
    artist: str
    tracks: list[BurnTrack] = field(default_factory=list)
    problems: list[Problem] = field(default_factory=list)
    capacity_sectors: int = DEFAULT_CAPACITY_SECTORS

    @property
    def total_sectors(self) -> int:
        return LEAD_IN_SECTORS + sum(track.sectors for track in self.tracks)

    @property
    def total_seconds(self) -> float:
        return self.total_sectors / SECTORS_PER_SECOND

    @property
    def can_burn(self) -> bool:
        return not self.problems and bool(self.tracks)

    def problems_for(self, track_number: int) -> list[Problem]:
        return [problem for problem in self.problems if problem.track_number == track_number]


def build_burn_plan(
    sources,
    *,
    album: str = "",
    artist: str = "",
    capacity_sectors: int = DEFAULT_CAPACITY_SECTORS,
    analyze=decode.analyze,
) -> BurnPlan:
    """Turns (path, title, artist) triples into a plan, with every reason it
    could not be burned attached rather than raised.

    Attached rather than raised because the dialog has to show all of them
    at once, next to the tracks they are about: stopping at the first bad
    file would make fixing an album a matter of running into one problem
    per attempt.
    """
    plan = BurnPlan(album=album, artist=artist, capacity_sectors=capacity_sectors)

    for number, (path, title, track_artist) in enumerate(sources, start=1):
        path = Path(path)
        try:
            properties = analyze(path)
        except decode.DecodeError as exc:
            properties = None
            plan.problems.append(Problem(UNREADABLE, number, str(exc)))
        track = BurnTrack(source=path, title=title, artist=track_artist, properties=properties)
        plan.tracks.append(track)

        if properties is None:
            continue
        if not properties.is_red_book:
            plan.problems.append(
                Problem(
                    NOT_RED_BOOK,
                    number,
                    f"{properties.sample_rate} Hz / {properties.bits_per_sample}-bit / {properties.channels}ch",
                )
            )
        if track.sectors < MIN_TRACK_SECTORS:
            # Red Book's own minimum: a shorter track is not a small track,
            # it is a disc some players refuse.
            plan.problems.append(Problem(TOO_SHORT, number, f"{track.seconds:.1f}s"))

    if not plan.tracks:
        plan.problems.append(Problem(NO_TRACKS))
    if len(plan.tracks) > MAX_TRACKS:
        plan.problems.append(Problem(TOO_MANY_TRACKS, 0, str(len(plan.tracks))))
    if plan.total_sectors > capacity_sectors:
        over = (plan.total_sectors - capacity_sectors) / SECTORS_PER_SECOND
        plan.problems.append(Problem(TOO_LONG_FOR_DISC, 0, f"{over:.1f}s"))

    return plan


# -- CD-Text -------------------------------------------------------------


@dataclass(frozen=True)
class CdText:
    text: str
    dropped: list[str]


def cd_text(value: str) -> CdText:
    """A title as it can actually be written into CD-Text.

    Reuses mdrem.transliterate() -- the same problem in a different place.
    The CD-Text spec allows ISO-8859-1 (and MS-JIS), but what a given
    player's display does with either is anyone's guess, and this project
    already owns a transliterator whose contract is exactly the one wanted
    here: strip to ASCII, and *report* whatever had no equivalent instead
    of dropping it silently. A Japanese title therefore comes back empty
    with its characters listed, which the dialog can show before the disc
    is written rather than after.
    """
    result = transliterate(value)
    return CdText(text=result.text.strip(), dropped=list(result.dropped))


def _inf_quote(value: str) -> str:
    """A quoted string as cdrecord's *.inf parser reads them.

    Its rule, from cdrecord's own manual: the value starts after the first
    single quote on the line and ends before the *last* one, and "it needs
    no escape sequences in case that a single quote appears inside the
    string". So an apostrophe in the middle of a title is safe and must
    *not* be escaped -- but one at the very end would swallow the closing
    quote, so a trailing quote is dropped rather than escaped.
    """
    return "'" + value.replace("\n", " ").strip().rstrip("'") + "'"


def inf_text(plan: BurnPlan, number: int) -> str:
    """The *.inf file for one track: where its CD-Text comes from.

    cdrecord reads these when given `-useinfo -text`, matching each one to
    the audio file with the same prefix (01.wav <- 01.inf), which is why
    the names come from wav_name_for()/inf_name_for(). Only the CD-Text
    fields are written: MCN and ISRC are real subchannel data cdrecord
    would burn, and inventing either would put a false catalogue number or
    recording code on somebody's disc.
    """
    track = plan.tracks[number - 1]
    performer = track.artist or plan.artist
    return "\n".join(
        [
            "# Generated by MDTools -- CD-Text for cdrecord -useinfo -text",
            "Albumperformer=\t" + _inf_quote(cd_text(plan.artist).text),
            "Albumtitle=\t" + _inf_quote(cd_text(plan.album).text),
            "Performer=\t" + _inf_quote(cd_text(performer).text),
            "Tracktitle=\t" + _inf_quote(cd_text(track.title).text),
            f"Tracknumber=\t{number}",
            "Tracktype=\taudio",
            "Channels=\t2",
            "",
        ]
    )


def wav_name_for(number: int) -> str:
    """Zero-padded so the directory reads in disc order, the same reasoning
    cdrip.build_rip_plan() uses for its own filenames."""
    return f"{number:02d}.wav"


def inf_name_for(number: int) -> str:
    """cdrecord finds a track's CD-Text by swapping the audio file's
    extension, so this has to stay in step with wav_name_for()."""
    return f"{number:02d}.inf"


def prepare_wavs(
    plan: BurnPlan,
    directory: Path | str,
    *,
    on_progress=None,
    should_cancel=None,
    run=subprocess.run,
) -> list[str]:
    """Decodes every track into `directory` as Red Book WAV, in disc order.

    Returns the bare filenames. Raises BurnError on the first failure:
    unlike planning, there is nothing useful to do with a half-decoded
    album, and the plan has already reported everything that could be known
    in advance.

    Cancelling takes effect between tracks, and here that costs nothing --
    no disc has been touched yet, only a scratch folder. (Compare `burn()`,
    where stopping ruins the CD-R.)
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)

    names: list[str] = []
    for number, track in enumerate(plan.tracks, start=1):
        if should_cancel is not None and should_cancel():
            raise BurnCancelled()
        name = wav_name_for(number)
        try:
            decode.to_wav(track.source, directory / name, run=run)
        except decode.DecodeError as exc:
            raise BurnError(str(exc)) from exc
        names.append(name)
        if on_progress is not None:
            on_progress(number / len(plan.tracks))
    return names


def write_inf_files(plan: BurnPlan, directory: Path | str) -> list[str]:
    """One *.inf per track, beside its WAV. Returns their bare filenames.

    Written as ASCII deliberately: cd_text() has already reduced every
    title to what CD-Text can carry, so anything left that will not encode
    would be a bug rather than something to paper over with a more
    forgiving encoding.
    """
    directory = Path(directory)
    names = []
    for number in range(1, len(plan.tracks) + 1):
        name = inf_name_for(number)
        (directory / name).write_text(inf_text(plan, number), encoding="ascii", errors="replace")
        names.append(name)
    return names


# -- the tool ------------------------------------------------------------


def cdrecord_path() -> str | None:
    return find_tool("cdrecord")


def missing_tools() -> list[str]:
    """Which of the tools burning needs are not there -- named, so the
    dialog can say what to install rather than only that something failed."""
    missing = []
    if cdrecord_path() is None:
        missing.append("cdrecord")
    from mdtools.cdrip import flac_path

    if flac_path() is None:
        missing.append("flac")
    return missing


@dataclass(frozen=True)
class Burner:
    device: str
    description: str

    def display(self) -> str:
        return f"{self.device} - {self.description}" if self.description else self.device


# Verified by running the bundled binary here, not taken from documentation:
# `cdrecord -scanbus` prints its device list on *stdout* (the privilege
# warnings go to stderr) as
#
#     scsibus0:
#         0,0,0     0) 'HL-DT-ST' 'DVDRAM GP20N    ' '1.02' Removable CD-ROM
#         0,1,0     1) *
#         0,7,0     7) HOST ADAPTOR
#
# -- an empty slot is a bare `*`, and the last entry is the adapter itself.
# Neither is a drive.
_SCANBUS_LINE = re.compile(r"^\s*(\d+,\d+,\d+)\s*\d*\)\s*(.*?)\s*$")


def parse_scanbus(text: str) -> list[Burner]:
    """cdrecord's own idea of what the drives are called.

    Asking the tool rather than constructing a device string is the point:
    `0,0,0` is scsibus,target,lun as libscg numbers them, which is not
    something to derive from a drive letter.
    """
    burners = []
    for line in text.splitlines():
        match = _SCANBUS_LINE.match(line)
        if not match:
            continue
        description = match.group(2)
        if description in ("*", "") or "HOST ADAPTOR" in description.upper():
            continue
        burners.append(Burner(device=match.group(1), description=_tidy_description(description)))
    return burners


def _tidy_description(text: str) -> str:
    """'HL-DT-ST' 'DVDRAM GP20N    ' '1.02' Removable CD-ROM
    -> HL-DT-ST DVDRAM GP20N 1.02"""
    quoted = re.findall(r"'([^']*)'", text)
    if not quoted:
        return text
    return " ".join(part.strip() for part in quoted if part.strip())


def scan_command(tool: str) -> list[str]:
    return [tool, "-scanbus"]


def list_burners(*, run=subprocess.run) -> list[Burner]:
    """Every writer cdrecord can see.

    Like cd-paranoia's `-Q`, the exit code is not the evidence -- having
    parsed device lines out of the output is. Both streams are searched:
    the list comes out on stdout on the build tried here, but that was
    established by running it, and another build could differ.
    """
    tool = cdrecord_path()
    if tool is None:
        raise BurnError("cdrecord was not found")
    result = run(scan_command(tool), capture_output=True, text=True, creationflags=NO_WINDOW)
    return parse_scanbus((result.stdout or "") + "\n" + (result.stderr or ""))


@dataclass(frozen=True)
class DiscInfo:
    present: bool
    empty: bool
    capacity_sectors: int | None

    @property
    def usable(self) -> bool:
        """A CD-R that has already been written to cannot take a fresh
        disc-at-once burn."""
        return self.present and self.empty


def disc_info_command(tool: str, device: str) -> list[str]:
    return [tool, f"dev={device}", "-minfo"]


def parse_disc_info(text: str) -> DiscInfo:
    """cdrecord's `-minfo`, read for the three things that decide whether a
    burn can start at all.

    Tolerant on purpose: an unrecognised field means "unknown", never an
    error -- the drive is the last word regardless, and refusing to try on
    the strength of a line that read differently would be worse than
    letting the burn report its own failure. The one case that *is* certain
    is an empty drive, verified by running the bundled binary against one:
    it says "medium not present" and exits non-zero.
    """
    lowered = (text or "").lower()
    present = "medium not present" not in lowered and "no disk" not in lowered

    status = re.search(r"disk status:\s*(\w+)", lowered)
    empty = status.group(1) == "empty" if status else present

    # "Remaining writable size" is what the drive says can actually be
    # written; the lead-out address is two sectors larger on the real blank
    # this was read from, and is only a fallback for a drive that does not
    # report the first.
    capacity = None
    for pattern in (r"remaining writable size:?\s*(\d+)", r"start of lead ?out:?\s*(\d+)"):
        match = re.search(pattern, lowered)
        if match:
            capacity = int(match.group(1))
            break
    return DiscInfo(present=present, empty=empty, capacity_sectors=capacity)


def read_disc_info(device: str, *, run=subprocess.run) -> DiscInfo:
    tool = cdrecord_path()
    if tool is None:
        raise BurnError("cdrecord was not found")
    result = run(disc_info_command(tool, device), capture_output=True, text=True, creationflags=NO_WINDOW)
    return parse_disc_info((result.stdout or "") + "\n" + (result.stderr or ""))


def burn_command(
    tool: str,
    device: str,
    wav_names,
    *,
    speed: int = DEFAULT_SPEED,
    simulate: bool = False,
    eject: bool = True,
) -> list[str]:
    """The whole disc in one command.

    `-dao` is disc-at-once: one pass, no forced two-second gap between
    tracks, and the mode this drive writes CD-Text in (`-text -useinfo`,
    which makes cdrecord read the *.inf file beside each WAV -- see
    cdrecord's own README.cdtext). `-pad` covers a track whose length is
    not a whole number of sectors, since a CD cannot store a partial one.
    `-dummy` is cdrecord's own dry run: every step, laser off -- proven
    here on a real blank disc, which came through it still blank.

    `speed=` is a request, not a promise: asked for 8, the drive tried here
    reported "Starting to write ... at speed 10". Nothing depends on the
    number being honoured.

    **`-eject` opens the tray even when the run fails** -- observed here,
    on a dry run that stopped at "No disk / Wrong disk!" and ejected
    anyway. So it belongs only on a command that is meant to end with the
    disc coming out; `disc_info_command()` and `scan_command()` must never
    carry it, or merely looking at the drive would spit the disc out. (It
    also settled a real question: the drive obeys cdrecord with no
    elevation, whatever those six "Insufficient privileges" warnings say.)
    """
    command = [
        tool,
        f"dev={device}",
        "-v",
        f"speed={speed}",
        "-dao",
        "-audio",
        "-pad",
        "-text",
        "-useinfo",
    ]
    if simulate:
        command.append("-dummy")
    if eject:
        command.append("-eject")
    command.extend(str(name) for name in wav_names)
    return command


# Verified against a real dummy run on the bundled binary, which printed
#
#     Track 01:    0 of    3 MB written.
#     Track 01:    1 of    3 MB written (fifo 100%)   9.7x.
#     Track 01:    2 of    3 MB written (fifo 100%) [buf  90%]  10.3x.
#
# -- per track, not per disc, which is why burn() is given the track sizes
# and does the totalling itself. Note the first line of each track has no
# fifo/buf suffix at all, so nothing after "MB" can be relied on.
_PROGRESS = re.compile(r"Track\s+(\d+):\s+(\d+)\s+of\s+(\d+)\s*MB", re.IGNORECASE)


def parse_progress(text: str, megabytes=None) -> float | None:
    """The most recent per-track progress line, as a fraction of the disc.

    Anything unrecognised returns None, which `burn()` treats as "no
    progress information to report" rather than as a problem. A burn that
    finishes correctly while the bar never moved is a cosmetic failure; one
    that stopped because the output did not look as expected would be a
    wasted disc.
    """
    matches = _PROGRESS.findall(text or "")
    if not matches:
        return None
    number, written, total = (int(value) for value in matches[-1])

    if not megabytes:
        return max(0.0, min(1.0, written / total)) if total > 0 else None

    disc_total = sum(megabytes)
    if disc_total <= 0:
        return None
    done = sum(megabytes[: max(0, number - 1)]) + written
    return max(0.0, min(1.0, done / disc_total))


def track_megabytes(plan: BurnPlan) -> list[float]:
    """Each track's size as cdrecord counts it, so its per-track progress
    can be turned into a fraction of the whole disc."""
    return [track.sectors * BYTES_PER_SECTOR / 1_000_000 for track in plan.tracks]


def burn(
    device: str,
    directory: Path | str,
    wav_names,
    *,
    speed: int = DEFAULT_SPEED,
    simulate: bool = False,
    eject: bool = True,
    megabytes=None,
    on_progress=None,
    should_cancel=None,
    popen=subprocess.Popen,
    sleep=time.sleep,
) -> None:
    """Writes the disc, reporting 0.0-1.0 progress as it goes.

    Same shape as cdrip.rip_track(): the child's output goes to a *file*
    rather than a pipe (a pipe nobody drains blocks the child, and reading
    one line by line makes cancelling depend on a line arriving), and the
    loop polls the clock.

    **cdrecord runs with `directory` as its working directory and is given
    bare filenames.** The bundled Windows build is a Cygwin one, so handing
    it native Windows paths invites path-translation surprises for no
    benefit -- and each *.inf has to sit beside its WAV anyway.

    **Cancelling is not free here, and callers must treat it accordingly.**
    Stopping a rip leaves nothing anywhere; stopping a burn part way
    through leaves a disc that is neither blank nor finished, and a CD-R
    cannot be rewritten. This function does what it is told -- the warning
    belongs to the dialog.
    """
    tool = cdrecord_path()
    if tool is None:
        raise BurnError("cdrecord was not found")

    directory = Path(directory)
    log_path = directory / "burn.log"

    cancelled = False
    tail = ""
    with open(log_path, "w+", encoding="utf-8", errors="replace") as log:
        process = popen(
            burn_command(tool, device, wav_names, speed=speed, simulate=simulate, eject=eject),
            stdout=log,
            stderr=log,
            cwd=str(directory),
            creationflags=NO_WINDOW,
        )
        while process.poll() is None:
            if should_cancel is not None and should_cancel():
                process.kill()
                process.wait()
                cancelled = True
                break
            if on_progress is not None:
                log.seek(0)
                fraction = parse_progress(log.read(), megabytes)
                if fraction is not None:
                    on_progress(fraction)
            sleep(BURN_POLL_S)
        if not cancelled:
            log.seek(0)
            tail = log.read()[-_LOG_TAIL_CHARS:]

    # Deleting has to wait for the log above to be closed: Windows refuses
    # to unlink an open file (the same ordering constraint cdrip.rip_track
    # documents).
    if cancelled:
        raise BurnCancelled()

    if process.returncode != 0:
        # Kept on failure: with no way to read the disc back, this log is
        # the only account of what went wrong.
        raise BurnError(_last_useful_line(tail) or "cdrecord failed")

    log_path.unlink(missing_ok=True)
    if on_progress is not None:
        on_progress(1.0)


# Noise cdrecord prints on every run, on a machine where it nonetheless
# works: verified here, where -checkdrive still talked to the drive with
# all six "Insufficient privileges" lines present. Reporting one of those
# as the reason a burn failed would send the user chasing a permissions
# problem they do not have.
_NOISE = (
    "insufficient",
    "warning:",
    "track ",
    "using libscg",
    "cdrecord-prodvd",
    "scsidev",
    "scsibus",
)


def _last_useful_line(text: str) -> str:
    """cdrecord explains a failure at the end of its output, unlike
    cd-paranoia, whose first useful line is the one that matters."""
    for line in reversed((text or "").splitlines()):
        line = line.strip()
        if not line:
            continue
        if any(noise in line.lower() for noise in _NOISE):
            continue
        return line
    return ""
