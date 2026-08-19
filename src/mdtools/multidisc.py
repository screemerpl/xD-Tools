"""One album across several discs -- where each disc ends.

A double album does not fit on a MiniDisc, and a MiniDisc cannot be turned
over: 150 minutes of music is two discs, recorded one after the other, with
the deck ejecting in between. That decision -- which track is the last one
on each disc -- is this module, and it is deliberately separate from both
the dialog that drives the recording and the deck that receives it, the
same "build a plan, let the caller execute it" split as `mdrem.py`'s upload
plan, `tape.py`'s side split and `cdburn.py`'s burn plan.

Two things shape it.

**The running order is never changed.** A disc break is a *cut* in the
album, not a repacking of it, so the only choice is which track it falls
after. That is the same rule `tape.split_sides()` follows, and it is what
makes the split describable in one sentence on the dialog.

**Balanced, not filled to the brim.** Cramming the first disc full and
leaving a five-minute stub on the second wastes nothing -- the second disc
is a whole disc either way -- and costs the listener a lopsided record. So
among the splits that fit, the one with the shortest longest disc wins.

The capacity is the caller's to state and never this module's to guess: a
MiniDisc holds 80 minutes in SP and 160 in LP2, and which mode a deck is in
can neither be read nor set through the MDRem key table (see `mdrem.py`).
A CD-R is 74 or 80. All this module does is divide by the number it is
given.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import ceil

from mdtools.project import Track

# A MiniDisc in SP, and the longest CD-R anybody stocks. The default rather
# than the law -- LP2 doubles it, and the dialog lets it be typed.
DEFAULT_DISC_MINUTES = 80
MIN_DISC_MINUTES = 5
MAX_DISC_MINUTES = 320  # MDLP's LP4, the longest any of these media manage


@dataclass
class DiscPlan:
    """One disc: which tracks, and where they sit in the whole album."""

    number: int  # 1-based, which is also what the disc title says
    first_index: int  # index of its first track within the whole album
    tracks: list[Track] = field(default_factory=list)

    @property
    def last_index(self) -> int:
        return self.first_index + len(self.tracks) - 1

    @property
    def total_seconds(self) -> float:
        return sum(track.time_seconds or 0 for track in self.tracks)

    def contains(self, index: int) -> bool:
        return self.first_index <= index <= self.last_index


@dataclass
class MultiDiscPlan:
    """The whole recording, and whether it actually fits.

    `overflow_seconds` is how far the fullest disc runs past what one holds
    -- zero when it fits. Reported rather than raised, for the same reason
    `tape.TapePlan` reports it: which mode the deck is in is not knowable
    from here, so a plan that overruns an 80-minute assumption may be
    perfectly fine on a deck set to LP2. The dialog says so and lets the
    user decide.
    """

    discs: list[DiscPlan]
    capacity_seconds: float
    manual: bool = False  # the breaks were placed by the user, not computed

    @property
    def count(self) -> int:
        return len(self.discs)

    @property
    def overflow_seconds(self) -> float:
        if not self.discs:
            return 0.0
        return max(0.0, max(disc.total_seconds for disc in self.discs) - self.capacity_seconds)

    @property
    def fits(self) -> bool:
        return self.overflow_seconds <= 0

    @property
    def untimed(self) -> bool:
        """True when the tracks carry no running times, so nothing here can
        be weighed.

        A hand-typed track list has none. The album is then left whole
        rather than cut at a guess: unlike a cassette, where the tape runs
        out whether or not anything knows how long the music is, a disc
        that turns out too short costs one retry and no material."""
        return all((track.time_seconds or 0) == 0 for disc in self.discs for track in disc.tracks)

    @property
    def breaks(self) -> list[int]:
        """The album indices each disc after the first starts at -- the same
        form `plan_from_breaks()` takes, so a computed plan can be handed
        straight back as a manual one for the user to adjust."""
        return [disc.first_index for disc in self.discs[1:]]

    def disc_for_index(self, index: int) -> DiscPlan | None:
        for disc in self.discs:
            if disc.contains(index):
                return disc
        return None


def plan_from_breaks(
    tracks: list[Track], breaks: list[int] | tuple[int, ...], capacity_seconds: float
) -> MultiDiscPlan:
    """The plan a given set of break points describes.

    `breaks` are album indices at which a new disc *starts*. Anything
    outside the album, and any duplicate, is dropped rather than refused --
    they come from a table the user has been reordering, so a break left
    pointing past the end is a stale value, not something to raise about.
    """
    if not tracks:
        return MultiDiscPlan([], capacity_seconds)
    bounds = sorted({int(b) for b in breaks if 0 < int(b) < len(tracks)})
    starts = [0] + bounds
    ends = bounds + [len(tracks)]
    discs = [
        DiscPlan(number=number, first_index=start, tracks=list(tracks[start:end]))
        for number, (start, end) in enumerate(zip(starts, ends), start=1)
    ]
    return MultiDiscPlan(discs=discs, capacity_seconds=capacity_seconds, manual=bool(bounds))


def split_discs(tracks: list[Track], capacity_seconds: float) -> MultiDiscPlan:
    """Where to change discs: the fewest that fit, split as evenly as the
    running order allows.

    Fewest first, then balanced within that -- a two-disc album must never
    come back as three just because three would be tidier, and an album
    that fits on one is never cut at all.
    """
    durations = [int(round(track.time_seconds or 0)) for track in tracks]
    total = sum(durations)
    if not tracks or capacity_seconds <= 0 or total <= 0:
        # Nothing to weigh: one disc, and `untimed` tells the caller why.
        return plan_from_breaks(tracks, [], capacity_seconds)

    fewest = max(1, ceil(total / capacity_seconds))
    for count in range(fewest, len(tracks) + 1):
        plan = plan_from_breaks(tracks, _balanced_breaks(durations, count), capacity_seconds)
        if plan.fits:
            return plan
    # A single track longer than a whole disc: one track per disc is as far
    # as cutting can go, and the plan says plainly that it still overruns.
    return plan_from_breaks(tracks, list(range(1, len(tracks))), capacity_seconds)


def disc_count_for(tracks: list[Track], capacity_seconds: float) -> int:
    return split_discs(tracks, capacity_seconds).count


def _balanced_breaks(durations: list[int], count: int) -> list[int]:
    """Split into at most `count` contiguous parts, making the longest part
    as short as possible.

    Minimising the longest part is what "balanced" means here: it is the
    one objective that both keeps every disc under the limit and stops the
    last disc from being a stub. Solved the standard way -- binary search
    for the smallest limit that `count` parts can respect, then fill
    greedily up to it -- rather than by scoring every possible cut the way
    `tape._best_break()` does, which is affordable there only because a
    cassette has exactly one break to place.
    """
    count = max(1, min(count, len(durations)))
    if count == 1 or not durations:
        return []

    low, high = max(durations), sum(durations)
    while low < high:
        mid = (low + high) // 2
        if _parts_needed(durations, mid) <= count:
            high = mid
        else:
            low = mid + 1

    breaks: list[int] = []
    running = 0
    for index, value in enumerate(durations):
        if index > 0 and running + value > low:
            breaks.append(index)
            running = 0
        running += value
    return breaks


def _parts_needed(durations: list[int], limit: int) -> int:
    parts = 1
    running = 0
    for value in durations:
        if running + value > limit:
            parts += 1
            running = 0
        running += value
    return parts


__all__ = [
    "DEFAULT_DISC_MINUTES",
    "MAX_DISC_MINUTES",
    "MIN_DISC_MINUTES",
    "DiscPlan",
    "MultiDiscPlan",
    "disc_count_for",
    "plan_from_breaks",
    "split_discs",
]
