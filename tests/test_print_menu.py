"""Tests app_window's File > Print... wiring in isolation from the real
PrintDialog UI (which has its own tests in test_print_dialog.py)."""

from mdtools import app_window as app_window_module
from mdtools.app_window import MainWindow


class _FakeDialog:
    last_instance = None

    def __init__(self, project, parent=None):
        self.project = project
        self.parent = parent
        _FakeDialog.last_instance = self

    def exec(self):
        return 1


def test_print_project_opens_the_print_dialog_with_the_current_project(qt_app, monkeypatch):
    monkeypatch.setattr(app_window_module, "PrintDialog", _FakeDialog)

    win = MainWindow(show_startup_dialog=False)
    win._print_project()

    assert _FakeDialog.last_instance is not None
    assert _FakeDialog.last_instance.project is win.project


def test_print_project_does_nothing_without_an_open_project(qt_app, monkeypatch):
    monkeypatch.setattr(app_window_module, "PrintDialog", _FakeDialog)
    monkeypatch.setattr(_FakeDialog, "last_instance", None)

    win = MainWindow(show_startup_dialog=False)
    win.project = None
    win._print_project()  # must not raise

    assert _FakeDialog.last_instance is None
