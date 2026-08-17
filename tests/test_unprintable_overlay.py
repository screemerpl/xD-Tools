from PySide6.QtCore import QPointF

from mdtools.canvas.scene import DesignScene
from mdtools.canvas.view import DesignView
from mdtools.constants import mm_to_px
from mdtools.templates.models import CoverTemplate, DiscTemplate


def test_unprintable_area_excludes_the_inside_of_the_template(qt_app):
    scene = DesignScene(DiscTemplate(name="t", width_mm=37.0, height_mm=52.0))
    view = DesignView(scene)

    unprintable = view._unprintable_area_path()
    inside_point = QPointF(mm_to_px(18), mm_to_px(26))  # deep inside the 37x52mm template
    assert not unprintable.contains(inside_point)


def test_unprintable_area_covers_the_margin_outside_the_template(qt_app):
    scene = DesignScene(DiscTemplate(name="t", width_mm=37.0, height_mm=52.0))
    view = DesignView(scene)

    unprintable = view._unprintable_area_path()
    # just outside the template, within the scene's own margin
    outside_point = QPointF(-5, -5)
    assert unprintable.contains(outside_point)


def test_unprintable_area_includes_the_cover_cutout_hole(qt_app):
    template = CoverTemplate(
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
    scene = DesignScene(template)
    view = DesignView(scene)

    unprintable = view._unprintable_area_path()
    cutout_center = QPointF(mm_to_px((8.55 + 48.55) / 2), mm_to_px((29.55 + 69.55) / 2))
    assert unprintable.contains(cutout_center)

    elsewhere_in_panel = QPointF(mm_to_px(5), mm_to_px(5))
    assert not unprintable.contains(elsewhere_in_panel)


def test_overlay_paints_without_error_when_nothing_selected(qt_app):
    from PySide6.QtGui import QImage, QPainter

    scene = DesignScene(DiscTemplate(name="t", width_mm=37.0, height_mm=52.0))
    view = DesignView(scene)
    view.resize(300, 300)

    image = QImage(300, 300, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    try:
        view._draw_unprintable_area_overlay(painter)
    finally:
        painter.end()
