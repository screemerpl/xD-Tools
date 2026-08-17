from PySide6.QtCore import QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QColor, QImage

from mdtools.canvas.scene import DesignScene
from mdtools.io.png_export import export_png
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


def test_grayscale_export_desaturates_colored_artwork(qt_app, tmp_path):
    template = DiscTemplate(name="t", width_mm=37.0, height_mm=52.0, chamfer_mm=0, fillet_mm=0)
    scene = DesignScene(template)
    image_item = scene.add_image_from_data(_solid_png(40, "red"))
    image_item.setPos(0, 0)

    color_out = tmp_path / "color.png"
    gray_out = tmp_path / "gray.png"
    export_png(scene, color_out, dpi=96, grayscale=False)
    export_png(scene, gray_out, dpi=96, grayscale=True)

    color_result = QImage(str(color_out))
    gray_result = QImage(str(gray_out))

    # a point well inside the red square, away from the template's edges
    x, y = 30, 30
    color_pixel = color_result.pixelColor(x, y)
    gray_pixel = gray_result.pixelColor(x, y)

    assert color_pixel.red() > color_pixel.green()  # sanity: the color export really is red
    assert gray_pixel.red() == gray_pixel.green() == gray_pixel.blue()  # desaturated
    assert gray_pixel.alpha() == color_pixel.alpha() > 0  # opacity/clipping unaffected


def test_grayscale_export_applies_brightness_and_contrast(qt_app, tmp_path):
    template = DiscTemplate(name="t", width_mm=37.0, height_mm=52.0, chamfer_mm=0, fillet_mm=0)
    scene = DesignScene(template)
    image_item = scene.add_image_from_data(_solid_png(40, "gray"))
    image_item.setPos(0, 0)

    plain_out = tmp_path / "plain.png"
    adjusted_out = tmp_path / "adjusted.png"
    export_png(scene, plain_out, dpi=96, grayscale=True)
    export_png(scene, adjusted_out, dpi=96, grayscale=True, brightness=80, contrast=0)

    plain_pixel = QImage(str(plain_out)).pixelColor(30, 30)
    adjusted_pixel = QImage(str(adjusted_out)).pixelColor(30, 30)

    assert adjusted_pixel.red() > plain_pixel.red()  # brighter, as requested
    assert adjusted_pixel.alpha() == plain_pixel.alpha()  # clipping/opacity unaffected


def test_grayscale_export_still_clips_to_the_cut_outline(qt_app, tmp_path):
    template = DiscTemplate(name="t", width_mm=37.0, height_mm=52.0, chamfer_mm=5.0, fillet_mm=1.0)
    scene = DesignScene(template)
    image_item = scene.add_image_from_data(_solid_png(30, "blue"))
    image_item.setPos(0, 0)  # partly in the chamfered-off corner

    out = tmp_path / "gray_clip.png"
    export_png(scene, out, dpi=96, grayscale=True)

    result = QImage(str(out))
    assert result.pixelColor(12, 12).alpha() == 0  # inside the chamfer cut-off, still transparent
