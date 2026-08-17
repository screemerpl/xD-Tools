from PySide6.QtGui import QTransform
from PySide6.QtWidgets import QGraphicsEllipseItem, QGraphicsRectItem, QGraphicsTextItem

from mdtools.canvas.items import get_item_scale, set_item_scale
from mdtools.canvas.scene import DesignScene
from mdtools.constants import mm_to_px
from mdtools.templates.models import DiscTemplate


def _scene() -> DesignScene:
    return DesignScene(DiscTemplate(name="t", width_mm=37.0, height_mm=52.0))


def test_scaling_a_rectangle_resizes_its_own_geometry_not_a_transform(qt_app):
    scene = _scene()
    item = scene.add_rectangle()
    base_w, base_h = item.rect().width(), item.rect().height()

    set_item_scale(item, 2.0, 3.0)

    assert item.rect().width() == base_w * 2.0
    assert item.rect().height() == base_h * 3.0
    assert item.transform() == QTransform()  # identity -- no scale baked into a transform
    # boundingRect (rect() padded by half the pen width) reflects the real
    # size, not just the original small rect stretched by a transform
    assert abs(item.boundingRect().width() - base_w * 2.0) < 2.0


def test_scaling_an_ellipse_also_resizes_its_own_geometry(qt_app):
    scene = _scene()
    item = scene.add_ellipse()
    base_w, base_h = item.rect().width(), item.rect().height()

    set_item_scale(item, 0.5, 0.5)

    assert item.rect().width() == base_w * 0.5
    assert item.rect().height() == base_h * 0.5
    assert item.transform() == QTransform()


def test_scaling_a_rectangle_keeps_its_center_fixed_in_scene_space(qt_app):
    """Regression: rect() always starts at local (0, 0), so growing it in
    place used to keep the shape's top-left corner pinned at pos() and only
    expand toward the bottom-right, regardless of which resize handle was
    actually dragged -- a rectangle resized via a corner handle visibly
    jumped instead of growing symmetrically from its center."""
    scene = _scene()
    item = scene.add_rectangle()
    before_center = item.mapToScene(item.boundingRect().center())

    set_item_scale(item, 5.0, 3.0)

    after_center = item.mapToScene(item.boundingRect().center())
    assert (after_center - before_center).manhattanLength() < 1e-6


def test_scaling_an_ellipse_keeps_its_center_fixed_in_scene_space(qt_app):
    scene = _scene()
    item = scene.add_ellipse()
    before_center = item.mapToScene(item.boundingRect().center())

    set_item_scale(item, 0.4, 2.5)

    after_center = item.mapToScene(item.boundingRect().center())
    assert (after_center - before_center).manhattanLength() < 1e-6


def test_scaling_a_rectangle_updates_its_rotation_pivot_to_the_new_center(qt_app):
    """Regression: transformOriginPoint() (what native rotation always
    pivots around) was only ever set once, at creation -- resizing a
    rectangle left it stale at the *original* small size's center, so
    rotating an already-resized rectangle span around a point nowhere near
    its actual current center."""
    scene = _scene()
    item = scene.add_rectangle()

    set_item_scale(item, 5.0, 5.0)

    assert item.transformOriginPoint() == item.boundingRect().center()


def test_rotating_a_resized_rectangle_pivots_around_its_current_center(qt_app):
    scene = _scene()
    item = scene.add_rectangle()
    set_item_scale(item, 5.0, 5.0)
    center_before_rotation = item.mapToScene(item.transformOriginPoint())

    item.setRotation(90)

    center_after_rotation = item.mapToScene(item.transformOriginPoint())
    assert (center_after_rotation - center_before_rotation).manhattanLength() < 1e-6


def test_repeated_scaling_does_not_compound_off_the_already_resized_rect(qt_app):
    scene = _scene()
    item = scene.add_rectangle()
    base_w = item.rect().width()

    set_item_scale(item, 2.0, 1.0)
    set_item_scale(item, 3.0, 1.0)  # a later drag update, not "on top of" the 2x result

    assert item.rect().width() == base_w * 3.0


def test_get_item_scale_still_reports_the_cumulative_factor(qt_app):
    scene = _scene()
    item = scene.add_rectangle()

    set_item_scale(item, 2.0, 4.0)

    assert get_item_scale(item) == (2.0, 4.0)


def test_resetting_scale_to_one_restores_the_original_size(qt_app):
    scene = _scene()
    item = scene.add_rectangle()
    base_w, base_h = item.rect().width(), item.rect().height()

    set_item_scale(item, 5.0, 5.0)
    set_item_scale(item, 1.0, 1.0)

    assert item.rect().width() == base_w
    assert item.rect().height() == base_h


def test_text_items_are_unaffected_still_use_a_transform(qt_app):
    scene = _scene()
    item = scene.add_text("hello")
    assert isinstance(item, QGraphicsTextItem)

    set_item_scale(item, 2.0, 2.0)

    assert item.transform() != QTransform()  # text still scales via transform, as before


def test_clip_layers_rasterizes_an_enlarged_rectangle_at_full_resolution(qt_app):
    """Regression test for the reported bug: scaling a rectangle up and then
    running Tools > Clip Layers on it used to produce a blocky/pixelated
    result, because the rasterized pixmap was only ever sized for the
    original small rect and then stretched. With size baked directly into
    the rect's own geometry, the pixmap Clip Layers builds should scale up
    right along with the visible size (times DesignScene.shape_raster_supersample(),
    for print-quality resolution headroom) -- no stretching,
    no pixelation, and the on-screen footprint must still end up exactly
    the size the rectangle actually had, not that oversampled raster size."""
    template = DiscTemplate(name="plain", width_mm=200.0, height_mm=200.0, shape="full_label", corner_radius_mm=0.0)
    scene = DesignScene(template)
    item = scene.add_rectangle()  # 20mm x 14mm
    base_w, base_h = item.rect().width(), item.rect().height()

    scale_factor = 5.0
    set_item_scale(item, scale_factor, scale_factor)
    expected_bounds = item.boundingRect()  # captured post-scale, pen padding included
    # straddle the printable area's edge so Clip Layers treats it as
    # partially outside and rasterizes it
    item.setPos(mm_to_px(190), mm_to_px(5))
    expected_center = item.mapToScene(expected_bounds.center())

    items_to_remove, images_to_reclip, shapes_to_rasterize = scene.plan_clip_layers()

    assert items_to_remove == []
    assert len(shapes_to_rasterize) == 1
    _, new_item = shapes_to_rasterize[0]
    pixmap = new_item.pixmap()

    factor = DesignScene.shape_raster_supersample()
    # the pixmap must be sized for the *enlarged* rectangle (times the
    # supersample factor), not the original small one -- this is what keeps
    # the print resolution (pixels per mm) constant regardless of how much
    # it was scaled up, plus the extra headroom over screen (96dpi) scale
    assert pixmap.width() == round(expected_bounds.width() * factor)
    assert pixmap.height() == round(expected_bounds.height() * factor)
    assert pixmap.width() > round(base_w * 2)  # sanity: nowhere near the tiny original size

    # despite the backing raster being bigger, the replacement item must
    # still occupy exactly the same on-screen footprint the rectangle had
    new_bounds_scene = new_item.sceneTransform().mapRect(new_item.boundingRect())
    assert abs(new_bounds_scene.width() - expected_bounds.width()) < 1.0
    assert abs(new_bounds_scene.height() - expected_bounds.height()) < 1.0
    new_center = new_item.mapToScene(new_item.boundingRect().center())
    assert (new_center - expected_center).manhattanLength() < 0.01
