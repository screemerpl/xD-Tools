"""Where the album is turned over.

No Qt anywhere in here -- tape.py is the plan, not the dialog.
"""

from mdtools import tape
from mdtools.project import Track


def _album(*minutes: float) -> list[Track]:
    return [Track(title=f"Track {i}", time_seconds=int(m * 60)) for i, m in enumerate(minutes, start=1)]


# -- the tape itself -----------------------------------------------------


def test_a_stated_length_is_both_sides_together():
    """A C60 is thirty minutes a side, not sixty."""
    assert tape.side_seconds(60) == 30 * 60
    assert tape.CASSETTE_LENGTHS[1].name == "C60"
    assert tape.CASSETTE_LENGTHS[1].side_seconds == 30 * 60


def test_the_leader_silence_comes_out_of_every_side():
    assert tape.usable_seconds(60) == 30 * 60 - tape.LEADER_SECONDS


# -- the split -----------------------------------------------------------


def test_the_running_order_is_never_rearranged():
    tracks = _album(5, 5, 5, 5)
    plan = tape.split_sides(tracks, 60)

    assert [t.title for side in plan.sides for t in side.tracks] == [t.title for t in tracks]


def test_the_break_falls_where_the_two_sides_come_out_closest():
    # 10 + 4 + 4 + 10: breaking after track 2 gives 14/14, and every other
    # break is worse -- including the one that merely "fills side A".
    plan = tape.split_sides(_album(10, 4, 4, 10), 90)

    assert len(plan.sides[0].tracks) == 2
    assert plan.sides[0].music_seconds == plan.sides[1].music_seconds


def test_a_long_first_track_pushes_the_break_earlier_rather_than_overrunning():
    # 25 + 5 + 5 on a C60 (30 a side): the balanced-looking break after
    # track 2 puts 30 minutes plus leader on side A, which does not fit.
    plan = tape.split_sides(_album(25, 5, 5), 60)

    assert plan.fits
    assert len(plan.sides[0].tracks) == 1


def test_every_side_pays_for_its_own_leader():
    plan = tape.split_sides(_album(10, 10), 60)

    for side in plan.sides:
        assert side.total_seconds == side.music_seconds + tape.LEADER_SECONDS


def test_an_album_that_does_not_fit_is_reported_not_refused():
    plan = tape.split_sides(_album(30, 30), 60)

    assert plan.fits is False
    assert plan.overflow_seconds > 0
    # still a usable plan: one track a side, not an empty one
    assert len(plan.sides[0].tracks) == 1 and len(plan.sides[1].tracks) == 1


def test_a_track_list_with_no_times_is_split_down_the_middle_and_says_so():
    tracks = [Track(title=f"Track {i}") for i in range(1, 10)]

    plan = tape.split_sides(tracks, 90)

    assert plan.untimed is True
    # nine tracks, the extra one on the side people play first
    assert len(plan.sides[0].tracks) == 5
    assert len(plan.sides[1].tracks) == 4


def test_a_single_track_album_still_has_a_side_a():
    plan = tape.split_sides(_album(3), 60)

    assert len(plan.sides[0].tracks) == 1
    assert plan.sides[1].tracks == []


def test_no_tracks_at_all_is_an_empty_plan_not_a_crash():
    plan = tape.split_sides([], 60)

    assert plan.sides[0].tracks == [] and plan.sides[1].tracks == []


# -- picking a tape ------------------------------------------------------


def test_the_shortest_tape_that_holds_the_album_is_suggested():
    assert tape.suggested_length(_album(10, 10)).name == "C46"
    assert tape.suggested_length(_album(20, 20)).name == "C46"
    assert tape.suggested_length(_album(28, 28)).name == "C60"


def test_an_album_too_long_for_any_stocked_tape_suggests_nothing():
    assert tape.suggested_length(_album(60, 60)) is None


def test_an_untimed_track_list_suggests_nothing_rather_than_guessing():
    assert tape.suggested_length([Track(title="One"), Track(title="Two")]) is None


def test_running_times_read_the_way_a_deck_counter_does():
    assert tape.format_duration(0) == "0:00"
    assert tape.format_duration(605) == "10:05"
