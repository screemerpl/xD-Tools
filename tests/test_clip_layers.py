from PySide6.QtWidgets import QGraphicsPixmapItem, QGraphicsRectItem

from mdtools.canvas.items import opaque_content_rect
from mdtools.canvas.scene import DesignScene
from mdtools.constants import mm_to_px
from mdtools.templates.models import DiscTemplate


def _plain_square(size_mm: float = 40.0) -> DiscTemplate:
    """A trivial axis-aligned printable square (no chamfer/fillet/notch),
    so overlap math in these tests doesn't need to account for rounded
    corners."""
    return DiscTemplate(name="plain", width_mm=size_mm, height_mm=size_mm, shape="full_label", corner_radius_mm=0.0)


def _solid_pixmap(size: int, color: str):
    from PySide6.QtGui import QColor, QImage, QPixmap

    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(QColor(color))
    return QPixmap.fromImage(image)


def test_item_entirely_outside_is_marked_for_removal(qt_app):
    scene = DesignScene(_plain_square())
    item = scene.add_rectangle()
    item.setPos(mm_to_px(100), mm_to_px(100))  # nowhere near the 0..40mm square

    items_to_remove, images_to_reclip, shapes_to_rasterize = scene.plan_clip_layers()

    assert item in items_to_remove
    assert images_to_reclip == []
    assert shapes_to_rasterize == []


def test_item_entirely_inside_is_left_untouched(qt_app):
    scene = DesignScene(_plain_square())
    item = scene.add_rectangle()
    item.setPos(mm_to_px(5), mm_to_px(5))  # 20x14mm rect, fully inside 0..40mm

    items_to_remove, images_to_reclip, shapes_to_rasterize = scene.plan_clip_layers()

    assert item not in items_to_remove
    assert not any(pair[0] is item for pair in images_to_reclip)
    assert not any(pair[0] is item for pair in shapes_to_rasterize)


def test_text_partially_outside_is_left_untouched(qt_app):
    scene = DesignScene(_plain_square())
    item = scene.add_text("hello")
    item.setPos(mm_to_px(35), mm_to_px(35))  # straddles the 40mm edge

    items_to_remove, images_to_reclip, shapes_to_rasterize = scene.plan_clip_layers()

    assert item not in items_to_remove
    assert images_to_reclip == []
    assert shapes_to_rasterize == []


def test_image_partially_outside_is_reclipped_in_place(qt_app):
    scene = DesignScene(_plain_square())
    # sized in raw pixels to match 20mm of scene units (1 scene unit == 1
    # pixmap pixel for an unscaled QGraphicsPixmapItem), so mm-based offsets
    # below land at the same pixel offsets within the pixmap itself
    item = scene.add_image_from_data(_pixmap_bytes(_solid_pixmap(round(mm_to_px(20)), "green")))
    item.setPos(mm_to_px(30), mm_to_px(30))  # straddles the 40mm right/bottom edge

    items_to_remove, images_to_reclip, shapes_to_rasterize = scene.plan_clip_layers()

    assert items_to_remove == []
    assert shapes_to_rasterize == []
    assert len(images_to_reclip) == 1
    reclipped_item, new_pixmap = images_to_reclip[0]
    assert reclipped_item is item

    image = new_pixmap.toImage()
    # local (5, 5) -> scene (35, 35): inside the 40mm square
    inside = image.pixelColor(round(mm_to_px(5)), round(mm_to_px(5)))
    assert inside.alpha() > 0
    # local (15, 15) -> scene (45, 45): outside the 40mm square
    outside = image.pixelColor(round(mm_to_px(15)), round(mm_to_px(15)))
    assert outside.alpha() == 0


def test_rectangle_partially_outside_is_rasterized_into_a_replacement_pixmap_item(qt_app):
    scene = DesignScene(_plain_square())
    item = scene.add_rectangle()  # 20mm x 14mm
    item.setPos(mm_to_px(30), mm_to_px(30))  # straddles the 40mm right/bottom edge
    item.setZValue(3.5)

    items_to_remove, images_to_reclip, shapes_to_rasterize = scene.plan_clip_layers()

    assert items_to_remove == []
    assert images_to_reclip == []
    assert len(shapes_to_rasterize) == 1
    old_item, new_item = shapes_to_rasterize[0]
    assert old_item is item
    assert isinstance(new_item, QGraphicsPixmapItem)
    # the replacement's backing pixmap is oversampled (see
    # DesignScene.shape_raster_supersample()) and displayed back down via
    # scale, so its own pos() differs from item's -- what must line up is
    # where the two items' *centers* land in scene space.
    old_center = item.mapToScene(item.boundingRect().center())
    new_center = new_item.mapToScene(new_item.boundingRect().center())
    assert (new_center - old_center).manhattanLength() < 0.01
    assert new_item.rotation() == item.rotation()
    assert new_item.zValue() == item.zValue()

    factor = DesignScene.shape_raster_supersample()
    image = new_item.pixmap().toImage()
    # local (5, 5) -> scene (35, 35): inside both the rectangle and the square
    inside = image.pixelColor(round(mm_to_px(5) * factor), round(mm_to_px(5) * factor))
    assert inside.alpha() > 0
    # local (15, 5) -> scene (45, 35): inside the rectangle's own bounds but
    # outside the printable square
    outside = image.pixelColor(round(mm_to_px(15) * factor), round(mm_to_px(5) * factor))
    assert outside.alpha() == 0


def test_rasterizing_a_rectangle_repivots_rotation_to_its_visible_content(qt_app):
    """Regression: the replacement pixmap's rotate/scale pivot used to stay
    anchored at the *old, full pre-clip* boundingRect's center -- mostly
    empty space once clipped -- so rotating a clipped rectangle visibly
    swung it around a point nowhere near what was actually left on screen."""
    scene = DesignScene(_plain_square())
    item = scene.add_rectangle()
    item.setPos(mm_to_px(30), mm_to_px(30))  # straddles the 40mm right/bottom edge

    _, _, shapes_to_rasterize = scene.plan_clip_layers()
    _, new_item = shapes_to_rasterize[0]

    pivot_scene = new_item.mapToScene(new_item.transformOriginPoint())
    content_center_scene = new_item.mapToScene(opaque_content_rect(new_item).center())
    full_bounds_center_scene = new_item.mapToScene(new_item.boundingRect().center())

    assert (pivot_scene - content_center_scene).manhattanLength() < 0.01
    # sanity: the visible content's center is NOT the same as the full
    # (mostly transparent) pixmap's center -- otherwise this test wouldn't
    # actually be exercising the fix
    assert (pivot_scene - full_bounds_center_scene).manhattanLength() > 1.0


def test_rasterizing_a_rectangle_still_renders_in_the_same_place_after_repivoting(qt_app):
    """The repivot must not shift any already-correctly-placed pixels --
    only where future rotate/scale operations pivot around."""
    scene = DesignScene(_plain_square())
    item = scene.add_rectangle()
    item.setPos(mm_to_px(30), mm_to_px(30))
    expected_center = item.mapToScene(item.boundingRect().center())

    _, _, shapes_to_rasterize = scene.plan_clip_layers()
    _, new_item = shapes_to_rasterize[0]

    actual_center = new_item.mapToScene(new_item.boundingRect().center())
    assert (actual_center - expected_center).manhattanLength() < 0.01


def test_rasterizing_a_selected_rectangle_keeps_it_selected(qt_app):
    """Regression: clipping an image keeps its selection for free
    (SetPixmapCommand swaps the pixmap on the *same* item), but rasterizing
    a rectangle replaces it with a brand new item -- without carrying the
    selected flag over explicitly, a selected rectangle silently lost its
    selection (and so its selection frame) the moment Clip Layers ran."""
    scene = DesignScene(_plain_square())
    item = scene.add_rectangle()
    item.setPos(mm_to_px(30), mm_to_px(30))
    item.setSelected(True)

    _, _, shapes_to_rasterize = scene.plan_clip_layers()

    _, new_item = shapes_to_rasterize[0]
    assert new_item.isSelected()


def test_rasterizing_an_unselected_rectangle_stays_unselected(qt_app):
    scene = DesignScene(_plain_square())
    item = scene.add_rectangle()
    item.setPos(mm_to_px(30), mm_to_px(30))

    _, _, shapes_to_rasterize = scene.plan_clip_layers()

    _, new_item = shapes_to_rasterize[0]
    assert not new_item.isSelected()


def _pixmap_bytes(pixmap) -> bytes:
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice

    buffer = QByteArray()
    device = QBuffer(buffer)
    device.open(QIODevice.OpenModeFlag.WriteOnly)
    pixmap.save(device, "PNG")
    device.close()
    return bytes(buffer)


def test_clip_layers_removes_items_entirely_outside_as_one_undo_step(qt_app, tmp_path, monkeypatch):
    from mdtools.app_window import MainWindow
    from mdtools.project import PAGE_DISC
    from mdtools.templates import registry

    monkeypatch.setattr(registry, "user_templates_path", lambda: tmp_path / "templates.json")
    win = MainWindow(show_startup_dialog=False)
    win._show_page(PAGE_DISC)
    scene = win._current_scene()
    before_count = len(scene.print_items())

    win._add_rectangle()
    item = next(i for i in scene.print_items() if isinstance(i, QGraphicsRectItem))
    item.setPos(mm_to_px(1000), mm_to_px(1000))  # nowhere near the disc

    win._clip_layers()
    assert item.scene() is None
    assert len(scene.print_items()) == before_count

    win.undo_stack.undo()  # undoes only the clip-layers macro, not the earlier add
    assert item.scene() is scene
    assert len(scene.print_items()) == before_count + 1


def test_clip_layers_rasterizes_a_partially_outside_rectangle_as_one_undo_step(qt_app, tmp_path, monkeypatch):
    from mdtools.app_window import MainWindow
    from mdtools.project import PAGE_DISC
    from mdtools.templates import registry

    monkeypatch.setattr(registry, "user_templates_path", lambda: tmp_path / "templates.json")
    win = MainWindow(show_startup_dialog=False)
    win._show_page(PAGE_DISC)
    scene = win._current_scene()

    win._add_rectangle()
    rect_item = next(i for i in scene.print_items() if isinstance(i, QGraphicsRectItem))
    # the built-in disc is 37mm wide -- this straddles its right edge
    rect_item.setPos(mm_to_px(30), mm_to_px(5))

    win._clip_layers()
    assert rect_item.scene() is None
    new_item = next(i for i in scene.print_items() if isinstance(i, QGraphicsPixmapItem))

    win.undo_stack.undo()  # single step: restores the rectangle, removes the pixmap stand-in
    assert rect_item.scene() is scene
    assert new_item.scene() is None
