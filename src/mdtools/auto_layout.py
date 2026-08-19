"""Laying a disc label out by itself: cover art across the label, the
MiniDisc logo on the cartridge's sliding dust shutter.

Used by the record-from-foobar flow, which by that point already knows the
album and has its cover art, so there is nothing left for the user to
decide about a first draft of the label.

Each function builds and positions an item and returns it; turning that
into an undoable command is left to the caller, the same split the rest of
this codebase uses (DesignScene.add_*() vs app_window.py pushing commands,
plan_clip_layers() vs the caller executing the plan).
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGraphicsPixmapItem

from mdtools.canvas.items import set_item_scale
from mdtools.canvas.scene import DesignScene
from mdtools.palette import readable_text_colour, region_colour

# The insertion-orientation triangle and its label sit in the top quarter or
# so of the label (see DesignScene.seed_disc_defaults), so that is the part
# of the cover they have to stay legible against -- not the cover as a whole.
INSERTION_MARK_BAND = 0.3

# How much of the slider sticker the logo is allowed to occupy. It is meant
# to be decoration on a 27.5x17.5mm sticker that still has to read as a
# slider label, not artwork in its own right.
LOGO_FILL = 0.7

# Gap between the logo and the slider's right edge, as a fraction of the
# sticker's width -- on the real 27.5mm sticker that is about 1.6mm. The
# logo sits against that edge rather than in the middle so the rest of the
# sticker stays free for whatever the label actually needs to say.
LOGO_RIGHT_MARGIN = 0.06


def _move_centre_to(item: QGraphicsPixmapItem, point: QPointF) -> None:
    """Moves `item` so its own centre lands on `point`.

    Solved through mapToScene rather than by setting pos() directly: the
    item's transform (from set_item_scale) means its local origin and its
    centre no longer differ by a fixed offset -- the same reasoning as
    DesignScene._replacement_pixmap_item's placement."""
    current = item.mapToScene(item.boundingRect().center())
    item.setPos(item.pos() + (point - current))


def _scene_size(item: QGraphicsPixmapItem) -> QRectF:
    """The item's footprint in scene coordinates, i.e. after scaling."""
    return item.mapToScene(item.boundingRect()).boundingRect()


def place_cover_on_label(scene: DesignScene, cover_art: bytes) -> QGraphicsPixmapItem | None:
    """Cover art scaled to cover the label completely, then centred on it.

    Scaled by the *larger* of the two ratios so no part of the label is left
    bare -- the overhang is what Tools > Clip Layers then trims away, which
    is why this deliberately overshoots rather than fitting inside."""
    rects = scene.cut_shape_rects()
    if not rects:
        return None
    item = scene.add_image_from_data(cover_art)
    if item is None:
        return None

    label = rects[0]
    natural = item.boundingRect()
    if natural.width() <= 0 or natural.height() <= 0:
        return item
    scale = max(label.width() / natural.width(), label.height() / natural.height())
    set_item_scale(item, scale, scale)
    _move_centre_to(item, label.center())
    return item


def insertion_mark_colour(cover_art: bytes) -> str:
    """Black or white, whichever stays readable over the top of the cover.

    Default black text on a dark sleeve is invisible, which is exactly what
    a full-bleed cover produces: the triangle and "INSERT THIS END" were
    still there, just unreadable."""
    return readable_text_colour(region_colour(cover_art, 0.0, INSERTION_MARK_BAND))


def recolour_insertion_mark(scene: DesignScene, cover_art: bytes) -> list:
    """Recolours every text layer on a freshly laid-out disc page.

    Every text item, rather than matching on their contents: this only ever
    runs immediately after the page was rebuilt from a template, when the
    insertion mark is all the text there is -- and matching on the literal
    string "INSERT THIS END" would quietly stop working in a translated
    build or the moment anyone edited it."""
    if not cover_art:
        return []
    colour = QColor(insertion_mark_colour(cover_art))
    recoloured = []
    for item in scene.print_items():
        if hasattr(item, "setDefaultTextColor"):
            item.setDefaultTextColor(colour)
            recoloured.append(item)
    return recoloured


def place_logo_on_slider(scene: DesignScene, logo: QGraphicsPixmapItem | None) -> QGraphicsPixmapItem | None:
    """Scales an already-added logo item to sit inside the slider sticker,
    against its right edge.

    Fitted by the *smaller* ratio, unlike the cover: this one has to stay
    within the sticker rather than cover it. Placed right-aligned (vertically
    centred) rather than dead centre, so the rest of the sticker stays free.
    Returns None (leaving the item alone) on a template with no slider."""
    rects = scene.cut_shape_rects()
    if logo is None or len(rects) < 2:
        return None

    slider = rects[1]
    natural = logo.boundingRect()
    if natural.width() <= 0 or natural.height() <= 0:
        return logo
    scale = min(
        slider.width() * LOGO_FILL / natural.width(),
        slider.height() * LOGO_FILL / natural.height(),
    )
    set_item_scale(logo, scale, scale)

    margin = slider.width() * LOGO_RIGHT_MARGIN
    placed_width = _scene_size(logo).width()
    _move_centre_to(
        logo,
        QPointF(slider.right() - margin - placed_width / 2, slider.center().y()),
    )
    return logo
