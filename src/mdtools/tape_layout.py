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

from mdtools.canvas.scene import DesignScene
from mdtools.constants import mm_to_px
from mdtools.jcard_layout import (
    JCARD_BACK_HEIGHT_MM,
    _filled_rect,
    _move_top_left_to,
    _text,
    place_back,
    place_front_cover,
    place_spine,
)
from mdtools.palette import accent_colour, dominant_colour, readable_text_colour
from mdtools.project import ProjectMetadata
from mdtools.tape import SidePlan

# The shell label's own rhythm, in millimetres. It is a small, wide sticker
# -- roughly 89 x 43mm -- so the side letter takes a fixed column down the
# left and everything else shares what is left.
LABEL_PADDING_MM = 2.5
SIDE_LETTER_WIDTH_MM = 14.0
SIDE_LETTER_HEIGHT_MM = 16.0
LABEL_TITLE_MM = 4.2
LABEL_SUBTITLE_MM = 3.4
LABEL_GAP_MM = 1.0


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
    """One face of the cassette: the side letter, the album, and that side's
    tracks.

    Built out of `place_back()` with the side's own tracks substituted, so a
    shell label reads as part of the same set as the J-card's flap -- same
    colours, same heading, same numbered list -- rather than as a third
    design. The side letter is then laid over it, which is the one thing
    that is genuinely this page's own.

    An unfolded page is required rather than merely expected: a shell label
    with a crease in it would be a J-card, and printing half a track list
    either side of a fold nobody is going to fold is worse than saying so.
    """
    if scene.fold_panel_rects():
        raise TapeLayoutError("a shell label is a single unfolded page")
    if not metadata.cover_art:
        raise TapeLayoutError("there is no cover art to build the label from")

    panel = _page_rect(scene)
    background = dominant_colour(metadata.cover_art)
    accent = accent_colour(metadata.cover_art, against=background)

    letter_width = mm_to_px(SIDE_LETTER_WIDTH_MM)
    text_panel = QRectF(
        panel.left() + letter_width,
        panel.top(),
        max(0.0, panel.width() - letter_width),
        panel.height(),
    )

    # Numbered from one *for this side*: that is what the deck's own counter
    # will say when it plays them, and a label that started at seven would
    # disagree with the machine in front of you.
    side_metadata = dataclasses.replace(metadata, tracks=list(side.tracks))
    added: list[QGraphicsItem] = list(
        place_back(
            scene,
            text_panel,
            side_metadata,
            background,
            accent,
            turned=False,
            heading_scale=text_panel.height() / mm_to_px(JCARD_BACK_HEIGHT_MM),
        )
    )

    # The block behind the letter is drawn over the panel block place_back
    # already laid down, so the letter has its own field of colour rather
    # than sitting on whatever the track list's background happens to be.
    letter_area = QRectF(panel.left(), panel.top(), letter_width, panel.height())
    added.append(_filled_rect(scene, letter_area, accent))
    letter = _side_letter(scene, letter_area, side.label, readable_text_colour(accent))
    if letter is not None:
        added.append(letter)
    return added


def _side_letter(scene: DesignScene, area: QRectF, label: str, ink: str) -> QGraphicsItem | None:
    """A single big A or B, centred in its column.

    Fitted to a box rather than given a point size: the label's own size
    comes from the template, which is unverified and may well be measured
    and changed, and a hardcoded 40pt would then either overflow the sticker
    or rattle around inside it.
    """
    box = QRectF(0, 0, area.width() * 0.8, mm_to_px(SIDE_LETTER_HEIGHT_MM))
    item = _text(scene, label, box, ink, wrap=False, bold=True)
    if item is None:
        return None
    bounds = item.boundingRect()
    _move_top_left_to(
        item,
        QPointF(
            area.center().x() - bounds.width() / 2,
            area.center().y() - bounds.height() / 2,
        ),
    )
    return item


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
    return dataclasses.replace(metadata, tracks=list(side.tracks))


__all__ = [
    "TapeLayoutError",
    "build_jcard",
    "build_side_label",
    "label_metadata",
]
