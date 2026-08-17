"""Export Print PNG (Grayscale)'s pre-export brightness/contrast dialog.

Shows a live preview of the actual scene, desaturated and adjusted exactly
the way the real export will look -- both call through the same
mdtools.grayscale.apply_grayscale(), so what's previewed here and what
actually gets saved by export_png() can never visually diverge.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QFrame, QLabel, QSlider, QVBoxLayout

from mdtools import app_settings
from mdtools.grayscale import BRIGHTNESS_RANGE, CONTRAST_RANGE, apply_grayscale
from mdtools.io.png_export import render_scene_to_image
from mdtools.project import GrayscaleAdjustment

PREVIEW_MAX_SIZE = 260


class GrayscaleExportDialog(QDialog):
    def __init__(self, scene, adjustment: GrayscaleAdjustment, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Export Print PNG (Grayscale)"))
        self.result_adjustment: GrayscaleAdjustment | None = None

        # A screen-resolution render is plenty for this preview -- it's
        # only ever shown scaled down to PREVIEW_MAX_SIZE px, and
        # re-running apply_grayscale() on every slider move needs to stay
        # cheap. The real export still renders at the actually-chosen
        # export DPI in export_png() itself, from the scene directly --
        # this dialog never touches that step.
        self._base_image = render_scene_to_image(scene, dpi=app_settings.screen_dpi())

        layout = QVBoxLayout(self)

        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setFrameShape(QFrame.Shape.Box)
        self.preview_label.setMinimumSize(PREVIEW_MAX_SIZE, PREVIEW_MAX_SIZE)
        layout.addWidget(self.preview_label)

        form = QFormLayout()
        self.brightness_slider = QSlider(Qt.Orientation.Horizontal)
        self.brightness_slider.setRange(*BRIGHTNESS_RANGE)
        self.brightness_slider.setValue(adjustment.brightness)
        self.brightness_slider.valueChanged.connect(self._update_preview)
        form.addRow(self.tr("Brightness"), self.brightness_slider)

        self.contrast_slider = QSlider(Qt.Orientation.Horizontal)
        self.contrast_slider.setRange(*CONTRAST_RANGE)
        self.contrast_slider.setValue(adjustment.contrast)
        self.contrast_slider.valueChanged.connect(self._update_preview)
        form.addRow(self.tr("Contrast"), self.contrast_slider)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._update_preview()

    def _update_preview(self) -> None:
        adjusted = apply_grayscale(self._base_image, self.brightness_slider.value(), self.contrast_slider.value())
        pixmap = QPixmap.fromImage(adjusted).scaled(
            PREVIEW_MAX_SIZE,
            PREVIEW_MAX_SIZE,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.preview_label.setPixmap(pixmap)

    def _on_accept(self) -> None:
        self.result_adjustment = GrayscaleAdjustment(
            brightness=self.brightness_slider.value(), contrast=self.contrast_slider.value()
        )
        self.accept()
