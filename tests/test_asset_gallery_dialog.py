from pathlib import Path

from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QDialogButtonBox

from mdtools.panels import asset_gallery_dialog as asset_gallery_dialog_module
from mdtools.panels.asset_gallery_dialog import AssetGalleryDialog


def _write_tiny_png(path: Path) -> None:
    image = QImage(4, 4, QImage.Format.Format_ARGB32)
    image.fill(QColor("blue"))
    image.save(str(path), "PNG")


def test_empty_gallery_shows_a_hint_and_disables_ok(qt_app, monkeypatch):
    monkeypatch.setattr(asset_gallery_dialog_module, "list_gallery_images", lambda: [])

    dialog = AssetGalleryDialog()

    assert dialog.list_widget is None
    assert not dialog.button_box.button(QDialogButtonBox.StandardButton.Ok).isEnabled()


def test_gallery_images_are_listed_and_first_one_preselected(qt_app, tmp_path, monkeypatch):
    paths = [tmp_path / "a.png", tmp_path / "b.png"]
    for p in paths:
        _write_tiny_png(p)
    monkeypatch.setattr(asset_gallery_dialog_module, "list_gallery_images", lambda: paths)

    dialog = AssetGalleryDialog()

    assert dialog.list_widget.count() == 2
    assert dialog.list_widget.currentRow() == 0
    assert dialog.button_box.button(QDialogButtonBox.StandardButton.Ok).isEnabled()


def test_accepting_sets_selected_path_to_the_current_item(qt_app, tmp_path, monkeypatch):
    paths = [tmp_path / "a.png", tmp_path / "b.png"]
    for p in paths:
        _write_tiny_png(p)
    monkeypatch.setattr(asset_gallery_dialog_module, "list_gallery_images", lambda: paths)

    dialog = AssetGalleryDialog()
    dialog.list_widget.setCurrentRow(1)
    dialog.button_box.accepted.emit()

    assert dialog.selected_path == str(paths[1])
    assert dialog.result() == AssetGalleryDialog.DialogCode.Accepted


def test_double_clicking_an_item_accepts_immediately(qt_app, tmp_path, monkeypatch):
    paths = [tmp_path / "a.png", tmp_path / "b.png"]
    for p in paths:
        _write_tiny_png(p)
    monkeypatch.setattr(asset_gallery_dialog_module, "list_gallery_images", lambda: paths)

    dialog = AssetGalleryDialog()
    dialog.list_widget.itemDoubleClicked.emit(dialog.list_widget.item(1))

    assert dialog.selected_path == str(paths[1])
    assert dialog.result() == AssetGalleryDialog.DialogCode.Accepted
