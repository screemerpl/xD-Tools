"""Physical printing: paints rendered label artwork onto a real printer
page (or a standalone PNG/PDF file) at its exact physical millimeter size
and position.

Kept separate from panels/print_dialog.py so the actual paint routines --
the part that must stay pixel-for-pixel identical between the dialog's
own on-screen preview and the real printed/exported page -- have no Qt
dialog/widget dependencies pulled in alongside them.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QImage, QPainter, QTransform
from PySide6.QtPrintSupport import QPrinter

from mdtools import app_settings
from mdtools.constants import MM_PER_INCH

# Portrait only -- both label designs comfortably fit either page size
# right-side up; there was no request for landscape, so it's not offered.
PAGE_SIZES_MM: dict[str, tuple[float, float]] = {
    "A4": (210.0, 297.0),
    "Letter": (215.9, 279.4),
}

# Spacing between adjacent copies -- a layout choice for cutting
# clearance, not a measured spec (compare DiscTemplate.slider_gap_mm's
# own docstring). Kept small since real MiniDisc cover cards are already
# large relative to A4/Letter -- every extra mm here is a mm less
# available for fitting more copies.
COPY_GAP_MM = 3.0

# Upper bound for both the Copies spinbox and how far max_copies_that_fit()
# searches -- far more than any real MiniDisc print run would ever need,
# just a sanity backstop against an unbounded search.
MAX_COPIES = 99


@dataclass
class PrintPlacement:
    """One rendered label, positioned on the page in millimeters --
    `image` is whatever render_scene_to_image()/apply_grayscale() produced
    (already cropped to the template's own physical bounds -- see
    crop_to_template_bounds below), `width_mm`/`height_mm` its true
    physical size, `x_mm`/`y_mm` its top-left corner relative to the
    physical page's own top-left corner."""

    image: QImage
    x_mm: float
    y_mm: float
    width_mm: float
    height_mm: float


def image_physical_size_mm(image: QImage, dpi: float) -> tuple[float, float]:
    """The real-world size `image` prints at, given the DPI it was
    rendered at via render_scene_to_image(scene, dpi).

    Deliberately derived from the image's own pixel count divided by the
    DPI it was rendered at, NOT from the source scene's on-screen
    coordinates -- render_scene_to_image() already bakes the template's
    true mm dimensions into that pixel count (width_px == width_mm * dpi /
    25.4, by construction), so this recovers it losslessly and stays
    correct even though scene coordinates themselves are frozen in
    whatever Screen DPI was active when the project was opened (see
    CLAUDE.md's "Changing Screen DPI does not retroactively rescale a
    currently-open project" note) -- this function never touches that
    setting at all."""
    return image.width() / dpi * MM_PER_INCH, image.height() / dpi * MM_PER_INCH


def crop_to_template_bounds(scene, image: QImage, dpi: float) -> QImage:
    """Crops `image` (a render_scene_to_image() output for `scene`) down
    to the template's own clip-path bounding box, discarding the small
    fixed transparent margin every template outline builder adds around
    it (see e.g. DesignScene._build_disc_outline's `setSceneRect(QRectF(
    -10, -10, w + 20, h + 20))`).

    Those extra pixels are guaranteed transparent -- render_scene_to_image()
    already clips all painting to this same path -- and carry no physical
    cutting significance (they're purely a rendering/selection-outline
    convenience, not part of the template's actual cut geometry), so
    removing them lets Print... pack copies tighter without the copies'
    real physical cut shapes ever overlapping: user-reported ("transparent
    pixels are not printable so you can optimize it") after manually
    fitting more copies onto a page than this app's own automatic layout
    could, by trimming out exactly this kind of dead space itself."""
    scale = dpi / app_settings.screen_dpi()
    scene_rect = scene.sceneRect()
    to_device = QTransform(scale, 0, 0, scale, -scene_rect.left() * scale, -scene_rect.top() * scale)
    crop_rect = to_device.mapRect(scene.template_clip_path().boundingRect()).toAlignedRect()
    return image.copy(crop_rect)


class PrintLayoutError(Exception):
    """Raised by build_copies_layout() when the requested number of copies
    cannot fit on the chosen page size -- even rotated, even arranged
    side-by-side instead of stacked -- before any manual dragging."""


@dataclass
class PlacedCopies:
    """`positions` is a list of (x_mm, y_mm) top-left corners, one per
    copy, in the same order every time (so re-calling build_copies_layout()
    with the same arguments always reproduces the same layout). `rotated`
    is True if every copy of this label was turned 90 degrees to make the
    requested count fit -- the caller (panels/print_dialog.py) is
    responsible for actually rotating the artwork to match; this dataclass
    only carries the *decision*, not the pixels."""

    positions: list[tuple[float, float]]
    rotated: bool


@dataclass
class _GridLayout:
    columns: int
    rows: int
    width_mm: float
    height_mm: float


def _pack_grid(item_width_mm: float, item_height_mm: float, count: int, max_width_mm: float) -> _GridLayout:
    """Arranges `count` copies of an item_width_mm x item_height_mm
    rectangle (already in whichever orientation the caller wants tried)
    into as many columns as fit within max_width_mm, wrapping into
    additional rows as needed -- a simple row-major grid, not a general
    bin-packer.

    Always returns at least one column, even if that single column's
    width already exceeds max_width_mm -- callers are responsible for
    treating that as a "doesn't fit" result, not this function, since it
    has no page height to check against either."""
    if count <= 0:
        return _GridLayout(0, 0, 0.0, 0.0)
    max_columns_that_fit = int((max_width_mm + COPY_GAP_MM) // (item_width_mm + COPY_GAP_MM))
    columns = max(1, min(max_columns_that_fit, count))
    rows = math.ceil(count / columns)
    width_mm = columns * item_width_mm + (columns - 1) * COPY_GAP_MM
    height_mm = rows * item_height_mm + (rows - 1) * COPY_GAP_MM
    return _GridLayout(columns, rows, width_mm, height_mm)


@dataclass
class _BlockLayout:
    """Where one label type's grid of copies sits within the printable
    area -- `origin` is that block's own top-left corner, relative to the
    printable area's top-left (i.e. NOT yet offset by the page margin)."""

    columns: int
    width_mm: float
    height_mm: float
    origin: tuple[float, float]


def _search_horizontal_split(
    primary_size_mm: tuple[float, float],
    secondary_size_mm: tuple[float, float],
    copies: int,
    available_width_mm: float,
    available_height_mm: float,
) -> tuple[_BlockLayout, _BlockLayout] | None:
    """Tries placing the "primary" label's grid in a narrow, tall column
    (few columns, more rows) so the "secondary" label's grid can fit in
    the leftover width beside it -- the arrangement a simple
    stack-everything-vertically model can never discover, since it always
    gives each block the *entire* printable width and stacks blocks by
    height instead. Column counts are tried from 1 upward (the narrowest,
    tallest column first) since that leaves the most leftover width for
    the secondary block, and returns the first split where both blocks
    fit side by side within the printable area -- not necessarily the
    single most-compact split possible, but enough to recover the kind of
    manual arrangement (one label type as one tight column, the other
    filling the remaining strip beside it) that motivated this function to
    exist at all."""
    primary_w, primary_h = primary_size_mm
    secondary_w, secondary_h = secondary_size_mm
    max_primary_columns = max(1, int((available_width_mm + COPY_GAP_MM) // (primary_w + COPY_GAP_MM)))
    for primary_columns in range(1, min(max_primary_columns, copies) + 1):
        primary_rows = math.ceil(copies / primary_columns)
        primary_width_mm = primary_columns * primary_w + (primary_columns - 1) * COPY_GAP_MM
        primary_height_mm = primary_rows * primary_h + (primary_rows - 1) * COPY_GAP_MM
        if primary_width_mm > available_width_mm or primary_height_mm > available_height_mm:
            continue

        remaining_width_mm = available_width_mm - primary_width_mm - COPY_GAP_MM
        if remaining_width_mm <= 0:
            continue
        secondary_grid = _pack_grid(secondary_w, secondary_h, copies, remaining_width_mm)
        if secondary_grid.width_mm > remaining_width_mm or secondary_grid.height_mm > available_height_mm:
            continue

        primary_block = _BlockLayout(primary_columns, primary_width_mm, primary_height_mm, (0.0, 0.0))
        secondary_block = _BlockLayout(
            secondary_grid.columns, secondary_grid.width_mm, secondary_grid.height_mm, (primary_width_mm + COPY_GAP_MM, 0.0)
        )
        return primary_block, secondary_block
    return None


@dataclass
class _LayoutAttempt:
    disc_block: _BlockLayout
    cover_block: _BlockLayout
    disc_size_mm: tuple[float, float]  # as actually packed -- swapped if disc_rotated
    cover_size_mm: tuple[float, float]
    disc_rotated: bool
    cover_rotated: bool


# Tried in this order, first fit wins:
#  - "vertical": today's original model -- the disc grid as one block, the
#    cover grid as a second block stacked directly below it, each using
#    the *entire* printable width.
#  - "horizontal_cover_primary" / "horizontal_disc_primary": one label's
#    grid narrowed into a tight column so the other's grid can sit beside
#    it in the leftover width (see _search_horizontal_split) -- covers
#    real MiniDisc cover cards, which are wide enough that a single
#    upright column already uses most of the printable width, wasting a
#    usable strip beside it that a vertical-only model leaves empty.
_ARRANGEMENTS = ("vertical", "horizontal_cover_primary", "horizontal_disc_primary")

# Tried in this order, first fit wins -- upright/upright (the natural,
# expected look) always wins whenever it fits at all; rotation is only
# ever used as a fallback to make a copy count fit that otherwise
# wouldn't, never as a "more compact just because" default (a single
# label rotating itself for no visible reason would be a surprising,
# unwanted result of just bumping the copy count). For the same reason,
# every arrangement is tried at a given rotation level before any more
# rotation is introduced -- changing which side the disc/cover grids sit
# on relative to each other is a smaller, less surprising change than
# rotating a label's artwork sideways.
_ROTATION_COMBOS = [(False, False), (True, False), (False, True), (True, True)]


def _attempt_vertical_blocks(
    disc_w: float, disc_h: float, cover_w: float, cover_h: float, copies: int, available_width_mm: float
) -> tuple[_BlockLayout, _BlockLayout] | None:
    disc_grid = _pack_grid(disc_w, disc_h, copies, available_width_mm)
    cover_grid = _pack_grid(cover_w, cover_h, copies, available_width_mm)
    if disc_grid.width_mm > available_width_mm or cover_grid.width_mm > available_width_mm:
        return None
    disc_block = _BlockLayout(disc_grid.columns, disc_grid.width_mm, disc_grid.height_mm, (0.0, 0.0))
    cover_top_mm = disc_grid.height_mm + (COPY_GAP_MM if disc_grid.rows and cover_grid.rows else 0)
    cover_block = _BlockLayout(cover_grid.columns, cover_grid.width_mm, cover_grid.height_mm, (0.0, cover_top_mm))
    return disc_block, cover_block


def _attempt_horizontal_blocks(
    disc_w: float,
    disc_h: float,
    cover_w: float,
    cover_h: float,
    copies: int,
    available_width_mm: float,
    available_height_mm: float,
    primary_is_cover: bool,
) -> tuple[_BlockLayout, _BlockLayout] | None:
    primary_size_mm = (cover_w, cover_h) if primary_is_cover else (disc_w, disc_h)
    secondary_size_mm = (disc_w, disc_h) if primary_is_cover else (cover_w, cover_h)
    split = _search_horizontal_split(primary_size_mm, secondary_size_mm, copies, available_width_mm, available_height_mm)
    if split is None:
        return None
    primary_block, secondary_block = split
    return (secondary_block, primary_block) if primary_is_cover else (primary_block, secondary_block)


def _attempt_layout(
    disc_size_mm: tuple[float, float],
    cover_size_mm: tuple[float, float],
    copies: int,
    available_width_mm: float,
    available_height_mm: float,
    disc_rotated: bool,
    cover_rotated: bool,
    arrangement: str,
) -> _LayoutAttempt | None:
    """One candidate packing: a rotation choice for each label crossed
    with an arrangement strategy for how their two grids relate to each
    other (see _attempt_vertical_blocks/_attempt_horizontal_blocks).
    Returns None if this particular combination doesn't fit --
    build_copies_layout() decides which combination(s) to try and in what
    order."""
    disc_w, disc_h = disc_size_mm[::-1] if disc_rotated else disc_size_mm
    cover_w, cover_h = cover_size_mm[::-1] if cover_rotated else cover_size_mm

    if arrangement == "vertical":
        blocks = _attempt_vertical_blocks(disc_w, disc_h, cover_w, cover_h, copies, available_width_mm)
    else:
        primary_is_cover = arrangement == "horizontal_cover_primary"
        blocks = _attempt_horizontal_blocks(
            disc_w, disc_h, cover_w, cover_h, copies, available_width_mm, available_height_mm, primary_is_cover
        )
    if blocks is None:
        return None
    disc_block, cover_block = blocks

    total_width_mm = max(disc_block.origin[0] + disc_block.width_mm, cover_block.origin[0] + cover_block.width_mm)
    total_height_mm = max(disc_block.origin[1] + disc_block.height_mm, cover_block.origin[1] + cover_block.height_mm)
    if total_width_mm > available_width_mm or total_height_mm > available_height_mm:
        return None

    return _LayoutAttempt(disc_block, cover_block, (disc_w, disc_h), (cover_w, cover_h), disc_rotated, cover_rotated)


def _grid_positions(
    origin_mm: tuple[float, float], columns: int, item_size_mm: tuple[float, float], count: int
) -> list[tuple[float, float]]:
    origin_x_mm, origin_y_mm = origin_mm
    item_width_mm, item_height_mm = item_size_mm
    return [
        (
            origin_x_mm + (i % columns) * (item_width_mm + COPY_GAP_MM),
            origin_y_mm + (i // columns) * (item_height_mm + COPY_GAP_MM),
        )
        for i in range(count)
    ]


def build_copies_layout(
    disc_size_mm: tuple[float, float],
    cover_size_mm: tuple[float, float],
    copies: int,
    page_size_mm: tuple[float, float],
    margin_mm: float,
) -> tuple[PlacedCopies, PlacedCopies]:
    """Packs `copies` of the disc label and `copies` of the cover label
    onto one page, returning (disc_copies, cover_copies) -- see
    _ARRANGEMENTS/_ROTATION_COMBOS above for the combinations tried, in
    priority order, before giving up.

    Raises PrintLayoutError if `copies` don't fit in *any* combination --
    the caller decides how to surface that (see
    panels/print_dialog.py's _relayout_copies)."""
    page_width_mm, page_height_mm = page_size_mm
    available_width_mm = page_width_mm - 2 * margin_mm
    available_height_mm = page_height_mm - 2 * margin_mm

    attempt = None
    for disc_rotated, cover_rotated in _ROTATION_COMBOS:
        for arrangement in _ARRANGEMENTS:
            attempt = _attempt_layout(
                disc_size_mm,
                cover_size_mm,
                copies,
                available_width_mm,
                available_height_mm,
                disc_rotated,
                cover_rotated,
                arrangement,
            )
            if attempt is not None:
                break
        if attempt is not None:
            break

    if attempt is None:
        # report the plain, non-rotated, stacked case's shortfall -- the
        # most legible baseline, even though every combination was tried
        # and all of them fell short.
        disc_grid = _pack_grid(*disc_size_mm, copies, available_width_mm)
        cover_grid = _pack_grid(*cover_size_mm, copies, available_width_mm)
        needed_width_mm = max(disc_grid.width_mm, cover_grid.width_mm)
        needed_height_mm = disc_grid.height_mm + cover_grid.height_mm + COPY_GAP_MM
        raise PrintLayoutError(
            f"{copies} copies do not fit on this page (need at least "
            f"{needed_width_mm:.1f}x{needed_height_mm:.1f}mm printable area, have "
            f"{available_width_mm:.1f}x{available_height_mm:.1f}mm)."
        )

    disc_origin_mm = (margin_mm + attempt.disc_block.origin[0], margin_mm + attempt.disc_block.origin[1])
    cover_origin_mm = (margin_mm + attempt.cover_block.origin[0], margin_mm + attempt.cover_block.origin[1])
    disc_positions = _grid_positions(disc_origin_mm, attempt.disc_block.columns, attempt.disc_size_mm, copies)
    cover_positions = _grid_positions(cover_origin_mm, attempt.cover_block.columns, attempt.cover_size_mm, copies)
    return (
        PlacedCopies(disc_positions, attempt.disc_rotated),
        PlacedCopies(cover_positions, attempt.cover_rotated),
    )


def max_copies_that_fit(
    disc_size_mm: tuple[float, float],
    cover_size_mm: tuple[float, float],
    page_size_mm: tuple[float, float],
    margin_mm: float,
) -> int:
    """How many copies build_copies_layout() would actually accept for
    this page/margin (rotated/rearranged if that's what it takes) -- used
    only to make a "doesn't fit" message concretely actionable ("up to N
    copies fit"), not by the layout logic itself."""
    best = 0
    for copies in range(1, MAX_COPIES + 1):
        try:
            build_copies_layout(disc_size_mm, cover_size_mm, copies, page_size_mm, margin_mm)
        except PrintLayoutError:
            break
        best = copies
    return best


def print_placements(printer: QPrinter, placements: list[PrintPlacement]) -> None:
    """Paints every placement onto `printer` at its exact physical mm
    position/size.

    The caller must already have called `printer.setFullPage(True)` --
    otherwise Qt applies its own default page margins, offsetting
    everything away from the (0, 0)-is-the-page's-own-top-left-corner
    convention the print-layout dialog's positions are expressed in.

    `printer.resolution()` is the target device's dots-per-inch; scaling
    the painter by resolution/25.4 up front makes every subsequent logical
    unit equal to one physical millimeter, so each placement can be drawn
    straight into an (x_mm, y_mm, width_mm, height_mm) rect regardless of
    the source image's own pixel resolution -- Qt's drawImage scaling
    handles the rest."""
    painter = QPainter(printer)
    try:
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        scale = printer.resolution() / MM_PER_INCH
        painter.scale(scale, scale)
        for placement in placements:
            painter.drawImage(
                QRectF(placement.x_mm, placement.y_mm, placement.width_mm, placement.height_mm),
                placement.image,
            )
    finally:
        painter.end()


def render_page_to_image(page_size_mm: tuple[float, float], placements: list[PrintPlacement], dpi: float) -> QImage:
    """Renders `placements` onto a transparent, page-sized QImage at
    `dpi` -- the standalone-PNG equivalent of print_placements(), sharing
    the exact same per-placement paint logic (scale the painter to
    mm-per-unit, then drawImage into an (x_mm, y_mm, width_mm, height_mm)
    rect) so a PNG export can never look different from what Print... or
    Export PDF... would produce for the same on-screen state.

    Unlike a printed page or a PDF, there's no physical "paper" here, so
    the background is left fully transparent rather than painted white --
    the same convention Export Print PNG already uses for everything
    outside a single label's own cut outline."""
    width_mm, height_mm = page_size_mm
    scale = dpi / MM_PER_INCH
    width_px = math.ceil(width_mm * scale)
    height_px = math.ceil(height_mm * scale)

    image = QImage(width_px, height_px, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)

    painter = QPainter(image)
    try:
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.scale(scale, scale)
        for placement in placements:
            painter.drawImage(
                QRectF(placement.x_mm, placement.y_mm, placement.width_mm, placement.height_mm),
                placement.image,
            )
    finally:
        painter.end()

    dots_per_meter = round(dpi / 0.0254)
    image.setDotsPerMeterX(dots_per_meter)
    image.setDotsPerMeterY(dots_per_meter)
    return image
