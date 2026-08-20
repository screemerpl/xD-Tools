"""Where an album that does not fit on one disc gets cut.

Pure arithmetic -- no Qt, no deck, no foobar2000 -- which is the whole
point of multidisc.py being its own module: every rule about where a disc
ends is testable without any of them.
"""

from mdtools import multidisc
from mdtools.project import Track

DISC = 80 * 60


def _album(count: int, seconds: int = 300) -> list[Track]:
    return [Track(title=f"Track {i}", time_seconds=seconds) for i in range(1, count + 1)]


# --- how many discs --------------------------------------------------------


def test_an_album_that_fits_is_never_cut():
    plan = multidisc.split_discs(_album(10), DISC)  # 50 minutes
    assert plan.count == 1
    assert plan.fits
    assert plan.breaks == []


def test_a_hundred_and_fifty_minute_album_takes_two_discs():
    """The case this was built for: a double album, one MiniDisc each."""
    plan = multidisc.split_discs(_album(30), DISC)  # 150 minutes
    assert plan.count == 2
    assert plan.fits
    assert all(disc.total_seconds <= DISC for disc in plan.discs)


def test_it_never_uses_more_discs_than_it_has_to():
    """Three discs would be tidier to arrange and would mean buying one
    more than the album needs."""
    assert multidisc.split_discs(_album(30), DISC).count == 2
    assert multidisc.split_discs(_album(50), DISC).count == 4  # 250 minutes


def test_a_track_longer_than_a_whole_disc_is_reported_rather_than_hidden():
    """Nothing can cut inside a track, so the plan says plainly that it
    overruns instead of pretending a split fixed it."""
    plan = multidisc.split_discs([Track(title="Suite", time_seconds=100 * 60)], DISC)
    assert plan.count == 1
    assert not plan.fits
    assert plan.overflow_seconds == 20 * 60


# --- where the cut falls ---------------------------------------------------


def test_the_running_order_is_never_changed():
    """A disc break is a cut in the album, not a repacking of it."""
    album = _album(30)
    plan = multidisc.split_discs(album, DISC)
    ordered = [track for disc in plan.discs for track in disc.tracks]
    assert [track.title for track in ordered] == [track.title for track in album]


def test_the_discs_are_balanced_rather_than_the_first_one_filled():
    """Filling disc one to the brim wastes nothing -- disc two is a whole
    disc either way -- and leaves the listener a lopsided record."""
    plan = multidisc.split_discs(_album(30), DISC)
    first, second = plan.discs
    assert first.total_seconds == second.total_seconds == 75 * 60


def test_each_disc_knows_where_it_sits_in_the_album():
    """The recording flow plays playlist indices, so first/last have to be
    the album's own numbering, not each disc's."""
    plan = multidisc.split_discs(_album(30), DISC)
    first, second = plan.discs
    assert (first.number, first.first_index, first.last_index) == (1, 0, 14)
    assert (second.number, second.first_index, second.last_index) == (2, 15, 29)
    assert plan.disc_for_index(20) is second
    assert plan.breaks == [15]


def test_a_longer_mode_fits_the_same_album_on_one_disc():
    """LP2 is 160 minutes, and the capacity is the caller's to state --
    nothing here can read the deck's mode."""
    assert multidisc.split_discs(_album(30), 160 * 60).count == 1


# --- breaks placed by hand -------------------------------------------------


def test_manual_breaks_are_honoured_exactly():
    plan = multidisc.plan_from_breaks(_album(30), [8, 20], DISC)
    assert [len(disc.tracks) for disc in plan.discs] == [8, 12, 10]
    assert plan.manual


def test_a_manual_break_that_overruns_still_reports_it():
    """The user is allowed to insist; they are not allowed to be unaware."""
    plan = multidisc.plan_from_breaks(_album(30), [28], DISC)
    assert not plan.fits
    assert plan.overflow_seconds > 0


def test_stale_breaks_are_dropped_rather_than_raised_about():
    """They come from a table the user has been reordering, so a break
    pointing past the end is a stale value, not a bug."""
    plan = multidisc.plan_from_breaks(_album(5), [0, 3, 3, 99, -2], DISC)
    assert [len(disc.tracks) for disc in plan.discs] == [3, 2]


def test_a_computed_plan_can_be_handed_straight_back_as_a_manual_one():
    """Which is how "adjust the automatic split" works at all."""
    album = _album(30)
    computed = multidisc.split_discs(album, DISC)
    again = multidisc.plan_from_breaks(album, computed.breaks, DISC)
    assert [len(d.tracks) for d in again.discs] == [len(d.tracks) for d in computed.discs]


# --- nothing to weigh ------------------------------------------------------


def test_an_untimed_track_list_is_left_whole_and_says_so():
    """A hand-typed list carries no times. Guessing a cut from the track
    count would be inventing information -- unlike a cassette, where the
    tape ends whether or not anything knows how long the music is."""
    plan = multidisc.split_discs([Track(title=f"T{i}") for i in range(8)], DISC)
    assert plan.count == 1
    assert plan.untimed


def test_an_empty_album_is_an_empty_plan():
    plan = multidisc.split_discs([], DISC)
    assert plan.discs == []
    assert plan.fits
