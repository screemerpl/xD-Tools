"""Closing the project window goes back to the startup screen.

It used to quit the whole app, which made "open a different project" a
round trip through relaunching MDTools -- there was one route out of a
project and it took the program with it.
"""

import pytest
from PySide6.QtGui import QCloseEvent

from mdtools import app_window as app_module
from mdtools.app_window import MainWindow
from mdtools.io.project_io import save_project
from mdtools.panels.new_design_dialog import NewDesignDialog
from mdtools.panels.startup_dialog import StartupDialog
from mdtools.project import ProjectMetadata


def _window(monkeypatch) -> MainWindow:
    """A window that believes it has a startup screen, without one having
    been shown to build it."""
    monkeypatch.setattr(StartupDialog, "exec", lambda self: StartupDialog.DialogCode.Rejected)
    return MainWindow(show_startup_dialog=True)


def _startup_returns(monkeypatch, path=None, accepted: bool = True):
    def fake_exec(self):
        self.result_path = path
        return StartupDialog.DialogCode.Accepted if accepted else StartupDialog.DialogCode.Rejected

    monkeypatch.setattr(StartupDialog, "exec", fake_exec)


def _saved_project(tmp_path, album: str) -> str:
    source = MainWindow(show_startup_dialog=False)
    source.project.metadata = ProjectMetadata(album=album)
    path = tmp_path / f"{album}.mdproj"
    save_project(source.project, path)
    return str(path)


def test_closing_reopens_the_startup_screen_instead_of_quitting(qt_app, monkeypatch, tmp_path):
    window = _window(monkeypatch)
    path = _saved_project(tmp_path, "Chosen")
    _startup_returns(monkeypatch, path=path)
    event = QCloseEvent()

    window.closeEvent(event)

    assert not event.isAccepted(), "the window has to stay, now showing the newly opened project"
    assert window.project.metadata.album == "Chosen"
    assert window.isVisible()


def test_cancelling_the_startup_screen_really_does_close(qt_app, monkeypatch):
    """That is where quitting lives now -- otherwise there would be no way
    out at all."""
    window = _window(monkeypatch)
    _startup_returns(monkeypatch, accepted=False)
    event = QCloseEvent()

    window.closeEvent(event)

    assert event.isAccepted()


def test_backing_out_of_the_template_picker_returns_to_the_startup_screen(qt_app, monkeypatch):
    """Not to a closed app: cancelling "which template?" means "not that
    one", and quitting over it would be a startling answer."""
    window = _window(monkeypatch)
    attempts = []

    def fake_startup(self):
        self.result_path = None
        attempts.append(len(attempts))
        # New Project the first time, then give up -- otherwise this loops.
        return (
            StartupDialog.DialogCode.Accepted if len(attempts) == 1 else StartupDialog.DialogCode.Rejected
        )

    monkeypatch.setattr(StartupDialog, "exec", fake_startup)
    monkeypatch.setattr(NewDesignDialog, "exec", lambda self: NewDesignDialog.DialogCode.Rejected)

    window.closeEvent(QCloseEvent())

    assert len(attempts) == 2, "the startup screen must come back after the picker was cancelled"


def test_unsaved_changes_are_still_asked_about_first(qt_app, monkeypatch):
    window = _window(monkeypatch)
    window._mark_dirty()
    monkeypatch.setattr(
        StartupDialog, "exec", lambda self: pytest.fail("the startup screen must not appear before the prompt")
    )
    monkeypatch.setattr(app_module.QMessageBox, "question", lambda *a, **k: app_module.QMessageBox.StandardButton.Cancel)
    event = QCloseEvent()

    window.closeEvent(event)

    assert not event.isAccepted()


def test_discarding_changes_does_not_ask_about_them_twice(qt_app, monkeypatch, tmp_path):
    """The close prompt settles it; the startup screen's own load must not
    put the same question up again."""
    window = _window(monkeypatch)
    window._mark_dirty()
    asked = []
    monkeypatch.setattr(
        app_module.QMessageBox,
        "question",
        lambda *a, **k: (asked.append(True), app_module.QMessageBox.StandardButton.Discard)[1],
    )
    _startup_returns(monkeypatch, path=_saved_project(tmp_path, "Second"))

    window.closeEvent(QCloseEvent())

    assert len(asked) == 1
    assert window.project.metadata.album == "Second"


def test_file_exit_quits_rather_than_going_back(qt_app, monkeypatch):
    window = _window(monkeypatch)
    monkeypatch.setattr(StartupDialog, "exec", lambda self: pytest.fail("Exit means leave"))

    window._exit_app()

    assert window._quitting is True, "the close went through without diverting to the startup screen"


def test_a_refused_exit_does_not_arm_the_next_close(qt_app, monkeypatch):
    """Cancelling the save prompt during File > Exit must not leave the
    window primed to quit silently the next time it is closed."""
    window = _window(monkeypatch)
    window._mark_dirty()
    monkeypatch.setattr(app_module.QMessageBox, "question", lambda *a, **k: app_module.QMessageBox.StandardButton.Cancel)

    window._exit_app()

    assert window._quitting is False


def test_a_window_without_a_startup_screen_just_closes(qt_app, monkeypatch):
    """Everything embedding MainWindow directly -- the whole test suite --
    would otherwise stall on a dialog nothing is there to answer."""
    monkeypatch.setattr(StartupDialog, "exec", lambda self: pytest.fail("there is no startup screen here"))
    event = QCloseEvent()

    MainWindow(show_startup_dialog=False).closeEvent(event)

    assert event.isAccepted()
