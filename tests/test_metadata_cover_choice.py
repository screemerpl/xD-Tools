"""Choosing the cover art by hand, by clicking the preview.

Both automatic sources guess. iTunes returns whatever release its search
matched, which for a reissue or a band with a common name is regularly the
wrong sleeve, and until this existed there was no way to correct it from
this dialog at all.
"""

import pytest
from PySide6.QtCore import QBuffer, QByteArray, QPoint, Qt
from PySide6.QtGui import QColor, QMouseEvent, QPixmap

from mdtools.panels import metadata_dialog as dialog_module
from mdtools.panels.metadata_dialog import MetadataDialog
from mdtools.project import ProjectMetadata


def _image_bytes(colour: str = "green") -> bytes:
    pixmap = QPixmap(80, 80)
    pixmap.fill(QColor(colour))
    storage = QByteArray()  # named: QBuffer does not keep a temporary alive
    buffer = QBuffer(storage)
    buffer.open(QBuffer.OpenModeFlag.WriteOnly)
    pixmap.save(buffer, "PNG")
    buffer.close()
    return bytes(storage)


def _click(label, where: QPoint | None = None) -> None:
    """A real release event on the label, rather than emitting `clicked`
    directly -- the point of the feature is that clicking the picture works."""
    point = label.rect().center() if where is None else where
    label.mouseReleaseEvent(
        QMouseEvent(
            QMouseEvent.Type.MouseButtonRelease,
            point,
            label.mapToGlobal(point),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
    )


def _choose(monkeypatch, path) -> None:
    monkeypatch.setattr(dialog_module.QFileDialog, "getOpenFileName", lambda *a, **k: (str(path), ""))


def test_clicking_the_cover_opens_a_file_picker(qt_app, monkeypatch, tmp_path):
    path = tmp_path / "sleeve.png"
    path.write_bytes(_image_bytes())
    opened = []
    monkeypatch.setattr(
        dialog_module.QFileDialog, "getOpenFileName", lambda *a, **k: (opened.append(True), (str(path), ""))[1]
    )

    dialog = MetadataDialog(ProjectMetadata())
    _click(dialog.cover_label)

    assert opened, "the click must reach the file picker"


def test_a_chosen_file_replaces_the_cover(qt_app, monkeypatch, tmp_path):
    path = tmp_path / "sleeve.png"
    path.write_bytes(_image_bytes("blue"))
    _choose(monkeypatch, path)

    dialog = MetadataDialog(ProjectMetadata(album="A", cover_art=_image_bytes("red")))
    dialog.cover_label.clicked.emit()

    assert dialog._cover_art == path.read_bytes()
    assert not dialog.cover_label.pixmap().isNull()


def test_the_chosen_cover_is_what_gets_saved(qt_app, monkeypatch, tmp_path):
    """It has to survive OK -- the preview updating on its own would be a
    change the user could not keep."""
    path = tmp_path / "sleeve.png"
    path.write_bytes(_image_bytes("blue"))
    _choose(monkeypatch, path)

    dialog = MetadataDialog(ProjectMetadata(album="A"))
    dialog.cover_label.clicked.emit()
    dialog._on_accept()

    assert dialog.result_metadata.cover_art == path.read_bytes()


def test_cancelling_the_picker_keeps_the_existing_cover(qt_app, monkeypatch):
    monkeypatch.setattr(dialog_module.QFileDialog, "getOpenFileName", lambda *a, **k: ("", ""))
    original = _image_bytes("red")

    dialog = MetadataDialog(ProjectMetadata(cover_art=original))
    dialog.cover_label.clicked.emit()

    assert dialog._cover_art == original


def test_a_file_that_is_not_an_image_is_refused(qt_app, monkeypatch, tmp_path):
    """These bytes end up saved in the project and handed to the layout
    code, which has no way to report back that they were never a picture."""
    path = tmp_path / "notes.txt"
    path.write_text("this is not a picture", encoding="utf-8")
    _choose(monkeypatch, path)
    warned = []
    monkeypatch.setattr(dialog_module.QMessageBox, "warning", lambda *a, **k: warned.append(True))
    original = _image_bytes("red")

    dialog = MetadataDialog(ProjectMetadata(cover_art=original))
    dialog.cover_label.clicked.emit()

    assert warned, "the user has to be told why nothing changed"
    assert dialog._cover_art == original


def test_a_release_outside_the_label_is_not_a_click(qt_app, monkeypatch):
    """Pressing on it and dragging off before letting go is how a misclick
    gets cancelled."""
    monkeypatch.setattr(
        dialog_module.QFileDialog, "getOpenFileName", lambda *a, **k: pytest.fail("that was not a click")
    )
    dialog = MetadataDialog(ProjectMetadata())

    _click(dialog.cover_label, QPoint(-40, -40))


def test_the_empty_preview_says_it_can_be_clicked(qt_app):
    """An unlabelled square nobody knows is a button is the same as not
    having the feature."""
    assert MetadataDialog(ProjectMetadata()).cover_label.text().strip() != ""
