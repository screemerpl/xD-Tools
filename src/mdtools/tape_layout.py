"""Laying out a cassette's three pages: the J-card and a label per side.

The MiniDisc J-card is the closest relative, and this leans on it rather
than restating it -- a cassette J-card folds about vertical creases into a
front, a spine and a tuck-in flap, and is read a quarter turn round on the
sheet, which is exactly the shape `jcard_layout.py` already builds. So the
front cover, the spine band and the track-list panel are all its functions,
called with a cassette's own proportions.

What is genuinely different is the pair of shell labels, and the reason is
the medium itself: **a cassette is the first thing here that cannot hold an
album in one piece**. It has two faces and two running orders, and each
label has to say which half of the record it is looking at. `tape.py`
decides where that break falls; this module prints the answer.

Three consequences worth knowing:

- **The side letter is the biggest thing on the label.** Everything else on
  a shell label is read at arm's length while the tape is in your hand; the
  side is read while it is halfway into the deck, upside down.
- **Each side's tracks are numbered from one.** They are the tracks on that
  side, not tracks 7-12 of an album -- which is what the deck's own counter
  will agree with when it plays them.
- **The flap gets the whole album's list, not one side's.** It is the only
  panel that names the record as a whole, and a J-card that listed half of
  it would be a card for a tape nobody has.

No Qt UI here beyond the scene items it adds, matching jcard_layout.py and
cd_layout.py.
"""

from __future__ import annotations

import dataclasses

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtWidgets import QGraphicsItem

from mdtools.auto_layout import place_cover_on_label
from mdtools.canvas.items import set_item_scale
from mdtools.canvas.scene import DesignScene
from mdtools.cd_layout import lighten
from mdtools.constants import mm_to_px
from mdtools.jcard_layout import (
    JCARD_BACK_HEIGHT_MM,
    _move_top_left_to,
    _text,
    place_back,
    place_front_cover,
    place_spine,
)
from mdtools.palette import accent_colour, dominant_colour, readable_text_colour
from mdtools.project import ProjectMetadata, numbered_track_lines
from mdtools.tape import SidePlan

# How many columns the inlay's tuck-in flap deals the track list into.
FLAP_COLUMNS = 3

# The shell label's own rhythm, in millimetres. The label is cut around the
# two reel-hub openings, so the only unbroken space on it is the band above
# them, the band below, and the gutter between -- which is what everything
# here is laid into.
LABEL_PADDING_MM = 1.6
# Clearance around a hub opening, so nothing is printed right up against a
# cut edge (and so a sticker applied a millimetre out still reads).
HUB_MARGIN_MM = 1.2

# How far the sleeve is washed towards white before the text goes over it.
# Heavier than the CD label's, because a shell label is smaller and its
# type is smaller with it -- there is less of each letter to survive a
# busy background.
LABEL_LIGHTEN = 0.68


class TapeLayoutError(Exception):
    """The page could not be laid out -- a wrong template, or no artwork."""


# --- the J-card ------------------------------------------------------------


def build_jcard(scene: DesignScene, metadata: ProjectMetadata, logo_path: str = "") -> list[QGraphicsItem]:
    """Front cover, spine caption, and the album's track list on the flap.

    The three panels come from the card's own folds, so the proportions are
    whatever the template says rather than numbers repeated here. The flap
    is the narrow one -- under a quarter of the card -- which is why its
    heading band is scaled down from the MiniDisc J-card's: those millimetre
    constants were chosen against a 58.85mm panel, and at full size they ate
    a flap this shallow before the first track was printed.

    `logo_path` is optional and normally empty. The MiniDisc and CD cards
    both carry a format logo; a cassette's own marks (the shell's Type I/II
    notches, the Compact Cassette wordmark) belong to the tape rather than
    to the paper, and inventing one for the card would be putting a badge on
    it that no real inlay has.
    """
    panels = scene.fold_panel_rects()
    if len(panels) != 3:
        raise TapeLayoutError("this page is not a three-panel J-card")
    if not metadata.cover_art:
        raise TapeLayoutError("there is no cover art to build the J-card from")

    front, spine, flap = panels
    background = dominant_colour(metadata.cover_art)
    accent = accent_colour(metadata.cover_art, against=background)

    # Flap and spine first, so the cover added last can never end up painted
    # over by a panel block -- the same ordering jcard_layout.build_jcard
    # uses, and for the same reason.
    added: list[QGraphicsItem] = list(
        place_back(
            scene,
            flap,
            metadata,
            background,
            accent,
            # The panel is turned, so its *reading* height is its width on
            # the sheet -- that is what the heading bands are measured
            # against.
            heading_scale=flap.width() / mm_to_px(JCARD_BACK_HEIGHT_MM),
            # Three, because the flap is 102mm along and 24mm deep: in two
            # columns a normal album's list bottoms out at the smallest type
            # that still prints, and reads as a grey band rather than as
            # track names.
            columns=FLAP_COLUMNS,
        )
    )
    added.extend(place_spine(scene, spine, metadata, accent, logo_path))
    cover = place_front_cover(scene, front, metadata.cover_art)
    if cover is not None:
        added.append(cover)
    return added


# --- the shell labels ------------------------------------------------------


def build_side_label(
    scene: DesignScene,
    metadata: ProjectMetadata,
    side: SidePlan,
) -> list[QGraphicsItem]:
    """One face of the cassette: the sleeve, the side letter, and that
    side's tracks.

    Laid out around the holes, not on top of them. A full-face shell label
    is cut with an opening for each reel hub -- the deck's spindles come up
    through them -- so the unbroken space is three pieces: the band above
    the openings, the band below, and the gutter between them. Text in any
    other position would be printed onto something that gets cut away.

    - **The artwork is the whole label**, washed towards white the way a CD
      label's is (`cd_layout.lighten`), because there is text over it and a
      dark sleeve leaves that text invisible. One ordinary image layer,
      movable and replaceable like any other.
    - **The titles run across, not down.** A cassette label is four times
      wider than it is tall; a list turned on its side to fit would be read
      with the tape held sideways, which is not how anybody holds one.
    - **The tracks are this side's, numbered from one**, which is what the
      deck's counter will agree with once it is playing them.

    An unfolded page is required rather than merely expected: a shell label
    with a crease in it would be a J-card.
    """
    if scene.fold_panel_rects():
        raise TapeLayoutError("a shell label is a single unfolded page")
    if not metadata.cover_art:
        raise TapeLayoutError("there is no cover art to build the label from")

    panel = _page_rect(scene)
    background = dominant_colour(metadata.cover_art)
    # Scored against white rather than against the sleeve's own dominant
    # colour, because white is what it will be read on once the artwork
    # underneath has been washed out -- the same correction cd_layout's own
    # disc label needed.
    accent = accent_colour(metadata.cover_art, against="#ffffff")
    ink = readable_text_colour("#ffffff")

    added: list[QGraphicsItem] = []
    cover = place_cover_on_label(scene, lighten(metadata.cover_art, LABEL_LIGHTEN))
    if cover is not None:
        added.append(cover)

    top, gutter, bottom = _label_bands(scene, panel)

    letter = _text(scene, side.label, gutter, accent, wrap=False, bold=True)
    if letter is not None:
        # Grown to the gutter afterwards rather than fitted into it: the
        # font search is capped at MAX_POINT_SIZE, which is right for a
        # track list and leaves a single letter rattling around in a space
        # it is supposed to fill. This is the one piece of text on the
        # label read from across the room, or with the tape already half
        # into the deck.
        _fill(letter, gutter)
        _centre_in(letter, gutter)
        added.append(letter)

    heading = " · ".join(part for part in (metadata.artist.strip(), metadata.album.strip()) if part)
    title = _text(scene, heading, top, ink, wrap=False, bold=True)
    if title is not None:
        _move_top_left_to(title, top.topLeft())
        added.append(title)

    if side.tracks:
        # One run of titles rather than a column of them: the band is 9mm
        # deep and 86mm across, so a list would be the one shape that
        # cannot be fitted into it.
        listing = "   ".join(numbered_track_lines(_side_metadata(metadata, side)))
        tracks = _text(scene, listing, bottom, ink)
        if tracks is not None:
            _move_top_left_to(tracks, bottom.topLeft())
            added.append(tracks)
    return added


def _label_bands(scene: DesignScene, panel: QRectF) -> tuple[QRectF, QRectF, QRectF]:
    """The three pieces of a shell label that are not a hole: the band
    above the reel openings, the gutter between them, and the band below.

    Measured from the template's own hub geometry rather than from
    fractions of the label, so a corrected hub size or spacing moves the
    text with it -- and a label with no holes at all (any other sticker)
    still gets three sensible bands out of it.
    """
    template = scene.template
    pad = mm_to_px(LABEL_PADDING_MM)
    inner = panel.adjusted(pad, pad, -pad, -pad)

    diameter = mm_to_px(getattr(template, "hub_diameter_mm", 0.0) or 0.0)
    spacing = mm_to_px(getattr(template, "hub_spacing_mm", 0.0) or 0.0)
    if diameter <= 0 or spacing <= 0:
        third = inner.height() / 3
        return (
            QRectF(inner.left(), inner.top(), inner.width(), third),
            QRectF(inner.left(), inner.top() + third, inner.width(), third),
            QRectF(inner.left(), inner.bottom() - third, inner.width(), third),
        )

    margin = mm_to_px(HUB_MARGIN_MM)
    from_top = getattr(template, "hub_centre_from_top_mm", 0.0) or 0.0
    centre_y = panel.top() + (mm_to_px(from_top) if from_top > 0 else panel.height() / 2)
    hub_top = centre_y - diameter / 2 - margin
    hub_bottom = centre_y + diameter / 2 + margin

    top = QRectF(inner.left(), inner.top(), inner.width(), max(0.0, hub_top - inner.top()))
    bottom = QRectF(inner.left(), hub_bottom, inner.width(), max(0.0, inner.bottom() - hub_bottom))
    gutter = QRectF(
        panel.center().x() - (spacing - diameter) / 2 + margin,
        hub_top,
        max(0.0, spacing - diameter - 2 * margin),
        hub_bottom - hub_top,
    )
    return top, gutter, bottom


def _fill(item: QGraphicsItem, area: QRectF) -> None:
    """Scales an item up until one of its sides meets the area's."""
    bounds = item.boundingRect()
    if bounds.width() <= 0 or bounds.height() <= 0:
        return
    scale = min(area.width() / bounds.width(), area.height() / bounds.height())
    if scale > 1.0:
        set_item_scale(item, scale, scale)


def _centre_in(item: QGraphicsItem, area: QRectF) -> None:
    # By its footprint, not its own rect: an item scaled by set_item_scale
    # carries a transform anchored at its centre, so pos() is not where its
    # top-left is on the page (the mistake cd_layout documents twice).
    placed = item.mapToScene(item.boundingRect()).boundingRect()
    item.setPos(item.pos() + (area.center() - placed.center()))


def _side_metadata(metadata: ProjectMetadata, side: SidePlan) -> ProjectMetadata:
    return dataclasses.replace(metadata, tracks=list(side.tracks))


def _page_rect(scene: DesignScene) -> QRectF:
    """The cut shape's own rectangle, not the padded scene rect.

    Every template outline builder pads the scene around the cut shape by a
    fixed margin, and laying a label out against that padding would print
    the heading off the sticker -- see printing.crop_to_template_bounds(),
    which crops the same margin away for exactly the same reason.
    """
    rects = scene.cut_shape_rects()
    if not rects:
        raise TapeLayoutError("this page has no cut shape to lay out")
    return rects[0]


def label_metadata(metadata: ProjectMetadata, side: SidePlan) -> ProjectMetadata:
    """The album as one side of it sees itself -- exposed for the caller so
    a preview and the layout cannot disagree about what a side contains."""
    return _side_metadata(metadata, side)


__all__ = [
    "TapeLayoutError",
    "build_jcard",
    "build_side_label",
    "label_metadata",
]
