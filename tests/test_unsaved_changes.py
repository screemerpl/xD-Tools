"""Not losing a project by closing the window.

Until this existed, quitting threw away everything since the last save with
no warning at all -- and so did File > New and File > Open.
"""

import pytest
from PySide6.QtGui import QCloseEvent

from mdtools import app_window as app_module
from mdtools.app_window import MainWindow
from mdtools.commands import AddItemCommand
from mdtools.project import PAGE_DISC
from mdtools.templates.models import DiscTemplate


def _close_event() -> QCloseEvent:
    """A real QCloseEvent: the handler passes it on to QWidget, which
    refuses anything else. Whether the window closes is then readable from
    isAccepted()."""
    return QCloseEvent()


def _window() -> MainWindow:
    return MainWindow(show_startup_dialog=False)


def _dirty_window() -> MainWindow:
    window = _window()
    scene = window.project.pages[PAGE_DISC]
    window.undo_stack.push(AddItemCommand(scene, scene.add_text("unsaved"), "add"))
    assert window._dirty
    return window


def _answer(monkeypatch, button):
    monkeypatch.setattr(app_module.QMessageBox, "question", lambda *a, **k: button)


# --- what counts as a change -----------------------------------------------


def test_a_brand_new_project_has_nothing_to_lose(qt_app):
    """Building its pages runs through the undo stack, which would
    otherwise leave it looking modified before the user touched it."""
    assert _window()._dirty is False


def test_editing_the_canvas_marks_the_project_changed(qt_app):
    assert _dirty_window()._dirty


def test_changing_a_pages_template_marks_it_changed(qt_app):
    """It resets the undo stack, so cleanliness there would report an
    untouched project."""
    window = _window()
    window._mark_saved()

    window.apply_template(PAGE_DISC, DiscTemplate(name="other", width_mm=37.0, height_mm=52.0))

    assert window._dirty


def test_saving_clears_it(qt_app, tmp_path, monkeypatch):
    window = _dirty_window()
    window.current_project_path = str(tmp_path / "p.mdproj")

    assert window._save_project() is True
    assert window._dirty is False


# --- closing ---------------------------------------------------------------


def test_closing_an_unchanged_project_asks_nothing(qt_app, monkeypatch):
    monkeypatch.setattr(
        app_module.QMessageBox, "question", lambda *a, **k: pytest.fail("nothing to ask about")
    )
    event = _close_event()

    _window().closeEvent(event)

    assert event.isAccepted()


def test_cancelling_the_prompt_keeps_the_window_open(qt_app, monkeypatch):
    window = _dirty_window()
    _answer(monkeypatch, app_module.QMessageBox.StandardButton.Cancel)
    event = _close_event()

    window.closeEvent(event)

    assert not event.isAccepted(), "the close must be refused, not merely un-saved"


def test_discarding_closes_without_saving(qt_app, monkeypatch):
    window = _dirty_window()
    _answer(monkeypatch, app_module.QMessageBox.StandardButton.Discard)
    monkeypatch.setattr(window, "_save_project", lambda: pytest.fail("must not save when discarding"))
    event = _close_event()

    window.closeEvent(event)

    assert event.isAccepted()


def test_choosing_save_writes_the_file_then_closes(qt_app, tmp_path, monkeypatch):
    window = _dirty_window()
    window.current_project_path = str(tmp_path / "p.mdproj")
    _answer(monkeypatch, app_module.QMessageBox.StandardButton.Save)
    event = _close_event()

    window.closeEvent(event)

    assert event.isAccepted()
    assert (tmp_path / "p.mdproj").exists()


def test_backing_out_of_save_as_does_not_close_the_window(qt_app, monkeypatch):
    """Choosing Save and then cancelling the file dialog means the work is
    still unsaved -- closing anyway would lose exactly what was being
    protected."""
    window = _dirty_window()
    _answer(monkeypatch, app_module.QMessageBox.StandardButton.Save)
    monkeypatch.setattr(app_module.QFileDialog, "getSaveFileName", lambda *a, **k: ("", ""))
    event = _close_event()

    window.closeEvent(event)

    assert not event.isAccepted()


# --- the same guard on New and Open ----------------------------------------


def test_starting_a_new_project_asks_first(qt_app, monkeypatch):
    window = _dirty_window()
    _answer(monkeypatch, app_module.QMessageBox.StandardButton.Cancel)
    before = window.project

    assert window._new_design(prompt=False) is False
    assert window.project is before


def test_opening_a_project_asks_first(qt_app, monkeypatch):
    window = _dirty_window()
    _answer(monkeypatch, app_module.QMessageBox.StandardButton.Cancel)
    monkeypatch.setattr(
        app_module, "load_project", lambda path: pytest.fail("must not read a file after cancelling")
    )

    assert window._open_project_path("whatever.mdproj") is False


def test_the_startup_flow_is_not_interrupted(qt_app, monkeypatch):
    """There is no project yet at that point, so the guard has to stay
    silent -- otherwise launching the app would prompt about nothing."""
    monkeypatch.setattr(
        app_module.QMessageBox, "question", lambda *a, **k: pytest.fail("nothing exists to lose yet")
    )
    window = _window()
    window.project = None

    assert window._may_discard_changes() is True
