"""Building a J-card from a project's metadata and its cover art.

The card is one strip folded into three panels (see
DesignScene.fold_panel_rects): front, spine, back, left to right.

  front  the cover art, rotated so its own top edge runs down the card's
         left edge, stretched to fill the panel completely -- aspect ratio
         is deliberately not preserved here (explicit user instruction),
         because a J-card front is nearly square and a letterboxed cover
         with bands of background looks worse than a slightly stretched one
  spine  a band in an accent colour taken from the cover, carrying the year,
         album and artist rotated to read down it, plus the MiniDisc logo
  back   the cover's most common colour, with the numbered track list

Every colour comes from the cover (mdtools.palette), including the text
colours, which are picked for contrast rather than chosen.

Like auto_layout.py, each function builds and positions items and returns
them; turning that into undoable commands is the caller's job.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPen
from PySide6.QtWidgets import QGraphicsItem

from mdtools.canvas.items import SCALE_ROLE, set_item_scale, set_text_shadow
from mdtools.canvas.scene import DesignScene
from mdtools.constants import mm_to_px
from mdtools.palette import accent_colour, dominant_colour, readable_text_colour, tint_monochrome_png
from mdtools.project import ProjectMetadata, numbered_track_lines, track_list_columns

# Breathing room inside a panel, in millimetres. The back panel's text needs
# more than the spine's, which has barely 8.3mm to work with.
BACK_PADDING_MM = 3.0
SPINE_PADDING_MM = 1.2
FRONT_LOGO_MARGIN_MM = 2.5

# The back panel's vertical rhythm, top to bottom in reading order. A bare
# track list on a flat colour looked unfinished; a heading, a rule in the
# accent colour and a running-time footer give it something to hang on.
BACK_TITLE_MM = 6.5
BACK_SUBTITLE_MM = 4.5
BACK_RULE_MM = 0.7
BACK_FOOTER_MM = 3.5
BACK_GAP_MM = 1.8

# The logo on the front is decoration in a corner, not a design element.
FRONT_LOGO_HEIGHT_MM = 7.0

# Font search bounds, in points. The upper bound stops a two-track album
# from rendering its list in enormous type; the lower one is where print
# stops being readable on a physical card.
MAX_POINT_SIZE = 20.0
MIN_POINT_SIZE = 3.5
POINT_STEP = 0.25

# The height of a J-card's own back panel. Every other card's heading bands
# are scaled against it (see place_back's heading_scale) rather than given a
# second set of constants to drift from.
JCARD_BACK_HEIGHT_MM = 58.85

# Beyond this many tracks a single column gets too tall and thin to read, so
# the list splits into the two side-by-side columns project.py already knows
# how to build.
TWO_COLUMN_THRESHOLD = 9


@dataclass
class JCard:
    """Everything the layout added, so the caller can push one command per
    item and report what happened."""

    items: list[QGraphicsItem] = field(default_factory=list)
    background: str = ""
    accent: str = ""

    def add(self, item: QGraphicsItem | None) -> QGraphicsItem | None:
        if item is not None:
            self.items.append(item)
        return item


def _scene_rect_of(item: QGraphicsItem) -> QRectF:
    return item.mapToScene(item.boundingRect()).boundingRect()


def _move_top_left_to(item: QGraphicsItem, point: QPointF) -> None:
    """Aligns an item's *scene* bounding box, which is what a caller means
    by "put it here" once the item has been scaled or rotated -- its pos()
    alone no longer corresponds to any visible corner."""
    item.setPos(item.pos() + (point - _scene_rect_of(item).topLeft()))


def _move_centre_to(item: QGraphicsItem, point: QPointF) -> None:
    item.setPos(item.pos() + (point - _scene_rect_of(item).center()))


def _filled_rect(scene: DesignScene, area: QRectF, colour: str) -> QGraphicsItem:
    """A flat block of colour covering `area`.

    The rect's own geometry is set rather than scaling it: a scaled shape
    caches a base rect for later resizes (see canvas/items.py), and starting
    it at its final size keeps that bookkeeping out of the picture."""
    item = scene.add_rectangle()
    item.setRect(QRectF(0, 0, area.width(), area.height()))
    brush = QColor(colour)
    item.setBrush(QBrush(brush))
    # Frame always matches fill in this app -- see the note in scene.py.
    item.setPen(QPen(brush))
    item.setTransformOriginPoint(item.boundingRect().center())
    item.setPos(area.topLeft())
    return item


def _fit_text(item: QGraphicsItem, area: QRectF, *, wrap: bool) -> None:
    """Shrinks the text until it fits `area`.

    A search rather than a calculation: the height of wrapped rich text
    depends on where Qt breaks the lines, which is not something to
    re-derive here. It walks down from MAX_POINT_SIZE and stops at the first
    size that fits, so the result is the largest readable one."""
    font = item.font()
    size = MAX_POINT_SIZE
    while size > MIN_POINT_SIZE:
        font.setPointSizeF(size)
        item.setFont(font)
        if wrap:
            item.setTextWidth(area.width())
        bounds = item.boundingRect()
        if bounds.width() <= area.width() and bounds.height() <= area.height():
            return
        size -= POINT_STEP
    font.setPointSizeF(MIN_POINT_SIZE)
    item.setFont(font)


def _fits(item: QGraphicsItem, area: QRectF, *, wrap: bool) -> bool:
    if wrap:
        item.setTextWidth(area.width())
    bounds = item.boundingRect()
    return bounds.width() <= area.width() and bounds.height() <= area.height()


def _fit_together(items: list[QGraphicsItem], area: QRectF, *, wrap: bool = True) -> None:
    """Shrinks several blocks to a *single* size, the largest at which they
    all fit.

    A track list split into two columns used to be fitted one column at a
    time, so each got whichever size suited its own longest line -- and two
    columns of the same list, read side by side, came out in visibly
    different type. Reported directly, on both the J-card and the CD
    insert, which share this function.

    The search is the same walk down from MAX_POINT_SIZE as _fit_text, just
    with the test being "all of them fit" rather than "this one does".
    """
    if not items:
        return
    font = items[0].font()
    size = MAX_POINT_SIZE
    while size > MIN_POINT_SIZE:
        font.setPointSizeF(size)
        for item in items:
            item.setFont(font)
        if all(_fits(item, area, wrap=wrap) for item in items):
            return
        size -= POINT_STEP
    font.setPointSizeF(MIN_POINT_SIZE)
    for item in items:
        item.setFont(font)


def _text(
    scene: DesignScene,
    text: str,
    area: QRectF,
    colour: str,
    *,
    wrap: bool = True,
    bold: bool = False,
    fit: bool = True,
) -> QGraphicsItem | None:
    """`fit=False` leaves the size alone, for a caller that is going to fit
    this block together with others (see _fit_together)."""
    if not text.strip():
        return None
    item = scene.add_text(text)
    item.setDefaultTextColor(QColor(colour))
    # Every auto-generated cover/label runs its text through here, and it
    # sits directly on top of a photograph -- a plain flat colour, however
    # well contrasted, can still get lost in a busy patch of the cover.
    # The shadow is a small, automatic extra margin of legibility; it
    # remains an ordinary per-layer toggle a user can turn back off.
    set_text_shadow(item, True)
    if bold:
        font = item.font()
        font.setBold(True)
        item.setFont(font)
    if fit:
        _fit_text(item, area, wrap=wrap)
    return item


def total_running_time(metadata: ProjectMetadata) -> str:
    """"46:29" across the whole album, or "" if the tracks carry no times.

    Worth printing: it is the one fact about a compilation that the track
    list itself doesn't tell you, and it fills the foot of the back panel
    with something real rather than decoration."""
    seconds = sum(track.time_seconds or 0 for track in metadata.tracks)
    if seconds <= 0:
        return ""
    minutes, remainder = divmod(seconds, 60)
    return f"{minutes}:{remainder:02d}"


def _inset(area: QRectF, millimetres: float) -> QRectF:
    padding = mm_to_px(millimetres)
    return area.adjusted(padding, padding, -padding, -padding)


def has_cover_window(template) -> bool:
    """Whether this cover template has a die-cut window in it at all.

    Every CoverTemplate carries the `cutout_*` fields, so "has a window"
    has to mean a window with area rather than merely the fields existing.
    Which *panel* it lands on is a separate question -- see
    window_on_track_panel().
    """
    if not getattr(template, "fold_offsets_mm", None):
        return False
    return getattr(template, "cutout_width_mm", 0.0) > 0 and getattr(template, "cutout_height_mm", 0.0) > 0


def window_on_track_panel(template) -> bool:
    """Whether this cover template's die-cut window lands on the panel that
    would otherwise carry the track list -- i.e. whether build_jcard has to
    turn the whole card end-for-end (see its own `flipped` parameter).

    A window is a hole, so whatever is printed on the panel it lands on has
    a hole in it. Through a track list that is destructive: it takes out the
    middle of the one thing the panel exists to say, and no arrangement of
    what is left puts it back. Through the cover artwork it is the *point*
    -- a die-cut sleeve, the disc's own label showing through the front of
    the case. So the panel with the window is the one that gets the
    artwork, which for a window cut to the right of the last fold line
    means the front and the back swap over.

    `cutout_side == "left"` needs no flip: that window is measured leftward
    from the *first* fold line, so it already lands on the front panel, and
    the plain arrangement is right as it stands.
    """
    if not has_cover_window(template):
        return False
    return getattr(template, "cutout_side", "right") == "right"


def reading_size(panel: QRectF) -> tuple[float, float]:
    """A turned panel's size as it is actually read: the front and back are
    laid out flat as tall narrow strips, but the card goes into the case
    turned a quarter turn, so what is 58.85mm wide and 73mm tall on the
    sheet is 73mm wide and 58.85mm tall to the eye."""
    return panel.height(), panel.width()


def _place_turned(item: QGraphicsItem, panel: QRectF, x: float, y: float, *, clockwise: bool = False) -> None:
    """Turns `item` a quarter turn and puts it at (x, y) in the panel's
    *reading* coordinates -- origin top-left, x running along the 73mm side.

    Front and back turn opposite ways. The card wraps around the case, so
    turning it over to read the back puts that panel the other way up; laying
    both out anticlockwise left the back upside down in the case.

    Each mapping falls straight out of its rotation. Anticlockwise: reading-y
    becomes the panel's horizontal axis and reading-x its vertical axis
    measured up from the bottom, so the item's own unrotated *width* is
    subtracted. Clockwise is the mirror of that, and subtracts its *height*.
    """
    unrotated = item.boundingRect()
    scale = item.data(SCALE_ROLE) or (1.0, 1.0)
    item.setTransformOriginPoint(unrotated.center())

    if clockwise:
        item.setRotation(90)
        span = unrotated.height() * scale[1]
        target = QPointF(panel.left() + panel.width() - y - span, panel.top() + x)
    else:
        item.setRotation(-90)
        span = unrotated.width() * scale[0]
        target = QPointF(panel.left() + y, panel.top() + panel.height() - x - span)
    _move_top_left_to(item, target)


# --- front -----------------------------------------------------------------


def place_front_cover(
    scene: DesignScene, panel: QRectF, cover_art: bytes, *, flipped: bool = False
) -> QGraphicsItem | None:
    """The cover, rotated a quarter turn anticlockwise so its own top edge
    ends up running down the card's left edge, stretched to fill the panel.

    The scale factors are crossed, and the reason is a Qt detail worth
    knowing: an item's own transform() (which set_item_scale writes) is
    applied *after* rotation(), so the scale acts on already-rotated axes.
    A quarter turn has swapped width and height by then, so filling a
    Pw x Ph panel needs sx = Pw / natural_height and sy = Ph / natural_width.
    Getting this backwards is invisible on a square cover -- the rotation
    still happens, the artwork still turns, only the panel ends up filled
    the wrong way round."""
    item = scene.add_image_from_data(cover_art)
    if item is None:
        return None
    natural = item.boundingRect()
    if natural.width() <= 0 or natural.height() <= 0:
        return item

    # Anticlockwise, so the cover's top edge ends up down the left side --
    # clockwise on a flipped card, which is that same card read from the
    # other end (see build_jcard). Either way the quarter turn swaps width
    # and height, so the crossed scale factors below are unchanged and the
    # artwork still comes out exactly panel-sized; only which way up it is
    # differs, which is the whole point of the flip.
    item.setRotation(90 if flipped else -90)
    set_item_scale(item, panel.width() / natural.height(), panel.height() / natural.width())
    _move_top_left_to(item, panel.topLeft())
    return item


def place_front_logo(
    scene: DesignScene, panel: QRectF, logo_path: str, *, flipped: bool = False
) -> QGraphicsItem | None:
    """A small MiniDisc logo in the front's bottom-right corner -- turned
    the same quarter turn as the cover it sits on.

    Leaving it upright was the obvious thing to do and looked wrong the
    moment the card was held the right way up: the whole front is read
    turned, so anything on it that has an up must be turned too."""
    item = scene.add_image(logo_path)
    if item is None:
        return None
    natural = item.boundingRect()
    if natural.height() <= 0:
        return item

    scale = mm_to_px(FRONT_LOGO_HEIGHT_MM) / natural.height()
    set_item_scale(item, scale, scale)
    width, height = reading_size(panel)
    margin = mm_to_px(FRONT_LOGO_MARGIN_MM)
    side = mm_to_px(FRONT_LOGO_HEIGHT_MM)
    # Reading coordinates, so this stays the bottom-right corner *as read*
    # whichever way the card is turned -- _place_turned maps it onto
    # whichever physical corner that actually is.
    _place_turned(item, panel, x=width - margin - side, y=height - margin - side, clockwise=flipped)
    return item


# --- spine -----------------------------------------------------------------


def _logo_item(scene: DesignScene, logo_path: str, ink: str | None):
    """The logo, tinted to `ink` first when one is given -- see place_spine's
    own `logo_ink` note for when that is right and when it is not."""
    if not logo_path:
        return None
    if ink is None:
        return scene.add_image(logo_path)
    try:
        data = Path(logo_path).read_bytes()
    except OSError:
        return None
    return scene.add_image_from_data(tint_monochrome_png(data, ink))


def spine_caption(metadata: ProjectMetadata) -> str:
    parts = [str(metadata.year) if metadata.year else "", metadata.album.strip(), metadata.artist.strip()]
    return "  ·  ".join(part for part in parts if part)


def place_spine(
    scene: DesignScene,
    panel: QRectF,
    metadata: ProjectMetadata,
    accent: str,
    logo_path: str,
    *,
    flipped: bool = False,
    logo_ink: str | None = None,
) -> list[QGraphicsItem]:
    """Accent band, the caption rotated to read down it, and the logo.

    The caption is fitted against a *swapped* rectangle -- the spine is
    8.3mm wide and 73mm tall, so once rotated the text has the panel's
    height to run along and its width to be tall in.

    `logo_ink`, given, recolours the logo to that colour before placing
    it -- for a mark that is a mask rather than a picture (the Digital
    Audio mark, which is one opaque colour). Left `None`, which is what
    every MiniDisc and cassette caller does, the file is placed exactly as
    it is: the MiniDisc logo is black *and* white, and tinting it would
    erase the wordmark inside it. See palette.tint_monochrome_png.

    `flipped` turns the strip end-for-end with the rest of the card (see
    build_jcard): the caption rotates the other way, and the logo moves to
    the strip's other end so that it still sits at the caption's *foot*
    once the card is the right way up. Turning the caption and not the logo
    would leave the logo at the head of the spine, above the text."""
    added: list[QGraphicsItem] = [_filled_rect(scene, panel, accent)]
    ink = readable_text_colour(accent)

    inner = _inset(panel, SPINE_PADDING_MM)
    logo = _logo_item(scene, logo_path, logo_ink)
    logo_span = 0.0
    if logo is not None and logo.boundingRect().height() > 0:
        scale = inner.width() / logo.boundingRect().width()
        set_item_scale(logo, scale, scale)
        placed = _scene_rect_of(logo)
        logo_span = placed.height()
        # The foot of the strip *as read*, which on a flipped card is its
        # top edge on the sheet rather than its bottom.
        logo_top = inner.top() if flipped else inner.bottom() - placed.height()
        _move_top_left_to(logo, QPointF(inner.left(), logo_top))
        added.append(logo)

    caption = spine_caption(metadata)
    text_height = max(inner.height() - logo_span - mm_to_px(SPINE_PADDING_MM), mm_to_px(10))
    # Bold: at the size a spine allows, a regular weight is legible on
    # screen and disappears once printed.
    item = _text(scene, caption, QRectF(0, 0, text_height, inner.width()), ink, wrap=False, bold=True)
    if item is not None:
        item.setTransformOriginPoint(item.boundingRect().center())
        # Clockwise, so the caption reads top-to-bottom with the case
        # standing upright -- the way a CD or MD spine conventionally does.
        # Anticlockwise on a flipped card, which is that same direction
        # once the card itself has been turned end-for-end.
        item.setRotation(-90 if flipped else 90)
        # Centred along the strip rather than pinned to its top. A short
        # caption on a 118mm tray-card spine otherwise sat in the top
        # two-thirds and left the rest looking empty -- reported directly.
        # The logo is at the foot, so the space it takes is excluded before
        # centring in what is left.
        span = item.boundingRect().width()
        available = inner.height() - logo_span
        offset = max(0.0, (available - span) / 2)
        # Centred in what the logo leaves, which is the space below it
        # normally and above it on a flipped card, the logo having moved to
        # the other end.
        top = inner.top() + (logo_span if flipped else 0.0) + offset
        # And centred *across* the strip, between the two fold lines, not
        # pinned to the left one. _text() fits the caption inside the
        # spine's width, so a short caption -- or any caption at all, on a
        # 12.7mm cassette spine -- comes out narrower than the strip, and
        # anchoring it at inner.left() left every millimetre of that slack
        # against the other cut line. Reported on the MiniDisc and cassette
        # J-cards alike, which is one bug: both spines are this function.
        placed = _scene_rect_of(item)
        left = inner.left() + max(0.0, (inner.width() - placed.width()) / 2)
        _move_top_left_to(item, QPointF(left, top))
        added.append(item)
    return added


# --- back ------------------------------------------------------------------


def place_back(
    scene: DesignScene,
    panel: QRectF,
    metadata: ProjectMetadata,
    background: str,
    accent: str,
    *,
    turned: bool = True,
    flipped: bool = False,
    heading_scale: float = 1.0,
    columns: int = 0,
    track_columns: list[str] | None = None,
    heading: bool = True,
    track_fill: float = 1.0,
) -> list[QGraphicsItem]:
    """The back of the case: the cover's dominant colour, a heading, a rule
    in the accent colour, the numbered track list, and the running time.

    On a J-card everything is turned a quarter turn, like the front -- the
    card goes into the case that way round, so a track list left upright
    reads sideways. It is laid out here in *reading* coordinates (x along
    the 73mm side), with _place_turned doing the conversion.

    `flipped` turns the panel end-for-end with the rest of the card (see
    build_jcard) -- the same reading-coordinate layout, mapped onto the
    panel the other way round. Ignored when `turned=False`, which has no
    quarter turn to reverse.

    `turned=False` lays the same panel out upright, for a CD slim case
    insert, which is read the way it is printed. Only the mapping from
    reading coordinates to the panel changes: the heading, the rule, the
    two-column threshold and the centring of the list in its leftover space
    are the same job either way, and keeping them in one function is what
    stops the two cards drifting apart.

    `columns` forces how many side-by-side columns the track list is dealt
    into; 0 means "decide from the track count" (one, or two past
    TWO_COLUMN_THRESHOLD), which is what every caller wanted until a panel
    turned up that is four times wider than it is deep -- see
    tape_layout.build_jcard.

    `track_columns` replaces the track list outright with text the caller
    has already arranged into columns -- which is how a cassette's inlay
    gets a SIDE A block and a SIDE B block instead of one run of twelve
    tracks, without this function having to learn what a side is. The
    column count then comes from the list itself.

    `track_fill` is how much of the leftover space the track list is fitted
    into -- 1.0 uses all of it, which is right for a panel the list has to
    work to fit at all. A jewel case tray card is 138mm across and its list
    filled every millimetre of it, which read as a poster rather than as a
    sleeve; 0.7 there leaves the type at a size somebody would set by hand.
    The block is still centred in the *whole* space, so the slack is shared
    above and below rather than left at the bottom.

    `heading=False` drops the artist/album block and its rule, leaving the
    panel to the track list alone. For a cassette's tuck-in flap that is
    the difference between a legible list and one at the smallest size that
    prints: the panel is 24mm deep, the heading bands take a fifth of it,
    and the album is already named twice over on the spine beside it.

    `heading_scale` multiplies the heading, rule and footer bands, which
    are millimetre constants chosen for a J-card's own narrow panel. A CD
    slim case insert is twice as wide, and at 1.0 its heading came out
    looking lost above a full-height track list -- so the caller says how
    much bigger its panel is rather than this growing a second set of
    constants.

    The heading and rule exist because a bare list of tracks on a flat
    colour looked unfinished -- they give the panel something to be
    anchored by, and use the accent that is otherwise only on the spine."""
    added: list[QGraphicsItem] = [_filled_rect(scene, panel, background)]
    ink = readable_text_colour(background)
    width, height = reading_size(panel) if turned else (panel.width(), panel.height())
    # The padding shrinks with the headings on a shallow panel, and only
    # there (min(): a CD insert scales *up*, and a wider margin round a
    # bigger panel is right). Left unscaled, 6mm of top and bottom margin
    # is a quarter of a cassette flap gone before a track is printed.
    pad = mm_to_px(BACK_PADDING_MM * min(1.0, heading_scale))
    content_width = width - 2 * pad
    cursor = pad

    def put(item: QGraphicsItem, x: float, y: float) -> None:
        if turned:
            _place_turned(item, panel, x=x, y=y, clockwise=not flipped)
        else:
            _move_top_left_to(item, QPointF(panel.left() + x, panel.top() + y))

    def place(item: QGraphicsItem | None, span_mm: float) -> None:
        nonlocal cursor
        if item is not None:
            put(item, pad, cursor)
            added.append(item)
        cursor += mm_to_px(span_mm)

    artist = _text(
        scene,
        metadata.artist.strip() if heading else "",
        QRectF(0, 0, content_width, mm_to_px(BACK_TITLE_MM * heading_scale)),
        accent,
        wrap=False,
        bold=True,
    )
    place(artist, BACK_TITLE_MM * heading_scale if artist is not None else 0)

    album = _text(
        scene,
        metadata.album.strip() if heading else "",
        QRectF(0, 0, content_width, mm_to_px(BACK_SUBTITLE_MM * heading_scale)),
        ink,
        wrap=False,
    )
    place(album, (BACK_SUBTITLE_MM + BACK_GAP_MM) * heading_scale if album is not None else 0)

    if artist is not None or album is not None:
        rule = _filled_rect(scene, QRectF(0, 0, content_width, mm_to_px(BACK_RULE_MM * heading_scale)), accent)
        place(rule, (BACK_RULE_MM + BACK_GAP_MM) * heading_scale)

    footer_text = " · ".join(
        part for part in (str(metadata.year) if metadata.year else "", total_running_time(metadata)) if part
    )
    footer_span = (BACK_FOOTER_MM + BACK_GAP_MM) * heading_scale if footer_text else 0.0
    tracks_height = height - pad - cursor - mm_to_px(footer_span)

    listing = track_columns if track_columns is not None else None
    # The list is fitted into a share of the space and then centred in all
    # of it -- see track_fill.
    fitted_height = tracks_height * max(0.05, min(1.0, track_fill))
    if (listing or metadata.tracks) and tracks_height > mm_to_px(6):
        # The font search is capped, so a short album's list can end up much
        # shorter than the space it was given. Centring what it produced in
        # that space spreads the slack above and below instead of leaving
        # one dead band at the bottom.
        if listing is not None:
            column_count = len(listing)
        else:
            column_count = columns or (2 if len(metadata.tracks) > TWO_COLUMN_THRESHOLD else 1)
            listing = track_list_columns(metadata, column_count)
        if column_count > 1:
            gap = mm_to_px(BACK_PADDING_MM)
            column_width = (content_width - gap * (column_count - 1)) / column_count
            column_area = QRectF(0, 0, column_width, fitted_height)
            columns = [_text(scene, column, column_area, ink, fit=False) for column in listing]
            # One size across both, rather than one per column: they are
            # read side by side, and fitting them separately made the
            # halves of a single list differ visibly in type.
            _fit_together([item for item in columns if item is not None], column_area)
            tallest = max((item.boundingRect().height() for item in columns if item is not None), default=0.0)
            top = cursor + max(0.0, (tracks_height - tallest) / 2)
            for index, item in enumerate(columns):
                if item is not None:
                    put(item, pad + index * (column_width + gap), top)
                    added.append(item)
        else:
            item = _text(scene, listing[0], QRectF(0, 0, content_width, fitted_height), ink)
            if item is not None:
                top = cursor + max(0.0, (tracks_height - item.boundingRect().height()) / 2)
                put(item, pad, top)
                added.append(item)
        cursor += tracks_height

    if footer_text:
        footer = _text(
            scene, footer_text, QRectF(0, 0, content_width, mm_to_px(BACK_FOOTER_MM * heading_scale)), accent, wrap=False
        )
        if footer is not None:
            put(footer, pad, height - pad - mm_to_px(BACK_FOOTER_MM * heading_scale))
            added.append(footer)
    return added


# --- the whole card --------------------------------------------------------


def build_jcard(
    scene: DesignScene, metadata: ProjectMetadata, logo_path: str, *, flipped: bool | None = None
) -> JCard:
    """Lays out all three panels. Returns an empty JCard if the scene isn't
    a folded cover, or the metadata has no cover art to take colours from.

    `flipped` turns the whole card end-for-end: the artwork goes on the
    panel *after* the folds and the track list on the panel before them,
    and every element on all three panels rotates the other way so each
    still reads the right way up. It is one rigid 180-degree turn of the
    finished card, not a mirror -- a mirror is not something putting a card
    into a case differently can achieve, and would print every word
    backwards.

    `None`, which every caller uses, decides it from the template itself
    via window_on_track_panel(): a die-cut window has to fall on the
    artwork, so a template carrying one to the right of its last fold line
    is flipped and a plain one is not. The parameter stays overridable
    because "which way round is this card" is worth being able to assert on
    directly, rather than only through a template that happens to have a
    hole in it."""
    panels = scene.fold_panel_rects()
    if len(panels) < 3 or not metadata.cover_art:
        return JCard()

    if flipped is None:
        flipped = window_on_track_panel(scene.template)

    spine = panels[1]
    cover_panel, track_panel = (panels[2], panels[0]) if flipped else (panels[0], panels[2])
    background = dominant_colour(metadata.cover_art)
    accent = accent_colour(metadata.cover_art, against=background)
    card = JCard(background=background, accent=accent)

    # Track list and spine first so the cover artwork, added later, can
    # never be painted over by a panel block.
    for item in place_back(scene, track_panel, metadata, background, accent, flipped=flipped):
        card.add(item)
    for item in place_spine(scene, spine, metadata, accent, logo_path, flipped=flipped):
        card.add(item)
    card.add(place_front_cover(scene, cover_panel, metadata.cover_art, flipped=flipped))
    card.add(place_front_logo(scene, cover_panel, logo_path, flipped=flipped))
    return card
