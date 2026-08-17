from PySide6.QtWidgets import QGraphicsRectItem

from mdtools.canvas.scene import DesignScene
from mdtools.templates.models import DiscTemplate


def _scene() -> DesignScene:
    return DesignScene(DiscTemplate(name="t", width_mm=37.0, height_mm=52.0))


def test_add_rectangle_has_a_fill_color(qt_app):
    scene = _scene()
    item = scene.add_rectangle()
    assert isinstance(item, QGraphicsRectItem)
    assert item.brush().color().alpha() > 0


def test_add_rectangle_frame_matches_its_fill_not_a_separate_default(qt_app):
    scene = _scene()
    item = scene.add_rectangle()
    assert item.pen().color().name() == item.brush().color().name()


def test_add_text_defaults_to_black_not_the_ambient_palette_color(qt_app):
    # QGraphicsTextItem's real default is whatever the widget palette's Text
    # role resolves to -- white under a dark theme/OS setting, which made
    # new text on a (light) label look all but invisible. Must always be a
    # real, visible color regardless of the active palette/theme.
    scene = _scene()
    item = scene.add_text("hello")
    assert item.defaultTextColor().getRgb() == (0, 0, 0, 255)


def test_add_text_is_black_even_under_a_dark_application_palette(qt_app):
    from PySide6.QtGui import QColor, QPalette

    original = qt_app.palette()
    dark = QPalette(original)
    dark.setColor(QPalette.ColorRole.Text, QColor("white"))
    dark.setColor(QPalette.ColorRole.WindowText, QColor("white"))
    qt_app.setPalette(dark)
    try:
        scene = _scene()  # kept alive: GC'd otherwise, taking its items with it
        item = scene.add_text("hello")
        assert item.defaultTextColor().getRgb() == (0, 0, 0, 255)
    finally:
        qt_app.setPalette(original)


def test_new_items_stack_on_top_of_earlier_ones(qt_app):
    scene = _scene()
    first = scene.add_text("first")
    second = scene.add_rectangle()

    ordered = scene.print_items()  # topmost first
    assert ordered == [second, first]


def test_move_item_up_and_down_swap_stacking_order(qt_app):
    scene = _scene()
    first = scene.add_text("first")
    second = scene.add_rectangle()
    assert scene.print_items() == [second, first]

    scene.move_item_up(first)  # first should move from back to front
    assert scene.print_items() == [first, second]

    scene.move_item_down(first)
    assert scene.print_items() == [second, first]


def test_move_item_up_at_front_is_a_no_op(qt_app):
    scene = _scene()
    first = scene.add_text("first")
    second = scene.add_rectangle()

    scene.move_item_up(second)  # already topmost
    assert scene.print_items() == [second, first]


def test_move_item_down_at_back_is_a_no_op(qt_app):
    scene = _scene()
    first = scene.add_text("first")
    scene.add_rectangle()

    scene.move_item_down(first)  # already at the back
    assert scene.print_items()[-1] is first
