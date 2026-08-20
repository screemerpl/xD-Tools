"""Choosing a background treatment for a disc/shell label's cover art,
before the label is actually generated.

Six tiles, each a live preview built by running the real cover through
`cover_filters.apply_cover_filter()` -- the exact function the caller then
uses to build the actual label, so nothing here can show one thing and
print another. Clicking a tile chooses it and closes the dialog, the same
single-click-to-commit interaction as picking a colour with the eyedropper
elsewhere in this app; there's no separate OK button to press afterwards.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QLabel,
    QToolButton,
    QVBoxLayout,
)

from mdtools import cover_filters

THUMBNAIL_PX = 150
_COLUMNS = 3


class CoverFilterDialog(QDialog):
    def __init__(self, cover_art: bytes, title: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        # None until a tile is actually clicked -- Cancel/closing the
        # dialog leaves it at None, which the caller reads as "don't build
        # this label after all" rather than silently picking a default.
        self.result_filter_id: str | None = None

        # Built here, not at module scope: self.tr() needs a live QObject,
        # and this dict only exists for the lifetime of one dialog anyway.
        labels = {
            cover_filters.FILTER_NONE: self.tr("No Filter"),
            cover_filters.FILTER_BRIGHTEN: self.tr("Brighten"),
            cover_filters.FILTER_BLUR: self.tr("Gaussian Blur"),
            cover_filters.FILTER_POSTERIZE: self.tr("Posterize"),
            cover_filters.FILTER_HALFTONE: self.tr("Halftone"),
            cover_filters.FILTER_PIXELATE: self.tr("Pixelate"),
        }

        layout = QVBoxLayout(self)

        heading = QLabel(self.tr("Pick a background treatment for the cover art -- click one to use it."))
        heading.setWordWrap(True)
        layout.addWidget(heading)

        grid = QGridLayout()
        grid.setSpacing(10)
        layout.addLayout(grid)
        for index, filter_id in enumerate(cover_filters.FILTER_IDS):
            tile = self._build_tile(cover_art, filter_id, labels[filter_id])
            grid.addWidget(tile, index // _COLUMNS, index % _COLUMNS)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _build_tile(self, cover_art: bytes, filter_id: str, label_text: str) -> QToolButton:
        tile = QToolButton()
        tile.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        tile.setText(label_text)
        tile.setIconSize(QSize(THUMBNAIL_PX, THUMBNAIL_PX))
        tile.setIcon(QIcon(self._thumbnail(cover_art, filter_id)))
        tile.clicked.connect(lambda checked=False, chosen=filter_id: self._choose(chosen))
        return tile

    def _thumbnail(self, cover_art: bytes, filter_id: str) -> QPixmap:
        filtered = cover_filters.apply_cover_filter(cover_art, filter_id)
        pixmap = QPixmap()
        pixmap.loadFromData(filtered)
        # KeepAspectRatioByExpanding + a centre-crop, not a plain scaled():
        # every tile has to come out the same THUMBNAIL_PX square regardless
        # of the source cover's own aspect ratio, or filters that work on a
        # fixed pixel scale (the halftone dot grid, the pixelate block size)
        # would render at visibly different densities tile to tile.
        scaled = pixmap.scaled(
            THUMBNAIL_PX,
            THUMBNAIL_PX,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = max(0, (scaled.width() - THUMBNAIL_PX) // 2)
        y = max(0, (scaled.height() - THUMBNAIL_PX) // 2)
        return scaled.copy(x, y, THUMBNAIL_PX, THUMBNAIL_PX)

    def _choose(self, filter_id: str) -> None:
        self.result_filter_id = filter_id
        self.accept()
