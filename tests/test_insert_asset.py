from pathlib import Path

from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QDialog

from mdtools.app_window import MainWindow
from mdtools.project import PAGE_COVER


def _write_tiny_png(path: Path) -> None:
    image = QImage(4, 4, QImage.Format.Format_ARGB32)
    image.fill(QColor("blue"))
    image.save(str(path), "PNG")


def _stub_dialog_class(selected_path, accepted):
    """A stand-in for AssetGalleryDialog: MainWindow only relies on
    .exec()'s return value and .selected_path afterward, plus .DialogCode
    (inherited from QDialog here) to interpret that return value."""

    class _StubDialog(QDialog):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.selected_path = selected_path

        def exec(self):
            return QDialog.DialogCode.Accepted if accepted else QDialog.DialogCode.Rejected

    return _StubDialog


def _win() -> MainWindow:
    win = MainWindow(show_startup_dialog=False)
    win._show_page(PAGE_COVER)  # blank canvas -- disc page auto-seeds a triangle+label
    return win


def test_insert_asset_adds_the_selected_image_as_a_layer(qt_app, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QGraphicsPixmapItem

    from mdtools import app_window as app_window_module

    png_path = tmp_path / "logo.png"
    _write_tiny_png(png_path)
    monkeypatch.setattr(app_window_module, "AssetGalleryDialog", _stub_dialog_class(str(png_path), True))

    win = _win()
    scene = win._current_scene()
    win._insert_asset()

    items = scene.print_items()
    assert len(items) == 1
    assert isinstance(items[0], QGraphicsPixmapItem)


def test_insert_asset_is_undoable(qt_app, tmp_path, monkeypatch):
    from mdtools import app_window as app_window_module

    png_path = tmp_path / "logo.png"
    _write_tiny_png(png_path)
    monkeypatch.setattr(app_window_module, "AssetGalleryDialog", _stub_dialog_class(str(png_path), True))

    win = _win()
    scene = win._current_scene()
    win._insert_asset()
    assert len(scene.print_items()) == 1

    win.undo_stack.undo()
    assert scene.print_items() == []


def test_cancelling_the_dialog_inserts_nothing(qt_app, monkeypatch):
    from mdtools import app_window as app_window_module

    monkeypatch.setattr(app_window_module, "AssetGalleryDialog", _stub_dialog_class(None, False))

    win = _win()
    scene = win._current_scene()
    win._insert_asset()

    assert scene.print_items() == []
