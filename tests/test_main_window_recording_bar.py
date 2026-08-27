"""MainWindow's own bottom-of-window progress bar (#27): what drives it,
what its two buttons dispatch to, and the two guards that exist only
because Hide leaves the main window usable while an operation runs on.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QDialog

from mdtools import app_window as app_module
from mdtools.app_window import MainWindow


class _FakeOperationDialog(QDialog):
    """A stand-in for RecordDialog & co: a real QDialog with the real
    signals MainWindow connects to, and an exec() that reports progress
    from inside itself (the only place a test can observe the bar while
    it is actually being driven, since exec() returns synchronously
    here)."""

    running_changed = Signal(bool)
    overall_progress_changed = Signal(float, str)
    track_progress_changed = Signal(float, str)
    visibility_changed = Signal(bool)
    show_requested = Signal()

    result_metadata = None

    def __init__(self, *args, **kwargs):
        super().__init__()
        self.hidden_for_background = False
        self.stop_calls = 0
        self.show_calls = 0
        self.seen_while_running: list = []
        self.during_exec = None

    def request_stop(self) -> None:
        self.stop_calls += 1

    def request_show(self) -> None:
        self.show_calls += 1
        # What exec_hideable() does for a real dialog once it re-enters
        # exec(): says it is back, which is what puts MainWindow's own
        # hidden flag and the bar's button away again. Without it this
        # fake would look permanently hidden and get asked back twice.
        self.visibility_changed.emit(False)

    def exec(self) -> int:
        self.running_changed.emit(True)
        self.overall_progress_changed.emit(0.5, "halfway")
        self.track_progress_changed.emit(0.25, "Track One")
        if self.during_exec is not None:
            self.during_exec(self)
        self.running_changed.emit(False)
        return QDialog.DialogCode.Rejected


def _window() -> MainWindow:
    return MainWindow(show_startup_dialog=False)


def _run_with(window, monkeypatch, dialog_factory) -> None:
    monkeypatch.setattr(app_module, "RecordDialog", dialog_factory)
    window._run_record_dialog("COM7", ["01.flac"])


def test_the_bar_starts_hidden(qt_app):
    # isHidden() rather than isVisible(): these tests never show()
    # MainWindow itself, and a child of an unshown window reports
    # isVisible() False whatever its own state is. isHidden() is the
    # widget's own explicit flag, which is what these assertions mean.
    assert _window().recording_bar.isHidden()


def test_progress_reaches_the_bar_while_the_dialog_runs(qt_app, monkeypatch):
    seen: dict = {}

    def capture(dialog):
        bar = window.recording_bar
        seen["shown"] = not bar.isHidden()
        seen["overall"] = (bar.overall_bar.value(), bar.overall_label.text())
        seen["track"] = (bar.track_bar.value(), bar.track_label.text())

    window = _window()

    def factory(*args, **kwargs):
        dialog = _FakeOperationDialog()
        dialog.during_exec = capture
        return dialog

    _run_with(window, monkeypatch, factory)

    assert seen["shown"] is True
    assert seen["overall"] == (500, "halfway")
    assert seen["track"] == (250, "Track One")


def test_the_bar_is_released_once_the_dialog_is_done(qt_app, monkeypatch):
    window = _window()
    _run_with(window, monkeypatch, _FakeOperationDialog)

    assert window.recording_bar.isHidden()
    assert window._active_recording_dialog is None


def test_the_bar_is_released_even_if_the_dialog_raises(qt_app, monkeypatch):
    """The call sites wrap exec() in try/finally for exactly this -- a bar
    left behind would also leave the concurrency guard latched on."""

    class _Exploding(_FakeOperationDialog):
        def exec(self):
            self.running_changed.emit(True)
            raise RuntimeError("boom")

    window = _window()
    with pytest.raises(RuntimeError):
        _run_with(window, monkeypatch, _Exploding)

    assert window.recording_bar.isHidden()
    assert window._active_recording_dialog is None


def test_stop_dispatches_to_the_running_dialog(qt_app, monkeypatch):
    dialogs: list[_FakeOperationDialog] = []

    def capture(dialog):
        window.recording_bar.stop_btn.click()

    window = _window()

    def factory(*args, **kwargs):
        dialog = _FakeOperationDialog()
        dialog.during_exec = capture
        dialogs.append(dialog)
        return dialog

    _run_with(window, monkeypatch, factory)

    assert dialogs[0].stop_calls == 1


def test_show_dispatches_to_the_running_dialog(qt_app, monkeypatch):
    """The bar asks the dialog to come back rather than show()ing it --
    only exec_hideable() can put it back into a modal loop."""
    dialogs: list[_FakeOperationDialog] = []

    def capture(dialog):
        dialog.visibility_changed.emit(True)
        assert not window.recording_bar.show_dialog_btn.isHidden()
        window.recording_bar.show_dialog_btn.click()
        # Putting the button away again is exec_hideable()'s job, off its
        # own visibility_changed(False) as it re-enters exec() -- one
        # place for every route back, so this fake (which never goes
        # through it) deliberately does not see that happen here. See
        # test_hideable_dialog.py.

    window = _window()

    def factory(*args, **kwargs):
        dialog = _FakeOperationDialog()
        dialog.during_exec = capture
        dialogs.append(dialog)
        return dialog

    _run_with(window, monkeypatch, factory)

    assert dialogs[0].show_calls == 1


def test_a_second_operation_is_refused_while_one_is_running(qt_app, monkeypatch):
    """Only reachable because Hide leaves the main window usable -- two
    operations would fight over the same port/device/drive."""
    warned: list = []
    monkeypatch.setattr(app_module.QMessageBox, "information", lambda *a, **k: warned.append(a))
    started: list = []

    def capture(dialog):
        # Still "inside" the first operation here.
        started.append(window._run_record_dialog("COM7", ["02.flac"]))

    window = _window()

    def factory(*args, **kwargs):
        dialog = _FakeOperationDialog()
        dialog.during_exec = capture
        capture.__dict__.setdefault("used", True)
        dialog.during_exec = capture if len(started) == 0 else None
        return dialog

    _run_with(window, monkeypatch, factory)

    assert warned, "starting a second operation was not refused"


def test_closing_the_window_is_refused_while_an_operation_runs(qt_app, monkeypatch):
    """Quitting out from under a still-running worker thread is the
    "QThread destroyed while still running" process abort."""
    warned: list = []
    monkeypatch.setattr(app_module.QMessageBox, "information", lambda *a, **k: warned.append(a))
    refused: list = []

    def capture(dialog):
        refused.append(window.close())

    window = _window()

    def factory(*args, **kwargs):
        dialog = _FakeOperationDialog()
        dialog.during_exec = capture
        return dialog

    _run_with(window, monkeypatch, factory)

    assert refused == [False], "the window closed while an operation was still running"
    assert warned


def test_closing_is_allowed_again_once_the_operation_ends(qt_app, monkeypatch):
    window = _window()
    _run_with(window, monkeypatch, _FakeOperationDialog)

    assert window._active_recording_dialog is None


def test_an_operation_finishing_while_hidden_asks_for_its_window_back(qt_app, monkeypatch):
    """Reported: recorded a disc with the window hidden, the bar went
    away when the recording finished, and then the main window refused to
    close because "something is still running".

    It was: RecordDialog does not close itself when a recording ends (it
    waits for Close), so it was still open, still hidden, and still
    holding the guard -- while the bar that carried the only way back to
    it had just hidden itself along with the progress. The way out is to
    bring the window back, which is what anyone hiding a job they are
    waiting on expects anyway."""
    dialogs: list[_FakeOperationDialog] = []

    def capture(dialog):
        # The user hides it mid-operation...
        dialog.hide()
        dialog.visibility_changed.emit(True)
        assert not window.recording_bar.show_dialog_btn.isHidden()
        # ...and it stays open (no accept/reject) once the work is done,
        # which is exactly what RecordDialog does after titling.

    window = _window()

    def factory(*args, **kwargs):
        dialog = _FakeOperationDialog()
        dialog.during_exec = capture
        dialogs.append(dialog)
        return dialog

    _run_with(window, monkeypatch, factory)

    # running_changed(False) fires at the end of the fake's exec(), while
    # the dialog is hidden: it must have been asked back rather than left
    # unreachable behind a bar that is about to disappear.
    assert dialogs[0].show_calls == 1


# --- the bar outlives every pause in the work it reports on ------------------
#
# Both reported directly, and both the same underlying mistake: the bar's
# visibility used to be tied to running_changed rather than to whether a
# dialog was attached at all. It carries the only route back to a hidden
# window, so anything that takes it away mid-operation strands that window.


def test_the_bar_is_up_from_the_moment_a_dialog_is_attached(qt_app):
    """Reported: opened a window, clicked Hide immediately, and there was
    no bar and so nothing to click to get it back -- the operation had
    not emitted running_changed(True) yet, and that was what used to be
    the only thing that ever showed the bar."""
    window = _window()
    dialog = _FakeOperationDialog()

    window._drive_recording_bar(dialog, track_progress=False)

    assert not window.recording_bar.isHidden()

    dialog.visibility_changed.emit(True)  # the user clicks Hide
    assert not window.recording_bar.isHidden()
    assert not window.recording_bar.show_dialog_btn.isHidden(), "no way back to the hidden window"


def test_the_bar_survives_the_work_finishing_while_the_window_is_open(qt_app):
    """RecordDialog does not close itself when a recording ends -- it
    waits for Close. The bar has to stay for that whole wait, or a user
    who hid it is left with a window they cannot reach and a main window
    that refuses to close because the guard can still see the dialog."""
    window = _window()
    dialog = _FakeOperationDialog()
    window._drive_recording_bar(dialog, track_progress=False)
    dialog.running_changed.emit(True)

    dialog.running_changed.emit(False)  # the work ends, the dialog stays open

    assert not window.recording_bar.isHidden()


def test_only_releasing_the_dialog_takes_the_bar_away(qt_app):
    window = _window()
    dialog = _FakeOperationDialog()
    window._drive_recording_bar(dialog, track_progress=False)
    dialog.running_changed.emit(True)
    dialog.running_changed.emit(False)
    assert not window.recording_bar.isHidden()

    window._release_recording_bar(dialog)

    assert window.recording_bar.isHidden()


def test_editing_the_project_mid_operation_leaves_the_bar_alone(qt_app, monkeypatch):
    """Reported: recording was running with the bar up, the user
    regenerated a page from the metadata, and the bar vanished. Whatever
    the main window is used for while an operation runs in the
    background, the bar is not the main window's to take away."""
    from PySide6.QtWidgets import QMessageBox

    window = _window()
    dialog = _FakeOperationDialog()
    window._drive_recording_bar(dialog, track_progress=False)
    dialog.running_changed.emit(True)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.StandardButton.Yes)

    page = window.current_page
    scene = window._current_scene()
    window.apply_template(page, scene.template)

    assert not window.recording_bar.isHidden()


# --- the bar has exactly one owner -------------------------------------------


class _FakeMetadataDialog(QDialog):
    """MetadataDialog's shape: it proxies for the MDRemUploadDialog its
    "Upload Tracklist" button opens, so no track progress and no Hide of
    its own."""

    running_changed = Signal(bool)
    overall_progress_changed = Signal(float, str)
    visibility_changed = Signal(bool)
    show_requested = Signal()

    result_metadata = None

    def __init__(self, *args, **kwargs):
        super().__init__()
        self.hidden_for_background = False
        self._is_recording_busy = kwargs.get("is_recording_busy")
        self.during_exec = None

    def request_stop(self) -> None:
        pass

    def request_show(self) -> None:
        self.visibility_changed.emit(False)

    def exec(self) -> int:
        if self.during_exec is not None:
            self.during_exec(self)
        return QDialog.DialogCode.Rejected


def _open_metadata_over(window, monkeypatch, during_exec=None):
    """Patches in a *class*, not a factory function: the call site reads
    MetadataDialog.DialogCode off the patched name."""

    class _Patched(_FakeMetadataDialog):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.during_exec = during_exec

    monkeypatch.setattr(app_module, "MetadataDialog", _Patched)
    window._edit_metadata()


def test_opening_metadata_mid_operation_does_not_steal_the_bar(qt_app, monkeypatch):
    """Reported: was ripping a CD, opened Project Metadata, closed it,
    and the bar was gone. MetadataDialog is the one dialog that opens
    without the concurrency guard -- editing metadata mid-rip is an
    ordinary thing to want -- so it was free to seize the bar on the way
    in and switch it off again on the way out, taking the rip's progress
    and the only way back to its hidden window with it."""
    window = _window()
    rip = _FakeOperationDialog()
    window._drive_recording_bar(rip, track_progress=True)
    rip.running_changed.emit(True)
    rip.overall_progress_changed.emit(0.4, "Ripping 3 of 8")
    rip.visibility_changed.emit(True)  # the rip window is hidden

    _open_metadata_over(window, monkeypatch)

    assert not window.recording_bar.isHidden(), "the rip's bar went away with the metadata dialog"
    assert window.recording_bar.overall_label.text() == "Ripping 3 of 8"
    assert not window.recording_bar.show_dialog_btn.isHidden(), "no way back to the hidden rip"
    assert window._active_recording_dialog is rip


def test_metadata_does_not_put_up_a_bar_just_for_being_open(qt_app, monkeypatch):
    """It is not an operation -- it only proxies for the title upload its
    own button can start. A bar reading "Waiting..." with a Stop button,
    put up because somebody opened Project Metadata, describes something
    that is not happening."""
    window = _window()
    seen: dict = {}

    _open_metadata_over(window, monkeypatch, lambda d: seen.update(bar=not window.recording_bar.isHidden()))

    assert seen["bar"] is False


def test_metadata_takes_the_bar_only_while_its_upload_runs(qt_app, monkeypatch):
    window = _window()
    seen: dict = {}

    def upload(dialog):
        dialog.running_changed.emit(True)
        seen["during"] = not window.recording_bar.isHidden()
        dialog.overall_progress_changed.emit(0.5, "Writing titles")
        seen["label"] = window.recording_bar.overall_label.text()
        dialog.running_changed.emit(False)
        seen["after"] = not window.recording_bar.isHidden()

    _open_metadata_over(window, monkeypatch, upload)

    assert seen["during"] is True
    assert seen["label"] == "Writing titles"
    assert seen["after"] is False
    assert window._active_recording_dialog is None


def test_upload_tracklist_is_not_refused_by_its_own_dialog(qt_app, monkeypatch):
    """The guard asks "is anything running?" off _active_recording_dialog.
    While MetadataDialog held that for as long as it was open, its own
    Upload Tracklist button looked at it, saw itself, and refused with a
    "something is still running" box with nothing running."""
    window = _window()
    seen: dict = {}

    _open_metadata_over(window, monkeypatch, lambda d: seen.update(allowed=d._is_recording_busy()))

    assert seen["allowed"] is True


def test_upload_tracklist_is_still_refused_while_something_else_runs(qt_app, monkeypatch):
    """The other half of the same guard -- it must not have been loosened
    into never refusing anything."""
    window = _window()
    rip = _FakeOperationDialog()
    window._drive_recording_bar(rip, track_progress=True)
    rip.running_changed.emit(True)
    monkeypatch.setattr(app_module.QMessageBox, "information", lambda *a, **k: None)
    seen: dict = {}

    _open_metadata_over(window, monkeypatch, lambda d: seen.update(allowed=d._is_recording_busy()))

    assert seen["allowed"] is False
