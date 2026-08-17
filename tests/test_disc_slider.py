from PySide6.QtCore import QPointF

from mdtools.canvas.scene import DesignScene
from mdtools.constants import mm_to_px
from mdtools.templates.models import DiscTemplate


def _disc_with_slider(**overrides) -> DiscTemplate:
    defaults = dict(
        name="disc",
        width_mm=37.0,
        height_mm=52.0,
        chamfer_mm=3.0,
        fillet_mm=1.0,
        slider_width_mm=27.5,
        slider_height_mm=17.5,
        slider_corner_radius_mm=2.5,
        slider_gap_mm=3.0,
    )
    defaults.update(overrides)
    return DiscTemplate(**defaults)


def test_no_slider_shape_when_dimensions_are_zero(qt_app):
    scene = DesignScene(_disc_with_slider(slider_width_mm=0.0, slider_height_mm=0.0))
    assert len(scene.cut_only_items()) == 1


def test_slider_adds_a_second_independent_cut_shape(qt_app):
    scene = DesignScene(_disc_with_slider())
    assert len(scene.cut_only_items()) == 2


def test_slider_is_positioned_to_the_right_of_the_disc_and_vertically_centered(qt_app):
    scene = DesignScene(_disc_with_slider())
    # scene.cut_only_items() (backed by QGraphicsScene.items()) doesn't
    # preserve insertion order for items tied at the same z-value (both
    # outline shapes are) -- _outline_items is a plain Python list, so it's
    # reliably [disc, slider] in the order _build_disc_outline appended them.
    disc_path, slider_path = (i.path() for i in scene._outline_items)

    disc_w, disc_h = mm_to_px(37.0), mm_to_px(52.0)
    slider_w, slider_h = mm_to_px(27.5), mm_to_px(17.5)
    gap = mm_to_px(3.0)

    slider_center = QPointF(disc_w + gap + slider_w / 2, (disc_h - slider_h) / 2 + slider_h / 2)
    assert slider_path.contains(slider_center)
    assert not disc_path.contains(slider_center)


def test_scene_rect_expands_to_include_the_slider(qt_app):
    scene = DesignScene(_disc_with_slider())
    without_slider = DesignScene(_disc_with_slider(slider_width_mm=0.0, slider_height_mm=0.0))
    assert scene.sceneRect().width() > without_slider.sceneRect().width()
    assert scene.sceneRect().height() == without_slider.sceneRect().height()


def test_template_clip_path_covers_both_shapes(qt_app):
    scene = DesignScene(_disc_with_slider())
    clip = scene.template_clip_path()

    disc_center = QPointF(mm_to_px(18.5), mm_to_px(26))  # roughly mid-disc, avoiding the corners
    slider_center = QPointF(mm_to_px(37 + 3 + 27.5 / 2), mm_to_px(52 / 2))
    gap_point = QPointF(mm_to_px(37 + 1.5), mm_to_px(26))  # in the gap between the two shapes

    assert clip.contains(disc_center)
    assert clip.contains(slider_center)
    assert not clip.contains(gap_point)


def test_seed_disc_defaults_centers_on_the_disc_not_the_whole_canvas(qt_app):
    scene = DesignScene(_disc_with_slider())
    scene.seed_disc_defaults()

    disc_center_x = mm_to_px(37.0) / 2
    for item in scene.print_items():
        item_center_x = item.pos().x() + item.boundingRect().width() / 2
        assert abs(item_center_x - disc_center_x) < 0.5


def test_svg_export_includes_both_cut_shapes(qt_app, tmp_path):
    from mdtools.io.svg_export import export_svg

    scene = DesignScene(_disc_with_slider())
    out = tmp_path / "disc_slider.svg"
    export_svg(scene, out)

    svg_text = out.read_text(encoding="utf-8")
    # both shapes share the same cut-outline styling (red stroke); a rough
    # proxy for "two separate paths were drawn" is two <path elements.
    assert svg_text.count("<path") >= 2


def test_png_export_is_printable_in_the_slider_area(qt_app, tmp_path):
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

    scene = DesignScene(_disc_with_slider())
    image_item = scene.add_image_from_data(solid_png(20, "green"))
    slider_x_mm, slider_y_mm = 37 + 3 + 5, 52 / 2 - 5  # comfortably inside the slider shape
    image_item.setPos(mm_to_px(slider_x_mm), mm_to_px(slider_y_mm))

    out = tmp_path / "slider.png"
    export_png(scene, out, dpi=96)  # dpi == SCREEN_DPI => 1 scene unit == 1 image pixel

    result = QImage(str(out))
    rect = scene.sceneRect()
    x = round(mm_to_px(slider_x_mm + 2.5) - rect.left())
    y = round(mm_to_px(slider_y_mm + 2.5) - rect.top())
    assert result.pixelColor(x, y).alpha() > 0
