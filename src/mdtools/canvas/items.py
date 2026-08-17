"""Shared item helpers.

Every item on the scene is tagged via QGraphicsItem.setData(LAYER_ROLE, ...)
so exporters know whether it belongs on the "cut" path (the template
outline/fold lines, sent to Cricut as vector cut lines) or the "print"
layer (everything the user draws: text, images, decorative shapes).
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QImage, QPainterPath, QPen, QTransform
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsPathItem,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsTextItem,
    QStyle,
    QStyleOptionGraphicsItem,
)

LAYER_ROLE = 0
LAYER_CUT = "cut"
LAYER_PRINT = "print"
LAYER_FOLD = "fold"

# QGraphicsItem's own scale()/setScale() is uniform-only; independent x/y
# resize is tracked ourselves here and applied as a custom transform
# (anchored at transformOriginPoint, same pivot rotation uses) instead.
SCALE_ROLE = 2

# The item's own rect() at creation time, before any resize -- see
# set_item_scale's rect-item branch. Set once by add_rectangle()/
# add_ellipse(), never overwritten afterward.
BASE_RECT_ROLE = 3

# User-assigned display name for the Layers panel (Layers > Rename...).
# None means "no custom name" -- the panel falls back to its own
# auto-generated label (see layers_panel._label_for) rather than storing an
# empty string as if it meant something.
NAME_ROLE = 4

# Cached (pixmap.cacheKey(), QRectF) for opaque_content_rect() below --
# recomputing this by scanning pixel data on every repaint (the selection
# frame is redrawn continuously while dragging) would be far too slow for
# a large baked/clipped page, so it's computed once per distinct pixmap and
# invalidated only when the pixmap's own cacheKey() changes (a pixmap swap,
# e.g. Clip Layers' SetPixmapCommand, always produces a different key).
CONTENT_RECT_ROLE = 5

_RESIZABLE_SHAPES = (QGraphicsRectItem, QGraphicsEllipseItem)


class _NoDefaultSelectionDecoration:
    """Mixin: suppresses the base QGraphicsItem's own selected-state
    decoration -- a dashed rectangle the base class paints around
    item.boundingRect() whenever QStyle.State_Selected is set, regardless
    of item type (text/rect/ellipse/pixmap all do this the same way).

    This app draws its own selection frame in DesignView.drawForeground()
    instead, sized to opaque_content_rect() rather than the plain
    boundingRect() -- the default decoration has no way to know about that
    tighter rect, so a clipped/baked layer's default dashed box kept
    showing its old, pre-clip extent even after the custom frame/handles
    were correctly tightened. Stripping State_Selected from a *copy* of the
    style option before delegating to the base paint() only affects that
    decoration; it has no effect on the in-document text-cursor selection a
    QGraphicsTextItem might show (a completely separate mechanism, and one
    this app doesn't use anyway -- text is edited via the Properties panel,
    not in-canvas)."""

    def paint(self, painter, option, widget=None) -> None:
        if option.state & QStyle.StateFlag.State_Selected:
            option = QStyleOptionGraphicsItem(option)
            option.state &= ~QStyle.StateFlag.State_Selected
        super().paint(painter, option, widget)


class DesignTextItem(_NoDefaultSelectionDecoration, QGraphicsTextItem):
    pass


class DesignRectItem(_NoDefaultSelectionDecoration, QGraphicsRectItem):
    pass


class DesignEllipseItem(_NoDefaultSelectionDecoration, QGraphicsEllipseItem):
    pass


class DesignPixmapItem(_NoDefaultSelectionDecoration, QGraphicsPixmapItem):
    pass


def get_item_scale(item) -> tuple[float, float]:
    stored = item.data(SCALE_ROLE)
    return stored if stored else (1.0, 1.0)


def get_item_name(item) -> str | None:
    return item.data(NAME_ROLE)


def set_item_name(item, name: str | None) -> None:
    item.setData(NAME_ROLE, name.strip() or None if name else None)


def set_item_scale(item, sx: float, sy: float) -> None:
    item.setData(SCALE_ROLE, (sx, sy))

    if isinstance(item, _RESIZABLE_SHAPES):
        # A rectangle/ellipse is pure vector geometry with no resolution of
        # its own -- resizing it should change its actual shape, not stretch
        # a transform on top of a fixed-size rect. Scaling via transform
        # instead would leave boundingRect() reporting the small original
        # size forever, which is exactly what made Tools > Clip Layers'
        # rasterization of a scaled-up rectangle come out pixelated: the
        # pixmap it built was only ever sized for the tiny original rect,
        # then stretched on screen to the much bigger apparent size.
        base_rect = item.data(BASE_RECT_ROLE)
        if base_rect is None:
            base_rect = item.rect()
            item.setData(BASE_RECT_ROLE, base_rect)
        # rect() always starts at local (0, 0), so growing it in place would
        # keep the shape's top-left corner pinned at pos() and only expand
        # toward the bottom-right -- regardless of which handle was actually
        # dragged. Recording where the shape is *currently* centered before
        # touching anything, then re-anchoring transformOriginPoint() to the
        # new rect's own center and solving pos() for that same scene point,
        # keeps every resize growing/shrinking symmetrically around the
        # shape's own center instead -- and keeps the rotate pivot
        # (transformOriginPoint, native rotation always pivots there)
        # tracking the shape's real center rather than going stale at
        # whatever point it happened to be at when the item was created.
        old_center_scene = item.mapToScene(item.boundingRect().center())
        item.setRect(QRectF(0, 0, base_rect.width() * sx, base_rect.height() * sy))
        item.setTransform(QTransform())
        new_center_local = item.boundingRect().center()
        item.setTransformOriginPoint(new_center_local)
        item.setPos(old_center_scene - new_center_local)
        return

    origin = item.transformOriginPoint()
    transform = QTransform()
    transform.translate(origin.x(), origin.y())
    transform.scale(sx, sy)
    transform.translate(-origin.x(), -origin.y())
    item.setTransform(transform)


def opaque_content_rect(item) -> QRectF:
    """The tight bounding rect (in `item`'s own local coordinates, same
    space as `boundingRect()`) of its actually-visible content -- for a
    QGraphicsPixmapItem, that means the non-fully-transparent pixels, not
    the pixmap's full (possibly much larger) extent. Clip Layers/Bake Layers
    both make everything outside the printable area transparent rather than
    cropping the pixmap itself, so without this the selection frame/resize
    handles around a clipped layer stayed sized to its old, pre-clip extent
    -- most of it empty. Any other item type has no "transparent padding"
    concept, so this is just its plain `boundingRect()`."""
    if not isinstance(item, QGraphicsPixmapItem):
        return item.boundingRect()
    pixmap = item.pixmap()
    if pixmap.isNull():
        return item.boundingRect()

    cache_key = pixmap.cacheKey()
    cached = item.data(CONTENT_RECT_ROLE)
    if cached is not None and cached[0] == cache_key:
        return cached[1]

    bounds = _opaque_pixel_bounds(pixmap)
    rect = QRectF(*bounds) if bounds is not None else item.boundingRect()
    item.setData(CONTENT_RECT_ROLE, (cache_key, rect))
    return rect


def _opaque_pixel_bounds(pixmap) -> tuple[float, float, float, float] | None:
    """(x, y, width, height) of the smallest box containing every
    non-fully-transparent pixel, or None if the whole pixmap is
    transparent. Uses Pillow's (C-optimized) Image.getbbox() on the alpha
    channel rather than a manual per-pixel Python scan -- this needs to
    stay fast even for a whole baked page at BAKE_DPI. constBits() hands
    back a memoryview over the actual pixel buffer, so building the Pillow
    image is a plain reinterpretation of that memory, not a copy."""
    from PIL import Image as PILImage

    image = pixmap.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
    buffer = bytes(image.constBits())
    pil_image = PILImage.frombuffer("RGBA", (image.width(), image.height()), buffer, "raw", "RGBA", 0, 1)
    box = pil_image.getchannel("A").getbbox()
    if box is None:
        return None
    left, top, right, bottom = box
    return (left, top, right - left, bottom - top)


def make_template_outline(path: QPainterPath, layer: str = LAYER_CUT) -> QGraphicsPathItem:
    item = QGraphicsPathItem(path)
    pen = QPen()
    pen.setWidthF(0.5)
    pen.setCosmetic(True)
    if layer == LAYER_FOLD:
        pen.setColor("#3399ff")
        pen.setStyle(Qt.PenStyle.DashLine)
    else:
        pen.setColor("#ff0000")
    item.setPen(pen)
    item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
    # Kept on top of design items (not behind) so the cut/fold guides stay
    # visible while positioning artwork; both layers are hidden/shown
    # selectively at export time (see DesignScene.hidden_for_export), so
    # this has no effect on the exported SVG/PNG.
    item.setZValue(1000)
    item.setFlag(item.GraphicsItemFlag.ItemIsSelectable, False)
    item.setFlag(item.GraphicsItemFlag.ItemIsMovable, False)
    item.setData(LAYER_ROLE, layer)
    return item


def tag_print_layer(item) -> None:
    item.setData(LAYER_ROLE, LAYER_PRINT)
