from PySide6.QtCore import QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QColor, QImage

from mdtools.canvas.scene import DesignScene
from mdtools.io.png_export import export_png, render_scene_to_image
from mdtools.io.svg_export import export_svg
from mdtools.templates.models import CoverTemplate, DiscTemplate


def _solid_png(size: int, color: str) -> bytes:
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(QColor(color))
    buffer = QByteArray()
    device = QBuffer(buffer)
    device.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(device, "PNG")
    device.close()
    return bytes(buffer)


def test_png_export_is_transparent_outside_the_chamfered_corner(qt_app, tmp_path):
    # a big chamfer makes the cut-off corner triangle easy to hit precisely
    template = DiscTemplate(name="t", width_mm=37.0, height_mm=52.0, chamfer_mm=5.0, fillet_mm=1.0)
    scene = DesignScene(template)
    image_item = scene.add_image_from_data(_solid_png(30, "red"))
    image_item.setPos(0, 0)  # top-left corner: partly in the chamfered-off triangle, partly not
    image_item.setOpacity(1.0)

    out = tmp_path / "clip.png"
    export_png(scene, out, dpi=96)  # dpi == SCREEN_DPI => 1 scene unit == 1 image pixel

    result = QImage(str(out))
    # scene (2,2) is inside the chamfer's cut-off triangle -> must be transparent
    # even though the red image covers that point.
    assert result.pixelColor(12, 12).alpha() == 0
    # scene (25,25) is inside both the image and the surviving template shape.
    inside = result.pixelColor(35, 35)
    assert inside.alpha() > 0
    assert inside.red() > inside.green()


def test_render_scene_to_image_paints_onto_a_premultiplied_buffer(qt_app):
    """Regression: painting antialiased text/shapes onto a plain (non-
    premultiplied) ARGB32 QImage forces an extra unpremultiply/repremultiply
    round trip per pixel in Qt's raster engine, most visible exactly on the
    partially-transparent edge pixels of antialiased glyphs against full
    transparency -- reported as poor-quality/blocky-looking text. Painting
    onto a premultiplied buffer instead avoids that conversion."""
    template = DiscTemplate(name="t", width_mm=37.0, height_mm=52.0)
    scene = DesignScene(template)
    scene.add_text("hello")

    image = render_scene_to_image(scene)

    assert image.format() == QImage.Format.Format_ARGB32_Premultiplied


def test_svg_export_contains_no_print_artwork(qt_app, tmp_path):
    template = DiscTemplate(name="t", width_mm=37.0, height_mm=52.0)
    scene = DesignScene(template)
    text_item = scene.add_text("SECRET TRACKLIST")
    from PySide6.QtGui import QColor as QC

    text_item.setDefaultTextColor(QC("#123456"))  # a distinctive color that shouldn't leak into the SVG

    out = tmp_path / "cut.svg"
    export_svg(scene, out)

    svg_text = out.read_text(encoding="utf-8")
    assert "SECRET TRACKLIST" not in svg_text
    assert "#123456" not in svg_text


def test_svg_export_excludes_fold_lines_but_keeps_the_cut_outline(qt_app, tmp_path):
    template = CoverTemplate(name="cover", width_mm=145.0, height_mm=68.0, fold_offsets_mm=[68.0, 73.0])
    scene = DesignScene(template)
    assert scene.fold_items(), "test setup: template should actually have fold lines"

    out = tmp_path / "cut.svg"
    export_svg(scene, out)

    svg_text = out.read_text(encoding="utf-8")
    assert "#ff0000" in svg_text  # the cut outline's red stroke is still there
    assert "#3399ff" not in svg_text  # the fold lines' blue dashed stroke must not be
