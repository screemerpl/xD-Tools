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
import math

from PySide6.QtCore import QCoreApplication, QPointF, QRectF
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
from mdtools.tape import SidePlan, TapePlan

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


def side_track_columns(metadata: ProjectMetadata, plan: TapePlan) -> list[str]:
    """The album as two headed blocks, one per side of the tape.

    A cassette's running order is two running orders, and an inlay that
    listed twelve tracks straight through would leave the reader to guess
    where the tape is turned over -- the one thing the card knows and they
    do not. Each side's tracks are numbered from one, matching both the
    shell label beside it and the deck's own counter.
    """
    columns = []
    for side in plan.sides:
        if not side.tracks:
            continue
        heading = QCoreApplication.translate("TapeLayout", "SIDE {side}").format(side=side.label)
        lines = numbered_track_lines(_side_metadata(metadata, side))
        columns.append("\n".join([heading, ""] + lines))
    return columns


def build_jcard(
    scene: DesignScene,
    metadata: ProjectMetadata,
    logo_path: str = "",
    plan: TapePlan | None = None,
) -> list[QGraphicsItem]:
    """Front cover, spine caption, and the album's track list on the flap.

    The three panels come from the card's own folds, so the proportions are
    whatever the template says rather than numbers repeated here. The flap
    is the narrow one -- under a quarter of the card -- which is why its
    heading band is scaled down from the MiniDisc J-card's: those millimetre
    constants were chosen against a 58.85mm panel, and at full size they ate
    a flap this shallow before the first track was printed.

    `plan`, when given, splits the flap's track list into a SIDE A block
    and a SIDE B block -- see side_track_columns. Without one the whole
    album is listed straight through, which is the right answer only for a
    card whose tape nobody has decided on yet.

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
            # track names. A split by side overrides that with two columns
            # of its own, which is what the card is actually about.
            columns=FLAP_COLUMNS,
            track_columns=side_track_columns(metadata, plan) if plan is not None else None,
            # No artist/album block here: the spine right beside it carries
            # both, and on a panel this shallow that heading costs a fifth
            # of the space the tracks are trying to fit into.
            heading=False,
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
    *,
    background_art: bytes | None = None,
) -> list[QGraphicsItem]:
    """One face of the cassette: the sleeve, the side letter, and that
    side's tracks.

    `background_art`, given, is used as-is for the sleeve instead of
    lighten()ing `metadata.cover_art` here -- see cd_layout.build_disc_label's
    own docstring for why: it's what lets a caller offer the
    CoverFilterDialog picker and have this place exactly what was chosen.
    Omitted, this keeps lightening by default, unchanged from before.

    Laid out around the opening, not over it. A shell label is cut with one
    hole through its middle -- the two reel hubs and, between them, the
    window the tape is watched through -- so what is left to print on is
    three pieces: the band above it, the band below, and the columns at
    either end. Anything placed anywhere else would be printed onto a hole.

    - **The artwork is the whole label**, washed towards white the way a CD
      label's is (`cd_layout.lighten`), because there is text over it and a
      dark sleeve leaves that text invisible. One ordinary image layer,
      movable and replaceable like any other.
    - **The titles run across, not down.** A cassette label is twice as
      wide as it is tall and its bands are a centimetre deep; a list turned
      on its side to fit would be read with the tape held sideways, which
      is not how anybody holds one.
    - **The tracks go in the deeper band**, above the window, and the
      album's own name in the shallower one below -- there are more of the
      former and they need the room.
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
    # The exact background/accent/ink triple cd_layout.build_disc_label()
    # now uses (which itself matches the case insert's own back panel) --
    # not a separately-scored approximation of it. Scoring against a flat
    # white was tried first here too, on the reasoning that white is what
    # the text is actually read against once the artwork underneath is
    # washed out -- but that made accent_colour()'s result depend on what
    # it was scored against, so this label's colours could never actually
    # agree with the J-card's for the same album. See cd_layout.
    # build_disc_label's own note on this for the full story (found there
    # first, from a real cover).
    background = dominant_colour(metadata.cover_art)
    accent = accent_colour(metadata.cover_art, against=background)
    ink = readable_text_colour(background)

    added: list[QGraphicsItem] = []
    art = background_art if background_art is not None else lighten(metadata.cover_art, LABEL_LIGHTEN)
    cover = place_cover_on_label(scene, art)
    if cover is not None:
        added.append(cover)

    above, beside, below = _label_bands(scene, panel)

    letter = _text(scene, side.label, beside, accent, wrap=False, bold=True)
    if letter is not None:
        # Grown to its column afterwards rather than fitted into it: the
        # font search is capped at MAX_POINT_SIZE, which is right for a
        # track list and leaves a single letter rattling around in a space
        # it is supposed to fill. This is the one piece of text on the
        # label read from across the room, or with the tape already half
        # into the deck.
        _fill(letter, beside)
        _centre_in(letter, beside)
        added.append(letter)

    if side.tracks:
        # One run of titles rather than a column of them: the band is under
        # a centimetre and a half deep and 86mm across, so a list is the one
        # shape that cannot be fitted into it.
        listing = "   ".join(numbered_track_lines(_side_metadata(metadata, side)))
        tracks = _text(scene, listing, above, ink)
        if tracks is not None:
            _move_top_left_to(tracks, above.topLeft())
            added.append(tracks)

    heading = " · ".join(part for part in (metadata.artist.strip(), metadata.album.strip()) if part)
    title = _text(scene, heading, below, ink, wrap=False, bold=True)
    if title is not None:
        # Centred across the label, not pinned to the band's left edge --
        # asked for directly. _text() fits this line into the band, so it
        # is normally narrower than the band is wide, and anchoring it left
        # left the artist and album sitting off to one side of a sticker
        # whose other content (the side letter, the titles) reads centred.
        _centre_in(title, below)
        added.append(title)
    return added


def _label_bands(scene: DesignScene, panel: QRectF) -> tuple[QRectF, QRectF, QRectF]:
    """The three pieces of a shell label that are not a hole: the band
    above the reel opening, the column beside it, and the band below.

    Measured from the template's own opening rather than from fractions of
    the label, so a corrected diameter, spacing or height moves the text
    with it -- and a label with no opening at all (any other sticker) still
    gets three sensible bands out of it.

    The column is to the *left* of the whole opening, not between the reels:
    the gap between them is the tape window, and it is cut away.
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
    window_top = centre_y - diameter / 2 - margin
    window_bottom = centre_y + diameter / 2 + margin
    window_left = panel.center().x() - spacing / 2 - diameter / 2 - margin

    # The top band is kept clear of the chamfered corners: at the very top
    # of the label the material narrows by the chamfer's own leg on each
    # side, so a full-width block there would start in a piece that has
    # been cut off.
    chamfer = mm_to_px(getattr(template, "top_chamfer_mm", 0.0) or 0.0) / math.sqrt(2)
    top_inset = max(pad, chamfer)
    above = QRectF(
        panel.left() + top_inset,
        inner.top(),
        max(0.0, panel.width() - 2 * top_inset),
        max(0.0, window_top - inner.top()),
    )
    below = QRectF(inner.left(), window_bottom, inner.width(), max(0.0, inner.bottom() - window_bottom))
    beside = QRectF(
        inner.left(),
        window_top,
        max(0.0, window_left - inner.left()),
        window_bottom - window_top,
    )
    return above, beside, below


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
