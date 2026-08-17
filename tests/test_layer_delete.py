from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtCore import QEvent

from mdtools.canvas.scene import DesignScene
from mdtools.canvas.view import DesignView
from mdtools.panels.layers_panel import LayersPanel
from mdtools.templates.models import DiscTemplate


def test_remove_item_takes_it_out_of_the_scene(qt_app):
    scene = DesignScene(DiscTemplate(name="t", width_mm=37.0, height_mm=52.0))
    item = scene.add_text("hello")
    assert item in scene.print_items()

    scene.remove_item(item)
    assert item not in scene.items()


def test_layers_panel_emits_delete_requested_for_selected_row(qt_app):
    panel = LayersPanel()
    sentinel = object()
    panel.refresh([sentinel])
    panel.list_widget.setCurrentRow(0)

    received = []
    panel.delete_requested.connect(received.append)
    panel.delete_btn.click()

    assert received == [sentinel]


def test_delete_key_removes_selected_item_from_view(qt_app):
    scene = DesignScene(DiscTemplate(name="t", width_mm=37.0, height_mm=52.0))
    item = scene.add_text("hello")
    item.setSelected(True)
    view = DesignView(scene)

    deleted_signals = []
    view.items_deleted.connect(lambda: deleted_signals.append(True))

    event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Delete, Qt.KeyboardModifier.NoModifier)
    view.keyPressEvent(event)

    assert item not in scene.items()
    assert deleted_signals == [True]
