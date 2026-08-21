"""Laying out a CD-R's two pages from an album: the disc label and the
folded slim-case insert.

The MiniDisc equivalents are `auto_layout.py` (disc label) and
`jcard_layout.py` (J-card), and this leans on both rather than restating
them -- `place_cover_on_label()` already scales artwork to cover a cut
shape, and `jcard_layout.place_back()` already builds a track-list panel
out of the cover's own colours. What is genuinely different here is
physical:

- **The disc is a ring with a hole through the middle.** Nothing can be
  printed across the hub, so the text sits in the bands above and below it,
  each one only as wide as the circle is at that height (`_chord_rect()`).
- **The label's artwork is lightened.** A CD label is read at arm's length
  with text over it, and a dark sleeve leaves that text invisible -- the
  same problem `auto_layout.recolour_insertion_mark()` solves for a
  MiniDisc by recolouring the text, except here there is much more text and
  a whole face to put it on. Lightening the picture keeps one readable
  answer regardless of what the sleeve happens to be.
- **The insert is read upright**, unlike a J-card, which goes into its case
  a quarter turn round. That is the only reason `place_back()` grew a
  `turned` flag rather than this module getting its own copy of it.

The right-hand panel is the front cover; the left-hand one, because of how
the sheet folds (crease at the middle, left half folded behind the right,
so the right half faces out at the front and the left half faces out
through the clear back of the tray), is whichever of two things build_insert()
decides it should be -- see that function. Both panels stay upright --
folding about a vertical crease and then reading the other side flips
left-right twice, which cancels.

No Qt UI here beyond the scene items it adds, matching jcard_layout.py.
"""

from __future__ import annotations

import io
import math

from PIL import Image
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtWidgets import QGraphicsItem

from mdtools.auto_layout import place_cover_on_label
from mdtools.canvas.items import set_item_scale
from mdtools.canvas.scene import DesignScene
from mdtools.constants import mm_to_px
from mdtools.jcard_layout import (
    BACK_FOOTER_MM,
    BACK_GAP_MM,
    BACK_PADDING_MM,
    BACK_TITLE_MM,
    JCARD_BACK_HEIGHT_MM,
    _filled_rect,
    _move_top_left_to,
    _text,
    place_back,
    place_spine,
)
from mdtools.palette import accent_colour, dominant_colour, readable_text_colour
from mdtools.project import ProjectMetadata

# How far the label's artwork is blended towards white. Chosen so a dark
# sleeve still reads as itself while black text over it stays legible; a
# heavier wash turns every cover into a pale smudge, a lighter one leaves
# dark covers unreadable.
LIGHTEN = 0.55

# The bands of the label that text can use, as fractions of the disc's own
# diameter measured from its top edge. The hub sits in the middle and
# cannot be printed on, so the artist/album go above it and the year and
# the Digital Audio mark below.
TOP_BAND = (0.06, 0.28)
BOTTOM_BAND = (0.70, 0.94)

# Kept clear of the outer edge, where a label that is a hair off-centre
# would otherwise lose the ends of a word.
EDGE_MARGIN_MM = 4.0

DISC_TITLE_MM = 9.0
DISC_SUBTITLE_MM = 7.0
DISC_FOOTER_MM = 5.0
DISC_LOGO_HEIGHT_MM = 8.0
DISC_GAP_MM = 1.5

# The tray card's own mark, in the corner opposite the running-time
# footer, and how much of the panel its track list is allowed to fill.
BACK_LOGO_HEIGHT_MM = 7.0
BACK_LOGO_MARGIN_MM = 4.0
BACK_TRACK_FILL = 0.7

class CdLayoutError(Exception):
    """The page could not be laid out -- a wrong template, or no artwork."""


def lighten(image_data: bytes, amount: float = LIGHTEN) -> bytes:
    """The cover blended `amount` of the way towards white, as PNG bytes.

    Done to the picture rather than by laying a translucent white rectangle
    over it, on purpose: the result is one ordinary image layer that can be
    moved, replaced or deleted like any other, instead of two layers whose
    stacking order quietly matters. Pillow rather than Qt because this is
    plain pixel arithmetic and palette.py already reads covers with it.
    """
    amount = max(0.0, min(1.0, amount))
    with Image.open(io.BytesIO(image_data)) as image:
        rgb = image.convert("RGB")
        white = Image.new("RGB", rgb.size, (255, 255, 255))
        blended = Image.blend(rgb, white, amount)
        out = io.BytesIO()
        blended.save(out, format="PNG")
        return out.getvalue()


def _chord_rect(disc: QRectF, top_fraction: float, bottom_fraction: float, margin_mm: float) -> QRectF:
    """The widest upright rectangle that fits inside the disc between two
    heights.

    A circle is narrower away from its middle, so a band's usable width is
    the chord at whichever of its two edges is further from the centre --
    using the wider one would push text off the label. Straight geometry
    rather than a guessed inset: the label gets cut along that circle.
    """
    radius = disc.width() / 2
    centre_y = disc.center().y()
    top = disc.top() + disc.height() * top_fraction
    bottom = disc.top() + disc.height() * bottom_fraction

    furthest = max(abs(top - centre_y), abs(bottom - centre_y))
    half_chord = math.sqrt(max(0.0, radius * radius - furthest * furthest))
    half_width = max(0.0, half_chord - mm_to_px(margin_mm))

    return QRectF(disc.center().x() - half_width, top, 2 * half_width, bottom - top)


def _footprint(item: QGraphicsItem) -> QRectF:
    """Where the item actually lands in the scene, scaling included."""
    return item.mapToScene(item.boundingRect()).boundingRect()


def _centre_in(item: QGraphicsItem, area: QRectF, top: float) -> None:
    """Centres `item` horizontally in `area`, with its top edge at `top`.

    Moved by the difference between where it *is* and where it should be,
    rather than by setting pos() outright: an item scaled by
    set_item_scale() carries a transform anchored at its own centre, so its
    local origin and its visible top-left no longer differ by a fixed
    offset (the same reasoning auto_layout._move_centre_to gives). Getting
    this wrong put the Digital Audio mark half off the disc, where Clip
    Layers removed it as being outside the cut shape -- it did not look
    misplaced, it simply was not there.
    """
    footprint = _footprint(item)
    item.setPos(
        item.pos()
        + QPointF(area.center().x() - footprint.center().x(), top - footprint.top())
    )


def _right_band_rect(scene: DesignScene, disc: QRectF, margin_mm: float) -> QRectF:
    """The horizontal strip to the right of the hub, at the disc's own
    vertical centre -- the widest point on that side of the ring, so
    placing something there needs no fractional y-band the way the
    artist/album/year text bands do; the centreline already clears the hub
    by definition (both are centred on the same point) and has the most
    room of any height to spare.
    """
    hole_diameter_mm = getattr(scene.template, "hole_diameter_mm", 0.0)
    hub_radius = mm_to_px(hole_diameter_mm) / 2
    margin = mm_to_px(margin_mm)
    left = disc.center().x() + hub_radius + margin
    right = disc.right() - margin
    width = max(0.0, right - left)
    # Half the disc's own diameter as a generous height cap -- comfortably
    # more than a small logo needs, and this close to the vertical centre
    # (the circle's widest point) there is no risk of it pushing outside
    # the ring at that height.
    height = disc.height() * 0.5
    return QRectF(left, disc.center().y() - height / 2, width, height)


def _right_align_vcentre_on(item: QGraphicsItem, area: QRectF, disc: QRectF) -> None:
    """Moves `item` so its right edge sits at `area`'s right edge, centred
    vertically on `disc` -- the mirror of _centre_in's "centred
    horizontally, aligned to one edge", for a mark placed beside the ring
    rather than above or below it."""
    footprint = _footprint(item)
    item.setPos(
        item.pos()
        + QPointF(area.right() - footprint.right(), disc.center().y() - footprint.center().y())
    )


def place_disc_logo(scene: DesignScene, disc: QRectF, logo_path: str) -> QGraphicsItem | None:
    """The Digital Audio mark, on the right side of the label, level with
    the hub.

    Scaled by the *smaller* ratio, so it stays whole inside the band -- the
    opposite of the cover, which is deliberately overshot and then clipped.
    A mark cropped by the disc's edge would be worse than no mark at all.
    """
    item = scene.add_image(logo_path)
    if item is None:
        return None
    natural = item.boundingRect()
    if natural.width() <= 0 or natural.height() <= 0:
        return item

    band = _right_band_rect(scene, disc, EDGE_MARGIN_MM)
    height = mm_to_px(DISC_LOGO_HEIGHT_MM)
    scale = min(band.width() / natural.width(), height / natural.height())
    set_item_scale(item, scale, scale)
    _right_align_vcentre_on(item, band, disc)
    return item


def build_disc_label(
    scene: DesignScene,
    metadata: ProjectMetadata,
    logo_path: str | None = None,
    *,
    background_art: bytes | None = None,
) -> list:
    """The label: the cover lightened across the whole face, the album's
    details above the hub, the Digital Audio mark beside it, and the year
    at the very bottom.

    The cover deliberately overshoots the disc -- Tools > Clip Layers is
    what trims it back to the ring, exactly as on a MiniDisc label.

    `background_art`, if given, is used **as-is** for that background
    instead of lighten()ing `metadata.cover_art` here -- this is what lets
    a caller offer the CoverFilterDialog picker (brighten is one of six
    choices there, not the only one) and have this function place exactly
    what was chosen, rather than always lightening regardless. Omitting it
    keeps every existing caller's behaviour (this module's own default of
    "lighten it") unchanged.
    """
    rects = scene.cut_shape_rects()
    if not rects:
        raise CdLayoutError("this page is not a disc label")
    if not metadata.cover_art:
        raise CdLayoutError("there is no cover art to build the label from")

    disc = rects[0]
    added: list = []

    cover = place_cover_on_label(scene, background_art if background_art is not None else lighten(metadata.cover_art))
    if cover is not None:
        added.append(cover)

    # The *exact same* background/accent/ink triple build_insert() computes
    # for the case insert's back panel (jcard_layout.place_back) -- not a
    # separately-scored approximation of it. An earlier version scored
    # these against a flat "#ffffff" instead, reasoning that white is what
    # they would be read against once the artwork underneath is lightened
    # -- which kept a pale accent legible on a pale background, but also
    # meant the disc label's own artist/album colours could never actually
    # match the insert's, since accent_colour()'s result depends on what it
    # was scored against. Reported directly, from a real cover, with the
    # two pages showing visibly different accent colours for the same
    # album. Using the identical inputs is what actually delivers "the same
    # palette as the case insert" -- and the risk that motivated scoring
    # against white (a pale accent disappearing into the lightened
    # background) is what every auto-generated text layer's shadow now
    # exists to cover for regardless of which colour was chosen.
    background = dominant_colour(metadata.cover_art)
    accent = accent_colour(metadata.cover_art, against=background)
    ink = readable_text_colour(background)

    top_band = _chord_rect(disc, TOP_BAND[0], TOP_BAND[1], EDGE_MARGIN_MM)
    cursor = top_band.top()

    artist = _text(
        scene,
        metadata.artist.strip(),
        QRectF(0, 0, top_band.width(), mm_to_px(DISC_TITLE_MM)),
        accent,
        wrap=False,
        bold=True,
    )
    if artist is not None:
        _centre_in(artist, top_band, cursor)
        added.append(artist)
        cursor += mm_to_px(DISC_TITLE_MM + DISC_GAP_MM)

    album = _text(
        scene,
        metadata.album.strip(),
        QRectF(0, 0, top_band.width(), mm_to_px(DISC_SUBTITLE_MM)),
        ink,
        wrap=False,
    )
    if album is not None:
        _centre_in(album, top_band, cursor)
        added.append(album)

    logo = place_disc_logo(scene, disc, logo_path) if logo_path else None
    if logo is not None:
        added.append(logo)

    if metadata.year:
        # The logo no longer shares this band -- it sits beside the ring
        # now, not below it -- so the year is free to sit at the very
        # bottom of the label, centred, with nothing else to make room for.
        bottom_band = _chord_rect(disc, BOTTOM_BAND[0], BOTTOM_BAND[1], EDGE_MARGIN_MM)
        year = _text(
            scene,
            str(metadata.year),
            QRectF(0, 0, bottom_band.width(), mm_to_px(DISC_FOOTER_MM)),
            # Same ink the album line uses, not a hardcoded white -- still
            # one of the case insert's own two colours (the other being
            # accent, already spoken for by the artist), and readable_text_
            # colour() already picked it specifically to contrast with the
            # actual dominant cover colour, which a fixed white is not
            # guaranteed to do.
            ink,
            wrap=False,
        )
        if year is not None:
            top = bottom_band.bottom() - mm_to_px(DISC_FOOTER_MM)
            _centre_in(year, bottom_band, top)
            added.append(year)
    return added


def place_insert_cover(scene: DesignScene, panel: QRectF, cover_art: bytes) -> QGraphicsItem | None:
    """The sleeve across the whole front panel.

    Stretched to the panel rather than fitted inside it, the same call
    `jcard_layout.place_front_cover()` makes and for the same reason: the
    panel is nearly square, and a letterboxed cover with bands of
    background either side looks worse than one a couple of percent out of
    proportion. No rotation -- a slim case insert is read upright.
    """
    item = scene.add_image_from_data(cover_art)
    if item is None:
        return None
    natural = item.boundingRect()
    if natural.width() <= 0 or natural.height() <= 0:
        return item
    set_item_scale(item, panel.width() / natural.width(), panel.height() / natural.height())
    # By its *footprint*, not by pos(): set_item_scale anchors its transform
    # at the item's centre, so setting pos() to the panel's corner left the
    # cover floating in the middle of the panel with white either side --
    # the same mistake the Digital Audio mark made on the label.
    footprint = _footprint(item)
    item.setPos(item.pos() + (panel.topLeft() - footprint.topLeft()))
    return item


def _place_contained(scene: DesignScene, image_bytes: bytes, rect: QRectF) -> QGraphicsItem | None:
    """Fits an image inside `rect`, aspect ratio intact -- scaled by the
    *smaller* ratio, the same technique place_disc_logo() already uses so
    a mark is never cropped or stretched. Explicit choice for a person's
    photo: place_insert_cover()'s own non-uniform stretch is fine for a
    nearly-square album cover, but doing that to a face is a much more
    noticeable distortion than a couple of percent off on a sleeve. Centred
    in `rect`, so any leftover space (whichever axis the photo's own
    proportions don't fill) is split evenly on both sides rather than
    pinned to one corner."""
    item = scene.add_image_from_data(image_bytes)
    if item is None:
        return None
    natural = item.boundingRect()
    if natural.width() <= 0 or natural.height() <= 0:
        return item
    scale = min(rect.width() / natural.width(), rect.height() / natural.height())
    set_item_scale(item, scale, scale)
    footprint = _footprint(item)
    target = QPointF(rect.center().x() - footprint.width() / 2, rect.center().y() - footprint.height() / 2)
    item.setPos(item.pos() + (target - footprint.topLeft()))
    return item


def place_artist_panel(
    scene: DesignScene,
    panel: QRectF,
    metadata: ProjectMetadata,
    background: str,
    accent: str,
    artist_photo: bytes | None,
) -> list[QGraphicsItem]:
    """The insert's left panel for a project that also has a case back of
    its own.

    A full jewel case's tray card already carries the track list
    (build_case_back's own middle panel) -- repeating it here, which is
    what a *slim* case's insert has no choice but to do (there is nowhere
    else on that case for it to go), would just be the same list printed
    twice. In its place: the artist's name, the year, and -- network and a
    good enough match permitting, see metadata_lookup.find_artist_photo --
    a photo of the artist. That is what the reverse of a front insert
    traditionally carries in a full jewel case, since the tray card is
    what actually holds the track list there.

    Artist and year keep the exact padding/position/colour roles
    place_back() already gives its own heading and footer -- accent for the
    bold artist line, ink for the one below it -- so this still reads as
    the same family of panel as every other back/insert page, just with a
    photo where the track list would otherwise be. A missing photo (no
    match found, or none fetched at all) simply leaves that space empty
    rather than falling back to the track list -- the point of this panel
    is that the list lives on the case back now, and that stays true
    whether or not a photo could be found for it.
    """
    added: list[QGraphicsItem] = [_filled_rect(scene, panel, background)]
    ink = readable_text_colour(background)
    pad = mm_to_px(BACK_PADDING_MM)
    content_width = panel.width() - 2 * pad
    cursor = pad

    artist = _text(
        scene,
        metadata.artist.strip(),
        QRectF(0, 0, content_width, mm_to_px(BACK_TITLE_MM)),
        accent,
        wrap=False,
        bold=True,
    )
    if artist is not None:
        _move_top_left_to(artist, QPointF(panel.left() + pad, panel.top() + cursor))
        added.append(artist)
        cursor += mm_to_px(BACK_TITLE_MM + BACK_GAP_MM)

    footer_height = mm_to_px(BACK_FOOTER_MM + BACK_GAP_MM) if metadata.year else 0.0
    photo_top = panel.top() + cursor
    photo_height = panel.height() - cursor - footer_height - pad

    if artist_photo and photo_height > mm_to_px(15):
        photo_rect = QRectF(panel.left() + pad, photo_top, content_width, photo_height)
        photo = _place_contained(scene, artist_photo, photo_rect)
        if photo is not None:
            added.append(photo)

    if metadata.year:
        year = _text(
            scene,
            str(metadata.year),
            QRectF(0, 0, content_width, mm_to_px(BACK_FOOTER_MM)),
            ink,
            wrap=False,
        )
        if year is not None:
            _move_top_left_to(
                year, QPointF(panel.left() + pad, panel.bottom() - pad - mm_to_px(BACK_FOOTER_MM))
            )
            added.append(year)

    return added


def build_case_back(scene: DesignScene, metadata: ProjectMetadata, logo_path: str | None = None) -> list:
    """The jewel case tray card: a spine down each side, the track list on
    the panel between them.

    Three panels, from the card's two folds -- and the outer two are the
    strips that show down the sides of the closed case, which is why they
    are the ones carrying the album's name. `jcard_layout.place_spine()`
    already draws exactly that (an accent band, the caption turned to read
    top-to-bottom, the logo at its foot), so both spines are it, called
    twice; the middle panel is `place_back()`, the same track-list block
    the J-card and the folded insert use.

    Not a new layout so much as the two existing ones meeting on one sheet
    -- which is the point: a tray card that looked like neither would be
    the odd one out in a set that has to be read together.
    """
    panels = scene.fold_panel_rects()
    if len(panels) != 3:
        raise CdLayoutError("this page is not a three-panel tray card")
    if not metadata.cover_art:
        raise CdLayoutError("there is no cover art to build the case back from")

    left_spine, middle, right_spine = panels
    background = dominant_colour(metadata.cover_art)
    accent = accent_colour(metadata.cover_art, against=background)

    added = list(
        place_back(
            scene,
            middle,
            metadata,
            background,
            accent,
            turned=False,
            heading_scale=middle.height() / mm_to_px(JCARD_BACK_HEIGHT_MM),
            # A track list stretched across all 138mm of this panel read as
            # a poster rather than as a sleeve -- reported directly.
            track_fill=BACK_TRACK_FILL,
        )
    )
    mark = place_back_logo(scene, middle, logo_path or "")
    if mark is not None:
        added.append(mark)
    for spine in (left_spine, right_spine):
        # Both spines get the same caption on purpose: which side of the
        # case is visible depends on how it was shelved, and a card that
        # only names the album on one of them is a card that is often
        # facing the wrong way.
        added.extend(place_spine(scene, spine, metadata, accent, logo_path or ""))
    return added


def place_back_logo(scene: DesignScene, panel: QRectF, logo_path: str) -> QGraphicsItem | None:
    """The Digital Audio mark in the tray card's bottom-right corner.

    The bottom-*left* of that panel already carries the year and the
    running time (place_back's own footer), so the mark takes the other
    end of the same line rather than competing with it.
    """
    if not logo_path:
        return None
    item = scene.add_image(logo_path)
    if item is None:
        return None
    natural = item.boundingRect()
    if natural.width() <= 0 or natural.height() <= 0:
        return item

    scale = mm_to_px(BACK_LOGO_HEIGHT_MM) / natural.height()
    set_item_scale(item, scale, scale)
    margin = mm_to_px(BACK_LOGO_MARGIN_MM)
    placed = _footprint(item)
    # By its footprint, not by pos(): set_item_scale anchors its transform
    # at the item's own centre.
    item.setPos(
        item.pos()
        + QPointF(
            panel.right() - margin - placed.right(),
            panel.bottom() - margin - placed.bottom(),
        )
    )
    return item


def build_insert(
    scene: DesignScene,
    metadata: ProjectMetadata,
    *,
    has_case_back: bool = False,
    artist_photo: bytes | None = None,
) -> list:
    """The folded insert: the cover on the right panel always; the left one
    is either the track list or the artist panel, depending on
    `has_case_back`.

    Which panel is which follows from the fold -- see this module's own
    header. Raises rather than returning quietly if the page is not a
    two-panel insert: laying a track list across an unfolded sheet would
    put half of it where the crease is not.

    `has_case_back` -- whether this project *also* has a jewel case back
    page (see project.PAGE_BACK) -- decides which left panel gets built:
    the ordinary track list (place_back(), unchanged default) when there
    isn't one, since a slim case's insert is the only place that list can
    go; place_artist_panel() (artist, year, and a photo of the artist)
    when there is, since the tray card already carries the list and
    printing it twice would be redundant. `artist_photo`, if given, is
    what that panel places -- the caller's job to find (see
    metadata_lookup.find_artist_photo), since this module has no network
    access of its own, matching the "plan it, the caller executes/fetches
    for it" split used throughout this app.
    """
    panels = scene.fold_panel_rects()
    if len(panels) != 2:
        raise CdLayoutError("this page is not a two-panel folded insert")
    if not metadata.cover_art:
        raise CdLayoutError("there is no cover art to build the insert from")

    left, right = panels
    background = dominant_colour(metadata.cover_art)
    accent = accent_colour(metadata.cover_art, against=background)

    # The left panel first, so the cover added afterwards can never end up
    # painted over by the panel block behind it.
    if has_case_back:
        added = list(place_artist_panel(scene, left, metadata, background, accent, artist_photo))
    else:
        added = list(
            place_back(
                scene,
                left,
                metadata,
                background,
                accent,
                turned=False,
                heading_scale=left.height() / mm_to_px(JCARD_BACK_HEIGHT_MM),
            )
        )
    cover = place_insert_cover(scene, right, metadata.cover_art)
    if cover is not None:
        added.append(cover)
    return added


def build_front_insert(scene: DesignScene, metadata: ProjectMetadata) -> list:
    """The slim case's front-only insert: build_insert()'s own right panel
    (place_insert_cover(), unchanged), covering the *whole* card instead of
    just the half of it right of a crease.

    There is no fold here at all -- the card is only the front cover, since
    a slim case's back is bare plastic tray with no pocket for a second
    panel (see this module's own header) -- so there is nowhere for a track
    list or artist panel to go, and this builds nothing but the cover.
    Raises rather than returning quietly if the page turns out to actually
    be folded (that is build_insert()'s job, not this one) or has no cut
    shape at all.
    """
    if scene.fold_panel_rects():
        raise CdLayoutError("this page is a folded insert, not a front-only one")
    rects = scene.cut_shape_rects()
    if not rects:
        raise CdLayoutError("this page has no cut shape to place the cover on")
    if not metadata.cover_art:
        raise CdLayoutError("there is no cover art to build the insert from")

    cover = place_insert_cover(scene, rects[0], metadata.cover_art)
    return [cover] if cover is not None else []


__all__ = [
    "CdLayoutError",
    "build_case_back",
    "build_disc_label",
    "build_front_insert",
    "build_insert",
    "lighten",
    "place_artist_panel",
    "place_back_logo",
    "place_disc_logo",
    "place_insert_cover",
]
