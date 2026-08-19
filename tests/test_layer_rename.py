from mdtools.canvas.items import get_item_name, set_item_name
from mdtools.canvas.scene import DesignScene
from mdtools.panels.layers_panel import LayersPanel, _label_for
from mdtools.templates.models import DiscTemplate


def test_get_and_set_item_name_round_trip(qt_app):
    scene = DesignScene(DiscTemplate(name="t", width_mm=37.0, height_mm=52.0))
    item = scene.add_text("hello")

    assert get_item_name(item) is None
    set_item_name(item, "Title")
    assert get_item_name(item) == "Title"


def test_setting_an_empty_name_clears_it_back_to_none(qt_app):
    scene = DesignScene(DiscTemplate(name="t", width_mm=37.0, height_mm=52.0))
    item = scene.add_text("hello")

    set_item_name(item, "Title")
    set_item_name(item, "   ")
    assert get_item_name(item) is None


def test_label_for_prefers_a_custom_name_over_the_auto_generated_one(qt_app):
    scene = DesignScene(DiscTemplate(name="t", width_mm=37.0, height_mm=52.0))
    item = scene.add_text("hello world")

    assert _label_for(item) == "Text: hello world"
    set_item_name(item, "Background")
    assert _label_for(item) == "Background"


def test_label_for_tolerates_plain_sentinel_objects(qt_app):
    # LayersPanel signal-wiring tests refresh() with plain objects, not real
    # QGraphicsItems -- _label_for must not crash trying to read a name off
    # something with no .data() method.
    sentinel = object()
    assert _label_for(sentinel) == "object"


def test_layers_panel_emits_rename_requested_for_selected_row(qt_app):
    panel = LayersPanel()
    sentinel = object()
    panel.refresh([sentinel])
    panel.list_widget.setCurrentRow(0)

    received = []
    panel.rename_requested.connect(received.append)
    panel.rename_btn.click()

    assert received == [sentinel]


def test_rename_button_disabled_until_a_row_is_selected(qt_app):
    panel = LayersPanel()
    sentinel = object()
    panel.refresh([sentinel])

    assert not panel.rename_btn.isEnabled()
    panel.list_widget.setCurrentRow(0)
    assert panel.rename_btn.isEnabled()


def test_rename_layer_end_to_end_via_main_window_is_undoable(qt_app, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    from mdtools.app_window import MainWindow
    from mdtools.project import PAGE_DISC
    from mdtools.templates import registry

    monkeypatch.setattr(registry, "user_templates_path", lambda: tmp_path / "templates.json")
    win = MainWindow(show_startup_dialog=False)
    win._show_page(PAGE_DISC)
    scene = win._current_scene()
    win._add_rectangle()
    from PySide6.QtWidgets import QGraphicsRectItem

    item = next(i for i in scene.print_items() if isinstance(i, QGraphicsRectItem))

    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("Background", True)))
    win._rename_item(item)
    assert get_item_name(item) == "Background"

    win.undo_stack.undo()
    assert get_item_name(item) is None

    win.undo_stack.redo()
    assert get_item_name(item) == "Background"


def test_rename_layer_cancelled_dialog_leaves_name_unchanged(qt_app, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QGraphicsRectItem, QInputDialog

    from mdtools.app_window import MainWindow
    from mdtools.project import PAGE_DISC
    from mdtools.templates import registry

    monkeypatch.setattr(registry, "user_templates_path", lambda: tmp_path / "templates.json")
    win = MainWindow(show_startup_dialog=False)
    win._show_page(PAGE_DISC)
    scene = win._current_scene()
    win._add_rectangle()
    item = next(i for i in scene.print_items() if isinstance(i, QGraphicsRectItem))

    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("Ignored", False)))
    before_count = win.undo_stack.count()
    win._rename_item(item)

    assert get_item_name(item) is None
    assert win.undo_stack.count() == before_count


def test_layers_are_named_after_what_they_are_not_their_class(qt_app):
    """They read as "DesignPixmap" once: the fallback stripped
    "QGraphics"/"Item" off the type name, which stopped working when these
    became Design*Item subclasses (see canvas/items.py)."""
    from pathlib import Path

    from mdtools.canvas.scene import DesignScene
    from mdtools.panels.layers_panel import _label_for
    from mdtools.templates.models import DiscTemplate

    scene = DesignScene(DiscTemplate(name="t", width_mm=37.0, height_mm=52.0))

    assert _label_for(scene.add_rectangle()) == "Rectangle"
    assert _label_for(scene.add_ellipse()) == "Ellipse"
    assert _label_for(scene.add_image(str(Path("assets/img/mdlogo.png")))) == "Image"
    assert "Design" not in _label_for(scene.add_rectangle())
