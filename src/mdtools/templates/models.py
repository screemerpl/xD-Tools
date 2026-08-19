"""Data model for label templates (MiniDisc disc labels, cover/J-cards, ...).

All dimensions are in millimeters. Templates are intentionally generic
(chamfered/filleted rect / rectangle-with-folds) so new physical formats
can be added later without code changes -- see registry.py and defaults.json.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DiscTemplate:
    """The MiniDisc label sticker: a rectangle with a chamfered top-left
    corner (a straight diagonal cut) and filleted (rounded) top-right,
    bottom-right and bottom-left corners.

    Optionally also includes a second, independent cut shape for the
    cartridge's sliding-shutter label: a slider_width_mm x
    slider_height_mm rectangle with its left two corners rounded
    (slider_corner_radius_mm) and right two corners square, placed
    slider_gap_mm to the right of the main disc shape, vertically centered.
    slider_width_mm/slider_height_mm of 0 (either) means "no slider label".

    shape == "full_label" switches to a completely different outline: a
    plain corner_radius_mm-rounded rectangle covering most of the disc's
    face (chamfer_mm/fillet_mm are then unused), with the cartridge's
    shutter notch cut out of the right edge instead of placed
    as an adjacent shape. The notch is slider_notch_width_mm x
    slider_notch_height_mm with its left two corners rounded
    (slider_notch_corner_radius_mm), flush against the label's right edge,
    positioned slider_notch_top_mm below the label's own top edge.
    slider_notch_buffer_mm is a physical clearance cut expanding the notch
    by that amount on its top/bottom/left (its right side is already flush
    with the label edge, so there's nothing to expand into there) -- this is
    why that clearance strip can't be printed on, not because of any
    separate no-print-zone concept. slider_travel_mm extends the
    (already-buffered) notch further down by that amount, at the same
    buffered width, forming one continuous cutout: the slot the slider tab
    travels through as it's slid open/closed.

    shape == "cd_label" switches to a CD/CD-R disc label: a plain annulus
    (one circle with the spindle hole subtracted out of it), built the same
    subtracted-path way "full_label" builds its notch, so template_clip_path()
    excludes the hole with no extra union/subtract logic anywhere else.
    outer_diameter_mm is the label's own outer edge and hole_diameter_mm the
    hole punched for the disc's hub; width_mm/height_mm stay equal to
    outer_diameter_mm so everything that reasons about a template's physical
    footprint (printing, copy packing, crop_to_template_bounds) keeps working
    unchanged. Every slider_* field is unused for this shape -- a CD has no
    cartridge and no shutter.

    slider_width_mm/slider_height_mm/slider_corner_radius_mm do double duty:
    for shape == "sticker" they describe the adjacent slider-label shape
    described above; for shape == "full_label" they instead describe a
    second, independent printable/cuttable slider-sticker shape positioned
    *inside* the notch -- flush with the label's right edge and aligned to
    the notch's own (unbuffered) top -- rather than placed beside the disc
    (slider_gap_mm is unused in that case). 0 for either means no such
    piece.
    """

    name: str
    width_mm: float
    height_mm: float
    chamfer_mm: float = 3.0
    fillet_mm: float = 1.0
    safe_margin_mm: float = 1.5
    slider_width_mm: float = 0.0
    slider_height_mm: float = 0.0
    slider_corner_radius_mm: float = 0.0
    slider_gap_mm: float = 3.0
    shape: str = "sticker"  # "sticker" (chamfer+fillet), "full_label" (rounded rect + slider notch), "cd_label" (annulus)
    corner_radius_mm: float = 0.0  # used only when shape == "full_label"
    slider_notch_width_mm: float = 0.0
    slider_notch_height_mm: float = 0.0
    slider_notch_corner_radius_mm: float = 0.0
    slider_notch_top_mm: float = 0.0
    slider_notch_buffer_mm: float = 0.0
    slider_travel_mm: float = 0.0
    # used only when shape == "cd_label"
    outer_diameter_mm: float = 0.0
    hole_diameter_mm: float = 0.0
    kind: str = "disc"
    # Which physical medium this template is for: "md" (MiniDisc) or "cd"
    # (CD-R). File > New offers only the templates matching the medium the
    # project is being started for. Defaults to "md" so every template
    # written before CD support existed stays a MiniDisc one.
    medium: str = "md"
    # False for the built-in defaults: measure your own media/case and
    # correct these numbers (or clone+edit via the Template Manager)
    # before cutting anything for real.
    verified: bool = False
    # Built-in templates (seeded from defaults.json) can't be deleted from
    # the Template Manager, only edited -- so there's always at least one
    # disc and one cover template available for File > New.
    builtin: bool = False
    # Pre-made print layers (text/shapes/images), captured via Tools >
    # "Save as Template..." (see app_window._save_as_template) -- each is
    # one item_to_dict()/item_from_dict() entry, the same format .mdproj
    # project files use. Empty for a plain shape-only template, in which
    # case a fresh disc page falls back to seed_disc_defaults() instead.
    items: list[dict] = field(default_factory=list)


@dataclass
class CoverTemplate:
    """A rectangular label/insert, optionally with vertical fold (score) lines
    and an optional rectangular cutout (a hole cut through the material,
    e.g. a window over the case's shutter).

    fold_offsets_mm are measured from the left edge, e.g. a 3-panel J-card
    with a spine in the middle would have two offsets.

    The cutout, if any, is positioned relative to whichever fold line is on
    its cutout_side ("left" -> the leftmost fold line, cutout sits to its
    left; "right" -> the rightmost fold line, cutout sits to its right):
    cutout_from_fold_mm is the distance from that fold line to the cutout's
    near edge. cutout_from_bottom_mm is the distance from the template's
    bottom edge to the cutout's bottom edge. cutout_width_mm/cutout_height_mm
    of 0 means no cutout.
    """

    name: str
    width_mm: float
    height_mm: float
    corner_radius_mm: float = 0.0
    fold_offsets_mm: list[float] = field(default_factory=list)
    safe_margin_mm: float = 1.5
    cutout_width_mm: float = 0.0
    cutout_height_mm: float = 0.0
    cutout_radius_mm: float = 0.0
    cutout_from_fold_mm: float = 0.0
    cutout_from_bottom_mm: float = 0.0
    cutout_side: str = "left"  # "left" or "right" -- which fold line it's measured from
    # A cassette shell label is cut around the middle of the cassette, and
    # that is **one opening rather than two**: a hole for each reel hub,
    # and between them the window the tape itself is watched through.
    # Measured off a real shell -- two half-circles hub_diameter_mm across,
    # their centres hub_spacing_mm apart and hub_centre_from_top_mm down
    # from the top edge (0 = centred), joined by the rectangle between
    # them. A diameter of 0 means no opening, which is every other label
    # there is.
    hub_diameter_mm: float = 0.0
    hub_spacing_mm: float = 0.0
    hub_centre_from_top_mm: float = 0.0
    # The two top corners cut off at 45 degrees, as a cassette label's are.
    # This is the length of the cut line itself, not of the piece it takes
    # off each edge -- it is what a ruler laid along the cut reads, which
    # is where the number came from. 0 leaves square (or corner_radius_mm
    # rounded) corners.
    top_chamfer_mm: float = 0.0
    # "cover" (an insert or J-card) or "label" (a sticker that goes on the
    # medium itself). Same dataclass, because the shape is the same
    # rectangle -- but a different family, so File > New cannot offer a
    # J-card where a shell label belongs.
    kind: str = "cover"
    # See DiscTemplate.medium.
    medium: str = "md"
    verified: bool = False
    builtin: bool = False
    # Pre-made print layers (text/shapes/images), captured via Tools >
    # "Save as Template..." (see app_window._save_as_template) -- each is
    # one item_to_dict()/item_from_dict() entry, the same format .mdproj
    # project files use. Empty for a plain shape-only template.
    items: list[dict] = field(default_factory=list)


Template = DiscTemplate | CoverTemplate
