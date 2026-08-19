from PySide6.QtCore import QPointF

from mdtools.app_window import MainWindow
from mdtools.canvas.items import get_item_scale
from mdtools.project import PAGE_COVER

# The cover page starts genuinely empty (unlike the disc page, which
# auto-seeds an "INSERT THIS END" arrow+label on every new project), so
# tests use it as a blank canvas rather than asserting against print_items()
# counts that would otherwise include those seeded items.


def _win() -> MainWindow:
    win = MainWindow(show_startup_dialog=False)
    win._show_page(PAGE_COVER)
    return win


def test_add_text_is_undoable(qt_app):
    win = _win()
    scene = win._current_scene()
    assert scene.print_items() == []

    win._add_text()
    assert len(scene.print_items()) == 1

    win.undo_stack.undo()
    assert scene.print_items() == []

    win.undo_stack.redo()
    assert len(scene.print_items()) == 1


def test_add_rectangle_is_undoable(qt_app):
    win = _win()
    scene = win._current_scene()

    win._add_rectangle()
    assert len(scene.print_items()) == 1

    win.undo_stack.undo()
    assert scene.print_items() == []


def test_delete_via_layers_panel_is_undoable(qt_app):
    win = _win()
    scene = win._current_scene()
    win._add_text()
    item = scene.print_items()[0]

    win._delete_item(item)
    assert scene.print_items() == []

    win.undo_stack.undo()
    assert scene.print_items() == [item]


def test_delete_key_on_canvas_is_undoable(qt_app):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QKeyEvent

    win = _win()
    scene = win._current_scene()
    win._add_text()
    item = scene.print_items()[0]
    item.setSelected(True)

    event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Delete, Qt.KeyboardModifier.NoModifier)
    win.view.keyPressEvent(event)
    assert scene.print_items() == []

    win.undo_stack.undo()
    assert scene.print_items() == [item]


def test_move_up_and_down_are_undoable(qt_app):
    win = _win()
    scene = win._current_scene()
    win._add_text()
    first = scene.print_items()[0]
    win._add_rectangle()
    second = scene.print_items()[0]
    assert scene.print_items() == [second, first]

    win._move_item_up(first)
    assert scene.print_items() == [first, second]

    win.undo_stack.undo()
    assert scene.print_items() == [second, first]

    win.undo_stack.redo()
    assert scene.print_items() == [first, second]


def test_canvas_rotate_drag_is_undoable(qt_app):
    win = _win()
    scene = win._current_scene()
    win._add_rectangle()
    item = scene.print_items()[0]
    item.setSelected(True)

    view = win.view
    _, rotate_handle, origin = view._handle_geometry(item)
    view._begin_drag("rotate", item, rotate_handle)
    vec = rotate_handle - origin
    view._update_drag(origin + QPointF(-vec.y(), vec.x()))  # rotate 90 degrees
    view._commit_drag_command()

    assert abs(item.rotation() - 90) < 1.0

    win.undo_stack.undo()
    assert item.rotation() == 0


def test_canvas_scale_drag_is_undoable(qt_app):
    win = _win()
    scene = win._current_scene()
    win._add_rectangle()
    item = scene.print_items()[0]
    item.setSelected(True)

    view = win.view
    corners, _, origin = view._handle_geometry(item)
    corner = corners[2]
    view._begin_drag("scale", item, corner)
    view._update_drag(origin + (corner - origin) * 2, constrained=True)
    view._commit_drag_command()

    sx, sy = get_item_scale(item)
    assert sx > 1.5 and sy > 1.5

    win.undo_stack.undo()
    assert get_item_scale(item) == (1.0, 1.0)


def test_native_drag_move_is_undoable(qt_app):
    """Native click-and-drag move (QGraphicsItem's own ItemIsMovable
    dragging, handled by Qt's default mouse handling rather than our custom
    handle-drag code) is captured via DesignView._pre_move_positions /
    _commit_native_move_command -- see mousePressEvent/mouseReleaseEvent."""
    win = _win()
    scene = win._current_scene()
    win._add_rectangle()
    item = scene.print_items()[0]
    item.setSelected(True)
    original = (item.x(), item.y())

    view = win.view
    view._pre_move_positions = {item: original}
    item.setPos(original[0] + 50, original[1] + 30)
    view._commit_native_move_command()

    assert original != (item.x(), item.y())
    win.undo_stack.undo()
    assert original == (item.x(), item.y())


def test_two_separate_native_drags_are_each_independently_undoable(qt_app):
    """Regression: two separate, completed mouse drags (pick up, drop, pick
    up again, drop again) used to silently merge into a single undo step
    whenever nothing else got pushed onto the stack in between -- a single
    Ctrl+Z after both drags jumped all the way back past *both* of them,
    with no way to undo just the second one."""
    win = _win()
    scene = win._current_scene()
    win._add_rectangle()
    item = scene.print_items()[0]
    item.setSelected(True)
    view = win.view
    original = (item.x(), item.y())

    view._pre_move_positions = {item: original}
    item.setPos(original[0] + 50, original[1] + 30)
    view._commit_native_move_command()
    after_first_drag = (item.x(), item.y())

    view._pre_move_positions = {item: after_first_drag}
    item.setPos(after_first_drag[0] + 100, after_first_drag[1] + 5)
    view._commit_native_move_command()

    win.undo_stack.undo()
    assert after_first_drag == (item.x(), item.y())  # only the second drag undone

    win.undo_stack.undo()
    assert original == (item.x(), item.y())  # now the first drag too


def test_two_separate_arrow_key_taps_are_each_independently_undoable(qt_app):
    """Same regression as the mouse-drag case above, but for two separate,
    non-held taps of an arrow key (not an OS auto-repeat burst)."""
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent

    win = _win()
    scene = win._current_scene()
    win._add_rectangle()
    item = scene.print_items()[0]
    item.setSelected(True)
    view = win.view
    original = (item.x(), item.y())

    def fresh_tap():
        event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Right, Qt.KeyboardModifier.NoModifier, "", False, 1)
        view._nudge_selected([item], (1, 0), event)

    fresh_tap()
    after_first_tap = (item.x(), item.y())
    fresh_tap()
    after_second_tap = (item.x(), item.y())
    assert after_first_tap != after_second_tap != original

    win.undo_stack.undo()
    assert after_first_tap == (item.x(), item.y())

    win.undo_stack.undo()
    assert original == (item.x(), item.y())


def test_held_arrow_key_repeats_still_merge_into_one_undo_step(qt_app):
    """The intended, still-preserved behavior: a genuine OS auto-repeat
    burst of the same held key collapses into a single undo step."""
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent

    win = _win()
    scene = win._current_scene()
    win._add_rectangle()
    item = scene.print_items()[0]
    item.setSelected(True)
    view = win.view
    original = (item.x(), item.y())

    def press(autorep):
        event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Right, Qt.KeyboardModifier.NoModifier, "", autorep, 1)
        view._nudge_selected([item], (1, 0), event)

    stack_size_before = win.undo_stack.count()
    press(False)  # the initial (non-repeat) press that starts the hold
    press(True)  # OS auto-repeat while still held
    press(True)
    press(True)

    assert (item.x(), item.y()) != original
    assert win.undo_stack.count() == stack_size_before + 1  # one entry for the whole hold

    win.undo_stack.undo()
    assert original == (item.x(), item.y())


def test_properties_panel_position_edit_is_undoable_and_coalesces(qt_app):
    win = _win()
    scene = win._current_scene()
    win._add_rectangle()
    item = scene.print_items()[0]

    win.properties_panel.set_item(item)
    original_x = item.x()

    stack_size_after_add = win.undo_stack.count()

    # simulate several ticks of dragging the X spinbox -- should coalesce
    # into a single undo step, not one per tick.
    win.properties_panel.x_spin.setValue(10)
    win.properties_panel.x_spin.setValue(20)
    win.properties_panel.x_spin.setValue(30)

    assert item.x() != original_x
    # exactly one new stack entry for all three ticks combined
    assert win.undo_stack.count() == stack_size_after_add + 1

    win.undo_stack.undo()
    assert item.x() == original_x


def test_property_edits_separated_by_a_pause_do_not_merge(qt_app, monkeypatch):
    """Regression: PropertyEditCommand used to merge with the previous edit
    to the same (item, field) unconditionally, however much real time (and
    however many unrelated, non-undo-tracked interactions) had passed in
    between -- so a second, clearly separate editing session on the same
    field silently absorbed into the first and couldn't be undone alone.
    A tiny merge window (via monkeypatch) keeps this test fast."""
    import time

    from mdtools import commands as commands_module

    monkeypatch.setattr(commands_module, "PROPERTY_EDIT_MERGE_WINDOW_MS", 10)

    win = _win()
    scene = win._current_scene()
    win._add_rectangle()
    item = scene.print_items()[0]
    win.properties_panel.set_item(item)
    original_x = item.x()

    win.properties_panel.x_spin.setValue(10)
    after_first_edit = item.x()

    time.sleep(0.05)  # well past the (patched) merge window

    win.properties_panel.x_spin.setValue(20)
    assert item.x() != after_first_edit

    win.undo_stack.undo()
    assert after_first_edit == item.x()  # only the second edit undone

    win.undo_stack.undo()
    assert original_x == item.x()


def test_reset_to_default_is_undoable(qt_app):
    win = _win()
    scene = win._current_scene()
    win._add_rectangle()
    item = scene.print_items()[0]
    item.setRotation(42)

    win.properties_panel.set_item(item)
    win.properties_panel.reset_btn.click()
    assert item.rotation() == 0

    win.undo_stack.undo()
    assert item.rotation() == 42


def test_copy_paste_creates_an_independent_clone(qt_app):
    win = _win()
    scene = win._current_scene()
    win._add_text()
    original = scene.print_items()[0]
    original.setSelected(True)

    win._copy_selected()
    win._paste()

    items = scene.print_items()
    assert len(items) == 2
    pasted = [i for i in items if i is not original][0]
    assert pasted is not original
    assert pasted.toPlainText() == original.toPlainText()
    assert pasted.x() == original.x() + 10  # nudged, not stacked exactly on top

    win.undo_stack.undo()
    assert scene.print_items() == [original]


def test_cut_then_paste_round_trips(qt_app):
    win = _win()
    scene = win._current_scene()
    win._add_text()
    item = scene.print_items()[0]
    item.setSelected(True)

    win._cut_selected()
    assert scene.print_items() == []

    win._paste()
    assert len(scene.print_items()) == 1
    assert scene.print_items()[0].toPlainText() == "Text"


def test_paste_across_pages_works(qt_app):
    from mdtools.project import PAGE_DISC

    win = _win()
    win._show_page(PAGE_DISC)
    disc_baseline = len(win._current_scene().print_items())  # arrow + label
    win._add_rectangle()
    item = win._current_scene().print_items()[0]
    item.setSelected(True)
    win._copy_selected()

    win._show_page(PAGE_COVER)
    assert win._current_scene().print_items() == []
    win._paste()

    assert len(win._current_scene().print_items()) == 1
    assert len(win.project.pages[PAGE_DISC].print_items()) == disc_baseline + 1


def test_dragging_an_unselected_layer_is_undoable(qt_app):
    """Reported as "undo does not work when moving, maybe I move too fast".
    Speed had nothing to do with it: the pre-move snapshot was taken
    *before* super().mousePressEvent(), and it is that call which selects
    the item under the cursor. Clicking straight onto an unselected layer
    and dragging in one motion -- how anyone actually moves something --
    therefore snapshotted an empty selection and pushed nothing."""
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtGui import QUndoStack
    from PySide6.QtTest import QTest

    from mdtools.canvas.scene import DesignScene
    from mdtools.canvas.view import DesignView
    from mdtools.templates.models import DiscTemplate

    scene = DesignScene(DiscTemplate(name="t", width_mm=37.0, height_mm=52.0))
    item = scene.add_rectangle()
    item.setPos(30, 30)
    view = DesignView()
    view.setScene(scene)
    view.undo_stack = QUndoStack()
    view.resize(600, 600)
    view.show()
    view.centerOn(item)
    assert not item.isSelected(), "the point of this test is that it starts unselected"

    start = view.mapFromScene(item.sceneBoundingRect().center())
    end = QPoint(start.x() + 60, start.y() + 40)
    QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
    QTest.mouseMove(view.viewport(), end)
    QTest.mouseMove(view.viewport(), QPoint(end.x() + 1, end.y() + 1))
    QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, end)

    assert (round(item.x()), round(item.y())) != (30, 30), "the drag did not move anything"
    assert view.undo_stack.count() == 1

    view.undo_stack.undo()
    assert (round(item.x()), round(item.y())) == (30, 30)
