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

The right-hand panel is the front cover and the left-hand one the track
list, because of how the sheet folds: crease at the middle, left half
folded behind the right, so the right half faces out at the front and the
left half faces out through the clear back of the tray. Both stay upright
-- folding about a vertical crease and then reading the other side flips
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
from mdtools.jcard_layout import _text, place_back, place_spine
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

# The height of a J-card's own back panel, which is what jcard_layout's
# heading constants were chosen against. Everything here is measured
# against it rather than given a second set of numbers to drift from.
JCARD_BACK_HEIGHT_MM = 58.85


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


def place_disc_logo(scene: DesignScene, disc: QRectF, logo_path: str) -> QGraphicsItem | None:
    """The Digital Audio mark, at the foot of the label.

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

    band = _chord_rect(disc, BOTTOM_BAND[0], BOTTOM_BAND[1], EDGE_MARGIN_MM)
    height = mm_to_px(DISC_LOGO_HEIGHT_MM)
    scale = min(band.width() / natural.width(), height / natural.height())
    set_item_scale(item, scale, scale)
    _centre_in(item, band, band.bottom() - _footprint(item).height())
    return item


def build_disc_label(scene: DesignScene, metadata: ProjectMetadata, logo_path: str | None = None) -> list:
    """The label: the cover lightened across the whole face, the album's
    details above the hub, the year and the Digital Audio mark below it.

    The cover deliberately overshoots the disc -- Tools > Clip Layers is
    what trims it back to the ring, exactly as on a MiniDisc label.
    """
    rects = scene.cut_shape_rects()
    if not rects:
        raise CdLayoutError("this page is not a disc label")
    if not metadata.cover_art:
        raise CdLayoutError("there is no cover art to build the label from")

    disc = rects[0]
    added: list = []

    cover = place_cover_on_label(scene, lighten(metadata.cover_art))
    if cover is not None:
        added.append(cover)

    # Swatches from the *original* cover -- the lightened one has been
    # washed towards white and every colour in it would agree on a pale
    # nothing -- but scored against **white**, because white is what they
    # will be read on once the artwork underneath has been lightened.
    # Scoring against the sleeve's own dominant colour instead picked a pale
    # yellow: right against dark navy, invisible on the label.
    accent = accent_colour(metadata.cover_art, against="#ffffff")
    ink = readable_text_colour("#ffffff")

    top_band = _chord_rect(disc, TOP_BAND[0], TOP_BAND[1], EDGE_MARGIN_MM)
    cursor = top_band.top()

    artist = _text(
        scene,
        metadata.artist.strip(),
        QRectF(0, 0, top_band.width(), mm_to_px(DISC_TITLE_MM)),
        ink,
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
        accent,
        wrap=False,
    )
    if album is not None:
        _centre_in(album, top_band, cursor)
        added.append(album)

    bottom_band = _chord_rect(disc, BOTTOM_BAND[0], BOTTOM_BAND[1], EDGE_MARGIN_MM)
    logo = place_disc_logo(scene, disc, logo_path) if logo_path else None
    if logo is not None:
        added.append(logo)

    if metadata.year:
        year = _text(
            scene,
            str(metadata.year),
            QRectF(0, 0, bottom_band.width(), mm_to_px(DISC_FOOTER_MM)),
            ink,
            wrap=False,
        )
        if year is not None:
            # Directly above the mark rather than at the top of the band,
            # where it landed on the seam between two parts of the artwork
            # and read as a stray number.
            top = bottom_band.bottom() - mm_to_px(DISC_FOOTER_MM + DISC_GAP_MM)
            if logo is not None:
                top = _footprint(logo).top() - mm_to_px(DISC_FOOTER_MM + DISC_GAP_MM)
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
        )
    )
    for spine in (left_spine, right_spine):
        # Both spines get the same caption on purpose: which side of the
        # case is visible depends on how it was shelved, and a card that
        # only names the album on one of them is a card that is often
        # facing the wrong way.
        added.extend(place_spine(scene, spine, metadata, accent, logo_path or ""))
    return added


def build_insert(scene: DesignScene, metadata: ProjectMetadata) -> list:
    """The folded insert: track list on the left panel, cover on the right.

    Which panel is which follows from the fold -- see this module's own
    header. Raises rather than returning quietly if the page is not a
    two-panel insert: laying a track list across an unfolded sheet would
    put half of it where the crease is not.
    """
    panels = scene.fold_panel_rects()
    if len(panels) != 2:
        raise CdLayoutError("this page is not a two-panel folded insert")
    if not metadata.cover_art:
        raise CdLayoutError("there is no cover art to build the insert from")

    left, right = panels
    background = dominant_colour(metadata.cover_art)
    accent = accent_colour(metadata.cover_art, against=background)

    # The track list first, so the cover added afterwards can never end up
    # painted over by the panel block behind it.
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


__all__ = [
    "CdLayoutError",
    "build_case_back",
    "build_disc_label",
    "build_insert",
    "lighten",
    "place_disc_logo",
    "place_insert_cover",
]
