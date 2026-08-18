"""Writing an audio CD-R: what will be on it, and the tool that puts it there.

The split is the one cdrip.py, mdrem.py and printing.py already use -- a
pure planning half that needs no drive and no QApplication, and a thin
executing half. Everything about what lands on the disc (track order,
lengths, whether it fits, what CD-Text will say) is decided in
`build_burn_plan()`, so all of it is testable, and the burn dialog shows
the user the same object the burner is handed.

**cdrdao, not cdrecord**: a `.toc` file describes the whole disc in one
pass (disc-at-once), which is what makes CD-Text and gapless track
boundaries fall out naturally instead of being bolted on. It is bundled
into `bin/win64` exactly like cd-paranoia and flac, and found on PATH on
Linux where distros package it -- `cdrip.find_tool()` already implements
that rule and is reused here rather than copied.

**Two things here are assumptions until they have been run against a real
burner**, and are marked as such at each site: the spelling cdrdao wants
for a device on Windows, and the exact shape of its progress output. Both
are exactly the kind of thing cd-paranoia taught this project not to take
from documentation -- that it writes to stderr, success included, and that
`-Q` exits 0 even with no drive at all, were both established by running
it. `list_burners()` therefore asks cdrdao itself for device names rather
than guessing them, and `burn()` treats unparseable progress as "no
progress information", never as a failure.

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
# like anything else. ASSUMPTION until measured against a real burn:
# cdrdao adds this itself in disc-at-once mode.
LEAD_IN_SECTORS = 2 * SECTORS_PER_SECOND

# ASSUMPTION until run against a real drive. generic-mmc is cdrdao's
# ordinary driver for any modern burner; if a drive needs another one it is
# a per-machine setting, which is why this is a parameter everywhere below
# rather than baked into the command.
DEFAULT_DRIVER = "generic-mmc"
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


def _quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _cd_text_block(title: str, performer: str, indent: str) -> list[str]:
    lines = [f"{indent}LANGUAGE 0 {{"]
    lines.append(f"{indent}  TITLE {_quote(cd_text(title).text)}")
    lines.append(f"{indent}  PERFORMER {_quote(cd_text(performer).text)}")
    lines.append(f"{indent}}}")
    return lines


def toc_text(plan: BurnPlan, wav_names) -> str:
    """The `.toc` file describing the whole disc.

    `wav_names` are bare filenames, not paths, and that is deliberate: the
    toc is written into the same directory as the WAVs, so there is no path
    to escape -- which on Windows would otherwise mean backslashes inside a
    quoted string in a format that uses backslash as its own escape.
    """
    lines = ["CD_DA", "", "CD_TEXT {", "  LANGUAGE_MAP { 0 : EN }"]
    lines += _cd_text_block(plan.album, plan.artist, "  ")
    lines += ["}", ""]

    for number, (track, name) in enumerate(zip(plan.tracks, wav_names), start=1):
        lines.append(f"// track {number}")
        lines.append("TRACK AUDIO")
        lines.append("CD_TEXT {")
        lines += _cd_text_block(track.title, track.artist or plan.artist, "  ")
        lines.append("}")
        lines.append(f"FILE {_quote(str(name))} 0")
        lines.append("")

    return "\n".join(lines) + "\n"


def wav_name_for(number: int) -> str:
    """Zero-padded so the directory reads in disc order, the same reasoning
    cdrip.build_rip_plan() uses for its own filenames."""
    return f"{number:02d}.wav"


def prepare_wavs(plan: BurnPlan, directory: Path | str, *, on_progress=None, run=subprocess.run) -> list[str]:
    """Decodes every track into `directory` as Red Book WAV, in disc order.

    Returns the bare filenames, ready for `toc_text()`. Raises BurnError on
    the first failure: unlike planning, there is nothing useful to do with
    a half-decoded album, and the plan has already reported everything that
    could be known in advance.
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)

    names: list[str] = []
    for number, track in enumerate(plan.tracks, start=1):
        name = wav_name_for(number)
        try:
            decode.to_wav(track.source, directory / name, run=run)
        except decode.DecodeError as exc:
            raise BurnError(str(exc)) from exc
        names.append(name)
        if on_progress is not None:
            on_progress(number / len(plan.tracks))
    return names


def write_toc(plan: BurnPlan, directory: Path | str, wav_names) -> Path:
    directory = Path(directory)
    toc_path = directory / "disc.toc"
    toc_path.write_text(toc_text(plan, wav_names), encoding="ascii", errors="replace")
    return toc_path


# -- the tool ------------------------------------------------------------


def cdrdao_path() -> str | None:
    return find_tool("cdrdao")


def missing_tools() -> list[str]:
    """Which of the tools burning needs are not there -- named, so the
    dialog can say what to install rather than only that something failed."""
    missing = []
    if cdrdao_path() is None:
        missing.append("cdrdao")
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


_SCANBUS_LINE = re.compile(r"^\s*([0-9]+,[0-9]+,[0-9]+|[A-Za-z]:)\s*:\s*(.*?)\s*$")


def parse_scanbus(text: str) -> list[Burner]:
    """cdrdao's own idea of what the drives are called.

    Asking the tool rather than constructing a device string is the whole
    point: what spelling cdrdao wants on Windows is precisely the detail
    this module refuses to assume.
    """
    burners = []
    for line in text.splitlines():
        match = _SCANBUS_LINE.match(line)
        if match:
            burners.append(Burner(device=match.group(1), description=match.group(2)))
    return burners


def scan_command(tool: str) -> list[str]:
    return [tool, "scanbus"]


def list_burners(*, run=subprocess.run) -> list[Burner]:
    """Every writer cdrdao can see.

    Like cd-paranoia's `-Q`, the exit code is not the evidence -- having
    parsed device lines out of the output is. cdrdao also writes its
    scanbus results to stderr, so both streams are searched.
    """
    tool = cdrdao_path()
    if tool is None:
        raise BurnError("cdrdao was not found")
    result = run(scan_command(tool), capture_output=True, text=True, creationflags=NO_WINDOW)
    return parse_scanbus((result.stdout or "") + "\n" + (result.stderr or ""))


@dataclass(frozen=True)
class DiscInfo:
    empty: bool
    appendable: bool
    capacity_sectors: int | None

    @property
    def usable(self) -> bool:
        """A CD-R that has already been written to cannot take a fresh
        disc-at-once burn."""
        return self.empty


def disc_info_command(tool: str, device: str, driver: str = DEFAULT_DRIVER) -> list[str]:
    return [tool, "disk-info", "--device", device, "--driver", driver]


def parse_disc_info(text: str) -> DiscInfo:
    """cdrdao's `disk-info`, read for the three things that decide whether a
    burn can start at all.

    Tolerant on purpose: an unrecognised field means "unknown", never an
    error, since the dialog can still offer to try -- the drive itself is
    the last word regardless.
    """
    empty = _flag(text, "CD-R empty")
    appendable = _flag(text, "CD-R medium.*appendable") or _flag(text, "Appendable")
    capacity = None
    match = re.search(r"total capacity.*?(\d+):(\d+):(\d+)", text, re.IGNORECASE)
    if match:
        minutes, seconds, sectors = (int(part) for part in match.groups())
        capacity = (minutes * 60 + seconds) * SECTORS_PER_SECOND + sectors
    return DiscInfo(empty=bool(empty), appendable=bool(appendable), capacity_sectors=capacity)


def _flag(text: str, label: str) -> bool | None:
    match = re.search(rf"{label}\s*:\s*(yes|no)", text, re.IGNORECASE)
    if match is None:
        return None
    return match.group(1).lower() == "yes"


def read_disc_info(device: str, *, driver: str = DEFAULT_DRIVER, run=subprocess.run) -> DiscInfo:
    tool = cdrdao_path()
    if tool is None:
        raise BurnError("cdrdao was not found")
    result = run(
        disc_info_command(tool, device, driver), capture_output=True, text=True, creationflags=NO_WINDOW
    )
    return parse_disc_info((result.stdout or "") + "\n" + (result.stderr or ""))


def burn_command(
    tool: str,
    device: str,
    toc_path: Path | str,
    *,
    speed: int = DEFAULT_SPEED,
    simulate: bool = False,
    eject: bool = True,
    driver: str = DEFAULT_DRIVER,
) -> list[str]:
    command = [tool, "write", "--device", device, "--driver", driver, "--speed", str(speed)]
    if simulate:
        # A dry run: the laser never writes. The only way to rehearse a burn
        # without spending a disc on it.
        command.append("--simulate")
    if eject:
        command.append("--eject")
    command.append(str(toc_path))
    return command


_PROGRESS = re.compile(r"Wrote\s+(\d+)\s+of\s+(\d+)\s*MB", re.IGNORECASE)


def parse_progress(text: str) -> float | None:
    """The most recent "Wrote N of M MB" in cdrdao's output, as 0.0-1.0.

    ASSUMPTION until seen from the real binary; anything unrecognised
    returns None, which `burn()` treats as "no progress information to
    report" rather than as a problem. A burn that finishes correctly while
    the bar never moved is a cosmetic failure; one that stops because the
    output did not look as expected would be a real one.
    """
    matches = _PROGRESS.findall(text or "")
    if not matches:
        return None
    written, total = (int(value) for value in matches[-1])
    if total <= 0:
        return None
    return max(0.0, min(1.0, written / total))


def burn(
    device: str,
    toc_path: Path | str,
    *,
    speed: int = DEFAULT_SPEED,
    simulate: bool = False,
    eject: bool = True,
    driver: str = DEFAULT_DRIVER,
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

    **Cancelling is not free here, and callers must treat it accordingly.**
    Stopping a rip leaves nothing anywhere; stopping a burn part way
    through leaves a disc that is neither blank nor finished, and a CD-R
    cannot be rewritten. This function does what it is told -- the warning
    belongs to the dialog.
    """
    tool = cdrdao_path()
    if tool is None:
        raise BurnError("cdrdao was not found")

    toc_path = Path(toc_path)
    log_path = toc_path.with_suffix(".log")

    cancelled = False
    tail = ""
    with open(log_path, "w+", encoding="utf-8", errors="replace") as log:
        process = popen(
            burn_command(
                tool, device, toc_path, speed=speed, simulate=simulate, eject=eject, driver=driver
            ),
            stdout=log,
            stderr=log,
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
                fraction = parse_progress(log.read())
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
        raise BurnError(_last_useful_line(tail) or "cdrdao failed")

    log_path.unlink(missing_ok=True)
    if on_progress is not None:
        on_progress(1.0)


def _last_useful_line(text: str) -> str:
    """cdrdao explains itself on its last line, unlike cd-paranoia, whose
    first useful line is the one that matters."""
    for line in reversed((text or "").splitlines()):
        line = line.strip()
        if line and not line.startswith("Wrote "):
            return line
    return ""
