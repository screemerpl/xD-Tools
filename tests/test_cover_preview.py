"""The cover thumbnail shared by the Metadata editor and all three
recording sources.

The rule it carries is the point of having one of these rather than four:
every automatic source guesses, so the picture has to be clickable, and the
bytes have to be checked by trying to draw them rather than by trusting a
file extension.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QBuffer, QPoint, Qt
from PySide6.QtGui import QColor, QImage, QMouseEvent
from PySide6.QtWidgets import QFileDialog, QMessageBox

from mdtools.metadata_lookup import AlbumCandidate, MetadataLookupError
from mdtools.panels import cover_preview as module
from mdtools.panels.cover_preview import CoverPreview, fetch_into


def _png(colour: str = "red") -> bytes:
    image = QImage(4, 4, QImage.Format.Format_ARGB32)
    image.fill(QColor(colour))
    buffer = QBuffer()
    buffer.open(QBuffer.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(buffer.data())


# --- what it holds ----------------------------------------------------


def test_an_empty_preview_says_what_to_do_with_it(qt_app):
    preview = CoverPreview()
    assert preview.data is None
    assert preview.text().strip()


def test_setting_a_real_image_draws_it(qt_app):
    preview = CoverPreview()
    assert preview.set_cover(_png()) is True
    assert not preview.pixmap().isNull()
    assert preview.data == _png()


def test_bytes_qt_cannot_draw_are_still_kept(qt_app):
    """Deliberate: they came from somewhere that had a reason for them, and
    Pillow -- which palette.py reads a cover with -- understands formats
    this preview does not. Only the picture falls back."""
    preview = CoverPreview()

    assert preview.set_cover(b"not an image") is False
    assert preview.data == b"not an image"
    assert preview.text().strip(), "the placeholder is shown instead"


def test_clearing_it_goes_back_to_the_placeholder(qt_app):
    preview = CoverPreview()
    preview.set_cover(_png())

    preview.set_cover(None)

    assert preview.data is None
    assert preview.text().strip()


# --- replacing it -----------------------------------------------------


def test_clicking_it_opens_a_picker_and_adopts_the_file(qt_app, tmp_path, monkeypatch):
    path = tmp_path / "sleeve.png"
    path.write_bytes(_png("blue"))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(path), "")))
    preview = CoverPreview()
    changes: list = []
    preview.changed.connect(lambda: changes.append(True))

    preview.clicked.emit()

    assert preview.data == _png("blue")
    assert changes == [True]


def test_cancelling_the_picker_leaves_the_cover_alone(qt_app, monkeypatch):
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: ("", "")))
    preview = CoverPreview()
    preview.set_cover(_png())

    preview.clicked.emit()

    assert preview.data == _png()


def test_a_file_that_is_not_an_image_is_refused_and_the_old_one_kept(qt_app, tmp_path, monkeypatch):
    """The extension is not trusted: these bytes end up saved in the project
    and handed to the layout code, which cannot report back that they were
    never a picture. A bad pick must also not destroy a good cover."""
    path = tmp_path / "sleeve.png"
    path.write_bytes(b"%PDF-1.4 not really")
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(path), "")))
    warned: list = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: warned.append(True)))
    preview = CoverPreview()
    preview.set_cover(_png())

    preview.clicked.emit()

    assert preview.data == _png(), "the good cover survived"
    assert warned


def test_a_press_that_wandered_off_before_release_is_not_a_click(qt_app):
    """How anyone cancels a misclick."""
    preview = CoverPreview()
    clicks: list = []
    preview.clicked.connect(lambda: clicks.append(True))

    preview.mouseReleaseEvent(
        QMouseEvent(
            QMouseEvent.Type.MouseButtonRelease,
            QPoint(-40, -40),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
    )

    assert clicks == []


# --- the lookup helper ------------------------------------------------


def _candidate(year=2016):
    return AlbumCandidate(
        collection_id=1,
        artist_name="Skillet",
        collection_name="Unleashed",
        year=year,
        track_count=12,
        artwork_url="http://example/600x600bb.jpg",
    )


def test_a_found_cover_is_shown_and_saved_to_the_gallery(qt_app, monkeypatch):
    """Saving it is what makes a fetched sleeve turn up in Insert Asset,
    with no separate "add to gallery" step anywhere."""
    monkeypatch.setattr(module, "find_cover", lambda *a, **k: (_png(), _candidate()))
    saved: list = []
    monkeypatch.setattr(module, "save_downloaded_cover", lambda *a: saved.append(a))
    preview = CoverPreview()

    chosen = fetch_into(preview, "Skillet", "Unleashed", 12)

    assert preview.data == _png()
    assert chosen.year == 2016
    assert saved and saved[0][2] == _png()


def test_the_candidate_comes_back_even_with_no_artwork(qt_app, monkeypatch):
    """It carries a release year the caller may be missing -- the same
    reason find_cover hands it back."""
    monkeypatch.setattr(module, "find_cover", lambda *a, **k: (None, _candidate(1999)))
    preview = CoverPreview()

    assert fetch_into(preview, "Skillet", "Unleashed").year == 1999
    assert preview.data is None


def test_a_network_failure_is_swallowed_not_raised(qt_app, monkeypatch):
    """Artwork is a bonus on top of whatever the caller was really doing --
    a warning box about it would interrupt something that succeeded."""
    def boom(*args, **kwargs):
        raise MetadataLookupError("offline")

    monkeypatch.setattr(module, "find_cover", boom)

    assert fetch_into(CoverPreview(), "Skillet", "Unleashed") is None


def test_nothing_to_search_by_is_not_a_search(qt_app, monkeypatch):
    monkeypatch.setattr(module, "find_cover", lambda *a, **k: pytest.fail("must not search"))

    assert fetch_into(CoverPreview(), "  ", "") is None


def test_the_wait_cursor_is_always_put_back(qt_app, monkeypatch):
    """A lookup that failed used to be able to leave the whole app showing
    an hourglass."""
    from PySide6.QtWidgets import QApplication

    def boom(*args, **kwargs):
        raise MetadataLookupError("offline")

    monkeypatch.setattr(module, "find_cover", boom)
    fetch_into(CoverPreview(), "Skillet", "Unleashed")

    assert QApplication.overrideCursor() is None
