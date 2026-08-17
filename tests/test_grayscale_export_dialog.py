from PySide6.QtCore import QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QColor, QImage

from mdtools.canvas.scene import DesignScene
from mdtools.panels.grayscale_export_dialog import GrayscaleExportDialog
from mdtools.project import GrayscaleAdjustment
from mdtools.templates.models import DiscTemplate


def _solid_png(size: int, color: str) -> bytes:
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(QColor(color))
    buffer = QByteArray()
    device = QBuffer(buffer)
    device.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(device, "PNG")
    device.close()
    return bytes(buffer)


def _scene() -> DesignScene:
    """A disc scene with an actual filled layer -- an empty scene renders
    fully transparent everywhere, which would make a brightness/contrast
    change invisible in the preview pixel value regardless of whether the
    adjustment logic actually ran."""
    scene = DesignScene(DiscTemplate(name="t", width_mm=37.0, height_mm=52.0, chamfer_mm=0, fillet_mm=0))
    image_item = scene.add_image_from_data(_solid_png(200, "gray"))
    image_item.setPos(0, 0)
    return scene


def test_dialog_seeds_sliders_from_the_given_adjustment(qt_app):
    dialog = GrayscaleExportDialog(_scene(), GrayscaleAdjustment(brightness=30, contrast=-20))

    assert dialog.brightness_slider.value() == 30
    assert dialog.contrast_slider.value() == -20


def test_dialog_shows_a_preview_immediately_without_moving_a_slider(qt_app):
    dialog = GrayscaleExportDialog(_scene(), GrayscaleAdjustment())
    assert not dialog.preview_label.pixmap().isNull()


def test_accepting_reports_the_slider_values(qt_app):
    dialog = GrayscaleExportDialog(_scene(), GrayscaleAdjustment())
    dialog.brightness_slider.setValue(45)
    dialog.contrast_slider.setValue(-15)

    dialog._on_accept()

    assert dialog.result_adjustment == GrayscaleAdjustment(brightness=45, contrast=-15)


def test_moving_a_slider_updates_the_preview_pixmap(qt_app):
    dialog = GrayscaleExportDialog(_scene(), GrayscaleAdjustment())
    preview = dialog.preview_label.pixmap().toImage()
    before = preview.pixelColor(preview.width() // 2, preview.height() // 2)

    dialog.brightness_slider.setValue(100)

    preview = dialog.preview_label.pixmap().toImage()
    after = preview.pixelColor(preview.width() // 2, preview.height() // 2)
    assert after.red() > before.red()
