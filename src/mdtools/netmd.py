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

**Every NetMD recording goes over the USB cable, in every mode, and
nothing else is ever needed.** MDRem's own recording still runs a real
album through the sound card and an optical (Toslink) cable in real
time -- that has not changed, and cannot: MDRem presses buttons and hears
nothing back, so it cannot itself move audio at all. NetMD is different:
`netmdcli`'s `send` command takes a plain 16-bit/44100Hz WAV file with no
`-d` flag at all, which *is* SP -- Red Book PCM, unencoded -- so SP goes
out over USB exactly the way LP2/LP4 already do (those pass through
`-d lp2`/`-d lp4`, netmdcli's own on-the-fly ATRAC3 encoder, since a
digital input cannot carry ATRAC3 at all). One cable, one flow, for every
mode -- deliberately simpler than the version of this file that shipped
first, which still ran SP over Toslink because that is the only way MDRem
can do it. A NetMD user never has to reason about which cable a mode
needs, which is the whole point of `connection_advice()` existing at
all.

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
from pathlib import Path

from mdtools import cdrip, decode
from mdtools.mdrem import MAX_TRACK, transliterate

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

    `minutes` is the same number RecordDialog's "one disc holds" spin box
    has always taken -- stated here rather than typed there, now that
    something in the app actually knows which mode the deck is in.
    `encoder_flag` is what netmdcli's `-d` flag wants for this mode, or ""
    for SP, which needs no on-the-fly encoder because it is sent as plain
    PCM, not encoded at all -- see this module's own header for why that
    no longer means SP needs a different cable from LP2/LP4."""

    key: str
    label: str
    minutes: int
    encoder_flag: str


MODES: dict[str, RecordingMode] = {
    MODE_SP: RecordingMode(MODE_SP, "SP", 80, encoder_flag=""),
    MODE_LP2: RecordingMode(MODE_LP2, "LP2", 160, encoder_flag="lp2"),
    MODE_LP4: RecordingMode(MODE_LP4, "LP4", 320, encoder_flag="lp4"),
}


def mode(key: str) -> RecordingMode:
    """The mode a setting names, falling back to SP.

    Falling back rather than raising: this reads a stored string, and a
    settings file carrying something unknown (an older version's, a typo,
    a hand edit) should leave the app working in the mode that needs the
    least of the hardware, not refuse to open a dialog."""
    return MODES.get(str(key).strip().lower(), MODES[MODE_SP])


def connection_advice(*, netmd: bool) -> str:
    """What to plug in, in as many words.

    Only one answer exists on the NetMD side now, whatever mode is chosen
    -- SP, LP2 and LP4 all go out over the same USB cable as a file
    transfer, so there is no mode-specific mistake to warn about any more
    (see this module's own header). The MDRem side is unchanged: that
    adapter cannot move audio at all, so a real Toslink feed and a real
    album playing in real time are still how a recording actually reaches
    the deck.
    """
    if not netmd:
        return (
            "Connect the computer's optical (Toslink) output to the deck's digital input. "
            "The MDRem adapter marks the tracks and writes the titles."
        )
    return (
        "Connect the USB cable only. The audio, track splits and titles all go over it, in every "
        "recording mode -- no optical cable is needed."
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


def _run_checked(args: list[str], *, refusal: str, run=subprocess.run) -> None:
    """One command that either goes through or raises -- the same
    no-device/non-zero check `erase_disc()`, `write_titles()` and
    `send_tracks()` each already made their own way. `refusal` is what to
    say if the deck answers but declines, since "the deck refused" alone
    would read the same for an erase, a track title and a play command."""
    completed = run_command(args, run=run)
    output = _combined(completed)
    if _NO_DEVICE.search(output):
        raise NetMdError("no NetMD device found")
    if completed.returncode != 0:
        raise NetMdError(_first_useful_line(output) or refusal)


def erase_disc(run=subprocess.run) -> None:
    """Wipes the disc in the deck right now -- netmdcli's own `erase
    force`, mirroring the "Erase MiniDisc..." button MDRem's own
    RecordDialog offers (erase_dialog.py), which drives the exact same
    button sequence blind, over infrared, because it cannot ask the deck
    whether an erase actually needs confirming first. `force` is required
    here for the same reason it is in mdrem's own sequence: without it,
    netmdcli would be the one asking a question nothing here can answer."""
    _run_checked(["erase", "force"], refusal="the deck refused to erase the disc", run=run)


# --- transport control --------------------------------------------------
#
# `netmdcli`'s own commands, one call each -- the NetMD half of what
# RemoteDialog's button grid sends over infrared for MDRem. There is no
# equivalent of that dialog's titling/character-entry/track-editing
# groups here: a NetMD title is written by build_record_plan()/
# write_titles() in one shot, not typed key by key, and the deck answers
# every command (unlike MDRem), so there is nothing to "send and hope"
# about. There is also no `eject` in netmdcli's own command list --
# confirmed against its --help output, not assumed -- so panels/
# netmd_remote_dialog.py has no Eject button to offer.

PLAY_MODES = ("single", "repeat", "shuffle")


def play(track: int | None = None, *, run=subprocess.run) -> None:
    """Plays the current track, or a given one (1-based, as a person
    counts them -- track_command_index() owns the same off-by-one every
    other track-naming command in this module already does)."""
    args = ["play"] if track is None else ["play", str(track_command_index(track))]
    _run_checked(args, refusal="the deck refused to play", run=run)


def pause(*, run=subprocess.run) -> None:
    _run_checked(["pause"], refusal="the deck refused to pause", run=run)


def stop(*, run=subprocess.run) -> None:
    _run_checked(["stop"], refusal="the deck refused to stop", run=run)


def fast_forward(*, run=subprocess.run) -> None:
    _run_checked(["fforward"], refusal="the deck refused to fast-forward", run=run)


def rewind(*, run=subprocess.run) -> None:
    _run_checked(["rewind"], refusal="the deck refused to rewind", run=run)


def next_track(*, run=subprocess.run) -> None:
    _run_checked(["next"], refusal="the deck refused to skip ahead", run=run)


def previous_track(*, run=subprocess.run) -> None:
    _run_checked(["previous"], refusal="the deck refused to go back a track", run=run)


def restart_track(*, run=subprocess.run) -> None:
    _run_checked(["restart"], refusal="the deck refused to restart the track", run=run)


def set_play_mode(play_mode: str, *, run=subprocess.run) -> None:
    """`play_mode` is one of PLAY_MODES -- netmdcli takes the word as
    written, so this refuses anything else itself rather than letting a
    typo reach the deck as some other, unintended command."""
    if play_mode not in PLAY_MODES:
        raise NetMdError(f"unknown play mode: {play_mode}")
    _run_checked(
        ["setplaymode", play_mode], refusal="the deck refused to change play mode", run=run
    )


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


# --- recording a disc over USB -----------------------------------------
#
# `netmdcli send <file> [<title>]` takes a track's audio *and* its title
# in one command -- unlike MDRem, there is no separate titling pass here
# at all: a track lands on the disc already named. Everything below is
# the plan-then-execute shape cdburn.py's own burn plan already uses,
# for the same reason: what will happen has to be shown, in full, before
# a recording that cannot be undone starts.

# Problem codes -- bare strings rather than sentences, the same reasoning
# cdburn.Problem follows: no Qt in this module, so no tr() to phrase them
# with, and a dialog does that translation.
UNREADABLE = "unreadable"
TOO_MANY_TRACKS = "too_many_tracks"
TOO_LONG_FOR_DISC = "too_long_for_disc"
NO_TRACKS = "no_tracks"


class NetMdCancelled(Exception):
    """The user stopped a recording in progress."""


@dataclass(frozen=True)
class RecordProblem:
    code: str
    track_number: int = 0  # 1-based; 0 is about the disc as a whole
    detail: str = ""


@dataclass
class RecordTrack:
    source: Path
    title: str
    properties: object = None  # decode.AudioProperties, or None if unreadable

    @property
    def seconds(self) -> float:
        return self.properties.duration_seconds if self.properties else 0.0


@dataclass
class RecordPlan:
    """One disc's worth of NetMD recording, planned with no deck present.

    Titles are cleaned through `clean_title()` up front -- `changed`
    carries the same before/after pairs `build_title_plan()` reports --
    because the title sent alongside a track's audio is the only title a
    NetMD recording ever gets: there is no second, separate titling pass
    to catch a dropped character here, unlike MDRem's."""

    disc_title: str
    mode: RecordingMode
    tracks: list[RecordTrack] = field(default_factory=list)
    problems: list[RecordProblem] = field(default_factory=list)
    changed: list[tuple[str, str]] = field(default_factory=list)

    @property
    def total_seconds(self) -> float:
        return sum(track.seconds for track in self.tracks)

    @property
    def capacity_seconds(self) -> float:
        return self.mode.minutes * 60

    @property
    def can_record(self) -> bool:
        return not self.problems and bool(self.tracks)

    def problems_for(self, track_number: int) -> list[RecordProblem]:
        return [problem for problem in self.problems if problem.track_number == track_number]


def build_record_plan(
    sources,
    *,
    disc_title: str = "",
    mode_key: str = MODE_SP,
    analyze=decode.analyze,
) -> RecordPlan:
    """Turns (path, title) pairs into a plan, with every reason it could
    not be recorded attached rather than raised -- cdburn.build_burn_plan()'s
    own reasoning: the dialog shows all of them at once, next to the
    tracks they are about, rather than stopping at the first bad file.
    """
    chosen = mode(mode_key)
    cleaned_disc, disc_changed = clean_title(disc_title)
    plan = RecordPlan(disc_title=cleaned_disc, mode=chosen)
    if disc_changed:
        plan.changed.append((disc_title, cleaned_disc))

    for number, (path, title) in enumerate(sources, start=1):
        path = Path(path)
        try:
            properties = analyze(path)
        except decode.DecodeError as exc:
            properties = None
            plan.problems.append(RecordProblem(UNREADABLE, number, str(exc)))
        cleaned_title, changed = clean_title(title)
        if changed:
            plan.changed.append((title, cleaned_title))
        plan.tracks.append(RecordTrack(source=path, title=cleaned_title, properties=properties))

    if not plan.tracks:
        plan.problems.append(RecordProblem(NO_TRACKS))
    if len(plan.tracks) > MAX_TRACK:
        # The same ceiling MDRem titling is held to (MAX_TRACK) -- see its
        # own note on why 99 is real, not a round number: the deck's
        # number field commits on the second digit either way.
        plan.problems.append(RecordProblem(TOO_MANY_TRACKS, 0, str(len(plan.tracks))))
    if plan.total_seconds > plan.capacity_seconds:
        over = plan.total_seconds - plan.capacity_seconds
        plan.problems.append(RecordProblem(TOO_LONG_FOR_DISC, 0, f"{over:.1f}s"))
    return plan


def wav_name_for(number: int) -> str:
    """Zero-padded so a scratch folder reads in disc order -- the same
    convention cdburn.wav_name_for() uses for its own tracks."""
    return f"{number:02d}.wav"


def prepare_track_wavs(
    plan: RecordPlan,
    directory: Path | str,
    *,
    on_progress=None,
    should_cancel=None,
) -> list[str]:
    """Decodes every track into `directory` as Red Book WAV, in disc order
    -- cdburn.prepare_wavs(), for the same reason: netmdcli's `send` wants
    a plain WAV file on disk, not a stream, whatever mode is about to
    encode it (SP sends it as-is; LP2/LP4's `-d` flag does the ATRAC3
    encoding itself, on the fly, as the file goes out).

    Returns the bare filenames. Raises NetMdError on the first failure --
    unlike planning, there is nothing useful to do with a half-decoded
    album. Cancelling takes effect between tracks and costs nothing here:
    no deck has been touched yet, only a scratch folder."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    names: list[str] = []
    for number, track in enumerate(plan.tracks, start=1):
        if should_cancel is not None and should_cancel():
            raise NetMdCancelled()
        name = wav_name_for(number)
        try:
            decode.to_wav(track.source, directory / name)
        except decode.DecodeError as exc:
            raise NetMdError(str(exc)) from exc
        names.append(name)
        if on_progress is not None:
            on_progress(number / len(plan.tracks))
    return names


# How long netmdcli is given to send one track. Unlike a title command (a
# fraction of a second), this moves the whole file, and nothing here has
# been measured against real hardware: LP2/LP4's on-the-fly ATRAC3
# encoding is meant to be faster than real time, but whether a given
# deck's true-PCM SP upload is has not been confirmed on anything. Set
# generous rather than tight -- a timeout mid-transfer costs more than a
# slow-looking progress bar.
SEND_TIMEOUT_S = 600.0


def send_args(track_mode: RecordingMode, path: Path | str, title: str) -> list[str]:
    """One `send` invocation's arguments, after the tool itself --
    run_command() puts the tool in front, the same shape every other
    command in this module takes.

    The `-d` flag is netmdcli's own on-the-fly ATRAC3 encoder and comes
    *before* the command name, not after -- LP2/LP4 only. SP carries no
    flag at all: it needs no encoding, which is exactly why it can go out
    over the same USB cable as the other two (see this module's header)."""
    args = []
    if track_mode.encoder_flag:
        args += ["-d", track_mode.encoder_flag]
    args += ["send", str(path)]
    if title:
        args.append(title)
    return args


def send_tracks(
    plan: RecordPlan,
    directory: Path | str,
    names: list[str],
    *,
    on_progress=None,
    run=subprocess.run,
) -> None:
    """Sends every track, in order, then writes the disc's own title --
    stopping at the first refusal, write_titles()'s own reasoning: this is
    all one recording, and a deck that has just refused a track is not
    worth sending the next one to.

    `on_progress(index, total, description)` is called before each send,
    counting the disc title as the final step, so a dialog can show which
    track (or "the disc title") is going out."""
    directory = Path(directory)
    total = len(names) + (1 if plan.disc_title else 0)
    for index, (name, track) in enumerate(zip(names, plan.tracks), start=1):
        if on_progress is not None:
            on_progress(index, total, track.title)
        completed = run_command(
            send_args(plan.mode, directory / name, track.title), timeout=SEND_TIMEOUT_S, run=run
        )
        output = _combined(completed)
        if _NO_DEVICE.search(output):
            raise NetMdError("no NetMD device found")
        if completed.returncode != 0:
            raise NetMdError(_first_useful_line(output) or f"the deck refused track {index}")

    if plan.disc_title:
        if on_progress is not None:
            on_progress(total, total, plan.disc_title)
        completed = run_command(["rename_disc", plan.disc_title], run=run)
        output = _combined(completed)
        if _NO_DEVICE.search(output):
            raise NetMdError("no NetMD device found")
        if completed.returncode != 0:
            raise NetMdError(_first_useful_line(output) or "the deck refused the disc title")
