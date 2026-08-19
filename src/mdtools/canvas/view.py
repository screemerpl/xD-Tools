from __future__ import annotations

import math

from PySide6.QtCore import QElapsedTimer, QLineF, QPoint, QPointF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QGraphicsEffect, QGraphicsView

from mdtools.canvas.items import LAYER_CUT, LAYER_FOLD, LAYER_ROLE, get_item_scale, opaque_content_rect, set_item_scale
from mdtools.commands import DeleteItemsCommand, MoveItemsCommand, TransformCommand
from mdtools.constants import mm_to_px
from mdtools.grayscale import apply_grayscale

HANDLE_PIXELS = 9  # on-screen size of a corner scale handle, independent of zoom
ROTATE_HANDLE_OFFSET_PIXELS = 26  # distance of the rotate handle above the item
ROTATE_HANDLE_RADIUS_PIXELS = 6
HANDLE_HIT_MARGIN_PIXELS = 5  # extra slack added to hit-testing so handles are easy to grab

MIN_SCALE = 0.005
MAX_SCALE = 30.0
ROTATE_SNAP_DEGREES = 10
ZOOM_FACTOR = 1.15
MIN_ZOOM = 0.1
MAX_ZOOM = 8.0

ARROW_STEP_MM = 0.1  # per key press
ARROW_STEP_HELD_MM = 0.5  # once the key has been held past ARROW_HOLD_THRESHOLD_MS
ARROW_HOLD_THRESHOLD_MS = 500


class _TrueGrayscaleEffect(QGraphicsEffect):
    """A real desaturation -- black stays black, white stays white -- for
    the view-only grayscale preview toggle, plus the same brightness/
    contrast adjustment the toolbar sliders and Export Print PNG
    (Grayscale) use.

    QGraphicsColorizeEffect (tried first) is the wrong tool for this: even
    with a neutral gray color at full strength, it washes the whole image
    toward white rather than doing an honest luma conversion (it's meant
    for a sepia/tinted-photo look, not a true grayscale preview) --
    confirmed empirically, black mapped to RGB(128, 128, 128) instead of
    staying black, which is exactly the "black isn't black, looks too
    bright" a user reported. The actual pixel math (grayscale conversion,
    alpha preservation, and the brightness/contrast lookup table) lives in
    mdtools.grayscale.apply_grayscale, shared with the real export and its
    pre-export preview dialog, so this view-only preview can never look
    different from what actually gets saved."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.brightness = 0
        self.contrast = 0

    def set_adjustment(self, brightness: int, contrast: int) -> None:
        self.brightness = brightness
        self.contrast = contrast
        self.update()

    def draw(self, painter: QPainter) -> None:
        offset = QPoint()
        pixmap = self.sourcePixmap(Qt.CoordinateSystem.LogicalCoordinates, offset)
        if pixmap.isNull():
            self.drawSource(painter)
            return

        result = apply_grayscale(pixmap.toImage(), self.brightness, self.contrast)
        painter.drawImage(offset, result)


class DesignView(QGraphicsView):
    """QGraphicsView with mouse-wheel zoom, fit-to-window, mouse-driven
    scale/rotate handles drawn around the single selected item, and
    Delete/Backspace to remove the selected item(s).

    Handles are drawn in drawForeground(), which only runs for on-screen
    painting (export renders the QGraphicsScene directly), so they never
    end up in an exported SVG/PNG.
    """

    items_deleted = Signal()
    zoom_changed = Signal(float)  # current zoom as a fraction, e.g. 1.0 == 100%
    color_probed = Signal(QColor)  # the color under the mouse after start_color_probe()

    def __init__(self, scene=None, parent=None):
        super().__init__(scene, parent)
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.TextAntialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        # The canvas represents physical, printed material -- "physical
        # accuracy is load-bearing" per this project's own top-level rule
        # -- so it stays a plain white workspace regardless of the app's
        # own theme (see mdtools.theme's dark palette), the same way a page
        # in a real design tool stays white even inside a dark UI chrome.
        # Without this, the template outline (make_template_outline() sets
        # NoBrush -- it's a line, not a filled shape) would show whatever
        # the ambient palette happens to be behind it.
        self.setBackgroundBrush(QBrush(QColor("white")))
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        # MinimalViewportUpdate (the default) only repaints the scene-tracked
        # dirty rect of items that changed; our selection handles are drawn
        # outside the selected item's own bounding rect (drawForeground),
        # so as the item scales/rotates the *previous* handle positions
        # never get invalidated and are left behind as smudges. Repainting
        # the whole viewport every frame avoids that.
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self._zoom = 1.0
        self._drag_kind: str | None = None  # "scale" | "rotate"
        self._drag_item = None
        self._drag_origin_scene = QPointF()
        self._drag_start_mouse_scene = QPointF()
        self._drag_start_scale_xy = (1.0, 1.0)
        self._drag_start_rotation = 0.0
        self._drag_start_distance = 1.0
        self._drag_start_local = QPointF()
        self._drag_before_snapshot: dict | None = None
        self._pre_move_positions: dict = {}
        self._arrow_hold_key: int | None = None
        self._arrow_hold_timer = QElapsedTimer()
        self._probing_color = False
        # Set by MainWindow after construction; None (the default) means
        # "no undo history" -- drags/deletes still work, just aren't
        # undoable, which is what standalone/test usage of DesignView wants.
        self.undo_stack = None
        self._grayscale_effect = None
        # Remembered so a later set_grayscale_preview(True) re-applies
        # whatever was last set via set_grayscale_adjustment(), without the
        # caller (MainWindow) needing to resend it -- the effect object
        # itself only exists while the preview is actually on.
        self._grayscale_brightness = 0
        self._grayscale_contrast = 0

    # -- color probe (eyedropper) --------------------------------------------

    def start_color_probe(self) -> None:
        """The next left-click samples whatever color is on screen at that
        point (exactly as rendered -- template outline, other layers, and
        all) and emits color_probed instead of doing normal
        selection/drag handling."""
        self._probing_color = True
        self.setCursor(Qt.CursorShape.CrossCursor)

    def _finish_color_probe(self, view_pos) -> None:
        color = self.viewport().grab().toImage().pixelColor(view_pos)
        self._probing_color = False
        self.unsetCursor()
        self.color_probed.emit(color)

    # -- zoom / fit -----------------------------------------------------------

    def wheelEvent(self, event) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self._zoom_by(ZOOM_FACTOR if event.angleDelta().y() > 0 else 1 / ZOOM_FACTOR)
        else:
            super().wheelEvent(event)

    def current_zoom(self) -> float:
        return self._zoom

    def zoom_in(self) -> None:
        self._zoom_by(ZOOM_FACTOR)

    def zoom_out(self) -> None:
        self._zoom_by(1 / ZOOM_FACTOR)

    def zoom_reset(self) -> None:
        self.set_zoom(1.0)

    def _zoom_by(self, factor: float) -> None:
        self.set_zoom(self._zoom * factor)

    def set_zoom(self, target: float) -> None:
        new_zoom = max(MIN_ZOOM, min(MAX_ZOOM, target))
        if abs(new_zoom - self._zoom) < 1e-9:
            return
        applied = new_zoom / self._zoom
        self._zoom = new_zoom
        self.scale(applied, applied)
        self.zoom_changed.emit(self._zoom)

    def fit_to_window(self) -> None:
        if self.scene() is not None:
            self.fitInView(self.scene().sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
            self._zoom = self.transform().m11()
            self.zoom_changed.emit(self._zoom)

    # -- grayscale preview ------------------------------------------------------

    def set_grayscale_preview(self, enabled: bool) -> None:
        """A visual grayscale filter that also, deliberately, makes the
        canvas read-only while it's on -- desaturates everything painted
        in the viewport (design items, the unprintable-area overlay,
        selection handles, all of it) via a QGraphicsEffect, without
        touching the scene or its items' actual colors in any way. Never
        affects Export Print PNG (Grayscale) or anything else that reads
        actual item colors -- this is a quick preview, sharing its actual
        pixel math (mdtools.grayscale.apply_grayscale) with the real
        export rather than its own separate approximation (see
        _TrueGrayscaleEffect's docstring for why not
        QGraphicsColorizeEffect).

        Enabling it clears the current selection (so Properties/Layers
        panels drop out of sync with nothing to edit -- both already
        disable themselves with no selection, via the usual
        selectionChanged -> _on_selection_changed chain in app_window.py)
        and disables item interaction via setInteractive(False), so clicks
        can no longer select/drag an item and rubber-band selection stops
        working. This was an explicit follow-up request: a user could
        still select and edit items while merely *previewing* in
        grayscale, which defeats the point of a temporary, look-only
        preview."""
        if enabled:
            # kept alive on self: QWidget.setGraphicsEffect() does not
            # itself keep a Python reference (same gotcha as i18n's
            # QTranslator -- see i18n/__init__.py) -- a purely-local
            # QGraphicsEffect would be garbage collected the moment this
            # method returns, silently undoing the effect before it's ever
            # actually painted.
            self._grayscale_effect = _TrueGrayscaleEffect()
            self._grayscale_effect.set_adjustment(self._grayscale_brightness, self._grayscale_contrast)
            self.viewport().setGraphicsEffect(self._grayscale_effect)
            if self.scene() is not None:
                self.scene().clearSelection()
            self.setInteractive(False)
        else:
            self.viewport().setGraphicsEffect(None)
            self._grayscale_effect = None
            self.setInteractive(True)

    def set_grayscale_adjustment(self, brightness: int, contrast: int) -> None:
        """Updates the live grayscale preview's brightness/contrast (-100..100
        each, 0 = unchanged) -- called from MainWindow's toolbar sliders
        while the preview is on, and to seed it from the current project's
        saved GrayscaleAdjustment whenever a project is created/opened or
        the preview is (re-)enabled. Remembered even while the preview is
        off, so turning it back on doesn't reset to 0/0."""
        self._grayscale_brightness = brightness
        self._grayscale_contrast = contrast
        if self._grayscale_effect is not None:
            self._grayscale_effect.set_adjustment(brightness, contrast)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape and self._probing_color:
            self._probing_color = False
            self.unsetCursor()
            event.accept()
            return
        if self._grayscale_effect is not None:
            # Read-only while previewing in grayscale -- see
            # set_grayscale_preview(). Nothing is ever selected in this
            # state anyway (selection is cleared on enabling), so this is
            # mostly defensive, but skip our own Delete/nudge handling
            # explicitly rather than relying on that alone.
            super().keyPressEvent(event)
            return
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) and self.scene() is not None:
            selected = [i for i in self.scene().selectedItems() if i.data(LAYER_ROLE) not in (LAYER_CUT, LAYER_FOLD)]
            if selected:
                if self.undo_stack is not None:
                    self.undo_stack.push(DeleteItemsCommand(self.scene(), selected, "Delete Layer"))
                else:
                    for item in selected:
                        self.scene().removeItem(item)
                self.items_deleted.emit()
                event.accept()
                return
        arrow_deltas_mm = {
            Qt.Key.Key_Left: (-1, 0),
            Qt.Key.Key_Right: (1, 0),
            Qt.Key.Key_Up: (0, -1),
            Qt.Key.Key_Down: (0, 1),
        }
        if event.key() in arrow_deltas_mm and self.scene() is not None:
            selected = [i for i in self.scene().selectedItems() if i.data(LAYER_ROLE) not in (LAYER_CUT, LAYER_FOLD)]
            if selected:
                self._nudge_selected(selected, arrow_deltas_mm[event.key()], event)
                event.accept()
                return
        super().keyPressEvent(event)

    def _nudge_selected(self, items: list, direction_mm: tuple[float, float], event) -> None:
        """Moves `items` by one small step in `direction_mm` (a unit vector,
        e.g. (1, 0) for Right). A key held down (OS auto-repeat) switches to
        a bigger step past ARROW_HOLD_THRESHOLD_MS, so a quick tap nudges
        precisely but holding the key still covers distance reasonably fast.
        Consecutive nudges from the *same* held-key gesture merge into a
        single undo step (see MoveItemsCommand.mergeWith) -- undo restores
        the position from before the whole hold, not one tick at a time.
        `is_continuation` (an OS auto-repeat of the key already being
        tracked) is what actually decides mergeability, not just "same item
        set" -- a fresh, isolated tap must NOT merge into whatever nudge
        happened to be on top of the stack before it, or two clearly
        separate nudges (tap, pause, tap again) would collapse into one
        undo step."""
        is_continuation = event.isAutoRepeat() and self._arrow_hold_key == event.key()
        if not is_continuation:
            self._arrow_hold_key = event.key()
            self._arrow_hold_timer.start()
            step_mm = ARROW_STEP_MM
        else:
            step_mm = ARROW_STEP_HELD_MM if self._arrow_hold_timer.elapsed() >= ARROW_HOLD_THRESHOLD_MS else ARROW_STEP_MM

        dx = mm_to_px(direction_mm[0] * step_mm)
        dy = mm_to_px(direction_mm[1] * step_mm)

        before = {item: (item.x(), item.y()) for item in items}
        for item in items:
            item.setPos(item.x() + dx, item.y() + dy)
        after = {item: (item.x(), item.y()) for item in items}

        if self.undo_stack is not None:
            self.undo_stack.push(MoveItemsCommand(before, after, self.tr("Move"), mergeable=is_continuation))

    # -- selection handle geometry --------------------------------------------

    def _selected_transformable_item(self):
        scene = self.scene()
        if scene is None:
            return None
        selected = [i for i in scene.selectedItems() if i.data(LAYER_ROLE) not in (LAYER_CUT, LAYER_FOLD)]
        return selected[0] if len(selected) == 1 else None

    def _view_scale(self) -> float:
        return max(self.transform().m11(), 1e-6)

    def _handle_geometry(self, item):
        """Returns (corners[4 QPointF in scene coords], rotate_handle_pos, origin_scene).

        The frame is always an axis-aligned box in scene/screen space, even
        when the item itself is rotated -- it does not tilt with the item
        (like PowerPoint's selection box for a rotated shape). Corners are
        ordered TL, TR, BR, BL.

        Sized to opaque_content_rect(item), not the item's plain
        boundingRect() -- for a pixmap layer left mostly transparent by Clip
        Layers/Bake Layers, boundingRect() is still the old, pre-clip
        extent, which made the frame (and its resize handles) balloon out
        over empty space. The rotate/scale pivot (origin_scene, below)
        deliberately still comes from transformOriginPoint() rather than
        this tighter rect -- only what's drawn/grabbed changes, not the
        actual resize/rotate math."""
        poly = item.mapToScene(opaque_content_rect(item))
        xs = [poly[i].x() for i in range(4)]
        ys = [poly[i].y() for i in range(4)]
        left, right = min(xs), max(xs)
        top, bottom = min(ys), max(ys)
        corners = [
            QPointF(left, top),
            QPointF(right, top),
            QPointF(right, bottom),
            QPointF(left, bottom),
        ]
        top_mid = (corners[0] + corners[1]) / 2
        offset = ROTATE_HANDLE_OFFSET_PIXELS / self._view_scale()
        rotate_pos = top_mid + QPointF(0, -offset)  # screen-aligned frame: "up" is just scene -y
        origin_scene = item.mapToScene(item.transformOriginPoint())
        return corners, rotate_pos, origin_scene

    def _edge_segments(self, item):
        """Returns [(a, b, drag_kind), ...] for the 4 frame edges -- top/bottom
        resize height only ("scale-y"), left/right resize width only
        ("scale-x"), matching corners [TL, TR, BR, BL] from _handle_geometry."""
        corners, _, _ = self._handle_geometry(item)
        tl, tr, br, bl = corners
        return [
            (tl, tr, "scale-y"),
            (tr, br, "scale-x"),
            (br, bl, "scale-y"),
            (bl, tl, "scale-x"),
        ]

    # -- painting ---------------------------------------------------------------

    def drawForeground(self, painter, rect) -> None:
        super().drawForeground(painter, rect)
        self._draw_unprintable_area_overlay(painter)

        item = self._selected_transformable_item()
        if item is None:
            return

        corners, rotate_pos, _ = self._handle_geometry(item)
        handle_r = (HANDLE_PIXELS / 2) / self._view_scale()
        rotate_r = ROTATE_HANDLE_RADIUS_PIXELS / self._view_scale()

        # The connecting frame line itself -- drawn from the same (tight,
        # opaque_content_rect-based) corners as the handles below, so it
        # can never show a stale/bigger size than they do. This replaces
        # relying on each item's own default Qt-drawn selected-state
        # decoration (a dashed box around the plain boundingRect(), with no
        # idea of what's actually opaque) -- see DesignPixmapItem etc. in
        # canvas/items.py, which suppress that default decoration entirely.
        frame_pen = QPen(QColor("#1976d2"))
        frame_pen.setCosmetic(True)
        frame_pen.setWidthF(1.0)
        frame_pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(frame_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPolygon(QPolygonF(corners))

        pen = QPen(QColor("#1976d2"))
        pen.setCosmetic(True)
        pen.setWidthF(1.5)
        painter.setPen(pen)
        painter.setBrush(QBrush(QColor("#ffffff")))

        for corner in corners:
            painter.drawRect(corner.x() - handle_r, corner.y() - handle_r, handle_r * 2, handle_r * 2)

        top_mid = (corners[0] + corners[1]) / 2
        painter.drawLine(QLineF(top_mid, rotate_pos))
        painter.drawEllipse(rotate_pos, rotate_r, rotate_r)

    def _unprintable_area_path(self) -> QPainterPath:
        """Everything within the scene rect that Export Print PNG would
        clip away -- outside the cut outline, or inside a cutout."""
        scene = self.scene()
        if scene is None:
            return QPainterPath()
        printable = scene.template_clip_path()
        if printable.isEmpty():
            return QPainterPath()
        whole_scene = QPainterPath()
        whole_scene.addRect(scene.sceneRect())
        return whole_scene.subtracted(printable)

    def _draw_unprintable_area_overlay(self, painter) -> None:
        """Hatch out everything _unprintable_area_path() covers, so only
        what would actually appear in the exported PNG looks "normal" on
        the canvas. Screen-only: drawn in drawForeground, never exported."""
        unprintable = self._unprintable_area_path()
        if unprintable.isEmpty():
            return

        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(120, 120, 120, 90)))
        painter.drawPath(unprintable)
        painter.setBrush(QBrush(QColor(60, 60, 60, 140), Qt.BrushStyle.BDiagPattern))
        painter.drawPath(unprintable)
        painter.restore()

    # -- mouse interaction --------------------------------------------------------

    def mousePressEvent(self, event) -> None:
        if self._probing_color and event.button() == Qt.MouseButton.LeftButton:
            self._finish_color_probe(event.pos())
            event.accept()
            return
        if self._grayscale_effect is not None:
            # Read-only while previewing in grayscale -- see
            # set_grayscale_preview(). setInteractive(False) already stops
            # Qt's own click-to-select/drag; skip our own handle-drag
            # hit-testing too rather than relying on "nothing is selected"
            # alone.
            super().mousePressEvent(event)
            return

        item = self._selected_transformable_item()
        if item is not None and event.button() == Qt.MouseButton.LeftButton:
            scene_pos = self.mapToScene(event.pos())
            kind = self._hit_test(item, scene_pos)
            if kind is not None:
                self._begin_drag(kind, item, scene_pos)
                event.accept()
                return
        # No handle grabbed -- let Qt's native item dragging happen (if the
        # click landed on a movable item), then remember where every
        # selected item started so a completed native move can be pushed
        # onto the undo stack in mouseReleaseEvent. Harmless if nothing
        # actually gets dragged (the before/after comparison there is a
        # no-op).
        #
        # **After super(), not before, and that is the whole point.** It is
        # super() that selects the item under the cursor, so a snapshot
        # taken first saw the *previous* selection -- empty when clicking
        # straight onto an unselected item. Dragging something in one
        # motion, which is how anyone actually moves a layer, therefore
        # produced no undo entry at all: reported as "undo does not work
        # when moving, maybe I move too fast". Speed had nothing to do with
        # it. The positions are unchanged by selection, so reading them a
        # moment later is the same snapshot, only of the right items.
        super().mousePressEvent(event)
        scene = self.scene()
        self._pre_move_positions = {i: (i.x(), i.y()) for i in scene.selectedItems()} if scene else {}

    def mouseMoveEvent(self, event) -> None:
        if self._drag_kind is not None:
            # Ctrl held means "constrained": snap to 10-degree steps while
            # rotating, or keep the aspect ratio (uniform) while scaling.
            constrained = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
            self._update_drag(self.mapToScene(event.pos()), constrained=constrained)
            event.accept()
            return
        self._update_hover_cursor(event.pos())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._drag_kind is not None:
            self._commit_drag_command()
            self._drag_kind = None
            self._drag_item = None
            event.accept()
            return
        super().mouseReleaseEvent(event)
        self._commit_native_move_command()

    def _commit_drag_command(self) -> None:
        item = self._drag_item
        before = self._drag_before_snapshot
        if item is None or before is None or self.undo_stack is None:
            return
        after = _snapshot(item)
        if after != before:
            text = "Rotate" if self._drag_kind == "rotate" else "Resize"
            self.undo_stack.push(TransformCommand(item, before, after, text))

    def _commit_native_move_command(self) -> None:
        before = self._pre_move_positions
        self._pre_move_positions = {}
        if not before or self.undo_stack is None:
            return
        after = {item: (item.x(), item.y()) for item in before}
        changed_before = {i: p for i, p in before.items() if after[i] != p}
        if changed_before:
            changed_after = {i: after[i] for i in changed_before}
            # mergeable=False: a full mouse press-drag-release only ever
            # pushes once (there's nothing to coalesce within one drag), so
            # merging could only ever combine this with an unrelated,
            # already-completed *previous* drag -- see MoveItemsCommand's
            # docstring for why that's wrong.
            self.undo_stack.push(MoveItemsCommand(changed_before, changed_after, "Move", mergeable=False))

    def _hit_test(self, item, scene_pos: QPointF) -> str | None:
        corners, rotate_pos, _ = self._handle_geometry(item)
        hit_r = (HANDLE_PIXELS / 2 + HANDLE_HIT_MARGIN_PIXELS) / self._view_scale()
        rotate_hit_r = (ROTATE_HANDLE_RADIUS_PIXELS + HANDLE_HIT_MARGIN_PIXELS) / self._view_scale()
        if _distance(scene_pos, rotate_pos) <= rotate_hit_r:
            return "rotate"
        for corner in corners:
            if _distance(scene_pos, corner) <= hit_r:
                return "scale"
        # Corners take priority (checked above); only fall back to an edge
        # (single-axis resize) if the click isn't already on a corner handle.
        edge_hit_margin = HANDLE_HIT_MARGIN_PIXELS / self._view_scale()
        for a, b, kind in self._edge_segments(item):
            if _distance_to_segment(scene_pos, a, b) <= edge_hit_margin:
                return kind
        return None

    def _update_hover_cursor(self, view_pos) -> None:
        item = self._selected_transformable_item()
        if item is None:
            self.unsetCursor()
            return
        kind = self._hit_test(item, self.mapToScene(view_pos))
        if kind == "scale":
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif kind == "scale-x":
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        elif kind == "scale-y":
            self.setCursor(Qt.CursorShape.SizeVerCursor)
        elif kind == "rotate":
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.unsetCursor()

    def _begin_drag(self, kind: str, item, scene_pos: QPointF) -> None:
        self._drag_kind = kind
        self._drag_item = item
        self._drag_before_snapshot = _snapshot(item)
        _, _, origin_scene = self._handle_geometry(item)
        self._drag_origin_scene = origin_scene
        self._drag_start_mouse_scene = scene_pos
        self._drag_start_scale_xy = get_item_scale(item)
        self._drag_start_rotation = item.rotation()
        self._drag_start_distance = _distance(scene_pos, origin_scene) or 1.0
        # Screen-aligned frame: measured directly in scene axes, not the
        # item's own (possibly rotated) local axes.
        self._drag_start_local = scene_pos - origin_scene

    def _update_drag(self, scene_pos: QPointF, constrained: bool = False) -> None:
        item = self._drag_item
        if item is None:
            return
        if self._drag_kind in ("scale", "scale-x", "scale-y"):
            start_sx, start_sy = self._drag_start_scale_xy
            if self._drag_kind == "scale" and constrained:
                # Ctrl: uniform scale, tracking the drag distance from center
                # the same way regardless of which axis moved more.
                distance = _distance(scene_pos, self._drag_origin_scene)
                factor = distance / self._drag_start_distance
                new_sx = _clamp_scale(start_sx * factor)
                new_sy = _clamp_scale(start_sy * factor)
            else:
                # Independent x/y resize -- measured directly in scene axes
                # (the frame is screen-aligned, not tilted with the item), so
                # if the item is rotated this can skew it rather than keep it
                # a clean rectangle: sx/sy always scale the item's own
                # pre-rotation local axes (set_item_scale), but here they're
                # driven straight from raw scene-space drag deltas instead of
                # first un-rotating them into those local axes. At rotation
                # multiples of 180 this lines up perfectly; at other angles
                # (e.g. exactly 90) a screen-horizontal drag ends up growing
                # sx, which then renders as a vertical on-screen change. A
                # corner drag updates both axes; an edge (frame line) drag
                # updates only the axis it belongs to.
                local = scene_pos - self._drag_origin_scene
                eps = 1e-6
                rx = abs(local.x()) / max(abs(self._drag_start_local.x()), eps)
                ry = abs(local.y()) / max(abs(self._drag_start_local.y()), eps)
                new_sx = _clamp_scale(start_sx * rx) if self._drag_kind in ("scale", "scale-x") else start_sx
                new_sy = _clamp_scale(start_sy * ry) if self._drag_kind in ("scale", "scale-y") else start_sy
            set_item_scale(item, new_sx, new_sy)
        elif self._drag_kind == "rotate":
            start_angle = _angle_degrees(self._drag_origin_scene, self._drag_start_mouse_scene)
            current_angle = _angle_degrees(self._drag_origin_scene, scene_pos)
            new_rotation = self._drag_start_rotation + (current_angle - start_angle)
            if constrained:
                new_rotation = round(new_rotation / ROTATE_SNAP_DEGREES) * ROTATE_SNAP_DEGREES
            item.setRotation(new_rotation)
        self.viewport().update()


def _snapshot(item) -> dict:
    return {"rotation": item.rotation(), "scale": get_item_scale(item)}


def _distance(a: QPointF, b: QPointF) -> float:
    return math.hypot(a.x() - b.x(), a.y() - b.y())


def _distance_to_segment(point: QPointF, a: QPointF, b: QPointF) -> float:
    ab = QPointF(b.x() - a.x(), b.y() - a.y())
    length_sq = ab.x() ** 2 + ab.y() ** 2
    if length_sq < 1e-9:
        return _distance(point, a)
    ap = QPointF(point.x() - a.x(), point.y() - a.y())
    t = max(0.0, min(1.0, (ap.x() * ab.x() + ap.y() * ab.y()) / length_sq))
    closest = QPointF(a.x() + ab.x() * t, a.y() + ab.y() * t)
    return _distance(point, closest)


def _angle_degrees(origin: QPointF, point: QPointF) -> float:
    return math.degrees(math.atan2(point.y() - origin.y(), point.x() - origin.x()))


def _clamp_scale(value: float) -> float:
    return max(MIN_SCALE, min(MAX_SCALE, value))
