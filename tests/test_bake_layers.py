from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QGraphicsPixmapItem

from mdtools import app_settings
from mdtools.canvas.items import opaque_content_rect
from mdtools.canvas.scene import DesignScene
from mdtools.constants import mm_to_px
from mdtools.io.png_export import render_scene_to_image
from mdtools.templates.models import DiscTemplate


def _scene() -> DesignScene:
    return DesignScene(DiscTemplate(name="plain", width_mm=40.0, height_mm=40.0, shape="full_label", corner_radius_mm=0.0))


def test_baking_an_empty_scene_is_a_no_op(qt_app):
    scene = _scene()
    image = render_scene_to_image(scene)

    old_items, new_item = scene.plan_bake_layers(image)

    assert old_items == []
    assert new_item is None


def test_bake_flattens_every_layer_into_one_pixmap_item_matching_the_scene_rect(qt_app):
    scene = _scene()
    rect = scene.add_rectangle()
    brush = rect.brush()
    brush.setColor(QColor("blue"))
    rect.setBrush(brush)
    pen = rect.pen()
    pen.setColor(QColor("blue"))
    rect.setPen(pen)
    rect.setPos(mm_to_px(5), mm_to_px(5))
    text = scene.add_text("hi")
    text.setPos(mm_to_px(25), mm_to_px(25))

    image = render_scene_to_image(scene)
    old_items, new_item = scene.plan_bake_layers(image)

    assert set(old_items) == {text, rect}
    assert isinstance(new_item, QGraphicsPixmapItem)

    scene_rect = scene.sceneRect()
    new_bounds = new_item.sceneTransform().mapRect(new_item.boundingRect())
    assert abs(new_bounds.width() - scene_rect.width()) < 1.0
    assert abs(new_bounds.height() - scene_rect.height()) < 1.0
    assert abs(new_bounds.left() - scene_rect.left()) < 1.0
    assert abs(new_bounds.top() - scene_rect.top()) < 1.0


def test_bake_repivots_rotation_to_the_visible_content_not_the_whole_page(qt_app):
    """Same fix as Clip Layers' rectangle rasterization: a small rectangle
    baked onto an otherwise-empty page must pivot rotate/scale around its
    own visible content, not the page's (mostly transparent) center."""
    scene = _scene()
    rect = scene.add_rectangle()
    brush = rect.brush()
    brush.setColor(QColor("blue"))
    rect.setBrush(brush)
    pen = rect.pen()
    pen.setColor(QColor("blue"))
    rect.setPen(pen)
    rect.setPos(mm_to_px(5), mm_to_px(5))

    image = render_scene_to_image(scene)
    _, new_item = scene.plan_bake_layers(image)

    pivot_scene = new_item.mapToScene(new_item.transformOriginPoint())
    content_center_scene = new_item.mapToScene(opaque_content_rect(new_item).center())
    page_center_scene = new_item.mapToScene(new_item.boundingRect().center())

    assert (pivot_scene - content_center_scene).manhattanLength() < 1.0
    assert (pivot_scene - page_center_scene).manhattanLength() > 1.0


def test_bake_layers_end_to_end_via_main_window_replaces_layers_and_undoes_cleanly(qt_app, tmp_path, monkeypatch):
    from mdtools.app_window import MainWindow
    from mdtools.project import PAGE_DISC
    from mdtools.templates import registry

    monkeypatch.setattr(registry, "user_templates_path", lambda: tmp_path / "templates.json")
    win = MainWindow(show_startup_dialog=False)
    win._show_page(PAGE_DISC)
    scene = win._current_scene()

    win._add_rectangle()
    win._add_text()
    before_items = list(scene.print_items())
    before_count = len(before_items)
    assert before_count >= 2

    win._bake_layers()

    after_items = scene.print_items()
    assert len(after_items) == 1
    assert isinstance(after_items[0], QGraphicsPixmapItem)
    for item in before_items:
        assert item.scene() is None
    assert win.layers_panel.list_widget.count() == 1

    win.undo_stack.undo()  # undoes only the bake macro, not the earlier adds
    restored = scene.print_items()
    assert len(restored) == before_count
    for item in before_items:
        assert item in restored
    # regression: the Layers panel widget itself must reflect the restored
    # layers, not just the underlying scene -- undo doesn't go through
    # _bake_layers() (which explicitly refreshes the panel), so this only
    # happens via the undo-stack-driven auto-refresh (see
    # MainWindow._on_undo_index_changed).
    assert win.layers_panel.list_widget.count() == before_count

    win.undo_stack.redo()
    after_redo = scene.print_items()
    assert len(after_redo) == 1
    assert isinstance(after_redo[0], QGraphicsPixmapItem)
    assert win.layers_panel.list_widget.count() == 1


def test_bake_layers_renders_at_bake_dpi_not_the_plain_export_dpi(qt_app, tmp_path, monkeypatch):
    """Regression test: baking used to render at the same default export
    DPI as a plain PNG export, which -- because a baked layer's
    resolution is locked in for good, unlike a re-renderable vector layer
    -- came out looking soft/blocky, especially for text. bake_dpi() must
    be strictly higher, and _bake_layers() must actually use it."""
    import mdtools.app_window as app_window_module

    assert app_settings.bake_dpi() > app_settings.default_export_dpi()

    from mdtools.app_window import MainWindow
    from mdtools.project import PAGE_DISC
    from mdtools.templates import registry

    monkeypatch.setattr(registry, "user_templates_path", lambda: tmp_path / "templates.json")

    seen_dpi = []
    real_render = app_window_module.render_scene_to_image

    def _spy(scene, dpi=None):
        seen_dpi.append(dpi)
        return real_render(scene, dpi)

    monkeypatch.setattr(app_window_module, "render_scene_to_image", _spy)

    win = MainWindow(show_startup_dialog=False)
    win._show_page(PAGE_DISC)
    win._add_rectangle()

    win._bake_layers()

    assert seen_dpi == [app_settings.bake_dpi()]


def test_bake_layers_does_nothing_when_page_has_no_print_layers(qt_app, tmp_path, monkeypatch):
    from mdtools.app_window import MainWindow
    from mdtools.project import PAGE_DISC
    from mdtools.templates import registry

    monkeypatch.setattr(registry, "user_templates_path", lambda: tmp_path / "templates.json")
    win = MainWindow(show_startup_dialog=False)
    win._show_page(PAGE_DISC)
    scene = win._current_scene()
    for item in list(scene.print_items()):
        scene.remove_item(item)
    assert scene.print_items() == []

    before_count = win.undo_stack.count()
    win._bake_layers()  # must not raise, must not push an undo step

    assert scene.print_items() == []
    assert win.undo_stack.count() == before_count
