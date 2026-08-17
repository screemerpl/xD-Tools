import math

from PySide6.QtCore import QPointF

from mdtools.canvas.scene import DesignScene
from mdtools.canvas.view import MAX_ZOOM, MIN_ZOOM, DesignView, _angle_degrees
from mdtools.templates.models import DiscTemplate


def _view() -> tuple[DesignView, DesignScene]:
    scene = DesignScene(DiscTemplate(name="t", width_mm=37.0, height_mm=52.0))
    view = DesignView(scene)
    view.resize(400, 400)
    return view, scene


def test_zoom_in_and_out_change_scale_and_emit_signal(qt_app):
    view, scene = _view()
    zoom_values = []
    view.zoom_changed.connect(zoom_values.append)

    view.zoom_in()
    assert view.current_zoom() > 1.0
    assert zoom_values[-1] == view.current_zoom()

    start = view.current_zoom()
    view.zoom_out()
    assert view.current_zoom() < start


def test_zoom_is_clamped_to_min_and_max(qt_app):
    view, scene = _view()
    for _ in range(200):
        view.zoom_in()
    assert view.current_zoom() <= MAX_ZOOM

    for _ in range(200):
        view.zoom_out()
    assert view.current_zoom() >= MIN_ZOOM


def test_zoom_reset_returns_to_100_percent(qt_app):
    view, scene = _view()
    view.zoom_in()
    view.zoom_in()
    assert view.current_zoom() != 1.0

    zoom_values = []
    view.zoom_changed.connect(zoom_values.append)
    view.zoom_reset()

    assert view.current_zoom() == 1.0
    assert zoom_values[-1] == 1.0


def test_zoom_reset_is_a_no_op_already_at_100_percent(qt_app):
    view, scene = _view()
    zoom_values = []
    view.zoom_changed.connect(zoom_values.append)

    view.zoom_reset()

    assert zoom_values == []  # no signal emitted -- nothing actually changed


def test_fit_to_window_updates_zoom_and_emits_signal(qt_app):
    view, scene = _view()
    view.zoom_in()
    zoom_values = []
    view.zoom_changed.connect(zoom_values.append)

    view.fit_to_window()
    assert zoom_values, "fit_to_window should report the new zoom level"
    assert view.current_zoom() == zoom_values[-1]


def test_zoom_toolbar_100_percent_and_grayscale_actions_are_wired(qt_app):
    from PySide6.QtWidgets import QToolBar

    from mdtools.app_window import MainWindow

    win = MainWindow(show_startup_dialog=False)
    zoom_toolbar = next(tb for tb in win.findChildren(QToolBar) if tb.windowTitle() == "Zoom")
    actions = {a.text(): a for a in zoom_toolbar.actions() if a.text()}

    win.view.zoom_in()
    assert win.view.current_zoom() != 1.0
    actions["100%"].trigger()
    assert win.view.current_zoom() == 1.0

    grayscale_action = actions["Grayscale"]
    assert grayscale_action.isCheckable()
    grayscale_action.trigger()
    assert win.view.viewport().graphicsEffect() is not None
    # Grayscale preview is read-only -- the Tool and Layers panels (the
    # remaining ways to add/rename/reorder/delete a layer besides the
    # canvas itself) must be disabled for its whole duration too.
    assert not win.tool_panel.isEnabled()
    assert not win.layers_panel.isEnabled()

    grayscale_action.trigger()
    assert win.view.viewport().graphicsEffect() is None
    assert win.tool_panel.isEnabled()
    assert win.layers_panel.isEnabled()


def test_zoom_toolbar_actions_all_have_a_non_null_icon(qt_app):
    """Regression guard: these actions used to have no icon at all (text
    only) -- Zoom Out/In/100%/Fit/Grayscale should each show a colorful
    icon now, not just their existing text label."""
    from PySide6.QtWidgets import QToolBar

    from mdtools.app_window import MainWindow

    win = MainWindow(show_startup_dialog=False)
    zoom_toolbar = next(tb for tb in win.findChildren(QToolBar) if tb.windowTitle() == "Zoom")
    actions = {a.text(): a for a in zoom_toolbar.actions() if a.text()}

    assert set(actions) == {"Zoom Out", "Zoom In", "100%", "Fit", "Grayscale"}
    for label, action in actions.items():
        assert not action.icon().isNull(), f'"{label}" action has no icon'


def test_brightness_contrast_sliders_only_show_while_grayscale_is_on(qt_app):
    from mdtools.app_window import MainWindow

    win = MainWindow(show_startup_dialog=False)
    controls = (win.brightness_slider, win.contrast_slider)
    # win itself is never shown in this test, so isVisible() would read
    # False for everything regardless of our own setVisible() calls --
    # isVisibleTo(win) reports the widget's own visibility as if win were
    # shown, ignoring that outer gating.
    assert all(not w.isVisibleTo(win) for w in controls)  # hidden by default (grayscale starts off)

    win._on_grayscale_toggled(True)
    assert all(w.isVisibleTo(win) for w in controls)

    win._on_grayscale_toggled(False)
    assert all(not w.isVisibleTo(win) for w in controls)


def test_brightness_contrast_sliders_only_enabled_while_grayscale_is_on(qt_app):
    """The sliders must not just be hidden while grayscale preview is off
    -- they must be genuinely inert (disabled), not merely covered up."""
    from mdtools.app_window import MainWindow

    win = MainWindow(show_startup_dialog=False)
    controls = (win.brightness_slider, win.contrast_slider)
    assert all(not w.isEnabled() for w in controls)

    win._on_grayscale_toggled(True)
    assert all(w.isEnabled() for w in controls)

    win._on_grayscale_toggled(False)
    assert all(not w.isEnabled() for w in controls)


def test_moving_a_toolbar_slider_updates_the_live_preview_and_the_project(qt_app):
    from mdtools.app_window import MainWindow
    from mdtools.project import GrayscaleAdjustment

    win = MainWindow(show_startup_dialog=False)
    win._on_grayscale_toggled(True)

    win.brightness_slider.setValue(40)
    win.contrast_slider.setValue(-20)

    assert win.project.grayscale_adjustment == GrayscaleAdjustment(brightness=40, contrast=-20)
    assert win.view._grayscale_effect.brightness == 40
    assert win.view._grayscale_effect.contrast == -20


def test_toggling_grayscale_seeds_sliders_from_the_current_projects_saved_adjustment(qt_app):
    from mdtools.app_window import MainWindow
    from mdtools.project import GrayscaleAdjustment

    win = MainWindow(show_startup_dialog=False)
    win.project.grayscale_adjustment = GrayscaleAdjustment(brightness=15, contrast=30)

    win._on_grayscale_toggled(True)

    assert win.brightness_slider.value() == 15
    assert win.contrast_slider.value() == 30


def test_grayscale_preview_toggles_a_viewport_effect_on_and_off(qt_app):
    view, scene = _view()
    assert view.viewport().graphicsEffect() is None

    view.set_grayscale_preview(True)
    effect = view.viewport().graphicsEffect()
    assert effect is not None

    view.set_grayscale_preview(False)
    assert view.viewport().graphicsEffect() is None


def test_enabling_grayscale_preview_deselects_the_current_item(qt_app):
    """Regression: a user could enable grayscale preview while something
    was already selected and the selection frame/handles stayed on
    screen, still editable -- previewing should not leave an editable
    item selected."""
    view, scene = _view()
    item = scene.add_rectangle()
    item.setSelected(True)
    assert scene.selectedItems() == [item]

    view.set_grayscale_preview(True)

    assert scene.selectedItems() == []


def test_grayscale_preview_disables_canvas_item_interaction(qt_app):
    """Regression: nothing should be selectable/draggable on the canvas
    while grayscale preview is on -- it's meant to be a look-only
    preview, not just a color filter."""
    view, scene = _view()
    assert view.isInteractive()

    view.set_grayscale_preview(True)
    assert not view.isInteractive()

    view.set_grayscale_preview(False)
    assert view.isInteractive()


def test_grayscale_preview_blocks_delete_and_nudge_even_if_something_got_selected(qt_app):
    """Defensive regression: even if an item were somehow selected while
    grayscale preview is active, Delete/arrow-key nudge must still no-op
    -- editing must stay impossible for the whole duration of the
    preview, not just at the moment it was turned on."""
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent

    view, scene = _view()
    item = scene.add_rectangle()
    view.set_grayscale_preview(True)
    item.setSelected(True)  # bypassing the normal UI, to test the keyboard guard itself
    before = (item.x(), item.y())

    event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Right, Qt.KeyboardModifier.NoModifier)
    view.keyPressEvent(event)

    assert (item.x(), item.y()) == before
    assert scene.selectedItems() == [item]  # not deleted either


def test_grayscale_preview_effect_survives_after_the_call_returns(qt_app):
    """Regression: QWidget.setGraphicsEffect() does not itself keep a
    Python reference to the effect object (the same class of gotcha as
    i18n's QTranslator) -- a purely-local QGraphicsEffect got garbage
    collected the instant set_grayscale_preview() returned, silently
    undoing the toggle before anything ever painted with it."""
    view, scene = _view()
    view.set_grayscale_preview(True)

    import gc

    gc.collect()  # force collection of anything not properly kept alive

    assert view.viewport().graphicsEffect() is not None


def test_grayscale_preview_does_not_lighten_black(qt_app):
    """Regression: the first implementation used QGraphicsColorizeEffect
    (color=gray, strength=1.0), which -- despite looking like the obvious
    choice -- washes the whole image toward white rather than doing an
    honest luma conversion: black rendered as RGB(128, 128, 128), reported
    as "black is not black, image looks very bright". The real fix
    (_TrueGrayscaleEffect, a native Format_Grayscale8 conversion) must
    leave black exactly black."""
    from PySide6.QtGui import QColor

    scene = DesignScene(DiscTemplate(name="t", width_mm=40.0, height_mm=40.0, shape="full_label", corner_radius_mm=0.0))
    rect = scene.add_rectangle()
    brush = rect.brush()
    brush.setColor(QColor("black"))
    rect.setBrush(brush)
    pen = rect.pen()
    pen.setColor(QColor("black"))
    rect.setPen(pen)

    view = DesignView(scene)
    view.resize(300, 300)
    view.fit_to_window()
    view.set_grayscale_preview(True)

    image = view.viewport().grab().toImage()
    darkest = min(max(image.pixelColor(x, y).red(), image.pixelColor(x, y).green(), image.pixelColor(x, y).blue())
                  for y in range(image.height()) for x in range(image.width()))
    assert darkest < 10  # a genuinely black pixel survived, not washed up toward gray/white


def test_grayscale_preview_desaturates_a_colored_shape(qt_app):
    """The preview should still actually desaturate -- a solid red
    rectangle must come out some shade of gray, not stay colored."""
    from PySide6.QtGui import QColor

    scene = DesignScene(DiscTemplate(name="t", width_mm=40.0, height_mm=40.0, shape="full_label", corner_radius_mm=0.0))
    rect = scene.add_rectangle()
    brush = rect.brush()
    brush.setColor(QColor("red"))
    rect.setBrush(brush)
    pen = rect.pen()
    pen.setColor(QColor("red"))
    rect.setPen(pen)

    view = DesignView(scene)
    view.resize(300, 300)
    view.fit_to_window()
    view.set_grayscale_preview(True)

    image = view.viewport().grab().toImage()
    found_gray_not_red = any(
        (c := image.pixelColor(x, y)).red() == c.green() == c.blue() and c.red() < 250
        for y in range(image.height())
        for x in range(image.width())
    )
    assert found_gray_not_red


def test_ctrl_held_snaps_rotation_to_10_degree_increments(qt_app):
    scene = DesignScene(DiscTemplate(name="t", width_mm=37.0, height_mm=52.0))
    item = scene.add_ellipse()
    item.setSelected(True)
    view = DesignView(scene)
    view.resize(400, 400)

    _, rotate_handle, origin = view._handle_geometry(item)
    view._begin_drag("rotate", item, rotate_handle)

    start_angle = _angle_degrees(origin, rotate_handle)
    target_rad = math.radians(start_angle + 47)  # an arbitrary, non-multiple-of-10 offset
    point = origin + QPointF(50 * math.cos(target_rad), 50 * math.sin(target_rad))

    view._update_drag(point, constrained=True)

    assert abs(item.rotation() - 50) < 1e-6  # 47 snaps to the nearest 10 degrees
