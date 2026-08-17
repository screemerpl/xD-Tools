from mdtools.app_window import MainWindow
from mdtools.project import PAGE_DISC


def test_selecting_item_on_canvas_syncs_layers_panel_for_move_buttons(qt_app):
    win = MainWindow(show_startup_dialog=False)
    scene = win.project.pages[PAGE_DISC]
    first = scene.add_text("first")
    second = scene.add_rectangle()
    win._refresh_layers()

    # simulate clicking the item directly on the canvas (not via the Layers
    # panel list) -- this is the scenario that used to leave the Layers
    # panel's selection stale, so Move Up/Down acted on the wrong item.
    scene.clearSelection()
    first.setSelected(True)

    assert win.layers_panel.move_up_btn.isEnabled()
    win.layers_panel.move_up_btn.click()

    # 'first' and 'second' were the two topmost items (newest-added-on-top);
    # a new disc page also seeds its own arrow/label text underneath them,
    # so check their relative order rather than the whole list.
    ordered = scene.print_items()
    assert ordered[:2] == [first, second]
