from __future__ import annotations

import math

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QStyleOptionGraphicsItem,
)

from mdtools.canvas.geometry import chamfered_fillet_rect, left_rounded_rect
from mdtools.canvas.items import (
    LAYER_CUT,
    LAYER_FOLD,
    LAYER_ROLE,
    DesignEllipseItem,
    DesignPixmapItem,
    DesignRectItem,
    DesignTextItem,
    get_item_scale,
    make_template_outline,
    opaque_content_rect,
    set_item_scale,
    tag_print_layer,
)
from mdtools import app_settings
from mdtools.constants import mm_to_px
from mdtools.templates.models import CoverTemplate, DiscTemplate

# A plain string, not a QColor: QColor (like any Qt GUI type) must not be
# constructed before a QApplication/QGuiApplication exists, and this module
# is imported well before main() creates one.
DEFAULT_RECT_FILL_HEX = "#4a90d9"


class DesignScene(QGraphicsScene):
    """The design canvas for one label (disc or cover).

    Coordinates are in on-screen pixels (mm_to_px), origin top-left, matching
    the template's bounding box. The template outline is drawn as guide
    items tagged "cut"/"fold" so exporters can find them; regular design
    items (text/shapes/images added by the user) are tagged "print".
    """

    def __init__(self, template: DiscTemplate | CoverTemplate, parent=None):
        super().__init__(parent)
        self.template = template
        self._outline_items: list = []
        self._build_template_outline()

    # -- template outline -------------------------------------------------

    def _build_template_outline(self) -> None:
        for item in self._outline_items:
            self.removeItem(item)
        self._outline_items.clear()

        if isinstance(self.template, DiscTemplate):
            self._build_disc_outline(self.template)
        else:
            self._build_cover_outline(self.template)

    def _build_disc_outline(self, t: DiscTemplate) -> None:
        if t.shape == "full_label":
            self._build_full_label_outline(t)
            return

        w, h = mm_to_px(t.width_mm), mm_to_px(t.height_mm)
        path = chamfered_fillet_rect(w, h, mm_to_px(t.chamfer_mm), mm_to_px(t.fillet_mm))
        outline = make_template_outline(path, LAYER_CUT)
        self.addItem(outline)
        self._outline_items.append(outline)

        total_w = w
        if t.slider_width_mm > 0 and t.slider_height_mm > 0:
            slider_w, slider_h = mm_to_px(t.slider_width_mm), mm_to_px(t.slider_height_mm)
            slider_path = left_rounded_rect(slider_w, slider_h, mm_to_px(t.slider_corner_radius_mm))
            slider_x = w + mm_to_px(t.slider_gap_mm)
            slider_y = (h - slider_h) / 2  # vertically centered against the main disc shape
            slider_path.translate(slider_x, slider_y)
            slider_outline = make_template_outline(slider_path, LAYER_CUT)
            self.addItem(slider_outline)
            self._outline_items.append(slider_outline)
            total_w = slider_x + slider_w

        self.setSceneRect(QRectF(-10, -10, total_w + 20, h + 20))

    def _build_full_label_outline(self, t: DiscTemplate) -> None:
        """A plain rounded-rect label covering most of the disc's face
        (shape == "full_label"), with the write-protect slider's notch --
        plus the channel it travels down through -- cut out of the right
        edge as one continuous shape. See DiscTemplate's docstring for the
        buffer/travel geometry."""
        w, h = mm_to_px(t.width_mm), mm_to_px(t.height_mm)
        path = QPainterPath()
        if t.corner_radius_mm > 0:
            r = mm_to_px(t.corner_radius_mm)
            path.addRoundedRect(QRectF(0, 0, w, h), r, r)
        else:
            path.addRect(QRectF(0, 0, w, h))

        if t.slider_notch_width_mm > 0 and t.slider_notch_height_mm > 0:
            buffer = mm_to_px(t.slider_notch_buffer_mm)
            notch_w = mm_to_px(t.slider_notch_width_mm) + 2 * buffer
            notch_h = mm_to_px(t.slider_notch_height_mm) + 2 * buffer + mm_to_px(t.slider_travel_mm)
            notch_r = mm_to_px(t.slider_notch_corner_radius_mm) + buffer
            notch_path = left_rounded_rect(notch_w, notch_h, notch_r)
            # flush against the label's right edge -- expanding the notch by
            # `buffer` on all sides pushes its right edge past that edge,
            # which is harmless: there's no label material out there to
            # subtract from anyway.
            notch_path.translate(w - notch_w, mm_to_px(t.slider_notch_top_mm) - buffer)
            path = path.subtracted(notch_path)

        outline = make_template_outline(path, LAYER_CUT)
        self.addItem(outline)
        self._outline_items.append(outline)

        if t.slider_width_mm > 0 and t.slider_height_mm > 0:
            # A second, independent printable/cuttable slider-sticker shape
            # -- unlike the plain "sticker" shape's version of this (placed
            # beside the disc via slider_gap_mm), here it's positioned right
            # inside the notch it's meant to sit on, flush with the label's
            # right edge and aligned to the notch's own (unbuffered) top, so
            # it nests inside the buffer clearance rather than sitting in
            # unused canvas space.
            slider_w, slider_h = mm_to_px(t.slider_width_mm), mm_to_px(t.slider_height_mm)
            slider_path = left_rounded_rect(slider_w, slider_h, mm_to_px(t.slider_corner_radius_mm))
            slider_path.translate(w - slider_w, mm_to_px(t.slider_notch_top_mm))
            slider_outline = make_template_outline(slider_path, LAYER_CUT)
            self.addItem(slider_outline)
            self._outline_items.append(slider_outline)

        self.setSceneRect(QRectF(-10, -10, w + 20, h + 20))

    def _build_cover_outline(self, t: CoverTemplate) -> None:
        w, h = mm_to_px(t.width_mm), mm_to_px(t.height_mm)
        path = QPainterPath()
        if t.corner_radius_mm > 0:
            path.addRoundedRect(QRectF(0, 0, w, h), mm_to_px(t.corner_radius_mm), mm_to_px(t.corner_radius_mm))
        else:
            path.addRect(QRectF(0, 0, w, h))

        if t.cutout_width_mm > 0 and t.cutout_height_mm > 0 and t.fold_offsets_mm:
            path = path.subtracted(self._cutout_path(t, h_px=h))

        outline = make_template_outline(path, LAYER_CUT)
        self.addItem(outline)
        self._outline_items.append(outline)

        for offset_mm in t.fold_offsets_mm:
            x = mm_to_px(offset_mm)
            fold_path = QPainterPath()
            fold_path.moveTo(x, 0)
            fold_path.lineTo(x, h)
            fold_item = make_template_outline(fold_path, LAYER_FOLD)
            self.addItem(fold_item)
            self._outline_items.append(fold_item)

        self.setSceneRect(QRectF(-10, -10, w + 20, h + 20))

    @staticmethod
    def _cutout_path(t: CoverTemplate, *, h_px: float) -> QPainterPath:
        """A rounded-rect cutout, positioned from whichever fold line is on
        its cutout_side and the template's bottom edge, per CoverTemplate's
        docstring."""
        cutout_w = mm_to_px(t.cutout_width_mm)
        cutout_h = mm_to_px(t.cutout_height_mm)
        offset = mm_to_px(t.cutout_from_fold_mm)
        if t.cutout_side == "right":
            fold_x = mm_to_px(max(t.fold_offsets_mm))
            left = fold_x + offset
        else:
            fold_x = mm_to_px(min(t.fold_offsets_mm))
            left = fold_x - offset - cutout_w
        bottom = h_px - mm_to_px(t.cutout_from_bottom_mm)
        rect = QRectF(left, bottom - cutout_h, cutout_w, cutout_h)

        cutout_path = QPainterPath()
        radius = mm_to_px(t.cutout_radius_mm)
        if radius > 0:
            cutout_path.addRoundedRect(rect, radius, radius)
        else:
            cutout_path.addRect(rect)
        return cutout_path

    # -- item helpers -------------------------------------------------------

    def next_print_z(self) -> float:
        """New items go on top of everything else already placed."""
        existing = [i.zValue() for i in self.print_items()]
        return (max(existing) + 1) if existing else 0.0

    def _init_item(self, item) -> None:
        item.setFlag(item.GraphicsItemFlag.ItemIsMovable, True)
        item.setFlag(item.GraphicsItemFlag.ItemIsSelectable, True)
        item.setPos(self.sceneRect().center())
        item.setTransformOriginPoint(item.boundingRect().center())
        item.setZValue(self.next_print_z())
        tag_print_layer(item)
        self.addItem(item)

    def add_text(self, text: str = "Text") -> QGraphicsTextItem:
        item = DesignTextItem(text)
        # QGraphicsTextItem's "default" text color is whatever the ambient
        # widget palette's Text role resolves to -- white under a dark
        # theme/OS setting. Labels print on light media, so force a real,
        # always-visible default rather than inheriting that; explicitly
        # colored/loaded items (project_io.py) override this immediately.
        item.setDefaultTextColor(QColor("black"))
        self._init_item(item)
        return item

    def add_rectangle(self) -> QGraphicsRectItem:
        size_w, size_h = mm_to_px(20), mm_to_px(14)
        item = DesignRectItem(0, 0, size_w, size_h)
        fill = QColor(DEFAULT_RECT_FILL_HEX)
        item.setBrush(QBrush(fill))
        # frame matches the fill exactly -- Properties panel's fill-color
        # picker keeps this in sync (see properties_panel._set_fill_color),
        # so this default has to start in sync with that too.
        item.setPen(QPen(fill))
        self._init_item(item)
        return item

    def add_ellipse(self) -> QGraphicsEllipseItem:
        size = mm_to_px(20)
        item = DesignEllipseItem(0, 0, size, size)
        self._init_item(item)
        return item

    def add_image(self, path: str) -> QGraphicsPixmapItem | None:
        pixmap = QPixmap(path)
        if pixmap.isNull():
            return None
        return self._add_pixmap_item(pixmap)

    def add_image_from_data(self, data: bytes) -> QGraphicsPixmapItem | None:
        pixmap = QPixmap()
        if not pixmap.loadFromData(data):
            return None
        return self._add_pixmap_item(pixmap)

    def _add_pixmap_item(self, pixmap: QPixmap) -> QGraphicsPixmapItem:
        item = DesignPixmapItem(pixmap)
        self._init_item(item)
        return item

    def seed_disc_defaults(self) -> None:
        """Add the conventional "insert this end first" triangle + label
        near the top of a fresh disc label. Both are ordinary, fully-editable
        text items -- move, restyle, or delete them like anything else."""
        triangle = self.add_text("▲")
        triangle_font = triangle.font()
        triangle_font.setPointSizeF(20)
        triangle.setFont(triangle_font)
        triangle.setTransformOriginPoint(triangle.boundingRect().center())

        label = self.add_text("INSERT THIS END")

        # the *disc shape's* own width, not sceneRect().width() -- that also
        # spans a slider label (if this template has one), which would
        # otherwise pull this centering off the actual disc.
        template_w = mm_to_px(self.template.width_mm)
        top_y = 4

        triangle.setPos((template_w - triangle.boundingRect().width()) / 2, top_y)
        label.setPos((template_w - label.boundingRect().width()) / 2, top_y + triangle.boundingRect().height())

    def remove_item(self, item) -> None:
        if item is not None and item.scene() is self:
            self.removeItem(item)

    def neighbor_above(self, item):
        """The item directly in front of `item` in the print stack -- what
        move_item_up() would swap with -- or None if already topmost."""
        ordered = self.print_items()
        idx = ordered.index(item)
        return ordered[idx - 1] if idx > 0 else None

    def neighbor_below(self, item):
        """The item directly behind `item` in the print stack -- what
        move_item_down() would swap with -- or None if already at the back."""
        ordered = self.print_items()
        idx = ordered.index(item)
        return ordered[idx + 1] if idx < len(ordered) - 1 else None

    def move_item_up(self, item) -> None:
        """Bring `item` one step closer to the front (topmost first)."""
        neighbor = self.neighbor_above(item)
        if neighbor is not None:
            self._swap_z(item, neighbor)

    def move_item_down(self, item) -> None:
        """Send `item` one step further toward the back."""
        neighbor = self.neighbor_below(item)
        if neighbor is not None:
            self._swap_z(item, neighbor)

    @staticmethod
    def _swap_z(a, b) -> None:
        a_z, b_z = a.zValue(), b.zValue()
        a.setZValue(b_z)
        b.setZValue(a_z)

    def print_items(self) -> list:
        """Items the user placed, ordered topmost-first (matches on-screen stacking)."""
        return [i for i in self.items() if i.data(LAYER_ROLE) not in (LAYER_CUT, LAYER_FOLD)]

    def cut_items(self) -> list:
        """All template guide items: the cut outline plus fold/score lines."""
        return [i for i in self.items() if i.data(LAYER_ROLE) in (LAYER_CUT, LAYER_FOLD)]

    def cut_only_items(self) -> list:
        """Just the actual cut outline -- not fold/score lines."""
        return [i for i in self.items() if i.data(LAYER_ROLE) == LAYER_CUT]

    def fold_items(self) -> list:
        """Just the fold/score guide lines -- not the cut outline."""
        return [i for i in self.items() if i.data(LAYER_ROLE) == LAYER_FOLD]

    def template_clip_path(self) -> QPainterPath:
        """The union of all cut-outline shapes (not fold lines) that bounds
        where printed artwork should actually be visible. Most templates
        have just one (the main label); a disc-with-slider template has two
        independent shapes, both of which should stay printable."""
        combined = QPainterPath()
        for item in self._outline_items:
            if item.data(LAYER_ROLE) == LAYER_CUT:
                combined = combined.united(item.mapToScene(item.path()))
        return combined

    def cut_shape_rects(self) -> list[QRectF]:
        """Each cut outline's own bounding rect, in the order the template
        built them: the main label first, then the slider sticker where a
        template has one.

        template_clip_path() unions the same shapes, which is what clipping
        wants and exactly wrong for *placing* something on one of them --
        fitting artwork to the union of a disc label and a slider sticker
        would size it to a rectangle spanning both."""
        return [
            item.mapToScene(item.path()).boundingRect()
            for item in self._outline_items
            if item.data(LAYER_ROLE) == LAYER_CUT
        ]

    def fold_panel_rects(self) -> list[QRectF]:
        """The cut shape split at its fold lines -- on a J-card that is
        front, spine and back, left to right.

        Empty for a template with no folds (every disc label), so callers
        can treat "no panels" and "not a cover" as the same case."""
        offsets = sorted(getattr(self.template, "fold_offsets_mm", None) or [])
        rects = self.cut_shape_rects()
        if not offsets or not rects:
            return []

        bounds = rects[0]
        edges = [bounds.left()] + [bounds.left() + mm_to_px(offset) for offset in offsets] + [bounds.right()]
        return [
            QRectF(left, bounds.top(), right - left, bounds.height())
            for left, right in zip(edges, edges[1:])
            if right > left
        ]

    def plan_clip_layers(self) -> tuple[list, list[tuple], list[tuple]]:
        """Tools > "Clip Layers": for every print layer, decide what to do
        against the template's printable area (template_clip_path()). A
        layer entirely outside it gets removed outright, whatever type it
        is. An image or rectangle layer only partially inside gets rebuilt
        as a new pixmap with everything outside made transparent -- the
        exact same clipping PNG export applies at render time (see
        png_export.export_png), baked into the layer itself instead of
        only showing up at export. A layer fully inside, or a layer of
        some other type (text) only partially inside -- there's no
        meaningful way to "clip" text here -- is left untouched.

        Returns (items_to_remove, images_to_reclip, shapes_to_rasterize):
        - images_to_reclip: (item, new_pixmap) pairs -- same
          QGraphicsPixmapItem, just a new pixmap.
        - shapes_to_rasterize: (old_item, new_item) pairs -- a rectangle
          can't hold a pixmap, so it's replaced outright by a fresh,
          fully-positioned QGraphicsPixmapItem (not yet added to the
          scene) showing its rasterized, clipped appearance.
        Nothing is mutated by this call; the caller applies these via
        undoable commands.
        """
        clip_path = self.template_clip_path()
        items_to_remove = []
        images_to_reclip = []
        shapes_to_rasterize = []

        for item in self.print_items():
            item_path = QPainterPath()
            item_path.addPolygon(item.mapToScene(item.boundingRect()))
            item_path.closeSubpath()

            if not clip_path.intersects(item_path):
                items_to_remove.append(item)
            elif not clip_path.contains(item_path):
                if isinstance(item, QGraphicsPixmapItem):
                    images_to_reclip.append((item, self._rasterized_pixmap(item, clip_path)))
                elif isinstance(item, QGraphicsRectItem):
                    shapes_to_rasterize.append((item, self._replacement_pixmap_item(item, clip_path)))

        return items_to_remove, images_to_reclip, shapes_to_rasterize

    @staticmethod
    def _rasterized_pixmap(item, clip_path_scene: QPainterPath, supersample: float = 1.0) -> QPixmap:
        """`item`'s own appearance -- painted exactly as scene.render()
        would paint it, via its own paint() -- with everything outside the
        (scene-space) clip path made transparent. Works for any item type
        whose local bounding rect starts at (0, 0), which every item this
        app creates does (see DesignScene._init_item).

        `supersample` bakes extra pixel density into the backing pixmap
        (painted at `supersample`x size, then scaled back down by whatever
        calls this) -- see shape_raster_supersample() below for why shapes
        need this and images don't."""
        local_rect = item.boundingRect()
        pixmap = QPixmap(
            max(1, round(local_rect.width() * supersample)), max(1, round(local_rect.height() * supersample))
        )
        pixmap.fill(Qt.GlobalColor.transparent)

        inverse, _ = item.sceneTransform().inverted()
        local_clip = inverse.map(clip_path_scene)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.scale(supersample, supersample)
        painter.setClipPath(local_clip)
        item.paint(painter, QStyleOptionGraphicsItem(), None)
        painter.end()
        return pixmap

    # Unlike a photo (which already carries its own, usually print-quality,
    # native pixel resolution), a rectangle/ellipse has none of its own --
    # rasterizing it at the screen's plain scene-unit size looks fine on
    # screen but comes out soft/blocky once printed at export DPI or
    # zoomed in further. Baking in extra pixel density up front (then
    # displaying it back down to the shape's real footprint via the same
    # scale mechanism drag-resize and serialization already use -- see
    # _replacement_pixmap_item) gives a clipped shape the same resolution
    # headroom a real image gets from its own native size, comfortably
    # above the default export DPI's print quality.
    #
    # A classmethod, not a fixed class attribute, since both DPIs it's
    # derived from are user-configurable (Window > Settings...) and can
    # change during a running session -- a value computed once at class
    # definition time would go stale the moment the user changed either
    # setting.
    @classmethod
    def shape_raster_supersample(cls) -> int:
        return math.ceil(app_settings.default_export_dpi() / app_settings.screen_dpi())

    @classmethod
    def _replacement_pixmap_item(cls, item, clip_path_scene: QPainterPath) -> QGraphicsPixmapItem:
        """A new, fully-positioned (but not yet scene-attached)
        QGraphicsPixmapItem standing in for `item`, showing its rasterized,
        clipped appearance -- for shape layers (e.g. rectangles) that can't
        hold a pixmap themselves."""
        supersample = cls.shape_raster_supersample()
        pixmap = cls._rasterized_pixmap(item, clip_path_scene, supersample=supersample)
        new_item = DesignPixmapItem(pixmap)
        new_item.setFlag(new_item.GraphicsItemFlag.ItemIsMovable, True)
        new_item.setFlag(new_item.GraphicsItemFlag.ItemIsSelectable, True)
        # An image being clipped keeps its selection for free (SetPixmapCommand
        # swaps the pixmap on the *same* item) -- a shape being rasterized here
        # instead ends up as a brand new item replacing the old one, so its
        # selected state has to be carried over explicitly, or a selected
        # rectangle would visibly lose its selection frame the moment Clip
        # Layers ran (and, once re-selected by clicking, the tight-frame fix
        # above never even got exercised on the rectangle path in practice).
        new_item.setSelected(item.isSelected())
        new_item.setRotation(item.rotation())
        origin = new_item.boundingRect().center()
        new_item.setTransformOriginPoint(origin)
        # The pixmap is `supersample`x bigger than `item`'s own footprint
        # (see shape_raster_supersample() above) -- scale it back down by
        # the inverse factor so it displays at exactly the size `item` had.
        # get_item_scale(item) would be wrong here: for a rectangle/ellipse
        # that factor is already baked into `item.boundingRect()` (and so
        # into this pixmap's size) by set_item_scale's rect-resizing
        # branch, so re-applying it on top would double-scale the result.
        inv = 1.0 / supersample
        set_item_scale(new_item, inv, inv)
        # item.pos() itself isn't reusable here -- the new pixmap's native
        # size differs from item's, so the two items' local origins don't
        # line up the way their centers do. Both set_item_scale (above) and
        # setRotation pivot around `origin`, which stays fixed under both --
        # so matching new_item's *center* in scene space to item's keeps it
        # exactly where item was, rotation included.
        old_center_scene = item.mapToScene(item.boundingRect().center())
        new_item.setPos(old_center_scene - origin)
        cls._repivot_to_opaque_content(new_item, inv, inv)
        new_item.setZValue(item.zValue())
        tag_print_layer(new_item)
        return new_item

    @staticmethod
    def _repivot_to_opaque_content(item, sx: float, sy: float) -> None:
        """Re-anchors `item`'s rotate/scale pivot (transformOriginPoint) to
        the center of its own opaque_content_rect(), instead of wherever it
        was anchored before this runs -- e.g. after Clip Layers/Bake
        Layers, most of a pixmap's own boundingRect() can be transparent
        padding, and rotating/resizing around the middle of that empty
        space (rather than around what's actually visible) looks wrong,
        pivoting the shape around a point nowhere near it on screen.

        `item` must already be correctly positioned -- anchored at its
        plain boundingRect().center(), which both call sites above set up
        first -- before this runs; it re-anchors the pivot *without moving
        any already-correctly-placed pixels*, by reading where the new
        anchor point currently, correctly, maps to in scene space, then
        solving pos() for that same mapping under the new anchor. `(sx,
        sy)` is the scale already in effect, needed to rebuild the
        transform around the new anchor (set_item_scale reads
        transformOriginPoint() internally, so simply calling
        setTransformOriginPoint() alone would leave the already-baked
        transform matrix pointing at the old anchor)."""
        content_origin = opaque_content_rect(item).center()
        content_center_scene = item.mapToScene(content_origin)
        item.setTransformOriginPoint(content_origin)
        set_item_scale(item, sx, sy)
        item.setPos(content_center_scene - content_origin)

    def plan_bake_layers(self, flattened_image: QImage) -> tuple[list, QGraphicsPixmapItem | None]:
        """Tools > "Bake Layers": flattens every print layer into a single
        replacement pixmap item. `flattened_image` is expected to be
        exactly what io.png_export.render_scene_to_image(self) produces --
        the same rendering path Export Print PNG uses, so "baked" and
        "exported" artwork can never visually diverge (same reasoning as
        Clip Layers reusing the item's own paint() call above).

        Returns (old_items, new_item) -- ([], None) if there's nothing to
        bake. Nothing is mutated here; the caller applies the result via
        undoable commands, same pattern as plan_clip_layers()."""
        old_items = self.print_items()
        if not old_items:
            return [], None

        new_item = DesignPixmapItem(QPixmap.fromImage(flattened_image))
        new_item.setFlag(new_item.GraphicsItemFlag.ItemIsMovable, True)
        new_item.setFlag(new_item.GraphicsItemFlag.ItemIsSelectable, True)
        origin = new_item.boundingRect().center()
        new_item.setTransformOriginPoint(origin)
        # flattened_image was rendered at the *scene rect's* size scaled up
        # by whatever dpi render_scene_to_image() used -- scale back down
        # (derived from the ratio of sizes, not assumed to be any particular
        # DPI) so the baked layer displays at the plain scene-unit footprint
        # the original layers occupied. Same oversized-raster-plus-
        # compensating-scale trick as the rectangle rasterization above; see
        # there for why the position has to go through the item's *center*
        # (here, the sceneRect's center) rather than a direct pos() copy.
        rect = self.sceneRect()
        inv = rect.width() / flattened_image.width()
        set_item_scale(new_item, inv, inv)
        new_item.setPos(rect.center() - origin)
        self._repivot_to_opaque_content(new_item, inv, inv)
        new_item.setZValue(self.next_print_z())
        tag_print_layer(new_item)
        return old_items, new_item

    def hidden_for_export(self, *, show_print: bool, show_cut: bool, show_fold: bool = False):
        """Context manager: temporarily show only the requested layer(s).

        show_cut and show_fold are independent -- the cut outline and the
        fold/score lines can be shown/hidden separately (SVG export shows
        only the cut outline; fold lines are an on-canvas design aid only).
        """
        return _LayerVisibility(self, show_print=show_print, show_cut=show_cut, show_fold=show_fold)

    def deselected_for_export(self):
        """Context manager: temporarily clear selection, restoring it
        afterward. scene.render() (used by both PNG/SVG export) paints each
        item's own selected-state decoration (Qt's default dashed outline)
        exactly like on-screen painting does -- without this, exporting
        while something is selected bakes that outline into the file."""
        return _Deselected(self)


class _LayerVisibility:
    def __init__(self, scene: DesignScene, *, show_print: bool, show_cut: bool, show_fold: bool):
        self._scene = scene
        self._show_print = show_print
        self._show_cut = show_cut
        self._show_fold = show_fold
        self._previous: dict = {}

    def __enter__(self):
        for item in self._scene.print_items():
            self._previous[item] = item.isVisible()
            item.setVisible(self._show_print)
        for item in self._scene.cut_only_items():
            self._previous[item] = item.isVisible()
            item.setVisible(self._show_cut)
        for item in self._scene.fold_items():
            self._previous[item] = item.isVisible()
            item.setVisible(self._show_fold)
        return self

    def __exit__(self, exc_type, exc, tb):
        for item, was_visible in self._previous.items():
            item.setVisible(was_visible)


class _Deselected:
    def __init__(self, scene: DesignScene):
        self._scene = scene
        self._selected: list = []

    def __enter__(self):
        self._selected = self._scene.selectedItems()
        self._scene.clearSelection()
        return self

    def __exit__(self, exc_type, exc, tb):
        for item in self._selected:
            item.setSelected(True)
