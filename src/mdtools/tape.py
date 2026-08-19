"""Compact cassette: how long a tape is, and where the album is turned over.

A cassette is the first medium here that cannot hold an album in one piece.
A MiniDisc and a CD-R are one surface with one running order; a C60 is two
sides of half an hour, and something has to decide which track is the last
one before the user gets up and turns it over. That decision is this
module, and it is deliberately separate from both the layout that prints
the two sides and the dialog that talks the user through recording them --
the same "build a plan, let the caller execute it" split as `mdrem.py`'s
upload plan and `cdburn.py`'s burn plan.

Two physical facts shape everything below.

**Every side starts with leader tape**, a few inches of untreated plastic
spliced in to take the wear of being wound around the hub. Nothing recorded
onto it survives, because it is not magnetic -- so a recording that starts
the instant the deck does loses the first seconds of the first track on each
side. `LEADER_SECONDS` (10) of silence is recorded first instead, which is
the user's explicit instruction and comfortably more than the ~7 seconds of
leader a normal cassette carries. It comes out of the side's usable time,
on both sides, because both have leader.

**A stated length is a total across both sides.** A C60 is sixty minutes of
tape, thirty per side -- so `side_seconds()` halves it, and every capacity
check here is per side, never against the whole tape. Getting that backwards
would let a 55-minute album look like it fits a C60 comfortably.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from mdtools.project import Track

# Silence recorded at the start of each side, before the first track, so
# the music does not begin on the leader. Ten seconds by explicit request.
LEADER_SECONDS = 10

# The gap the deck leaves between the two sides in practice -- the seconds
# spent stopping, ejecting, flipping and pressing record again. Not part of
# the arithmetic; noted here because it is why nothing tries to be clever
# about using every last second of a side.
FLIP_IS_MANUAL = True


@dataclass(frozen=True)
class CassetteLength:
    """One of the lengths cassettes are actually sold in.

    `name` is the label on the shell (a C60 is sixty minutes) and
    `total_seconds` what that means. Anything else -- a C46 dub, a C120 --
    is a plain number the user can type; these are the shortcuts.
    """

    name: str
    total_minutes: int

    @property
    def total_seconds(self) -> int:
        return self.total_minutes * 60

    @property
    def side_seconds(self) -> int:
        return self.total_seconds // 2


# C46 is the album length (two 23-minute sides, an LP), C60 and C90 the two
# everybody owns, C100 the longest that is still common and reliable -- C120
# tape is thin enough to stretch and jam, so it is deliberately not offered
# as a shortcut even though the arithmetic would handle it.
CASSETTE_LENGTHS: tuple[CassetteLength, ...] = (
    CassetteLength("C46", 46),
    CassetteLength("C60", 60),
    CassetteLength("C90", 90),
    CassetteLength("C100", 100),
)

DEFAULT_LENGTH = CASSETTE_LENGTHS[2]  # C90: the one that fits almost anything


def side_seconds(total_minutes: float) -> float:
    """Half the tape, in seconds -- a stated length is both sides together."""
    return total_minutes * 60 / 2


def usable_seconds(total_minutes: float, leader_seconds: float = LEADER_SECONDS) -> float:
    """What one side can actually hold, once the leader silence is paid for."""
    return max(0.0, side_seconds(total_minutes) - leader_seconds)


@dataclass
class SidePlan:
    """One side of the tape: which tracks, and how full it ends up."""

    label: str  # "A" or "B"
    tracks: list[Track] = field(default_factory=list)
    leader_seconds: float = LEADER_SECONDS

    @property
    def music_seconds(self) -> float:
        return sum(t.time_seconds or 0 for t in self.tracks)

    @property
    def total_seconds(self) -> float:
        return self.leader_seconds + self.music_seconds


@dataclass
class TapePlan:
    """The whole recording: two sides, and whether it actually fits.

    `overflow_seconds` is how far the worse side runs past what the tape
    holds -- zero when it fits. It is reported rather than raised because
    running over is the user's call to make: a stated C90 usually has a
    minute or two of slack, and a track that ends a few seconds into the
    run-out is a nuisance, not a lost recording. The dialog says so and
    lets them go ahead, the same way the MiniDisc flow warns about an album
    longer than 80 minutes without refusing to record it.
    """

    sides: tuple[SidePlan, SidePlan]
    total_minutes: float
    side_capacity_seconds: float

    @property
    def fits(self) -> bool:
        return self.overflow_seconds <= 0

    @property
    def overflow_seconds(self) -> float:
        return max(0.0, max(side.total_seconds for side in self.sides) - self.side_capacity_seconds)

    @property
    def untimed(self) -> bool:
        """True when the split is a guess because the tracks carry no times.

        A hand-typed track list has none, and then the arithmetic below is
        counting zeros -- it still splits the album down the middle by track
        count, which is the best guess available, but the caller must not
        present that as "this fits"."""
        return all((track.time_seconds or 0) == 0 for side in self.sides for track in side.tracks)


def split_sides(
    tracks: list[Track],
    total_minutes: float,
    leader_seconds: float = LEADER_SECONDS,
) -> TapePlan:
    """Where to turn the tape over.

    The album's order is never changed -- a side break is a *cut* in the
    running order, not a repacking of it. So the only choice is which track
    the break falls after, and every possible break is tried: the one that
    leaves the two sides closest in length wins, among those that fit.

    Balancing rather than filling side A to the brim is the point. Cramming
    A and leaving B nearly empty wastes no tape at all (the tape is the same
    length either way) and costs the listener a lopsided record, so there is
    nothing to be gained by it. When nothing fits, the least-overrun break is
    returned anyway with `fits` False -- see TapePlan for why that is not an
    exception.
    """
    capacity = side_seconds(total_minutes)
    usable = max(0.0, capacity - leader_seconds)
    durations = [float(t.time_seconds or 0) for t in tracks]

    best_index = _best_break(durations, usable)
    plan = TapePlan(
        sides=(
            SidePlan("A", list(tracks[:best_index]), leader_seconds),
            SidePlan("B", list(tracks[best_index:]), leader_seconds),
        ),
        total_minutes=total_minutes,
        side_capacity_seconds=capacity,
    )
    return plan


def _best_break(durations: list[float], usable: float) -> int:
    """The index the second side starts at.

    Two passes rather than one scoring function: a break that fits is always
    better than a shorter-but-overrunning one, however well balanced, and
    collapsing "does it fit" into the same number as "how balanced is it"
    would let a tiny imbalance outrank an album that does not fit at all.
    """
    if not durations:
        return 0
    if all(value == 0 for value in durations):
        # No times to weigh, so the only honest answer is the middle. Round
        # up, so a 9-track album puts the extra track on side A -- the side
        # people play first.
        return (len(durations) + 1) // 2

    if len(durations) == 1:
        # Nothing to split: one track is side A, whether or not it fits.
        return 1

    total = sum(durations)
    candidates = range(1, len(durations))

    fitting: list[tuple[float, int]] = []
    overrunning: list[tuple[float, int]] = []
    for index in candidates:
        first = sum(durations[:index])
        second = total - first
        imbalance = abs(first - second)
        if first <= usable and second <= usable:
            fitting.append((imbalance, index))
        else:
            overrunning.append((max(first, second) - usable, index))

    if fitting:
        return min(fitting)[1]
    return min(overrunning)[1]


def format_duration(seconds: float) -> str:
    """m:ss, the way a tape's remaining time is read off a deck's counter."""
    seconds = max(0, int(round(seconds)))
    return f"{seconds // 60}:{seconds % 60:02d}"


def suggested_length(tracks: list[Track], leader_seconds: float = LEADER_SECONDS) -> CassetteLength | None:
    """The shortest stocked cassette this album fits on, or None if it fits
    none of them.

    Offered as a default rather than chosen silently: what tape is in the
    box is a fact about the user's shelf, not about the album, and the
    dialog only pre-selects this. Untimed tracks give None -- guessing a
    length from a track count would be inventing information.
    """
    if not tracks or all((track.time_seconds or 0) == 0 for track in tracks):
        return None
    for length in CASSETTE_LENGTHS:
        if split_sides(tracks, length.total_minutes, leader_seconds).fits:
            return length
    return None


__all__ = [
    "CASSETTE_LENGTHS",
    "DEFAULT_LENGTH",
    "LEADER_SECONDS",
    "CassetteLength",
    "SidePlan",
    "TapePlan",
    "format_duration",
    "side_seconds",
    "split_sides",
    "suggested_length",
    "usable_seconds",
]
