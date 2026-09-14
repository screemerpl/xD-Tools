"""netmd.py -- driving a deck over USB through the bundled netmdcli.

No deck, no USB cable and no driver anywhere in here: every command goes
through an injected `run` the way cdrip's own tests drive cd-paranoia, so
what is tested is the parsing, the planning and the off-by-one -- the
parts that would otherwise only be found out with a real disc in a real
deck, where getting them wrong costs the disc.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from mdtools import netmd


class _Completed:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def _answering(*results, record=None):
    """A `run` that hands back canned results in order, remembering the
    argument lists it was called with."""
    queue = list(results)

    def run(args, **kwargs):
        if record is not None:
            record.append(list(args))
        return queue.pop(0) if queue else _Completed()

    return run


NO_DEVICE = _Completed(stdout="Found no NetMD device(s).\n", returncode=1)

DISC_JSON = """
{
  "title": "Night Ferry",
  "tracks": [
    {"no": 1, "name": "Harbour Lights", "time": 252},
    {"no": 2, "name": "Slow Tide", "time": 228}
  ],
  "free": 1800
}
"""


# --- recording modes ------------------------------------------------------


def test_the_three_modes_carry_their_own_capacity():
    assert netmd.MODES[netmd.MODE_SP].minutes == 80
    assert netmd.MODES[netmd.MODE_LP2].minutes == 160
    assert netmd.MODES[netmd.MODE_LP4].minutes == 320


def test_only_the_lp_modes_carry_an_encoder_flag():
    """SP is sent as plain, unencoded PCM -- LP2/LP4 need netmdcli's own
    on-the-fly ATRAC3 encoder, requested with -d."""
    assert netmd.MODES[netmd.MODE_SP].encoder_flag == ""
    assert netmd.MODES[netmd.MODE_LP2].encoder_flag == "lp2"
    assert netmd.MODES[netmd.MODE_LP4].encoder_flag == "lp4"


def test_an_unknown_mode_falls_back_to_sp():
    """A settings file can carry anything -- an older version's value, a
    typo, a hand edit. Falling back to the mode that needs least of the
    hardware beats refusing to open the dialog."""
    assert netmd.mode("wobble").key == netmd.MODE_SP
    assert netmd.mode("").key == netmd.MODE_SP
    assert netmd.mode("LP2").key == netmd.MODE_LP2, "and it is case-insensitive"


def test_netmd_advice_is_usb_only_whatever_the_mode():
    """Every NetMD mode -- SP included -- goes out over USB now, so there
    is no mode-specific cable mistake to warn about any more."""
    advice = netmd.connection_advice(netmd=True)
    assert "usb" in advice.lower()
    assert "no optical cable" in advice.lower()


def test_without_netmd_the_advice_is_the_mdrem_one():
    """MDRem still needs the real Toslink feed: it cannot move audio at
    all, so this half is unaffected by NetMD going USB-only."""
    advice = netmd.connection_advice(netmd=False)
    assert "MDRem" in advice
    assert "optical" in advice.lower()


# --- finding the tool and the deck ---------------------------------------


def test_the_bundled_tool_is_found():
    """It ships in bin/win64 -- if this fails on Windows, the binary is
    missing from the build rather than the deck being unplugged."""
    import sys

    if sys.platform != "win32":
        pytest.skip("nothing is bundled for Linux; netmdcli comes from PATH there")
    assert netmd.netmdcli_path() is not None
    assert netmd.missing_tools() == []


def test_no_device_reads_as_no_device():
    assert netmd.device_present(run=_answering(NO_DEVICE)) is False


def test_a_deck_that_answers_counts_as_present():
    assert netmd.device_present(run=_answering(_Completed(stdout="Track 1 playing"))) is True


def test_a_tool_that_cannot_run_is_not_a_crash():
    """A missing driver, a binary that will not start: still just "no
    device" to everything upstream."""

    def explode(args, **kwargs):
        raise OSError("nope")

    assert netmd.device_present(run=explode) is False


def test_a_timeout_is_reported_as_one():
    def hang(args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args, timeout=1)

    with pytest.raises(netmd.NetMdError, match="did not answer"):
        netmd.run_command(["status"], run=hang)


# --- reading the disc -----------------------------------------------------


def test_the_disc_and_its_tracks_are_read():
    disc = netmd.read_disc(run=_answering(_Completed(stdout=DISC_JSON)))

    assert disc.title == "Night Ferry"
    assert disc.track_count == 2
    assert [track.title for track in disc.tracks] == ["Harbour Lights", "Slow Tide"]
    assert disc.tracks[0].seconds == 252
    assert disc.free_seconds == 1800


def test_json_after_a_banner_is_still_read():
    """netmdcli prints its own chatter before the document when anything
    raised the log level -- the same tolerance cdrip.parse_toc() applies
    to cdparanoia's banner."""
    disc = netmd.parse_disc("NetMD command line tool\nopening device...\n" + DISC_JSON)
    assert disc.title == "Night Ferry"


def test_the_older_key_names_are_read_too():
    """These have moved between netmdcli versions, and the bundled build
    cannot be asked which it uses without a deck attached."""
    disc = netmd.parse_disc('{"name": "Mixtape", "trackList": [{"title": "One"}]}')
    assert disc.title == "Mixtape"
    assert [track.title for track in disc.tracks] == ["One"]


def test_a_clock_time_is_read_as_seconds():
    """Some versions write durations as h:mm:ss rather than a number.
    Reading one as the other turns a 4-minute track into 4 seconds, with
    nothing to signal it."""
    disc = netmd.parse_disc('{"title": "x", "tracks": [{"name": "a", "time": "4:12"}]}')
    assert disc.tracks[0].seconds == 252


def test_tracks_numbered_from_zero_are_renumbered():
    """Whichever way the document counts, a person counts from one."""
    disc = netmd.parse_disc('{"title": "x", "tracks": [{"no": 0, "name": "a"}, {"no": 1, "name": "b"}]}')
    assert [track.number for track in disc.tracks] == [1, 2]


def test_an_unreadable_answer_is_an_error_not_an_empty_disc():
    """An empty disc and a deck that said nothing must never look alike:
    one is something to write titles onto, the other is a fault."""
    with pytest.raises(netmd.NetMdError):
        netmd.parse_disc("Found no NetMD device(s).")


def test_reading_with_no_device_says_so():
    with pytest.raises(netmd.NetMdError, match="no NetMD device"):
        netmd.read_disc(run=_answering(NO_DEVICE))


def test_erase_sends_force_so_nothing_here_has_to_ask():
    sent: list[list[str]] = []
    netmd.erase_disc(run=_answering(record=sent))
    assert [args[1:] for args in sent] == [["erase", "force"]]


def test_erase_with_no_device_says_so():
    with pytest.raises(netmd.NetMdError, match="no NetMD device"):
        netmd.erase_disc(run=_answering(NO_DEVICE))


def test_a_refused_erase_is_reported():
    with pytest.raises(netmd.NetMdError, match="nope"):
        netmd.erase_disc(run=_answering(_Completed(stderr="nope", returncode=1)))


# --- transport control ------------------------------------------------


def test_play_with_no_track_just_plays():
    sent: list[list[str]] = []
    netmd.play(run=_answering(record=sent))
    assert [args[1:] for args in sent] == [["play"]]


def test_play_a_track_uses_the_same_off_by_one_as_rename():
    sent: list[list[str]] = []
    netmd.play(12, run=_answering(record=sent))
    assert [args[1:] for args in sent] == [["play", "11"]]


@pytest.mark.parametrize(
    "call, expected",
    [
        (lambda run: netmd.pause(run=run), ["pause"]),
        (lambda run: netmd.stop(run=run), ["stop"]),
        (lambda run: netmd.fast_forward(run=run), ["fforward"]),
        (lambda run: netmd.rewind(run=run), ["rewind"]),
        (lambda run: netmd.next_track(run=run), ["next"]),
        (lambda run: netmd.previous_track(run=run), ["previous"]),
        (lambda run: netmd.restart_track(run=run), ["restart"]),
    ],
)
def test_each_transport_command_sends_its_own_word(call, expected):
    sent: list[list[str]] = []
    call(_answering(record=sent))
    assert [args[1:] for args in sent] == [expected]


def test_set_play_mode_sends_the_word_chosen():
    sent: list[list[str]] = []
    netmd.set_play_mode("shuffle", run=_answering(record=sent))
    assert [args[1:] for args in sent] == [["setplaymode", "shuffle"]]


def test_an_unknown_play_mode_is_refused_before_it_reaches_the_deck():
    sent: list[list[str]] = []
    with pytest.raises(netmd.NetMdError, match="unknown play mode"):
        netmd.set_play_mode("random", run=_answering(record=sent))
    assert sent == [], "nothing should be sent for a mode netmdcli was never going to accept"


def test_transport_with_no_device_says_so():
    with pytest.raises(netmd.NetMdError, match="no NetMD device"):
        netmd.play(run=_answering(NO_DEVICE))


def test_a_refused_transport_command_reports_the_decks_own_complaint():
    with pytest.raises(netmd.NetMdError, match="nope"):
        netmd.pause(run=_answering(_Completed(stderr="nope", returncode=1)))


def test_a_refused_transport_command_falls_back_to_a_plain_message():
    """The deck can refuse with nothing useful in its output at all --
    still an error, not a silent no-op."""
    with pytest.raises(netmd.NetMdError, match="refused to pause"):
        netmd.pause(run=_answering(_Completed(returncode=1)))


# --- the off-by-one -------------------------------------------------------


def test_netmdcli_counts_tracks_from_zero():
    """Its own help says so: "track numbers are off by one (ie track 1 is
    0)". One function owns this, because getting it wrong retitles the
    wrong track on a real disc."""
    assert netmd.track_command_index(1) == 0
    assert netmd.track_command_index(12) == 11


def test_track_zero_never_becomes_minus_one():
    assert netmd.track_command_index(0) == 0


# --- planning the titles --------------------------------------------------


def test_a_plan_titles_the_disc_and_every_track():
    plan = netmd.build_title_plan("Night Ferry", ["Harbour Lights", "Slow Tide"], track_count=2)

    assert [command.args for command in plan.commands] == [
        ["rename_disc", "Night Ferry"],
        ["rename", "0", "Harbour Lights"],
        ["rename", "1", "Slow Tide"],
    ]


def test_titles_the_disc_cannot_carry_are_reported_not_silently_mangled():
    """The same transliteration the infrared titler uses, so both ways of
    getting a title onto a MiniDisc promise exactly the same thing."""
    plan = netmd.build_title_plan("Björk", ["Jôlie"], track_count=1)

    assert plan.disc_title == "Bjork"
    assert plan.track_titles == ["Jolie"]
    assert ("Björk", "Bjork") in plan.changed
    assert ("Jôlie", "Jolie") in plan.changed


def test_tracks_the_disc_does_not_have_are_skipped_and_named():
    """Writing to a track that is not there is not a no-op on a real
    deck."""
    plan = netmd.build_title_plan("x", ["one", "two", "three"], track_count=2)

    assert plan.skipped_tracks == [3]
    assert [command.args[-1] for command in plan.commands[1:]] == ["one", "two"]


def test_an_empty_disc_title_writes_no_disc_command():
    plan = netmd.build_title_plan("", ["one"], track_count=1)
    assert all(command.args[0] != "rename_disc" for command in plan.commands)


def test_a_pathological_title_is_cut_rather_than_sent():
    plan = netmd.build_title_plan("x" * 500, [], track_count=0)
    assert len(plan.disc_title) == netmd.MAX_TITLE


# --- writing them ---------------------------------------------------------


def test_every_command_is_run_in_order():
    sent: list[list[str]] = []
    plan = netmd.build_title_plan("Disc", ["one", "two"], track_count=2)

    netmd.write_titles(plan, run=_answering(record=sent))

    assert [args[1:] for args in sent] == [
        ["rename_disc", "Disc"],
        ["rename", "0", "one"],
        ["rename", "1", "two"],
    ]


def test_progress_is_reported_before_each_command():
    seen: list[tuple[int, int, str]] = []
    plan = netmd.build_title_plan("Disc", ["one"], track_count=1)

    netmd.write_titles(plan, on_progress=lambda *args: seen.append(args), run=_answering())

    assert [(index, total) for index, total, _ in seen] == [(1, 2), (2, 2)]
    assert "Disc" in seen[0][2]


def test_a_refused_command_stops_the_rest():
    """These are all edits to one TOC. A deck that has just refused one is
    not worth sending the next twenty to."""
    sent: list[list[str]] = []
    plan = netmd.build_title_plan("Disc", ["one", "two"], track_count=2)
    results = _answering(_Completed(), _Completed(stderr="write failed", returncode=1), record=sent)

    with pytest.raises(netmd.NetMdError, match="write failed"):
        netmd.write_titles(plan, run=results)

    assert len(sent) == 2, "it stopped at the failure rather than finishing the plan"


def test_the_deck_disappearing_mid_write_says_so():
    plan = netmd.build_title_plan("Disc", ["one"], track_count=1)

    with pytest.raises(netmd.NetMdError, match="no NetMD device"):
        netmd.write_titles(plan, run=_answering(_Completed(), NO_DEVICE))


# --- recording a disc over USB ---------------------------------------------


def _properties(seconds: float):
    from mdtools import decode

    return decode.AudioProperties(
        sample_rate=44100, bits_per_sample=16, channels=2, frames=int(seconds * 44100)
    )


def test_a_record_plan_carries_every_track_and_the_mode_chosen():
    plan = netmd.build_record_plan(
        [("a.wav", "Harbour Lights"), ("b.wav", "Slow Tide")],
        disc_title="Night Ferry",
        mode_key=netmd.MODE_LP2,
        analyze=lambda path: _properties(200.0),
    )
    assert plan.disc_title == "Night Ferry"
    assert plan.mode.key == netmd.MODE_LP2
    assert [track.title for track in plan.tracks] == ["Harbour Lights", "Slow Tide"]
    assert plan.total_seconds == 400.0
    assert plan.can_record is True


def test_record_plan_titles_are_cleaned_like_a_title_plan():
    plan = netmd.build_record_plan(
        [("a.wav", "Jôlie")], disc_title="Björk", analyze=lambda path: _properties(10.0)
    )
    assert plan.tracks[0].title == "Jolie"
    assert plan.disc_title == "Bjork"
    assert ("Björk", "Bjork") in plan.changed
    assert ("Jôlie", "Jolie") in plan.changed


def test_an_unreadable_track_is_a_problem_not_a_crash():
    from mdtools import decode

    def analyze(path):
        raise decode.DecodeError(f"bad {path}")

    plan = netmd.build_record_plan([("bad.wav", "x")], analyze=analyze)
    assert plan.tracks[0].properties is None
    assert plan.problems_for(1)[0].code == netmd.UNREADABLE
    assert plan.can_record is False


def test_too_long_for_the_chosen_mode_is_a_problem():
    plan = netmd.build_record_plan(
        [("a.wav", "x")],
        mode_key=netmd.MODE_SP,
        analyze=lambda path: _properties(81 * 60),
    )
    assert any(problem.code == netmd.TOO_LONG_FOR_DISC for problem in plan.problems)


def test_more_than_99_tracks_is_a_problem():
    sources = [(f"{i}.wav", str(i)) for i in range(100)]
    plan = netmd.build_record_plan(sources, analyze=lambda path: _properties(1.0))
    assert any(problem.code == netmd.TOO_MANY_TRACKS for problem in plan.problems)


def test_no_tracks_is_a_problem():
    plan = netmd.build_record_plan([], analyze=lambda path: _properties(1.0))
    assert plan.problems == [netmd.RecordProblem(netmd.NO_TRACKS)]
    assert plan.can_record is False


def test_send_args_puts_the_encoder_flag_before_the_command():
    sp = netmd.MODES[netmd.MODE_SP]
    lp2 = netmd.MODES[netmd.MODE_LP2]
    assert netmd.send_args(sp, "01.wav", "Harbour Lights") == ["send", "01.wav", "Harbour Lights"]
    assert netmd.send_args(lp2, "01.wav", "Harbour Lights") == [
        "-d",
        "lp2",
        "send",
        "01.wav",
        "Harbour Lights",
    ]


def test_send_args_omits_an_empty_title():
    sp = netmd.MODES[netmd.MODE_SP]
    assert netmd.send_args(sp, "01.wav", "") == ["send", "01.wav"]


def test_every_track_is_sent_then_the_disc_is_titled():
    sent: list[list[str]] = []
    plan = netmd.build_record_plan(
        [("a.wav", "one"), ("b.wav", "two")],
        disc_title="Disc",
        analyze=lambda path: _properties(10.0),
    )
    netmd.send_tracks(plan, "work", ["01.wav", "02.wav"], run=_answering(record=sent))

    assert [args[1:] for args in sent] == [
        ["send", str(Path("work") / "01.wav"), "one"],
        ["send", str(Path("work") / "02.wav"), "two"],
        ["rename_disc", "Disc"],
    ]


def test_send_progress_counts_the_disc_title_as_the_last_step():
    seen: list[tuple[int, int, str]] = []
    plan = netmd.build_record_plan(
        [("a.wav", "one")], disc_title="Disc", analyze=lambda path: _properties(10.0)
    )
    netmd.send_tracks(plan, "work", ["01.wav"], on_progress=lambda *a: seen.append(a), run=_answering())

    assert [(index, total) for index, total, _ in seen] == [(1, 2), (2, 2)]


def test_a_refused_track_stops_the_recording_before_the_title():
    sent: list[list[str]] = []
    plan = netmd.build_record_plan(
        [("a.wav", "one"), ("b.wav", "two")],
        disc_title="Disc",
        analyze=lambda path: _properties(10.0),
    )
    results = _answering(_Completed(stderr="write failed", returncode=1), record=sent)

    with pytest.raises(netmd.NetMdError, match="write failed"):
        netmd.send_tracks(plan, "work", ["01.wav", "02.wav"], run=results)

    assert len(sent) == 1


def test_sending_with_no_device_says_so():
    plan = netmd.build_record_plan([("a.wav", "one")], analyze=lambda path: _properties(10.0))
    with pytest.raises(netmd.NetMdError, match="no NetMD device"):
        netmd.send_tracks(plan, "work", ["01.wav"], run=_answering(NO_DEVICE))


def test_prepare_track_wavs_decodes_each_track_in_order(tmp_path, monkeypatch):
    calls = []

    def fake_to_wav(source, destination):
        calls.append((Path(source), Path(destination)))

    monkeypatch.setattr(netmd.decode, "to_wav", fake_to_wav)
    plan = netmd.build_record_plan(
        [("a.wav", "one"), ("b.wav", "two")], analyze=lambda path: _properties(10.0)
    )
    names = netmd.prepare_track_wavs(plan, tmp_path)

    assert names == ["01.wav", "02.wav"]
    assert [destination.name for _source, destination in calls] == ["01.wav", "02.wav"]


def test_prepare_track_wavs_cancels_between_tracks(tmp_path):
    plan = netmd.build_record_plan(
        [("a.wav", "one"), ("b.wav", "two")], analyze=lambda path: _properties(10.0)
    )
    with pytest.raises(netmd.NetMdCancelled):
        netmd.prepare_track_wavs(plan, tmp_path, should_cancel=lambda: True)
