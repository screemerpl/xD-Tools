"""Insert Asset: pick one of the bundled gallery images (assets/img) to add
as a new image layer -- a curated alternative to "Add Image..." browsing an
arbitrary file."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)

from mdtools.gallery import list_gallery_images

THUMBNAIL_SIZE = 96


class AssetGalleryDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Insert Asset"))
        self.resize(420, 320)
        self.selected_path: str | None = None
        self.list_widget: QListWidget | None = None

        layout = QVBoxLayout(self)

        images = list_gallery_images()
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons = self.button_box
        if not images:
            layout.addWidget(QLabel(self.tr("No images found in the asset gallery.")))
            buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        else:
            self.list_widget = QListWidget()
            self.list_widget.setViewMode(QListWidget.ViewMode.IconMode)
            self.list_widget.setIconSize(QSize(THUMBNAIL_SIZE, THUMBNAIL_SIZE))
            self.list_widget.setResizeMode(QListWidget.ResizeMode.Adjust)
            self.list_widget.setSpacing(8)
            for path in images:
                item = QListWidgetItem(QIcon(QPixmap(str(path))), path.stem)
                item.setData(Qt.ItemDataRole.UserRole, str(path))
                self.list_widget.addItem(item)
            self.list_widget.setCurrentRow(0)
            self.list_widget.itemDoubleClicked.connect(self._accept_item)
            layout.addWidget(self.list_widget)

        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _accept_item(self, item: QListWidgetItem) -> None:
        self.selected_path = item.data(Qt.ItemDataRole.UserRole)
        self.accept()

    def _on_accept(self) -> None:
        current = self.list_widget.currentItem() if self.list_widget else None
        if current is None:
            return
        self._accept_item(current)
