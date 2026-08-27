"""MDRemUploadDialog's side of #27: what it reports to MainWindow's
bottom progress bar, and its Hide button.

The dialog's own preview/transliteration behaviour is covered in
test_mdrem_ui.py -- this file is only about the progress it publishes
outward, which nothing else asserts.

Nothing here goes near a real serial port: the worker is never started,
and every method driven below is the GUI-thread half that the worker's
signals would have reached anyway.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtGui import QCloseEvent

from mdtools.panels import mdrem_upload_dialog as upload_module
from mdtools.panels.mdrem_upload_dialog import MDRemUploadDialog
from mdtools.project import ProjectMetadata, Track


class _NoSingleShot(QTimer):
    """A real QTimer in every way except the one that is a trap here.

    `unattended=True` schedules its own `_start()` through
    `QTimer.singleShot(0, ...)` -- which in a test starts a *real*
    _UploadWorker QThread, opening a real serial port, and then gets torn
    down with the thread still running. That is a silent process abort
    with no traceback (see CLAUDE.md), and it killed this file's run
    outright before this stand-in existed. Instances still tick normally,
    so the dialog's own progress ticker is untouched."""

    @staticmethod
    def singleShot(_ms, _callback):
        return None


@pytest.fixture
def no_deferred_start(monkeypatch):
    monkeypatch.setattr(upload_module, "QTimer", _NoSingleShot)


def _album() -> ProjectMetadata:
    return ProjectMetadata(
        album="Lost Souls", artist="Caskets", year=2021, tracks=[Track("The Only Ones"), Track("Glass Heart")]
    )


def _armed(dialog) -> None:
    """The state _start() would have left behind, without starting a
    worker thread -- estimates in place and the clocks running, which is
    all _tick() reads."""
    dialog._step_estimates = [10.0, 10.0, 10.0]
    dialog._total_estimate = 30.0
    dialog._completed_estimate = 0.0
    dialog._current_estimate = 10.0
    dialog._step_clock.start()
    dialog._total_clock.start()


def test_the_time_driven_estimate_is_published_outward(qt_app):
    """The deck cannot report progress at all, so what the bar shows is
    this dialog's own elapsed-time estimate -- the same number and the
    same words it puts on itself."""
    dialog = MDRemUploadDialog(_album(), "COM_TEST")
    _armed(dialog)
    seen: list = []
    dialog.overall_progress_changed.connect(lambda f, t: seen.append((f, t)))

    dialog._on_step_started(1, "Glass Heart")

    assert seen, "nothing was reported for the progress bar"
    fraction, text = seen[-1]
    # One step of three done, and barely into the second.
    assert fraction == pytest.approx(1 / 3, abs=0.05)
    assert text == dialog.status_label.text()
    assert "Glass Heart" in text


def test_progress_never_leaves_the_zero_to_one_range(qt_app):
    """A step running long must not push the bar past full -- _tick()
    clamps within the step, and the fraction it publishes is what
    MainWindow feeds straight into a QProgressBar."""
    dialog = MDRemUploadDialog(_album(), "COM_TEST")
    _armed(dialog)
    dialog._completed_estimate = 30.0
    dialog._current_estimate = 10.0
    seen: list[float] = []
    dialog.overall_progress_changed.connect(lambda f, t: seen.append(f))

    dialog._tick()

    assert seen and 0.0 <= seen[-1] <= 1.0


def test_nothing_is_reported_before_an_upload_starts(qt_app):
    """_tick() is a no-op until there are step estimates to measure
    against -- the bar must not move on a dialog still showing its
    preview."""
    dialog = MDRemUploadDialog(_album(), "COM_TEST")
    seen: list = []
    dialog.overall_progress_changed.connect(lambda f, t: seen.append(f))

    dialog._tick()

    assert seen == []


def test_the_run_is_declared_over_however_it_ended(qt_app):
    """running_changed(False) goes out at the very top of
    _on_worker_finished(), before the success/failure/unattended
    branching -- otherwise a failed upload would leave MainWindow's bar
    up with nothing driving it."""
    dialog = MDRemUploadDialog(_album(), "COM_TEST")
    seen: list[bool] = []
    dialog.running_changed.connect(seen.append)

    dialog._on_worker_finished()

    assert seen == [False]


def test_closing_mid_upload_keeps_it_going_and_says_so(qt_app):
    """The window's X must not read as a cancel while titles are still
    going out: it marks itself for exec_hideable() (see
    panels/hideable_dialog.py) and tells the bar to offer "Show
    recording window"."""
    dialog = MDRemUploadDialog(_album(), "COM_TEST")
    dialog._worker = object()  # only is_busy() looks at it here
    seen: list[bool] = []
    dialog.visibility_changed.connect(seen.append)

    event = QCloseEvent()
    dialog.closeEvent(event)

    assert not event.isAccepted(), "the close has to be refused so the dialog survives"
    assert seen == [True]
    assert dialog.hidden_for_background is True
    assert dialog.isHidden()


def test_closing_with_nothing_running_really_closes(qt_app):
    """Hiding is only for work worth keeping alive -- an idle window
    that could not be shut with its own X would be far more surprising."""
    dialog = MDRemUploadDialog(_album(), "COM_TEST")

    event = QCloseEvent()
    dialog.closeEvent(event)

    assert event.isAccepted()
    assert dialog.hidden_for_background is False


def test_asking_for_it_back_is_passed_on(qt_app):
    dialog = MDRemUploadDialog(_album(), "COM_TEST")
    seen: list = []
    dialog.show_requested.connect(lambda: seen.append(True))

    dialog.request_show()

    assert seen == [True]
