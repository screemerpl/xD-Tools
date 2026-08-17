from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QColor

from mdtools.canvas.items import get_item_scale
from mdtools.canvas.scene import DesignScene
from mdtools.canvas.view import MAX_SCALE, MIN_SCALE, DesignView
from mdtools.templates.models import DiscTemplate


def _make_view_with_selected_ellipse(qt_app):
    scene = DesignScene(DiscTemplate(name="t", width_mm=37.0, height_mm=52.0))
    item = scene.add_ellipse()
    item.setSelected(True)
    view = DesignView(scene)
    view.resize(400, 400)
    # keep `scene` alive: QGraphicsView.setScene() doesn't take a Python
    # reference, so without this the scene (and its items) get garbage
    # collected out from under the view.
    return view, scene, item


def test_scale_drag_along_the_diagonal_grows_both_axes_evenly(qt_app):
    view, scene, item = _make_view_with_selected_ellipse(qt_app)
    corners, _, origin = view._handle_geometry(item)

    view._begin_drag("scale", item, corners[2])  # bottom-right corner
    far_point = origin + (corners[2] - origin) * 2  # drag twice as far from center, same direction
    view._update_drag(far_point)

    sx, sy = get_item_scale(item)
    assert 1.9 < sx < 2.1
    assert 1.9 < sy < 2.1


def test_scale_drag_clamps_to_the_configured_min_and_max(qt_app):
    view, scene, item = _make_view_with_selected_ellipse(qt_app)
    corners, _, origin = view._handle_geometry(item)

    view._begin_drag("scale", item, corners[2])
    huge_point = origin + (corners[2] - origin) * 10000
    view._update_drag(huge_point, constrained=True)
    assert get_item_scale(item) == (MAX_SCALE, MAX_SCALE)

    view._begin_drag("scale", item, corners[2])
    tiny_point = origin + (corners[2] - origin) * 0.0000001
    view._update_drag(tiny_point, constrained=True)
    assert get_item_scale(item) == (MIN_SCALE, MIN_SCALE)


def test_scale_drag_without_ctrl_resizes_axes_independently(qt_app):
    view, scene, item = _make_view_with_selected_ellipse(qt_app)
    corners, _, origin = view._handle_geometry(item)

    view._begin_drag("scale", item, corners[2])  # bottom-right corner
    # move only horizontally from the start point -- width should grow,
    # height should stay roughly the same
    stretched = corners[2] + QPointF(80, 0)
    view._update_drag(stretched, constrained=False)

    sx, sy = get_item_scale(item)
    assert sx > 1.5
    assert 0.9 < sy < 1.1


def test_scale_drag_with_ctrl_stays_uniform_even_for_an_off_axis_drag(qt_app):
    view, scene, item = _make_view_with_selected_ellipse(qt_app)
    corners, _, origin = view._handle_geometry(item)

    view._begin_drag("scale", item, corners[2])
    # same lopsided drag as the non-uniform test, but with Ctrl (constrained)
    stretched = corners[2] + QPointF(80, 0)
    view._update_drag(stretched, constrained=True)

    sx, sy = get_item_scale(item)
    assert abs(sx - sy) < 1e-6


def test_rotate_drag_changes_rotation(qt_app):
    view, scene, item = _make_view_with_selected_ellipse(qt_app)
    _, rotate_handle, origin = view._handle_geometry(item)

    view._begin_drag("rotate", item, rotate_handle)
    # rotate the mouse 90 degrees around the origin
    vec = rotate_handle - origin
    rotated_point = origin + QPointF(-vec.y(), vec.x())
    view._update_drag(rotated_point)

    assert abs(item.rotation() - 90) < 1.0


def test_hit_test_finds_corner_and_rotate_handles(qt_app):
    view, scene, item = _make_view_with_selected_ellipse(qt_app)
    corners, rotate_handle, _ = view._handle_geometry(item)

    assert view._hit_test(item, corners[0]) == "scale"
    assert view._hit_test(item, rotate_handle) == "rotate"
    assert view._hit_test(item, item.mapToScene(item.boundingRect().center())) is None


def test_hit_test_finds_edge_midpoints_as_single_axis_handles(qt_app):
    view, scene, item = _make_view_with_selected_ellipse(qt_app)
    corners, _, _ = view._handle_geometry(item)
    tl, tr, br, bl = corners

    assert view._hit_test(item, (tl + tr) / 2) == "scale-y"  # top edge
    assert view._hit_test(item, (br + bl) / 2) == "scale-y"  # bottom edge
    assert view._hit_test(item, (tr + br) / 2) == "scale-x"  # right edge
    assert view._hit_test(item, (bl + tl) / 2) == "scale-x"  # left edge


def test_dragging_right_edge_grows_width_only(qt_app):
    view, scene, item = _make_view_with_selected_ellipse(qt_app)
    corners, _, origin = view._handle_geometry(item)
    tr, br = corners[1], corners[2]
    right_mid = (tr + br) / 2

    view._begin_drag("scale-x", item, right_mid)
    view._update_drag(right_mid + QPointF(80, 0))

    sx, sy = get_item_scale(item)
    assert sx > 1.5
    assert abs(sy - 1.0) < 1e-6


def test_dragging_bottom_edge_grows_height_only(qt_app):
    view, scene, item = _make_view_with_selected_ellipse(qt_app)
    corners, _, origin = view._handle_geometry(item)
    br, bl = corners[2], corners[3]
    bottom_mid = (br + bl) / 2

    view._begin_drag("scale-y", item, bottom_mid)
    view._update_drag(bottom_mid + QPointF(0, 80))

    sx, sy = get_item_scale(item)
    assert abs(sx - 1.0) < 1e-6
    assert sy > 1.5


def test_selection_frame_tightens_to_a_clipped_pixmap_layers_visible_content(qt_app):
    """After Clip Layers/Bake Layers, a pixmap layer's boundingRect() still
    spans its full pre-clip extent -- only a portion of it is actually
    opaque, the rest made transparent by clipping. The selection frame
    (and its resize handles) must size to that visible content, not the
    full, mostly-empty pixmap."""
    from PySide6.QtGui import QImage, QPixmap
    from PySide6.QtWidgets import QGraphicsPixmapItem

    scene = DesignScene(DiscTemplate(name="t", width_mm=37.0, height_mm=52.0))
    image = QImage(100, 100, QImage.Format.Format_ARGB32)
    image.fill(QColor(0, 0, 0, 0))
    for y in range(40, 60):
        for x in range(40, 60):
            image.setPixelColor(x, y, QColor(255, 0, 0, 255))
    item = QGraphicsPixmapItem(QPixmap.fromImage(image))
    item.setPos(0, 0)
    item.setSelected(True)
    scene.addItem(item)
    view = DesignView(scene)
    view.resize(400, 400)

    corners, _, _ = view._handle_geometry(item)
    tl, _, br, _ = corners[0], corners[1], corners[2], corners[3]

    assert abs(tl.x() - 40) < 1e-6
    assert abs(tl.y() - 40) < 1e-6
    assert abs(br.x() - 60) < 1e-6
    assert abs(br.y() - 60) < 1e-6


def test_selection_frame_is_unaffected_for_a_fully_opaque_pixmap(qt_app):
    from PySide6.QtGui import QImage, QPixmap
    from PySide6.QtWidgets import QGraphicsPixmapItem

    scene = DesignScene(DiscTemplate(name="t", width_mm=37.0, height_mm=52.0))
    image = QImage(50, 30, QImage.Format.Format_ARGB32)
    image.fill(QColor(255, 0, 0, 255))
    item = QGraphicsPixmapItem(QPixmap.fromImage(image))
    item.setPos(0, 0)
    item.setSelected(True)
    scene.addItem(item)
    view = DesignView(scene)
    view.resize(400, 400)

    corners, _, _ = view._handle_geometry(item)
    tl, br = corners[0], corners[2]
    assert abs(tl.x() - 0) < 1e-6 and abs(tl.y() - 0) < 1e-6
    assert abs(br.x() - 50) < 1e-6 and abs(br.y() - 30) < 1e-6


def test_selection_frame_stays_screen_aligned_when_item_is_rotated(qt_app):
    scene = DesignScene(DiscTemplate(name="t", width_mm=37.0, height_mm=52.0))
    item = scene.add_rectangle()  # 20mm x 14mm, non-square so axis swap is detectable
    item.setSelected(True)
    view = DesignView(scene)
    view.resize(400, 400)

    item.setRotation(37)  # arbitrary non-multiple-of-90 angle
    corners, _, _ = view._handle_geometry(item)
    tl, tr, br, bl = corners

    # A screen-aligned (non-tilted) frame has horizontal top/bottom edges
    # and vertical left/right edges, regardless of the item's own rotation.
    assert abs(tl.y() - tr.y()) < 1e-6
    assert abs(bl.y() - br.y()) < 1e-6
    assert abs(tl.x() - bl.x()) < 1e-6
    assert abs(tr.x() - br.x()) < 1e-6


def test_edge_drag_after_rotation_measures_in_screen_axes_not_item_axes(qt_app):
    """Scale factors (sx, sy) always scale the item's own pre-rotation local
    axes (see set_item_scale); the frame/drag math deliberately measures
    drags in raw scene coordinates rather than un-rotating them first (see
    _update_drag). At non-multiples of 180 degrees this is a known,
    accepted trade-off (screen-aligned frame > perfectly shear-free resize)
    -- e.g. at exactly 90 degrees, a screen-horizontal edge drag ends up
    growing sx, which then renders as a *vertical* on-screen change, since
    the item's local x-axis is now vertical on screen."""
    scene = DesignScene(DiscTemplate(name="t", width_mm=37.0, height_mm=52.0))
    item = scene.add_rectangle()
    item.setSelected(True)
    view = DesignView(scene)
    view.resize(400, 400)

    item.setRotation(90)
    corners, _, origin = view._handle_geometry(item)
    tr, br = corners[1], corners[2]
    right_mid = (tr + br) / 2

    view._begin_drag("scale-x", item, right_mid)
    view._update_drag(right_mid + QPointF(80, 0))  # drag along scene +x

    sx, sy = get_item_scale(item)
    assert sx > 1.5
    assert abs(sy - 1.0) < 1e-6


def test_start_color_probe_sets_crosshair_cursor(qt_app):
    view, scene, item = _make_view_with_selected_ellipse(qt_app)
    view.start_color_probe()
    assert view.cursor().shape() == Qt.CursorShape.CrossCursor


def test_finishing_a_probe_emits_the_sampled_color_and_resets_state(qt_app):
    scene = DesignScene(DiscTemplate(name="t", width_mm=37.0, height_mm=52.0))
    from PySide6.QtGui import QPen

    item = scene.add_rectangle()
    item.setBrush(QColor("red"))
    item.setPen(QPen(QColor("red")))
    item.setPos(0, 0)
    view = DesignView(scene)
    view.resize(400, 400)
    view.fit_to_window()

    captured = []
    view.color_probed.connect(captured.append)

    view.start_color_probe()
    # somewhere well inside the (0,0)-positioned red rectangle on screen
    probe_point = view.mapFromScene(item.sceneBoundingRect().center())
    view._finish_color_probe(QPoint(probe_point.x(), probe_point.y()))

    assert len(captured) == 1
    assert captured[0].red() > 200 and captured[0].green() < 50 and captured[0].blue() < 50
    assert view._probing_color is False
    assert view.cursor().shape() != Qt.CursorShape.CrossCursor


def test_escape_cancels_an_in_progress_probe(qt_app):
    from PySide6.QtGui import QKeyEvent

    view, scene, item = _make_view_with_selected_ellipse(qt_app)
    view.start_color_probe()

    event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
    view.keyPressEvent(event)

    assert view._probing_color is False
    assert view.cursor().shape() != Qt.CursorShape.CrossCursor
