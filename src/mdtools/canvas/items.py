"""Shared item helpers.

Every item on the scene is tagged via QGraphicsItem.setData(LAYER_ROLE, ...)
so exporters know whether it belongs on the "cut" path (the template
outline/fold lines, sent to Cricut as vector cut lines) or the "print"
layer (everything the user draws: text, images, decorative shapes).
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFontMetricsF,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTransform,
)
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsPathItem,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsTextItem,
    QStyle,
    QStyleOptionGraphicsItem,
)

from mdtools.palette import readable_text_colour

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

# Text-layer shadow/glow, both plain bool flags -- see DesignTextItem.paint().
SHADOW_ROLE = 6
GLOW_ROLE = 7

# Cached (cache_key, QPixmap, QPointF) for the glow halo bitmap -- see
# _draw_glow(). Rebuilding it (a Gaussian blur over a rendered text mask)
# on every repaint would be far too slow while the item is being dragged;
# it's only ever rebuilt when the text/font/colour/wrap width it was built
# from actually changes.
GLOW_CACHE_ROLE = 8

# Same caching, for the (also now blurred, see _build_shadow_pixmap) shadow
# bitmap.
SHADOW_CACHE_ROLE = 9

_RESIZABLE_SHAPES = (QGraphicsRectItem, QGraphicsEllipseItem)

# How far the shadow copy sits from the real text -- proportional to the
# font's own line height ("lekko przesunięty w dół i w prawo, zależnie od
# wielkości czcionki"), not a fixed pixel count, so a large heading and a
# small caption both get a shadow that looks the same *relative* size.
_SHADOW_OFFSET_RATIO = 0.06
# A soft edge, not a soft *shadow* -- "very little" blur, explicitly much
# smaller than the glow's own, just enough to take the hard vector edge off
# the offset copy rather than turning it into a second halo.
_SHADOW_BLUR_RATIO = 0.025
_SHADOW_PADDING_RATIO = 0.15
_SHADOW_ALPHA = 255  # fully opaque -- only its edge is soft, not its body

_GLOW_BLUR_RATIO = 0.16
_GLOW_PADDING_RATIO = 0.5
# 0-255. Raised from an original 130: at that alpha and a tighter blur, the
# halo's peak was already well past half-faded by the time it cleared the
# glyph's own antialiased edge, which is what "almost invisible" was --
# reported directly, from the real running app. "Lekko półprzezroczyste"
# (a soft halo, not a solid outline) still holds -- 210 is short of opaque
# -- but the earlier value was closer to "barely there" than "soft".
_GLOW_ALPHA = 210


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
    """A shadow and/or a glow can be toggled on any text layer -- see
    get_text_shadow()/set_text_shadow() and get_text_glow()/set_text_glow()
    below. Both are painted here, underneath the real text, rather than
    baked into the document/pixmap: toggling either is then just a flag
    flip plus a repaint, with the item's actual text/font/colour untouched.

    paint() runs entirely in the item's own local, unrotated coordinate
    space -- Qt applies the item's rotation() as an outer transform before
    calling this. So the shadow's "down and to the right" offset, applied
    here as a plain local-space translate, rotates along with the text for
    free: a caption rotated 90 degrees to run down a spine gets a shadow
    that still falls toward the *text's* own lower-right, not the label's,
    exactly as a real light source fixed relative to the glyphs would.
    """

    def paint(self, painter, option, widget=None) -> None:
        if get_text_glow(self):
            _draw_glow(self, painter)
        if get_text_shadow(self):
            _draw_shadow(self, painter)
        super().paint(painter, option, widget)


class DesignRectItem(_NoDefaultSelectionDecoration, QGraphicsRectItem):
    pass


class DesignEllipseItem(_NoDefaultSelectionDecoration, QGraphicsEllipseItem):
    pass


class DesignPixmapItem(_NoDefaultSelectionDecoration, QGraphicsPixmapItem):
    pass


def get_text_shadow(item) -> bool:
    return bool(item.data(SHADOW_ROLE))


def set_text_shadow(item, enabled: bool) -> None:
    item.setData(SHADOW_ROLE, bool(enabled))
    item.update()


def get_text_glow(item) -> bool:
    return bool(item.data(GLOW_ROLE))


def set_text_glow(item, enabled: bool) -> None:
    item.setData(GLOW_ROLE, bool(enabled))
    item.update()


def _effect_colour(text_colour: QColor) -> QColor:
    """The shadow/glow colour, picked from the text's own colour: much
    lighter when the text is dark, much darker when it's light, so the
    effect always reads as added contrast rather than blending into
    whichever colour the text already is. Reuses palette.
    readable_text_colour()'s own black-or-white contrast pick -- passing
    the text colour itself as the "background" it must contrast against
    is exactly that rule turned around."""
    return QColor(readable_text_colour(text_colour.name()))


def _text_reference_size(item) -> float:
    """The font's own line height, in the same local px units item.font()
    is drawn in -- what "zależnie od wielkości czcionki" (proportional to
    the font size) is measured against for both effects below."""
    return QFontMetricsF(item.font()).height()


def _render_text_document(item, colour: QColor) -> QTextDocument:
    """A standalone copy of `item`'s text, laid out identically (same font,
    wrap width, zero margin) but in a different colour -- used to paint a
    shadow copy or a glow mask without touching the real item's own
    document/defaultTextColor (which would trigger Qt's own change
    notifications mid-paint)."""
    doc = QTextDocument()
    doc.setDefaultFont(item.font())
    doc.setDocumentMargin(0)
    text_width = item.textWidth()
    if text_width > 0:
        doc.setTextWidth(text_width)
    doc.setPlainText(item.toPlainText())
    cursor = QTextCursor(doc)
    cursor.select(QTextCursor.SelectionType.Document)
    char_format = QTextCharFormat()
    char_format.setForeground(QBrush(colour))
    cursor.mergeCharFormat(char_format)
    return doc


def _draw_shadow(item, painter) -> None:
    colour = _effect_colour(item.defaultTextColor())
    key = (item.toPlainText(), item.font().toString(), colour.name(), item.textWidth())
    cached = item.data(SHADOW_CACHE_ROLE)
    if cached is not None and cached[0] == key:
        pixmap, origin = cached[1], cached[2]
    else:
        pixmap, origin = _build_shadow_pixmap(item, colour)
        item.setData(SHADOW_CACHE_ROLE, (key, pixmap, origin))
    if pixmap is not None:
        painter.drawPixmap(origin, pixmap)


def _draw_glow(item, painter) -> None:
    colour = _effect_colour(item.defaultTextColor())
    key = (item.toPlainText(), item.font().toString(), colour.name(), item.textWidth())
    cached = item.data(GLOW_CACHE_ROLE)
    if cached is not None and cached[0] == key:
        pixmap, origin = cached[1], cached[2]
    else:
        pixmap, origin = _build_glow_pixmap(item, colour)
        item.setData(GLOW_CACHE_ROLE, (key, pixmap, origin))
    if pixmap is not None:
        painter.drawPixmap(origin, pixmap)


def _build_effect_pixmap(
    item, colour: QColor, *, blur_radius: float, padding: float, alpha: int
) -> tuple[QPixmap | None, QPointF]:
    """The shared machinery behind both the shadow and the glow: render the
    text as a solid opaque mask, blur its alpha channel by `blur_radius`
    (Pillow, same C-optimized approach _opaque_pixel_bounds already uses
    below rather than a manual per-pixel Python pass), then recolour it to
    `colour` and fade it to `alpha`. The two effects differ only in these
    three numbers -- a small blur and full alpha for the shadow (a soft
    *edge*, not a soft shadow), a larger blur and partial alpha for the
    glow (an actual halo) -- see their respective callers.

    Returns the pixmap and the scene-local point its top-left belongs at;
    None (no pixmap) means the text was blank, so there was nothing to
    render at all."""
    from PIL import Image as PILImage, ImageFilter

    rect = item.boundingRect()
    width = int(rect.width() + padding * 2) + 1
    height = int(rect.height() + padding * 2) + 1
    if width <= 0 or height <= 0:
        return None, QPointF(0, 0)

    mask_image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    mask_image.fill(Qt.GlobalColor.transparent)
    mask_painter = QPainter(mask_image)
    mask_painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    mask_painter.translate(padding, padding)
    _render_text_document(item, QColor("black")).drawContents(mask_painter)
    mask_painter.end()

    converted = mask_image.convertToFormat(QImage.Format.Format_RGBA8888)
    buffer = bytes(converted.constBits())
    pil_image = PILImage.frombuffer("RGBA", (converted.width(), converted.height()), buffer, "raw", "RGBA", 0, 1)
    alpha_channel = pil_image.getchannel("A")
    if alpha_channel.getbbox() is None:
        return None, QPointF(0, 0)

    blurred = alpha_channel.filter(ImageFilter.GaussianBlur(blur_radius)) if blur_radius > 0 else alpha_channel
    faded = blurred.point(lambda a: min(255, a * alpha // 255))
    coloured = PILImage.new("RGBA", blurred.size, (colour.red(), colour.green(), colour.blue(), 0))
    coloured.putalpha(faded)

    result = QImage(coloured.tobytes(), coloured.width, coloured.height, QImage.Format.Format_RGBA8888)
    result = result.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    origin = QPointF(rect.x() - padding, rect.y() - padding)
    return QPixmap.fromImage(result), origin


def _build_shadow_pixmap(item, colour: QColor) -> tuple[QPixmap | None, QPointF]:
    """The offset copy of the text that sits behind it, edges softened by a
    small blur -- see _build_effect_pixmap. Drawn as a cached bitmap now
    rather than live vector text (which is what this was before the blur
    was added -- there is no way to blur a single drawContents() call
    otherwise), the same tradeoff the glow effect already made: resolution-
    independent crispness traded for the ability to blur it at all."""
    size = _text_reference_size(item)
    padding = max(2.0, size * _SHADOW_PADDING_RATIO)
    blur_radius = max(0.4, size * _SHADOW_BLUR_RATIO)
    pixmap, origin = _build_effect_pixmap(item, colour, blur_radius=blur_radius, padding=padding, alpha=_SHADOW_ALPHA)
    if pixmap is None:
        return None, origin
    shift = max(1.0, size * _SHADOW_OFFSET_RATIO)
    return pixmap, QPointF(origin.x() + shift, origin.y() + shift)


def _build_glow_pixmap(item, colour: QColor) -> tuple[QPixmap | None, QPointF]:
    """The soft halo behind the text -- see _build_effect_pixmap. Drawn
    *behind* the real text (see DesignTextItem.paint), so what actually
    shows is the blur bleeding out past the glyphs' own edges."""
    size = _text_reference_size(item)
    padding = max(2.0, size * _GLOW_PADDING_RATIO)
    blur_radius = max(1.0, size * _GLOW_BLUR_RATIO)
    return _build_effect_pixmap(item, colour, blur_radius=blur_radius, padding=padding, alpha=_GLOW_ALPHA)


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
