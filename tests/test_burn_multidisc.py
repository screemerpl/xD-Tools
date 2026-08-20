"""Writing one album across several CD-Rs.

Kept apart from test_burn_dialog.py, which covers a single disc: everything
here is about the split and about what happens between one disc and the
next.

Nothing reaches a drive -- the worker that decodes and burns is stood in
for, along with the burner list and every message box.
"""

import pytest

from mdtools import cdburn, decode, multidisc
from mdtools.panels import burn_dialog as burn_module
from mdtools.panels.burn_dialog import COL_DISC, BurnDialog

RATE = 44100


@pytest.fixture(autouse=True)
def measured_by_name(monkeypatch):
    """Every source file's length is read out of its own name.

    Real WAVs would mean writing tens of megabytes of silence per test to
    make an album long enough to need a second disc -- and not a byte of it
    would be read, since the worker that decodes and burns is faked here.
    """

    def analyze(path):
        seconds = float(str(path).rsplit("-", 1)[-1].removesuffix("s.wav"))
        return decode.AudioProperties(
            sample_rate=RATE, bits_per_sample=16, channels=2, frames=int(RATE * seconds)
        )

    monkeypatch.setattr(decode, "analyze", analyze)


@pytest.fixture(autouse=True)
def no_cover_lookup(monkeypatch):
    monkeypatch.setattr(burn_module, "fetch_into", lambda *a, **k: None)


@pytest.fixture
def burnable(monkeypatch):
    """A machine with cdrecord and a burner in it."""
    monkeypatch.setattr(cdburn, "cdrecord_path", lambda: "cdrecord")
    monkeypatch.setattr(cdburn, "missing_tools", lambda: [])
    monkeypatch.setattr(
        cdburn, "list_burners", lambda: [cdburn.Burner(device="1,0,0", description="ASUS BW-16D1HT")]
    )


def _sources(tmp_path, count=2, seconds=60.0):
    sources = []
    for number in range(1, count + 1):
        path = tmp_path / f"{number:02d}-{seconds}s.wav"
        path.write_bytes(b"")
        sources.append((path, f"Track {number}", "Artist"))
    return sources


def _short_disc(dialog, minutes=multidisc.MIN_DISC_MINUTES):
    """The smallest disc the dialog allows, so a handful of one-minute
    tracks already needs more than one of them."""
    dialog.disc_minutes_spin.setValue(minutes)
    dialog.multi_check.setChecked(True)


class _Signal:
    def __init__(self):
        self._slots = []

    def connect(self, slot):
        self._slots.append(slot)

    def emit(self, *args):
        for slot in list(self._slots):
            slot(*args)


class _FakeWorker:
    """Stands in for the thread that would hold the drive, and records what
    it was asked to write."""

    made: list = []

    def __init__(self, plan, device, work_dir, *, speed, simulate, eject, parent=None):
        self.plan = plan
        self.work_dir = work_dir
        self.eject = eject
        _FakeWorker.made.append(self)
        for name in ("stage", "progress", "failed", "cancelled", "succeeded", "finished"):
            setattr(self, name, _Signal())

    def start(self):
        pass

    def cancel(self):
        pass

    def finish_successfully(self):
        """The real worker's two signals, in the order Qt delivers them:
        the result first, the thread's own end after it."""
        self.succeeded.emit()
        self.finished.emit()


@pytest.fixture
def fake_worker(monkeypatch):
    _FakeWorker.made = []
    monkeypatch.setattr(burn_module, "_BurnWorker", _FakeWorker)
    return _FakeWorker.made


def _start_burn(dialog, monkeypatch, answers=None):
    """Presses Burn, answering every message box the flow puts up."""
    replies = list(answers or [])

    def _question(*args, **kwargs):
        if replies:
            return replies.pop(0)
        return burn_module.QMessageBox.StandardButton.Ok

    monkeypatch.setattr(burn_module.QMessageBox, "question", _question)
    monkeypatch.setattr(burn_module.QMessageBox, "information", lambda *a, **k: None)
    dialog._start()


# -- the split ------------------------------------------------------------


def test_an_album_that_fits_stays_one_disc(qt_app, tmp_path, burnable):
    dialog = BurnDialog(_sources(tmp_path, 2), album="Album", artist="Artist")
    dialog.multi_check.setChecked(True)

    assert len(dialog._plans) == 1
    assert dialog.table.isColumnHidden(COL_DISC)


def test_an_album_too_long_for_one_disc_is_split_across_several(qt_app, tmp_path, burnable):
    dialog = BurnDialog(_sources(tmp_path, 12), album="Album", artist="Artist")
    _short_disc(dialog)  # five minutes a disc, twelve one-minute tracks

    assert len(dialog._plans) == 3
    assert not dialog.table.isColumnHidden(COL_DISC)
    assert dialog.table.item(0, COL_DISC).text() == "1"
    assert dialog.table.item(11, COL_DISC).text() == "3"


def test_every_disc_says_which_one_it_is_in_its_cd_text(qt_app, tmp_path, burnable):
    """Two discs of one album carrying identical CD-Text are two discs
    nobody can tell apart in a player."""
    dialog = BurnDialog(_sources(tmp_path, 8), album="Album", artist="Artist")
    _short_disc(dialog)

    assert [plan.album for plan in dialog._plans] == ["Album [1/2]", "Album [2/2]"]


def test_each_disc_is_measured_against_the_disc_it_goes_on(qt_app, tmp_path, burnable):
    """Not against the album: the whole thing overruns, which is the point,
    and every disc of it still has to fit on its own."""
    dialog = BurnDialog(_sources(tmp_path, 12), album="Album", artist="Artist")
    _short_disc(dialog)

    assert all(plan.can_burn for plan in dialog._plans)
    assert dialog.burn_button.isEnabled()


def test_the_split_leaves_room_for_the_lead_in(qt_app, tmp_path, burnable):
    """A disc is not all music: BurnPlan counts a lead-in, so a split that
    filled the stated capacity exactly would produce discs that do not."""
    dialog = BurnDialog(_sources(tmp_path, 12), album="Album", artist="Artist")
    _short_disc(dialog)

    for plan in dialog._plans:
        assert plan.total_sectors <= plan.capacity_sectors


def test_a_track_longer_than_a_whole_disc_keeps_the_button_off(qt_app, tmp_path, burnable):
    """Nothing can cut inside a track, so splitting cannot rescue this."""
    long_track = tmp_path / "01-400.0s.wav"
    long_track.write_bytes(b"")
    dialog = BurnDialog([(long_track, "Long", "Artist")], album="Album", artist="Artist")
    _short_disc(dialog)

    assert not dialog.burn_button.isEnabled()


def test_the_split_follows_the_files_when_they_declare_their_discs(
    qt_app, tmp_path, burnable, monkeypatch
):
    """A two-disc rip carries DISCNUMBER, and honouring it beats balancing
    by running time -- the album already knows where it was divided."""
    monkeypatch.setattr(burn_module.audio_folder, "disc_breaks", lambda paths: [3])
    dialog = BurnDialog(_sources(tmp_path, 8), album="Album", artist="Artist")
    _short_disc(dialog, minutes=60)  # by time alone it would all fit on one

    assert [len(plan.tracks) for plan in dialog._plans] == [3, 5]


def test_the_capacity_is_what_the_user_says_it_is(qt_app, tmp_path, burnable):
    """74-minute blanks still exist, and only the person holding one knows."""
    dialog = BurnDialog(_sources(tmp_path, 2), album="Album", artist="Artist")
    dialog.disc_minutes_spin.setValue(74)

    assert dialog.capacity_sectors() == 74 * 60 * cdburn.SECTORS_PER_SECOND
    assert dialog._plans[0].capacity_sectors == 74 * 60 * cdburn.SECTORS_PER_SECOND


def test_a_set_downloaded_into_one_folder_is_put_back_in_order(
    qt_app, tmp_path, burnable, monkeypatch
):
    """Both discs of a set number their tracks from one, so by filename
    they arrive interleaved -- 2, 1, 2, 1. A break worked out from *that*
    order falls on nearly every track: a real 34-track album was offered as
    26 discs before the sources were sorted first."""
    interleaved = _sources(tmp_path, 6)
    numbers = {path: disc for path, disc in zip([s[0] for s in interleaved], [2, 1, 2, 1, 2, 1])}
    monkeypatch.setattr(
        burn_module.audio_folder,
        "disc_and_track_order",
        lambda paths: sorted(range(len(paths)), key=lambda i: (numbers[paths[i]], i)),
    )
    monkeypatch.setattr(
        burn_module.audio_folder,
        "disc_breaks",
        lambda paths: [3],  # once sorted, the change of disc is in the middle
    )

    dialog = BurnDialog(interleaved, album="Album", artist="Artist")
    dialog.multi_check.setChecked(True)

    assert [len(plan.tracks) for plan in dialog._plans] == [3, 3]


def test_a_break_placed_by_hand_wins_over_the_files(qt_app, tmp_path, burnable, monkeypatch):
    monkeypatch.setattr(burn_module.audio_folder, "disc_breaks", lambda paths: [4])
    dialog = BurnDialog(_sources(tmp_path, 8), album="Album", artist="Artist")
    _short_disc(dialog, minutes=60)
    dialog.table.setCurrentCell(2, burn_module.COL_TITLE)

    dialog._toggle_split()

    assert [len(plan.tracks) for plan in dialog._plans] == [2, 2, 4]
    dialog._auto_split()
    assert [len(plan.tracks) for plan in dialog._plans] == [4, 4]


def test_moving_a_track_changes_the_order_it_is_written_in(qt_app, tmp_path, burnable):
    """A burn hands the files to cdrecord itself, so this table *is* the
    disc's running order -- nothing outside the window has to be told."""
    dialog = BurnDialog(_sources(tmp_path, 3), album="Album", artist="Artist")
    dialog.table.setCurrentCell(0, burn_module.COL_TITLE)

    dialog._move_selected(1)

    assert [title for _path, title, _artist in dialog.track_sources()] == [
        "Track 2",
        "Track 1",
        "Track 3",
    ]
    assert [track.title for track in dialog._plans[0].tracks] == ["Track 2", "Track 1", "Track 3"]


# -- one disc after another ----------------------------------------------


def test_the_discs_are_written_one_after_another(qt_app, tmp_path, burnable, fake_worker, monkeypatch):
    dialog = BurnDialog(_sources(tmp_path, 8), album="Album", artist="Artist")
    _short_disc(dialog)
    _start_burn(dialog, monkeypatch)

    assert len(fake_worker) == 1, "only the first disc is under way"
    fake_worker[0].finish_successfully()

    assert len(fake_worker) == 2, "and the second follows once the blank is in"
    assert fake_worker[1].plan.album == "Album [2/2]"


def test_the_user_is_asked_for_the_blank_before_the_next_disc_starts(
    qt_app, tmp_path, burnable, fake_worker, monkeypatch
):
    dialog = BurnDialog(_sources(tmp_path, 8), album="Album", artist="Artist")
    _short_disc(dialog)
    # Ok to start the run, then Cancel when asked for the second blank.
    _start_burn(
        dialog,
        monkeypatch,
        answers=[
            burn_module.QMessageBox.StandardButton.Ok,
            burn_module.QMessageBox.StandardButton.Cancel,
        ],
    )
    fake_worker[0].finish_successfully()

    assert len(fake_worker) == 1, "nothing may be written to a disc nobody said was in"
    assert "1" in dialog.stage_label.text()


def test_every_disc_but_the_last_is_ejected_whatever_the_checkbox_says(
    qt_app, tmp_path, burnable, fake_worker, monkeypatch
):
    """The tray has to open for the next blank to go in."""
    dialog = BurnDialog(_sources(tmp_path, 8), album="Album", artist="Artist")
    _short_disc(dialog)
    dialog.eject_check.setChecked(False)
    _start_burn(dialog, monkeypatch)
    fake_worker[0].finish_successfully()

    assert fake_worker[0].eject is True
    assert fake_worker[1].eject is False


def test_each_disc_gets_its_own_scratch_folder(qt_app, tmp_path, burnable, fake_worker, monkeypatch):
    """Track numbering restarts on every disc, so one shared folder would
    leave a longer disc's WAVs sitting beside a shorter one's."""
    dialog = BurnDialog(_sources(tmp_path, 8), album="Album", artist="Artist")
    _short_disc(dialog)
    _start_burn(dialog, monkeypatch)
    fake_worker[0].finish_successfully()

    assert fake_worker[0].work_dir != fake_worker[1].work_dir


def test_what_the_project_adopts_is_the_whole_album(qt_app, tmp_path, burnable, fake_worker, monkeypatch):
    """The label describes the record, which is both discs of it."""
    dialog = BurnDialog(_sources(tmp_path, 8), album="Album", artist="Artist")
    _short_disc(dialog)
    _start_burn(dialog, monkeypatch)
    fake_worker[0].finish_successfully()
    fake_worker[1].finish_successfully()

    assert dialog.result_metadata is not None
    assert len(dialog.result_metadata.tracks) == 8
    assert dialog.result_metadata.album == "Album", "without the [1/2] the discs themselves carry"


def test_a_single_disc_burn_is_untouched_by_any_of_this(
    qt_app, tmp_path, burnable, fake_worker, monkeypatch
):
    dialog = BurnDialog(_sources(tmp_path, 2), album="Album", artist="Artist")
    _start_burn(dialog, monkeypatch)

    assert len(fake_worker) == 1
    assert fake_worker[0].plan.album == "Album"
    fake_worker[0].finish_successfully()
    assert len(fake_worker) == 1, "there is nothing to follow it"
