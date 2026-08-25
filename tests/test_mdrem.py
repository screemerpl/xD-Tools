"""The parts of MDRem support that need no hardware and no QApplication:
text conversion, disc-title formatting, and building the upload plan."""

import pytest

from mdtools import app_settings, mdrem
from mdtools.project import ProjectMetadata, Track


def _album(tracks: list[str], **kwargs) -> ProjectMetadata:
    defaults = dict(album="Lost Souls", artist="Caskets", year=2021)
    defaults.update(kwargs)
    return ProjectMetadata(tracks=[Track(t) for t in tracks], **defaults)


# --- transliteration -------------------------------------------------------


def test_plain_ascii_is_left_alone():
    result = mdrem.transliterate("Hopes & Dreams (2021)")
    assert result.text == "Hopes & Dreams (2021)"
    assert not result.is_lossy


def test_accented_latin_letters_lose_their_marks():
    assert mdrem.transliterate("Björk Homogénic").text == "Bjork Homogenic"


def test_polish_letters_including_the_ones_decomposition_does_not_touch():
    """NFKD turns ą into a+combining mark, but ł is its own letter with no
    decomposition at all -- it needs the explicit map, and used to vanish."""
    assert mdrem.transliterate("Zażółć gęślą jaźń").text == "Zazolc gesla jazn"
    assert mdrem.transliterate("ŁÓDŹ").text == "LODZ"


def test_typographic_punctuation_becomes_its_ascii_equivalent():
    # Exactly what an iTunes metadata lookup routinely returns.
    assert mdrem.transliterate("Don’t Look Back — “Live”").text == 'Don\'t Look Back - "Live"'


def test_every_unicode_dash_variant_becomes_a_plain_hyphen():
    """None of these has an NFKD decomposition to "-" (confirmed
    directly: U+2010 HYPHEN's own decomposition is itself), so without an
    explicit map entry each one used to fall through to `dropped` --
    real report: a MusicBrainz artist name using U+2010 for "blink-182"
    reached cdrip.py's own sanitize_filename() (which reuses this
    function) and broke a CD rip."""
    dashes = [chr(cp) for cp in (0x2010, 0x2011, 0x2012, 0x2013, 0x2014, 0x2212)]
    for dash in dashes:
        result = mdrem.transliterate(f"blink{dash}182")
        assert result.text == "blink-182", f"U+{ord(dash):04X} did not become a hyphen"
        assert not result.is_lossy


def test_characters_with_no_equivalent_are_reported_not_silently_dropped():
    result = mdrem.transliterate("日本語 title")
    assert result.text == "title"
    assert result.dropped == ["日", "本", "語"]
    assert result.is_lossy


def test_dropped_characters_are_listed_once_each():
    assert mdrem.transliterate("日日日").dropped == ["日"]


# --- disc title ------------------------------------------------------------


def test_disc_title_is_artist_album_year():
    assert mdrem.disc_title(_album([])) == "Caskets - Lost Souls (2021)"


def test_disc_title_skips_whatever_is_missing():
    assert mdrem.disc_title(_album([], artist="", year=None)) == "Lost Souls"
    assert mdrem.disc_title(_album([], album="", artist="")) == "2021"
    assert mdrem.disc_title(_album([], album="", artist="", year=None)) == ""


# --- typing one character --------------------------------------------------


def test_a_printable_character_is_sent_by_name():
    """And case is kept: the deck has a different code for A and for a."""
    assert mdrem.character_command("A") == "SEND A"
    assert mdrem.character_command("a") == "SEND a"
    assert mdrem.character_command("7") == "SEND 7"


def test_a_space_cannot_go_through_send_so_it_goes_as_its_own_code():
    """The firmware splits SEND's arguments on whitespace, so the argument
    would simply be missing. RAW takes the character code instead."""
    assert mdrem.character_command(" ") == f"RAW {mdrem.CHAR_CODE_BASE | 0x20:X} 20"


def test_a_character_the_deck_cannot_show_has_no_command_at_all():
    assert mdrem.character_command("日") is None
    assert mdrem.character_command("ł") is None  # transliterate first
    assert mdrem.character_command("ab") is None


# --- upload plan -----------------------------------------------------------


def _commands(plan, clearing=True):
    return [step.command(clearing) for step in plan.steps]


def test_plan_writes_the_disc_title_then_one_step_per_track():
    plan = mdrem.build_upload_plan(_album(["The Only Ones", "Glass Heart"]))
    assert _commands(plan) == [
        "TITLEDISCCLEAR Caskets - Lost Souls (2021)",
        "TITLETRACKCLEAR 1 The Only Ones",
        "TITLETRACKCLEAR 2 Glass Heart",
    ]


def test_whether_to_erase_first_is_said_in_the_command_not_in_a_global():
    """TIMING COUNT lives in the board's RAM until it is reset, so the same
    command meant different things depending on what ran before it. The
    firmware grew CLEAR/NOCLEAR forms to remove that shared state, and this
    is the whole reason the host stopped setting the global at all."""
    plan = mdrem.build_upload_plan(_album(["The Only Ones"]))
    assert _commands(plan, clearing=False) == [
        "TITLEDISCNOCLEAR Caskets - Lost Souls (2021)",
        "TITLETRACKNOCLEAR 1 The Only Ones",
    ]


def test_plan_transliterates_and_collects_every_dropped_character():
    plan = mdrem.build_upload_plan(_album(["日本", "Zażółć"], album="Ünïcode"))
    assert plan.steps[-1].command(True) == "TITLETRACKCLEAR 2 Zazolc"
    assert plan.dropped == ["日", "本"]


def test_a_track_above_25_is_sent_like_any_other():
    """The remote's number keys stop at 25; the firmware types the number
    instead (">25" and its digits, confirmed on an MDS-JE480 for 37, 42, 44
    and 50), so nothing here has to spell it differently -- TITLETRACK
    takes the whole range."""
    titles = [f"Track {i}" for i in range(1, 45)]
    plan = mdrem.build_upload_plan(_album(titles))

    assert "TITLETRACKCLEAR 44 Track 44" in _commands(plan)
    assert plan.skipped_tracks == []


def test_tracks_needing_three_digits_are_skipped_not_sent():
    """The number field commits on the second digit, so a three-digit
    number would select the first two digits' track and write this title
    over that one's -- on a disc nothing can read back. Reported rather
    than dropped, and rather than guessed at."""
    titles = [f"Track {i}" for i in range(1, mdrem.MAX_TRACK + 3)]
    plan = mdrem.build_upload_plan(_album(titles))

    commands = _commands(plan)
    assert f"TITLETRACKCLEAR {mdrem.MAX_TRACK} Track {mdrem.MAX_TRACK}" in commands
    assert not any(f" {mdrem.MAX_TRACK + 1} " in c for c in commands)
    assert plan.skipped_tracks == [f"Track {mdrem.MAX_TRACK + 1}", f"Track {mdrem.MAX_TRACK + 2}"]


def test_a_track_whose_title_is_entirely_unsupported_is_not_sent_as_an_empty_title():
    plan = mdrem.build_upload_plan(_album(["日本語"]))
    assert _commands(plan) == ["TITLEDISCCLEAR Caskets - Lost Souls (2021)"]


def test_plan_numbering_follows_the_track_list_not_the_sendable_subset():
    """A track that transliterates to nothing must not shift the numbers of
    the ones after it -- track 3 is still TRACK3 on the deck."""
    plan = mdrem.build_upload_plan(_album(["One", "日本語", "Three"]))
    assert _commands(plan)[1:] == ["TITLETRACKCLEAR 1 One", "TITLETRACKCLEAR 3 Three"]


def test_empty_metadata_gives_an_empty_plan():
    plan = mdrem.build_upload_plan(ProjectMetadata())
    assert plan.is_empty


def test_typing_a_track_number_costs_a_little_more_than_pressing_one_key():
    """Not much -- three presses rather than one -- but the estimate is
    what the progress bar is driven by, so it should not pretend the two
    are the same."""
    direct = mdrem.UploadStep(label="", text="Title", track=25)
    typed = mdrem.UploadStep(label="", text="Title", track=26)
    assert mdrem.estimated_step_seconds(typed) > mdrem.estimated_step_seconds(direct)


def test_estimate_grows_with_the_amount_being_written():
    short = mdrem.build_upload_plan(_album(["A"]))
    long = mdrem.build_upload_plan(_album(["A", "B", "C", "D"]))
    assert mdrem.estimated_seconds(long) > mdrem.estimated_seconds(short) > 0


def test_skipping_the_erase_step_roughly_halves_the_estimate():
    """Clearing overshoots the old title's length on purpose (the deck
    can't be read back), so it dominates the time for short titles."""
    plan = mdrem.build_upload_plan(_album(["The Only Ones", "Glass Heart"]))
    with_clear = mdrem.estimated_seconds(plan, clearing=True)
    without = mdrem.estimated_seconds(plan, clearing=False)
    assert without < with_clear / 2


# --- settings --------------------------------------------------------------


def test_mdrem_enabled_survives_a_round_trip_through_the_ini_file():
    """Regression guard: QSettings(IniFormat) hands a bool back as the
    *string* "false", and bool("false") is True -- reading this naively
    would make the setting impossible to turn off again."""
    app_settings.set_mdrem_enabled(True)
    assert app_settings.mdrem_enabled() is True
    app_settings.set_mdrem_enabled(False)
    assert app_settings.mdrem_enabled() is False


def test_the_extended_remote_choice_survives_the_same_round_trip():
    """Same trap as above, and the same guard: it is remembered between
    openings, so reading it naively would wedge it on."""
    app_settings.set_mdrem_extended_remote(True)
    assert app_settings.mdrem_extended_remote() is True
    app_settings.set_mdrem_extended_remote(False)
    assert app_settings.mdrem_extended_remote() is False


def test_mdrem_is_off_and_portless_until_configured():
    assert app_settings.mdrem_enabled() is False
    assert app_settings.mdrem_port() == ""


def test_mdrem_port_round_trips():
    app_settings.set_mdrem_port("COM7")
    assert app_settings.mdrem_port() == "COM7"


# --- MDRemClient.command()'s chunked polling --------------------------------
#
# Regression coverage for the GUI-freeze fix: reported directly as "the
# window looks frozen" while a title was being written. _read_line() used
# to hand waitForReadyRead() the *entire* remaining budget in one call --
# up to the whole 180 s TITLE_TIMEOUT_MS while waiting on the deck's reply
# -- and a Python QThread.run() override calling a wrapped Qt blocking
# method is not guaranteed to release the GIL for that call's own duration.
# These tests don't touch a real QSerialPort (this file's own header says
# "no hardware, no QApplication") -- they replace mdrem.QSerialPort with a
# fake that mimics just the surface MDRemClient actually calls, and replace
# time.monotonic() with a controllable fake clock so a 180 s deadline can be
# exercised without a slow test.


class _FakeClock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def advance(self, ms: float) -> None:
        self.now += ms / 1000.0


class _FakePort:
    """Stands in for QSerialPort -- just the methods/nested enums
    MDRemClient actually touches. Lines to deliver are queued via
    queue_line(); each is handed over only once waitForReadyRead() has been
    called `deliver_after` times, so a test can force _read_line() to poll
    repeatedly before data "arrives", exactly like a slow-replying deck."""

    class OpenModeFlag:
        ReadWrite = 3

    class DataBits:
        Data8 = 8

    class Parity:
        NoParity = 0

    class StopBits:
        OneStop = 1

    class FlowControl:
        NoFlowControl = 0

    def __init__(self, clock: _FakeClock):
        self._clock = clock
        self._is_open = False
        self._read_buffer = bytearray()
        self._pending_lines: list[tuple[bytes, int]] = []  # (line, deliver_after)
        self.readyread_calls: list[int] = []
        self.byteswritten_calls: list[int] = []
        self._bytes_to_write = 0
        self.flush_after = 1  # waitForBytesWritten calls before a write "completes"

    def queue_line(self, line: bytes, deliver_after: int = 1) -> None:
        self._pending_lines.append((line, deliver_after))

    # --- config no-ops, matching MDRemClient.__init__'s setup calls -----
    def setPortName(self, name): pass
    def setBaudRate(self, rate): pass
    def setDataBits(self, v): pass
    def setParity(self, v): pass
    def setStopBits(self, v): pass
    def setFlowControl(self, v): pass
    def setDataTerminalReady(self, v): pass
    def errorString(self): return "fake error"

    def isOpen(self) -> bool:
        return self._is_open

    def open(self, mode) -> bool:
        self._is_open = True
        return True

    def close(self) -> None:
        self._is_open = False

    def clear(self) -> None:
        self._read_buffer.clear()

    def write(self, data: bytes) -> int:
        self._bytes_to_write = len(data)
        return len(data)

    def bytesToWrite(self) -> int:
        return self._bytes_to_write

    def waitForBytesWritten(self, ms: int) -> bool:
        self.byteswritten_calls.append(ms)
        if len(self.byteswritten_calls) >= self.flush_after:
            self._bytes_to_write = 0
            self._clock.advance(min(ms, 1))
            return True
        self._clock.advance(ms)
        return False

    def canReadLine(self) -> bool:
        return b"\n" in self._read_buffer

    def waitForReadyRead(self, ms: int) -> bool:
        self.readyread_calls.append(ms)
        if self._pending_lines and len(self.readyread_calls) >= self._pending_lines[0][1]:
            line, _ = self._pending_lines.pop(0)
            self._read_buffer.extend(line)
            self._clock.advance(min(ms, 1))
            return True
        self._clock.advance(ms)
        return False

    def readLine(self) -> bytes:
        index = self._read_buffer.index(b"\n") + 1
        line, self._read_buffer[:] = bytes(self._read_buffer[:index]), self._read_buffer[index:]
        return line


def _fake_client(monkeypatch) -> tuple[mdrem.MDRemClient, _FakePort, _FakeClock]:
    clock = _FakeClock()
    monkeypatch.setattr(mdrem.time, "monotonic", clock.monotonic)
    port = _FakePort(clock)

    # MDRemClient.__init__()/open() reference QSerialPort.DataBits.Data8 etc.
    # directly off the module-level name, not off the constructed instance --
    # so the stand-in callable needs those nested enum classes attached to
    # itself too, not just to _FakePort. A plain function can carry
    # arbitrary attributes in Python, which is all this needs.
    def factory() -> _FakePort:
        return port

    for name in ("DataBits", "Parity", "StopBits", "FlowControl", "OpenModeFlag"):
        setattr(factory, name, getattr(_FakePort, name))

    monkeypatch.setattr(mdrem, "QSerialPort", factory)
    client = mdrem.MDRemClient("COM_TEST")
    client.open()
    return client, port, clock


def test_a_quick_reply_still_works_normally(monkeypatch):
    client, port, _clock = _fake_client(monkeypatch)
    port.queue_line(b"PONG\n")

    assert client.command("PING") == []


def test_a_slow_reply_is_polled_in_bounded_chunks_not_one_long_wait(monkeypatch):
    """The actual regression guard: a reply that only arrives after several
    polls proves waitForReadyRead() is never handed the whole remaining
    budget in one call."""
    client, port, _clock = _fake_client(monkeypatch)
    port.queue_line(b"OK\n", deliver_after=5)

    result = client.command("TITLETRACK 1 Test", timeout_ms=mdrem.TITLE_TIMEOUT_MS)

    assert result == []
    assert len(port.readyread_calls) == 5
    assert all(call <= mdrem._POLL_CHUNK_MS for call in port.readyread_calls)


def test_a_reply_that_never_arrives_still_times_out_at_the_deadline(monkeypatch):
    client, port, clock = _fake_client(monkeypatch)
    # Nothing queued -- every poll reports "still nothing".

    with pytest.raises(mdrem.MDRemError, match="no reply"):
        client.command("PING", timeout_ms=1000)

    # The fake clock only ever advances by what each poll actually waited,
    # so total elapsed time should land at the deadline, not drift past it
    # by more than one chunk.
    assert 1.0 <= clock.now <= 1.0 + mdrem._POLL_CHUNK_MS / 1000.0
    assert all(call <= mdrem._POLL_CHUNK_MS for call in port.readyread_calls)


def test_informational_lines_before_ok_are_returned(monkeypatch):
    client, port, _clock = _fake_client(monkeypatch)
    port.queue_line(b";some info\n")
    port.queue_line(b"OK\n")

    assert client.command("SOME COMMAND") == [";some info"]


def test_an_err_reply_raises(monkeypatch):
    client, port, _clock = _fake_client(monkeypatch)
    port.queue_line(b"ERR bad command\n")

    with pytest.raises(mdrem.MDRemError, match="ERR"):
        client.command("BOGUS")


def test_a_slow_write_is_also_polled_in_bounded_chunks(monkeypatch):
    client, port, clock = _fake_client(monkeypatch)
    port.flush_after = 4
    port.queue_line(b"OK\n")

    client.command("PING")

    assert len(port.byteswritten_calls) == 4
    assert all(call <= mdrem._POLL_CHUNK_MS for call in port.byteswritten_calls)


def test_a_write_that_never_flushes_times_out(monkeypatch):
    client, port, clock = _fake_client(monkeypatch)
    port.flush_after = 10**9  # never

    with pytest.raises(mdrem.MDRemError, match="timed out sending"):
        client.command("PING", timeout_ms=None)

    assert clock.now > 0
