from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QUndoStack

from mdtools.canvas.scene import DesignScene
from mdtools.canvas.view import ARROW_STEP_HELD_MM, ARROW_STEP_MM, DesignView
from mdtools.constants import mm_to_px
from mdtools.templates.models import DiscTemplate


class _FakeTimer:
    """Stands in for view._arrow_hold_timer -- lets tests fast-forward
    "how long has this key been held" without a real wall-clock wait."""

    def __init__(self):
        self._elapsed = 0

    def start(self):
        self._elapsed = 0

    def elapsed(self):
        return self._elapsed


def _make_view_with_selected_rect(qt_app):
    scene = DesignScene(DiscTemplate(name="t", width_mm=37.0, height_mm=52.0))
    item = scene.add_rectangle()
    item.setSelected(True)
    view = DesignView(scene)
    view.resize(400, 400)
    view._arrow_hold_timer = _FakeTimer()
    # keep `scene` alive: QGraphicsView.setScene() doesn't take a Python
    # reference, so without this the scene (and its items) get garbage
    # collected out from under the view.
    return view, scene, item


def _key_event(key, *, autorepeat: bool = False) -> QKeyEvent:
    return QKeyEvent(QKeyEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier, "", autorepeat)


def test_a_single_press_nudges_by_the_small_step(qt_app):
    view, scene, item = _make_view_with_selected_rect(qt_app)
    original = (item.x(), item.y())

    view.keyPressEvent(_key_event(Qt.Key.Key_Right))

    assert item.x() == original[0] + mm_to_px(ARROW_STEP_MM)
    assert item.y() == original[1]


def test_all_four_directions_move_the_expected_way(qt_app):
    view, scene, item = _make_view_with_selected_rect(qt_app)
    start = (item.x(), item.y())
    step = mm_to_px(ARROW_STEP_MM)

    view.keyPressEvent(_key_event(Qt.Key.Key_Left))
    assert (item.x(), item.y()) == (start[0] - step, start[1])

    item.setPos(*start)
    view.keyPressEvent(_key_event(Qt.Key.Key_Up))
    assert (item.x(), item.y()) == (start[0], start[1] - step)

    item.setPos(*start)
    view.keyPressEvent(_key_event(Qt.Key.Key_Down))
    assert (item.x(), item.y()) == (start[0], start[1] + step)


def test_holding_the_key_switches_to_the_larger_step(qt_app):
    view, scene, item = _make_view_with_selected_rect(qt_app)
    original_x = item.x()

    view.keyPressEvent(_key_event(Qt.Key.Key_Right))  # fresh press: small step
    assert item.x() == original_x + mm_to_px(ARROW_STEP_MM)

    view._arrow_hold_timer._elapsed = 1000  # simulate having held it for a while
    view.keyPressEvent(_key_event(Qt.Key.Key_Right, autorepeat=True))

    assert item.x() == original_x + mm_to_px(ARROW_STEP_MM) + mm_to_px(ARROW_STEP_HELD_MM)


def test_autorepeat_before_the_hold_threshold_still_uses_the_small_step(qt_app):
    view, scene, item = _make_view_with_selected_rect(qt_app)
    original_x = item.x()

    view.keyPressEvent(_key_event(Qt.Key.Key_Right))
    view._arrow_hold_timer._elapsed = 50  # well under ARROW_HOLD_THRESHOLD_MS
    view.keyPressEvent(_key_event(Qt.Key.Key_Right, autorepeat=True))

    assert item.x() == original_x + 2 * mm_to_px(ARROW_STEP_MM)


def test_a_fresh_press_after_release_resets_to_the_small_step(qt_app):
    view, scene, item = _make_view_with_selected_rect(qt_app)
    original_x = item.x()

    view.keyPressEvent(_key_event(Qt.Key.Key_Right))
    view._arrow_hold_timer._elapsed = 1000
    view.keyPressEvent(_key_event(Qt.Key.Key_Right, autorepeat=True))  # big step
    # key released, then pressed again fresh (isAutoRepeat=False)
    view.keyPressEvent(_key_event(Qt.Key.Key_Right))

    expected = original_x + mm_to_px(ARROW_STEP_MM) + mm_to_px(ARROW_STEP_HELD_MM) + mm_to_px(ARROW_STEP_MM)
    assert item.x() == expected


def test_nudging_without_a_selection_does_nothing(qt_app):
    view, scene, item = _make_view_with_selected_rect(qt_app)
    item.setSelected(False)
    original = (item.x(), item.y())

    view.keyPressEvent(_key_event(Qt.Key.Key_Right))

    assert (item.x(), item.y()) == original


def test_a_hold_gesture_is_undoable_as_a_single_step(qt_app):
    view, scene, item = _make_view_with_selected_rect(qt_app)
    view.undo_stack = QUndoStack()
    original = (item.x(), item.y())

    view.keyPressEvent(_key_event(Qt.Key.Key_Right))
    view._arrow_hold_timer._elapsed = 1000
    view.keyPressEvent(_key_event(Qt.Key.Key_Right, autorepeat=True))
    view.keyPressEvent(_key_event(Qt.Key.Key_Right, autorepeat=True))

    assert (item.x(), item.y()) != original
    assert view.undo_stack.count() == 1  # merged into one entry, not three

    view.undo_stack.undo()
    assert (item.x(), item.y()) == original
