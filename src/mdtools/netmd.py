"""NetMD: driving a MiniDisc recorder over its own USB cable.

**The second way to talk to a deck, and the better one where it applies.**
The MDRem infrared adapter (`mdrem.py`) presses the buttons on the front
of the deck and is told nothing back -- every write is "sent, unconfirmed"
because there is no return channel at all. A NetMD deck, plugged in over
USB, answers: it can be asked what is on the disc, told what to call it,
and -- in LP2/LP4 -- handed the audio itself, with no cable to the sound
card involved anywhere.

The two are mutually exclusive by setting (`app_settings`), not because
they would physically collide, but because every recording flow has to
know which machine it is driving before it starts: they arm the deck
differently, mark tracks differently, and write titles differently. One
answer, chosen once, beats a per-dialog guess.

**What a mode actually changes.** MiniDisc's recording modes are not just
how much fits on the disc:

- **SP** is what an optical (Toslink) feed carries. The deck records what
  arrives at its digital input in real time, exactly as it does today for
  MDRem -- so the audio path is unchanged, and NetMD is there to mark the
  tracks and write the titles.
- **LP2 / LP4** cannot arrive over Toslink at all: they are ATRAC3, and a
  digital input carries Red Book PCM. They go over the USB cable instead,
  as a file transfer -- which is not a recording in real time, and is
  faster than one.

So the mode decides the cable, and the cable decides the whole flow. That
is why `MODES` carries both, and why `connection_advice()` exists: a user
who plugs in the wrong thing for the mode they picked gets silence, and
finding out why afterwards costs a disc.

**Everything here shells out to `netmdcli.exe`** (bundled, see
`bin/win64/ATTRIBUTION.md`), the same plan-then-execute shape `cdrip.py`
and `cdburn.py` already use for their own tools: build the command list
with no device present, run it with one. That keeps the protocol -- Sony's
encrypted download included -- in an implementation already proven against
real hardware, rather than in a reimplementation nobody here can test.

**No Qt in here.** The dialogs import this; it imports nothing of theirs.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field

from mdtools import cdrip
from mdtools.mdrem import transliterate

# How long netmdcli is given to answer. A title write is a fraction of a
# second and reading the disc little more, but the deck has to spin up
# first, and a deck that has been sitting idle takes its time about it.
COMMAND_TIMEOUT_S = 30.0

# Reading the whole TOC of a full disc is the slowest of the quick
# commands -- a 254-track disc is 254 titles read one at a time.
READ_TIMEOUT_S = 60.0

# One title's ceiling. Not the real limit, which nothing here can know:
# a disc's titles all come out of one shared pool of TOC space, so what
# fits depends on every other title already written and only the deck can
# say. This is the per-title ceiling of the format itself, and exists to
# stop a pathological title (a whole tag dumped into the album field) from
# being sent at all rather than to predict what will fit.
MAX_TITLE = 200


class NetMdError(Exception):
    """Anything that stopped a NetMD command from doing its job."""


# --- recording modes --------------------------------------------------

MODE_SP = "sp"
MODE_LP2 = "lp2"
MODE_LP4 = "lp4"


@dataclass(frozen=True)
class RecordingMode:
    """One of MiniDisc's three recording modes, and what follows from it.

    `over_usb` is the load-bearing field: it decides which cable carries
    the audio, and with it which recording flow runs at all. `minutes` is
    the same number RecordDialog's "one disc holds" spin box has always
    taken -- stated here rather than typed there, now that something in
    the app actually knows which mode the deck is in."""

    key: str
    label: str
    minutes: int
    over_usb: bool
    # What netmdcli's -d flag wants for this mode, or "" for SP (which
    # needs no on-the-fly encoder because it is not encoded at all).
    encoder_flag: str


MODES: dict[str, RecordingMode] = {
    MODE_SP: RecordingMode(MODE_SP, "SP", 80, over_usb=False, encoder_flag=""),
    MODE_LP2: RecordingMode(MODE_LP2, "LP2", 160, over_usb=True, encoder_flag="lp2"),
    MODE_LP4: RecordingMode(MODE_LP4, "LP4", 320, over_usb=True, encoder_flag="lp4"),
}


def mode(key: str) -> RecordingMode:
    """The mode a setting names, falling back to SP.

    Falling back rather than raising: this reads a stored string, and a
    settings file carrying something unknown (an older version's, a typo,
    a hand edit) should leave the app working in the mode that needs the
    least of the hardware, not refuse to open a dialog."""
    return MODES.get(str(key).strip().lower(), MODES[MODE_SP])


def connection_advice(mode_key: str, *, netmd: bool) -> str:
    """What to plug in, in as many words, for the mode about to be used.

    The single most expensive mistake available here is a cable that is
    not connected to the thing the chosen mode needs: the recording runs,
    the disc turns, and what lands on it is silence. Nothing in the
    protocol can detect that in advance -- an optical output does not know
    whether anything is listening -- so it is said plainly up front
    instead.
    """
    chosen = mode(mode_key)
    if not netmd:
        return (
            "Connect the computer's optical (Toslink) output to the deck's digital input. "
            "The MDRem adapter marks the tracks and writes the titles."
        )
    if chosen.over_usb:
        return (
            "{label}: connect the USB cable only. The audio is sent over USB as a file, so no optical "
            "cable is needed and nothing plays in real time."
        ).format(label=chosen.label)
    return (
        "SP: connect both cables. The audio goes over the optical (Toslink) output to the deck's digital "
        "input and is recorded in real time; the USB cable marks the tracks and writes the titles."
    )


# --- the tool ---------------------------------------------------------


def netmdcli_path() -> str | None:
    """The bundled netmdcli, or whatever PATH offers.

    Through `cdrip.find_tool()` deliberately: bundled-then-PATH is one
    rule for every command line tool this app drives, and `bin/win64` is
    one folder. That function is named for the module it grew up in, not
    for CDs."""
    return cdrip.find_tool("netmdcli")


def missing_tools() -> list[str]:
    """Which tools NetMD support needs and cannot find, for a preflight
    message that names them instead of failing at the first command."""
    return [] if netmdcli_path() is not None else ["netmdcli"]


def run_command(args: list[str], *, timeout: float = COMMAND_TIMEOUT_S, run=subprocess.run):
    """One netmdcli invocation, with the tool located and the console
    window suppressed. Returns the CompletedProcess for a caller to read.

    `run` is injectable for the same reason `cdrip.read_toc()`'s is: every
    test in this module's suite has to be able to drive the parsing
    without a deck, a driver or a USB cable."""
    tool = netmdcli_path()
    if tool is None:
        raise NetMdError("netmdcli was not found")
    try:
        return run(
            [tool, *args],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
            creationflags=cdrip.NO_WINDOW,
        )
    except subprocess.TimeoutExpired as exc:
        raise NetMdError(f"the deck did not answer within {timeout:.0f}s") from exc
    except OSError as exc:
        raise NetMdError(f"could not run netmdcli: {exc}") from exc


# What netmdcli prints when it enumerates and finds nothing. Matched
# loosely (case-folded, punctuation-insensitive) because it is a message
# rather than a protocol, and because a deck bound to Sony's own driver
# instead of WinUSB produces exactly this too -- see ATTRIBUTION.md.
_NO_DEVICE = re.compile(r"found\s+no\s+netmd\s+device", re.IGNORECASE)


def _combined(completed) -> str:
    return f"{completed.stdout or ''}\n{completed.stderr or ''}"


def device_present(run=subprocess.run) -> bool:
    """Whether a NetMD deck is connected, awake and on a driver we can
    reach.

    There is no lighter question to ask than a real command -- netmdcli
    enumerates on every run and has no "is anything there?" mode -- so
    this asks for the disc's own status, which is the cheapest thing that
    requires a device to answer at all.

    A deck that is present but holds no disc still answers, because the
    enumeration happened first; that distinction is what makes this
    usable as "is the cable in?" rather than "is a disc in?"."""
    try:
        completed = run_command(["status"], run=run)
    except NetMdError:
        return False
    return not _NO_DEVICE.search(_combined(completed))


# --- what is on the disc ----------------------------------------------


@dataclass
class NetMdTrack:
    number: int  # 1-based, as a person counts them
    title: str = ""
    seconds: float = 0.0


@dataclass
class NetMdDisc:
    title: str = ""
    tracks: list[NetMdTrack] = field(default_factory=list)
    # Free space, when the deck said; None when it did not say at all,
    # which is not the same as "none left".
    free_seconds: float | None = None

    @property
    def track_count(self) -> int:
        return len(self.tracks)


def _seconds_from(value) -> float:
    """A duration out of whatever the tool wrote it as.

    netmdcli renders times as a number of seconds in some places and as
    `h:mm:ss.frames` in others, and which one appears has changed between
    the versions in circulation. Both are read here rather than one being
    assumed, since guessing wrong turns a 4-minute track into 4 seconds
    with nothing to signal it."""
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return 0.0
    parts = text.split(":")
    try:
        numbers = [float(part) for part in parts]
    except ValueError:
        return 0.0
    seconds = 0.0
    for number in numbers:
        seconds = seconds * 60 + number
    return seconds


def parse_disc(text: str) -> NetMdDisc:
    """The disc, out of `netmdcli json` output.

    **Deliberately tolerant about the document's shape**, the same stance
    `cdrip.parse_toc()` takes towards cdparanoia's banner: the key names
    have moved between netmdcli versions (`title`/`name`, `tracks`/
    `trackList`), the JSON is sometimes preceded by log lines, and a
    version that renders durations as text rather than numbers exists.
    What every version agrees on is that there is a disc title and a list
    of tracks with titles in order, so that is what this insists on and
    all it insists on.

    Raises NetMdError when there is no JSON document in `text` at all --
    which is what "the deck did not answer" looks like from here."""
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise NetMdError(_first_useful_line(text) or "the deck sent nothing readable")
    try:
        document = json.loads(text[start : end + 1])
    except ValueError as exc:
        raise NetMdError(f"could not read the deck's answer: {exc}") from exc
    if not isinstance(document, dict):
        raise NetMdError("the deck's answer was not a disc")

    disc = NetMdDisc(title=str(document.get("title") or document.get("name") or "").strip())

    raw_tracks = document.get("tracks")
    if raw_tracks is None:
        raw_tracks = document.get("trackList") or document.get("track_list") or []
    if isinstance(raw_tracks, dict):  # keyed by number rather than a list
        raw_tracks = [raw_tracks[key] for key in sorted(raw_tracks, key=str)]

    for index, raw in enumerate(raw_tracks if isinstance(raw_tracks, list) else [], start=1):
        if not isinstance(raw, dict):
            disc.tracks.append(NetMdTrack(number=index, title=str(raw).strip()))
            continue
        number = raw.get("no", raw.get("number", index))
        try:
            number = int(number)
        except (TypeError, ValueError):
            number = index
        # netmdcli counts tracks from 0 in its *commands* (see
        # track_command_index) but prints them as a person counts them
        # here; a document that turns out to start at 0 is renumbered
        # rather than left to produce a "track 0".
        disc.tracks.append(
            NetMdTrack(
                number=number,
                title=str(raw.get("name") or raw.get("title") or "").strip(),
                seconds=_seconds_from(raw.get("time", raw.get("duration", 0))),
            )
        )
    if disc.tracks and min(track.number for track in disc.tracks) == 0:
        for track in disc.tracks:
            track.number += 1

    free = document.get("free", document.get("recordable", document.get("available")))
    if free is not None:
        disc.free_seconds = _seconds_from(free)
    return disc


def _first_useful_line(text: str) -> str:
    """netmdcli's real complaint, out of whatever else it printed. Same
    job as `cdrip._first_useful_line()`, against a different tool's
    banner."""
    for line in reversed([line.strip() for line in text.splitlines() if line.strip()]):
        if not line.startswith(("NetMD command line tool", "Usage:")):
            return line
    return ""


def read_disc(run=subprocess.run) -> NetMdDisc:
    """What is on the disc in the deck right now."""
    completed = run_command(["json"], timeout=READ_TIMEOUT_S, run=run)
    output = _combined(completed)
    if _NO_DEVICE.search(output):
        raise NetMdError("no NetMD device found")
    return parse_disc(output)


# --- writing titles ---------------------------------------------------


def track_command_index(number: int) -> int:
    """The number netmdcli's own commands want for a track a person calls
    `number`.

    **netmdcli counts from zero** -- its own help says so: "track numbers
    are off by one (ie track 1 is 0)". Every command that names a track
    goes through this one function, so the off-by-one lives in a single
    place with a single test rather than at each call site, where getting
    it wrong would retitle the wrong track on a real disc."""
    return max(0, int(number) - 1)


@dataclass
class TitleCommand:
    """One netmdcli invocation, and what a person would call it."""

    args: list[str]
    description: str


@dataclass
class TitlePlan:
    """Every title to be written, worked out with no deck present.

    Plan-then-execute, like `cdrip.build_rip_plan()` and
    `cdburn.build_burn_plan()`: the whole of the decision-making is
    testable, and the user can be shown exactly what is about to be
    written before anything is."""

    disc_title: str
    track_titles: list[str] = field(default_factory=list)
    commands: list[TitleCommand] = field(default_factory=list)
    # Titles that lost characters on the way to ASCII, as
    # (what was asked for, what will be written) -- reported, never
    # silently accepted, exactly as the MDRem titler reports them.
    changed: list[tuple[str, str]] = field(default_factory=list)
    # Tracks the disc does not have, so nothing is written for them.
    skipped_tracks: list[int] = field(default_factory=list)


def clean_title(text: str) -> tuple[str, bool]:
    """A title as the disc will actually carry it, and whether that
    differs from what was asked for.

    The same `mdrem.transliterate()` the infrared titler uses, so both
    ways of writing a title onto a MiniDisc promise a person exactly the
    same thing about what will end up there -- the rule CD-Text already
    follows in `cdburn.py`."""
    result = transliterate(text or "")
    cleaned = result.text[:MAX_TITLE]
    return cleaned, cleaned != (text or "")


def build_title_plan(disc_title: str, track_titles: list[str], *, track_count: int) -> TitlePlan:
    """What to write onto a disc that already holds `track_count` tracks.

    `track_count` is the disc's own, read from the deck -- not the length
    of `track_titles`. Writing a title to a track that does not exist is
    not a no-op on a real deck, so anything past the end is skipped and
    reported rather than sent and hoped about."""
    plan = TitlePlan(disc_title="")

    cleaned_disc, changed = clean_title(disc_title)
    plan.disc_title = cleaned_disc
    if changed:
        plan.changed.append((disc_title, cleaned_disc))
    if cleaned_disc:
        plan.commands.append(
            TitleCommand(["rename_disc", cleaned_disc], f"Disc title: {cleaned_disc}")
        )

    for index, title in enumerate(track_titles, start=1):
        if index > track_count:
            plan.skipped_tracks.append(index)
            continue
        cleaned, changed = clean_title(title)
        plan.track_titles.append(cleaned)
        if changed:
            plan.changed.append((title, cleaned))
        plan.commands.append(
            TitleCommand(
                ["rename", str(track_command_index(index)), cleaned],
                f"Track {index}: {cleaned}",
            )
        )
    return plan


def write_titles(plan: TitlePlan, *, on_progress=None, run=subprocess.run) -> None:
    """Runs a plan's commands in order, stopping at the first failure.

    Stopping rather than carrying on: the commands are all edits to one
    TOC, and a deck that has just refused one of them is not in a state
    worth sending the next twenty to. `on_progress(index, total,
    description)` is called before each, which is what lets a dialog say
    which title is going out rather than only that something is."""
    total = len(plan.commands)
    for index, command in enumerate(plan.commands, start=1):
        if on_progress is not None:
            on_progress(index, total, command.description)
        completed = run_command(command.args, run=run)
        output = _combined(completed)
        if _NO_DEVICE.search(output):
            raise NetMdError("no NetMD device found")
        if completed.returncode != 0:
            raise NetMdError(
                _first_useful_line(output) or f"the deck refused: {' '.join(command.args)}"
            )
