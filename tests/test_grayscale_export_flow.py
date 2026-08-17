"""Tests app_window's _export_png_grayscale wiring: the pre-export dialog
must be shown, its result must be saved back onto the project (and mirror
into the toolbar sliders), and export_png must receive the confirmed
brightness/contrast -- all without actually touching the filesystem or
a real modal dialog.
"""

from mdtools import app_window as app_window_module
from mdtools.app_window import MainWindow
from mdtools.project import GrayscaleAdjustment


class _FakeDialog:
    """Stands in for GrayscaleExportDialog -- exercises app_window's own
    wiring in isolation from the real dialog's UI, which already has its
    own tests in test_grayscale_export_dialog.py."""

    DialogCode = type("DialogCode", (), {"Accepted": 1, "Rejected": 0})
    last_instance = None

    def __init__(self, scene, adjustment, parent=None):
        self.scene = scene
        self.adjustment = adjustment
        self.result_adjustment = GrayscaleAdjustment(brightness=60, contrast=-10)
        _FakeDialog.last_instance = self

    def exec(self):
        return self.DialogCode.Accepted


def test_confirming_the_dialog_saves_the_adjustment_and_passes_it_to_export(qt_app, tmp_path, monkeypatch):
    monkeypatch.setattr(app_window_module, "GrayscaleExportDialog", _FakeDialog)

    captured = {}
    monkeypatch.setattr(
        app_window_module,
        "export_png",
        lambda scene, path, grayscale=False, brightness=0, contrast=0: captured.update(
            grayscale=grayscale, brightness=brightness, contrast=contrast
        ),
    )
    out_path = tmp_path / "out.png"
    monkeypatch.setattr(
        app_window_module.QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(out_path), ""))
    )

    win = MainWindow(show_startup_dialog=False)
    win._export_png_grayscale()

    assert captured == {"grayscale": True, "brightness": 60, "contrast": -10}
    assert win.project.grayscale_adjustment == GrayscaleAdjustment(brightness=60, contrast=-10)


def test_cancelling_the_dialog_never_calls_export_or_touches_the_project(qt_app, monkeypatch):
    class _CancelledDialog(_FakeDialog):
        def exec(self):
            return self.DialogCode.Rejected

    monkeypatch.setattr(app_window_module, "GrayscaleExportDialog", _CancelledDialog)

    def fail_if_called(*a, **k):
        raise AssertionError("export_png should not run if the dialog was cancelled")

    monkeypatch.setattr(app_window_module, "export_png", fail_if_called)

    win = MainWindow(show_startup_dialog=False)
    original = win.project.grayscale_adjustment
    win._export_png_grayscale()  # must not raise

    assert win.project.grayscale_adjustment == original


def test_confirming_the_dialog_seeds_the_dialog_from_the_projects_current_adjustment(qt_app, monkeypatch):
    monkeypatch.setattr(app_window_module, "GrayscaleExportDialog", _FakeDialog)
    monkeypatch.setattr(app_window_module, "export_png", lambda *a, **k: None)
    monkeypatch.setattr(app_window_module.QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: ("", "")))

    win = MainWindow(show_startup_dialog=False)
    win.project.grayscale_adjustment = GrayscaleAdjustment(brightness=5, contrast=7)

    win._export_png_grayscale()

    assert _FakeDialog.last_instance.adjustment == GrayscaleAdjustment(brightness=5, contrast=7)


def test_confirming_the_dialog_also_updates_the_toolbar_sliders(qt_app, monkeypatch):
    monkeypatch.setattr(app_window_module, "GrayscaleExportDialog", _FakeDialog)
    monkeypatch.setattr(app_window_module, "export_png", lambda *a, **k: None)
    monkeypatch.setattr(app_window_module.QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: ("", "")))

    win = MainWindow(show_startup_dialog=False)
    win._export_png_grayscale()

    assert win.brightness_slider.value() == 60
    assert win.contrast_slider.value() == -10


def test_an_empty_save_path_does_not_export(qt_app, monkeypatch):
    monkeypatch.setattr(app_window_module, "GrayscaleExportDialog", _FakeDialog)

    def fail_if_called(*a, **k):
        raise AssertionError("export_png should not run without a chosen path")

    monkeypatch.setattr(app_window_module, "export_png", fail_if_called)
    monkeypatch.setattr(app_window_module.QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: ("", "")))

    win = MainWindow(show_startup_dialog=False)
    win._export_png_grayscale()  # must not raise
