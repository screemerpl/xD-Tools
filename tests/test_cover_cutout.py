from PySide6.QtCore import QPointF

from mdtools.canvas.scene import DesignScene
from mdtools.constants import mm_to_px
from mdtools.templates.models import CoverTemplate


def _template_with_cutout(**overrides) -> CoverTemplate:
    defaults = dict(
        name="cover",
        width_mm=126.0,
        height_mm=73.0,
        corner_radius_mm=2.0,
        fold_offsets_mm=[58.85, 67.15],
        cutout_width_mm=40.0,
        cutout_height_mm=40.0,
        cutout_radius_mm=1.0,
        cutout_from_fold_mm=10.3,
        cutout_from_bottom_mm=3.45,
        cutout_side="left",
    )
    defaults.update(overrides)
    return CoverTemplate(**defaults)


def test_cutout_is_a_hole_in_the_cut_outline(qt_app):
    scene = DesignScene(_template_with_cutout())
    outline_path = scene.cut_only_items()[0].path()

    # center of the cutout (computed from the spec: right edge = left fold
    # (58.85) - 10.3 = 48.55; left edge = 48.55 - 40 = 8.55; bottom edge =
    # height (73) - 3.45 = 69.55; top edge = 69.55 - 40 = 29.55)
    cutout_center = QPointF(mm_to_px((8.55 + 48.55) / 2), mm_to_px((29.55 + 69.55) / 2))
    assert not outline_path.contains(cutout_center)

    # a point elsewhere in the left panel, well clear of the cutout
    elsewhere = QPointF(mm_to_px(5), mm_to_px(5))
    assert outline_path.contains(elsewhere)


def test_cutout_side_right_mirrors_it_across_the_right_fold(qt_app):
    scene = DesignScene(_template_with_cutout(cutout_side="right"))
    outline_path = scene.cut_only_items()[0].path()

    # right fold at 67.15; cutout's left edge = 67.15 + 10.3 = 77.45,
    # right edge = 77.45 + 40 = 117.45 -- the mirror image of the left-side
    # placement (8.55..48.55) across the template's center (63mm).
    cutout_center = QPointF(mm_to_px((77.45 + 117.45) / 2), mm_to_px((29.55 + 69.55) / 2))
    assert not outline_path.contains(cutout_center)

    # the old left-side cutout position should now be solid material
    old_left_side_center = QPointF(mm_to_px((8.55 + 48.55) / 2), mm_to_px((29.55 + 69.55) / 2))
    assert outline_path.contains(old_left_side_center)


def test_no_cutout_when_dimensions_are_zero(qt_app):
    scene = DesignScene(_template_with_cutout(cutout_width_mm=0.0, cutout_height_mm=0.0))
    outline_path = scene.cut_only_items()[0].path()

    cutout_center = QPointF(mm_to_px((8.55 + 48.55) / 2), mm_to_px((29.55 + 69.55) / 2))
    assert outline_path.contains(cutout_center)  # no hole -- should be solid material there


def test_png_export_is_transparent_over_the_cutout(qt_app, tmp_path):
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice
    from PySide6.QtGui import QColor, QImage

    from mdtools.io.png_export import export_png

    def solid_png(size, color):
        image = QImage(size, size, QImage.Format.Format_ARGB32)
        image.fill(QColor(color))
        buffer = QByteArray()
        device = QBuffer(buffer)
        device.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(device, "PNG")
        device.close()
        return bytes(buffer)

    scene = DesignScene(_template_with_cutout())
    image_item = scene.add_image_from_data(solid_png(60, "green"))
    image_item.setPos(mm_to_px(8.55), mm_to_px(29.55))  # covers the whole cutout area

    out = tmp_path / "cutout.png"
    export_png(scene, out, dpi=96)  # dpi == SCREEN_DPI => 1 scene unit == 1 image pixel

    result = QImage(str(out))
    rect = scene.sceneRect()
    cutout_center_x = mm_to_px((8.55 + 48.55) / 2) - rect.left()
    cutout_center_y = mm_to_px((29.55 + 69.55) / 2) - rect.top()
    assert result.pixelColor(round(cutout_center_x), round(cutout_center_y)).alpha() == 0
