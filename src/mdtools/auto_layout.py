"""Laying a disc label out by itself: cover art across the label, the
MiniDisc logo on the cartridge's sliding dust shutter -- and, for the small
chamfered "sticker" template, a full text-and-palette treatment besides
(build_sticker_label(), at the bottom of this module).

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
from PySide6.QtWidgets import QGraphicsItem, QGraphicsPixmapItem

from mdtools.canvas.items import set_item_scale
from mdtools.canvas.scene import DesignScene
from mdtools.constants import mm_to_px
from mdtools.jcard_layout import _filled_rect, _move_top_left_to, _text
from mdtools.palette import accent_colour, dominant_colour, readable_text_colour, region_colour
from mdtools.project import ProjectMetadata

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

# The small chamfered "sticker" disc label (kind="disc", shape="sticker")
# is 37x52mm -- a fraction of the full-face label's own size, and far too
# small for that label's bare cover-plus-mark treatment to carry any text
# at all. build_sticker_label() gives it two solid bands instead: one at
# the top for the insertion mark, one at the bottom for Artist / a rule /
# Album + the year, in the same background/accent/ink palette and
# heading+rule motif jcard_layout.place_back() uses for the case's own
# back panel -- just scaled down to fit a label a fraction of that panel's
# size, so it gets its own constants rather than sharing place_back()'s.
STICKER_TOP_BAND_MM = 5.0
STICKER_BOTTOM_BAND_MM = 12.0
STICKER_BAND_PADDING_MM = 1.0
STICKER_MARK_PADDING_MM = 0.5
STICKER_ARTIST_MM = 5.0
STICKER_RULE_MM = 0.4
STICKER_FOOTER_MM = 3.6
# Deliberately smaller than STICKER_FOOTER_MM -- see _sticker_bottom_band's
# own note on why the year needs a shorter area than the album title does.
STICKER_YEAR_MM = 2.4
STICKER_ROW_GAP_MM = 0.5
# How much of the bottom band's own width the year gets, right-aligned,
# with the album line taking the rest -- close to how the two actually
# shared that row in the example this was built from.
STICKER_YEAR_WIDTH_FRACTION = 0.32


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


def _cover_rect_with_image(scene: DesignScene, cover_art: bytes, rect: QRectF) -> QGraphicsPixmapItem | None:
    """Cover art scaled to cover `rect` completely, then centred on it.

    Scaled by the *larger* of the two ratios so no part of `rect` is left
    bare -- the overhang is what Tools > Clip Layers then trims away, which
    is why this deliberately overshoots rather than fitting inside."""
    item = scene.add_image_from_data(cover_art)
    if item is None:
        return None
    natural = item.boundingRect()
    if natural.width() <= 0 or natural.height() <= 0:
        return item
    scale = max(rect.width() / natural.width(), rect.height() / natural.height())
    set_item_scale(item, scale, scale)
    _move_centre_to(item, rect.center())
    return item


def place_cover_on_label(scene: DesignScene, cover_art: bytes) -> QGraphicsPixmapItem | None:
    """Cover art scaled to cover the label completely, then centred on it."""
    rects = scene.cut_shape_rects()
    if not rects:
        return None
    return _cover_rect_with_image(scene, cover_art, rects[0])


def place_cover_on_slider(scene: DesignScene, cover_art: bytes) -> QGraphicsPixmapItem | None:
    """The same treatment as place_cover_on_label(), covering the slider
    sticker's own cut shape instead of the disc label's -- used by the
    small "MiniDisc Disc Label (with Slider)" sticker template, whose
    slider carries a snippet of the cover rather than sitting bare under
    just the MiniDisc logo (compare the full-face label's own slider,
    which place_logo_on_slider() places the logo on directly). None on a
    template with no slider shape, same convention place_logo_on_slider()
    already follows."""
    rects = scene.cut_shape_rects()
    if len(rects) < 2:
        return None
    return _cover_rect_with_image(scene, cover_art, rects[1])


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


# --- the small "sticker" disc label: a full text-and-palette treatment ------


def _fit_group_into_band(
    items: list[QGraphicsItem], band: QRectF, *, gap_mm: float = 0.0, horizontal: bool = False
) -> None:
    """Scales `items` uniformly -- by whichever factor is small enough to
    fit them into `band` -- then lays them out edge to edge in a single
    row or column, `gap_mm` apart, centred on `band`'s other axis.

    `horizontal=False` (the default) stacks top to bottom: each item's
    own width is what has to fit `band`'s width, and the whole stack's
    combined height (mark) `band`'s height. `horizontal=True` lays them
    left to right instead -- each item's own height fits `band`'s height,
    and the row's combined width fits `band`'s width, which is what lets
    each item use the *whole* band height rather than splitting it.

    Assumes every item is still at its natural, unscaled size: the factor
    this computes is meant to be handed straight to set_item_scale(), not
    multiplied onto a scale already in effect. That is true of the seeded
    insertion mark, which is the only caller (_fit_seeded_insertion_mark)
    -- freshly seeded and untouched every time this runs."""
    if not items:
        return
    natural_heights = [item.boundingRect().height() for item in items]
    natural_widths = [item.boundingRect().width() for item in items]
    gap = mm_to_px(gap_mm) * (len(items) - 1)

    if horizontal:
        total_width = sum(natural_widths) + gap
        max_height = max(natural_heights)
        if total_width <= 0 or max_height <= 0:
            return
        scale = min(band.width() / total_width, band.height() / max_height)
        cursor = band.left()
        for item, width in zip(items, natural_widths):
            set_item_scale(item, scale, scale)
            footprint = item.mapToScene(item.boundingRect()).boundingRect()
            target_y = band.center().y() - footprint.height() / 2
            item.setPos(item.pos() + QPointF(cursor - footprint.left(), target_y - footprint.top()))
            cursor += width * scale + mm_to_px(gap_mm)
        return

    max_width = max(natural_widths)
    total_height = sum(natural_heights) + gap
    if max_width <= 0 or total_height <= 0:
        return
    scale = min(band.width() / max_width, band.height() / total_height)
    cursor = band.top()
    for item, height in zip(items, natural_heights):
        set_item_scale(item, scale, scale)
        footprint = item.mapToScene(item.boundingRect()).boundingRect()
        target_x = band.center().x() - footprint.width() / 2
        item.setPos(item.pos() + QPointF(target_x - footprint.left(), cursor - footprint.top()))
        cursor += height * scale + mm_to_px(gap_mm)


def _fit_seeded_insertion_mark(scene: DesignScene, band: QRectF, colour: str) -> list:
    """Shrinks, recolours and lays out the seeded "▲"/"INSERT THIS END"
    pair (see DesignScene.seed_disc_defaults) into `band`, side by side --
    the triangle on the left, the text on the right -- rather than
    stacked, so each can use the *whole* band height instead of splitting
    it in two. Their default size assumes the full-face label's own
    generous top area, which a 37x52mm sticker's top band does not have
    room for at all.

    Picked up by being the only text on the page at this point, the same
    assumption recolour_insertion_mark() makes and for the same reason:
    matching on the literal strings would quietly stop working in a
    translated build. Ordered left to right by their own seeded y
    position rather than by z-value or contents -- the one thing
    seed_disc_defaults() actually guarantees about them (the triangle is
    seeded above the label, so it sorts first)."""
    marks = sorted(
        (item for item in scene.print_items() if hasattr(item, "toPlainText")),
        key=lambda item: item.y(),
    )
    if not marks:
        return []
    qcolour = QColor(colour)
    for item in marks:
        item.setDefaultTextColor(qcolour)
    pad = mm_to_px(STICKER_MARK_PADDING_MM)
    inner = QRectF(band.left() + pad, band.top() + pad, band.width() - 2 * pad, band.height() - 2 * pad)
    _fit_group_into_band(marks, inner, gap_mm=STICKER_MARK_PADDING_MM, horizontal=True)
    return marks


def _sticker_bottom_band(
    scene: DesignScene, band: QRectF, background: str, accent: str, ink: str, metadata: ProjectMetadata
) -> list:
    """Artist (accent, bold) as a heading, a rule in the accent colour,
    then Album (ink) and the year (accent) sharing the row underneath it
    -- jcard_layout.place_back()'s own heading+rule+content shape, with
    the track list it would otherwise hold replaced by the one line this
    label has room for."""
    added: list = [_filled_rect(scene, band, background)]
    pad = mm_to_px(STICKER_BAND_PADDING_MM)
    inner = QRectF(band.left() + pad, band.top() + pad, band.width() - 2 * pad, band.height() - 2 * pad)
    cursor = inner.top()

    artist = _text(
        scene,
        metadata.artist.strip(),
        QRectF(0, 0, inner.width(), mm_to_px(STICKER_ARTIST_MM)),
        accent,
        wrap=False,
        bold=True,
    )
    if artist is not None:
        _move_top_left_to(artist, QPointF(inner.left(), cursor))
        added.append(artist)
    cursor += mm_to_px(STICKER_ARTIST_MM + STICKER_ROW_GAP_MM)

    rule_height = mm_to_px(STICKER_RULE_MM)
    added.append(_filled_rect(scene, QRectF(inner.left(), cursor, inner.width(), rule_height), accent))
    cursor += rule_height + mm_to_px(STICKER_ROW_GAP_MM)

    footer = QRectF(inner.left(), cursor, inner.width(), mm_to_px(STICKER_FOOTER_MM))
    year_width = footer.width() * STICKER_YEAR_WIDTH_FRACTION
    album_area = QRectF(footer.left(), footer.top(), footer.width() - year_width, footer.height())
    # Shorter than album_area, on purpose -- the year is a secondary
    # detail next to the album title, not equal billing, and the same
    # footer height for both let a four-digit number come out reading as
    # large as the title beside it. Centred in footer's own height rather
    # than sharing its top edge, so it doesn't look like it's floating
    # above the row it's part of.
    year_area = QRectF(
        album_area.right(),
        footer.center().y() - mm_to_px(STICKER_YEAR_MM) / 2,
        year_width,
        mm_to_px(STICKER_YEAR_MM),
    )

    album = _text(scene, metadata.album.strip(), album_area, ink, wrap=False)
    if album is not None:
        _move_top_left_to(album, album_area.topLeft())
        added.append(album)

    if metadata.year:
        year = _text(scene, str(metadata.year), year_area, accent, wrap=False)
        if year is not None:
            # Right-aligned within its own area, not top-left like Album --
            # matching Album's own top-left placement would leave it
            # sitting against the crease between the two instead of the
            # label's own outer edge.
            footprint = year.mapToScene(year.boundingRect()).boundingRect()
            target_x = year_area.right() - footprint.width()
            item_pos_delta = QPointF(target_x - footprint.left(), year_area.top() - footprint.top())
            year.setPos(year.pos() + item_pos_delta)
            added.append(year)

    return added


def build_sticker_label(
    scene: DesignScene, metadata: ProjectMetadata, *, background_art: bytes | None = None
) -> list:
    """The small chamfered sticker disc label (kind="disc", shape="sticker"):
    cover art between the top and bottom bands, the top band carrying the
    insertion mark, and the bottom band carrying Artist / a rule / Album +
    the year -- see this module's own header for where the palette and the
    heading+rule shape come from.

    The cover is fitted to the *middle* rectangle left between the two
    bands, not the whole label -- explicit request, after an earlier
    version covered the entire label (running the bands' own opaque fill
    over the top and bottom of it) came out looking visibly cropped
    wrong, since how much of a square cover shows in that narrow middle
    strip had nothing to do with the strip's own shape. Fitting straight
    to that rectangle is still the same overshoot-and-crop technique
    place_cover_on_label() uses (uniform scale, so the aspect ratio is
    never distorted -- only which part of a non-matching-aspect cover
    shows changes), just aimed at a smaller, more relevant target.

    If the template also has a slider shape, it gets a snippet of the same
    cover (place_cover_on_slider) plus the MiniDisc logo -- added by the
    caller, the same "auto_layout.py places what comes from the cover art,
    app_window.py adds the bundled logo image itself" split
    _auto_layout_disc_label already uses. Without a slider (the plain
    "MiniDisc Disc Label" variant), nothing is placed there at all.

    `background_art`, if given, is used as-is for the cover instead of
    `metadata.cover_art` -- see place_cover_on_label's own docstring for
    why (the CoverFilterDialog picker).

    The cover and the top band are both explicitly pushed *behind* the
    page's existing content (the seeded insertion mark) rather than left
    at whatever z a freshly added item gets by default (on top of
    everything) -- new items always land on top, but the mark has to
    show *through* the top band, and the top band has to show *through*
    the cover, which is the opposite order. Fitting the cover to the
    middle rectangle keeps it (mostly) out of the bands' own area in the
    first place, but the two can still overlap by a little wherever the
    cover's own aspect ratio doesn't exactly match that rectangle's --
    the z-order is what keeps that overshoot from ever showing.
    """
    rects = scene.cut_shape_rects()
    if not rects:
        return []
    if not metadata.cover_art:
        return []

    art = background_art if background_art is not None else metadata.cover_art
    label = rects[0]
    added: list = []

    top_band = QRectF(label.left(), label.top(), label.width(), mm_to_px(STICKER_TOP_BAND_MM))
    bottom_band = QRectF(
        label.left(),
        label.bottom() - mm_to_px(STICKER_BOTTOM_BAND_MM),
        label.width(),
        mm_to_px(STICKER_BOTTOM_BAND_MM),
    )
    middle = QRectF(label.left(), top_band.bottom(), label.width(), bottom_band.top() - top_band.bottom())

    floor = min((item.zValue() for item in scene.print_items()), default=0.0)

    cover = _cover_rect_with_image(scene, art, middle)
    if cover is not None:
        cover.setZValue(floor - 2.0)
        added.append(cover)

    background = dominant_colour(metadata.cover_art)
    accent = accent_colour(metadata.cover_art, against=background)
    ink = readable_text_colour(background)

    band = _filled_rect(scene, top_band, accent)
    band.setZValue(floor - 1.0)
    added.append(band)
    # Not appended to `added`: these are the already-seeded mark items
    # (see seed_disc_defaults), not new ones -- fitting/recolouring them
    # in place isn't an undo command either, the same as
    # recolour_insertion_mark()'s own callers never push its result.
    _fit_seeded_insertion_mark(scene, top_band, readable_text_colour(accent))

    added.extend(_sticker_bottom_band(scene, bottom_band, background, accent, ink, metadata))

    if len(rects) >= 2:
        slider_cover = place_cover_on_slider(scene, art)
        if slider_cover is not None:
            added.append(slider_cover)

    return added
