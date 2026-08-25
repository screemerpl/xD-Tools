"""The die-cut window J-card -- "MiniDisc Cover (J-Card + Window)".

The window is a 40x40mm hole, so whatever is printed on the panel it lands
on has a hole in it. Cut where the plain card puts its *track list*, that is
destructive: it removes the middle of the one thing the panel exists to say.
Cut through the *cover artwork* it is the point of the template -- a die-cut
sleeve, with the disc's own label showing through the front of the case.

So build_jcard turns the whole card end-for-end for this template: the
artwork moves onto the panel after the folds, the track list onto the panel
before them, and every element on all three panels rotates the other way so
each still reads the right way up. That is one rigid 180-degree turn of the
finished card, not a mirror -- which is why the assertions here are about
*which panel* and *which rotation*, and why the plain card's own behaviour is
re-asserted alongside every flipped case as a regression guard.

The invariant both cards have to keep, and the easiest one to break by
turning only some of the elements: the spine borders the **foot** of the read
content on both panels, never its head.
"""

from __future__ import annotations

import io

import pytest
from PIL import Image
from PySide6.QtWidgets import QGraphicsPixmapItem, QGraphicsTextItem

from mdtools import gallery
from mdtools.canvas.scene import DesignScene
from mdtools.constants import mm_to_px
from mdtools.jcard_layout import build_jcard, spine_caption, window_on_track_panel
from mdtools.project import ProjectMetadata, Track
from mdtools.templates.models import CoverTemplate

# The real built-in geometry, from defaults.json. Constructed here rather
# than loaded from the registry so these assertions cannot be moved by a
# user's own customised templates.json (which the registry does read).
FOLDS = [58.85, 67.15]
CARD_W, CARD_H = 126.0, 73.0

# Where the window lands, derived the same way scene._cutout_path does:
# left = max(fold) + from_fold, bottom = height - from_bottom.
WINDOW_LEFT = 67.15 + 10.3
WINDOW_RIGHT = WINDOW_LEFT + 40.0
WINDOW_BOTTOM = CARD_H - 3.45
WINDOW_TOP = WINDOW_BOTTOM - 40.0


def _plain() -> CoverTemplate:
    return CoverTemplate(name="j-card", width_mm=CARD_W, height_mm=CARD_H, fold_offsets_mm=list(FOLDS))


def _window(**overrides) -> CoverTemplate:
    fields = dict(
        name="j-card + window",
        width_mm=CARD_W,
        height_mm=CARD_H,
        corner_radius_mm=2.0,
        fold_offsets_mm=list(FOLDS),
        cutout_width_mm=40.0,
        cutout_height_mm=40.0,
        cutout_radius_mm=1.0,
        cutout_from_fold_mm=10.3,
        cutout_from_bottom_mm=3.45,
        cutout_side="right",
    )
    fields.update(overrides)
    return CoverTemplate(**fields)


def _cover_bytes() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (300, 300), (28, 54, 96)).save(out, format="PNG")
    return out.getvalue()


def _metadata(tracks: int = 7) -> ProjectMetadata:
    return ProjectMetadata(
        album="Popular Monster",
        artist="Falling In Reverse",
        year=2024,
        tracks=[Track(f"Song {i}", 200) for i in range(1, tracks + 1)],
        cover_art=_cover_bytes(),
    )


def _logo() -> str:
    return str(gallery.gallery_dir() / "mdlogo.png")


def _bounds_mm(item):
    """Where an item actually lands, in millimetres -- its own rotation and
    scale included, which plain pos()/boundingRect() would both miss."""
    from mdtools.constants import px_to_mm

    rect = item.mapToScene(item.boundingRect()).boundingRect()
    return (
        px_to_mm(rect.left()),
        px_to_mm(rect.right()),
        px_to_mm(rect.top()),
        px_to_mm(rect.bottom()),
    )


def _artwork(card):
    """The cover art: the largest pixmap on the card by area, which is the
    only one anywhere near panel-sized (the two logos are ~7mm)."""
    pixmaps = [item for item in card.items if isinstance(item, QGraphicsPixmapItem)]
    assert pixmaps, "no pixmap on the card at all"
    return max(pixmaps, key=lambda item: (lambda b: (b[1] - b[0]) * (b[3] - b[2]))(_bounds_mm(item)))


def _texts(card):
    return [item for item in card.items if isinstance(item, QGraphicsTextItem)]


def _text_saying(card, wanted):
    for item in _texts(card):
        if item.toPlainText().strip() == wanted.strip():
            return item
    raise AssertionError(f"no text item saying {wanted!r}")


def _footer(card, metadata):
    for item in _texts(card):
        text = item.toPlainText()
        if "·" in text and str(metadata.year) in text and item.toPlainText().strip() != spine_caption(metadata):
            return item
    raise AssertionError("no footer text item")


def _built(template, metadata=None, **kwargs):
    """Returns the scene as well as the card, and callers must keep it: a
    DesignScene owns its items, so dropping the only reference to it has Qt
    delete every one of them underneath the card that still lists them."""
    metadata = metadata or _metadata()
    scene = DesignScene(template)
    card = build_jcard(scene, metadata, _logo(), **kwargs)
    assert card.items, "build_jcard produced nothing"
    return scene, card, metadata


# --- which templates need turning end-for-end ------------------------------


def test_a_right_side_window_lands_on_the_track_panel(qt_app):
    assert window_on_track_panel(_window()) is True


def test_a_left_side_window_needs_no_flip(qt_app):
    """Measured leftward from the *first* fold line, so it already lands on
    the front panel -- the plain arrangement is right as it stands."""
    assert window_on_track_panel(_window(cutout_side="left")) is False


def test_a_plain_card_needs_no_flip(qt_app):
    assert window_on_track_panel(_plain()) is False


def test_a_template_with_no_folds_needs_no_flip(qt_app):
    """A disc label or an unfolded insert has no front/back to swap."""
    assert window_on_track_panel(CoverTemplate(name="flat", width_mm=120.0, height_mm=120.0)) is False


def test_a_zero_sized_cutout_needs_no_flip(qt_app):
    """Every plain CoverTemplate carries cutout_* fields at 0 -- "has a
    window" has to mean a window with area, not merely the fields existing."""
    assert window_on_track_panel(_window(cutout_width_mm=0.0)) is False
    assert window_on_track_panel(_window(cutout_height_mm=0.0)) is False


# --- which panel gets which content ---------------------------------------


def test_the_window_variant_puts_the_artwork_on_the_window_panel(qt_app):
    scene, card, _ = _built(_window())
    left, right, _, _ = _bounds_mm(_artwork(card))

    # The panel after the folds: 67.15..126.
    assert left == pytest.approx(FOLDS[1], abs=0.2)
    assert right == pytest.approx(CARD_W, abs=0.2)


def test_the_plain_card_still_puts_the_artwork_before_the_folds(qt_app):
    """The regression guard: nothing about the plain card may move."""
    scene, card, _ = _built(_plain())
    left, right, _, _ = _bounds_mm(_artwork(card))

    assert left == pytest.approx(0.0, abs=0.2)
    assert right == pytest.approx(FOLDS[0], abs=0.2)


def test_the_window_is_cut_through_the_artwork_on_purpose(qt_app):
    """The die-cut *is* the template. The artwork has to span the hole --
    export and the cutter take it out of the print, which is why the J-card
    page needs no trip through Clip Layers even with a window in it."""
    scene, card, _ = _built(_window())
    left, right, top, bottom = _bounds_mm(_artwork(card))

    assert left <= WINDOW_LEFT
    assert right >= WINDOW_RIGHT
    assert top <= WINDOW_TOP
    assert bottom >= WINDOW_BOTTOM


def test_no_text_on_the_window_variant_is_printed_under_the_hole(qt_app):
    """The whole reason the card is turned end-for-end. A track list with a
    40mm hole in the middle of it is the bug this template used to have no
    generator because of."""
    scene, card, metadata = _built(_window())

    for item in _texts(card):
        left, right, top, bottom = _bounds_mm(item)
        overlaps = left < WINDOW_RIGHT and right > WINDOW_LEFT and top < WINDOW_BOTTOM and bottom > WINDOW_TOP
        assert not overlaps, f"{item.toPlainText()!r} is printed over the window"


def test_the_track_list_moves_to_the_panel_before_the_folds(qt_app):
    scene, card, metadata = _built(_window())
    left, right, _, _ = _bounds_mm(_text_saying(card, metadata.artist))

    # Somewhere in 0..58.85, i.e. clear of the last fold line entirely.
    assert right <= FOLDS[0] + 0.2


# --- every element turns the other way ------------------------------------


def test_flipping_turns_every_element_the_other_way(qt_app):
    """A 180-degree turn of the finished card: each element's own rotation
    flips sign. Turning only some of them is what leaves a card with its
    spine caption reading up while its track list reads down."""
    plain_scene, plain, metadata = _built(_plain())  # noqa: F841 -- keeps the items alive
    window_scene, flipped, _ = _built(_window())  # noqa: F841

    pairs = (
        ("artwork", _artwork(plain), _artwork(flipped)),
        ("heading", _text_saying(plain, metadata.artist), _text_saying(flipped, metadata.artist)),
        ("spine caption", _text_saying(plain, spine_caption(metadata)), _text_saying(flipped, spine_caption(metadata))),
        ("footer", _footer(plain, metadata), _footer(flipped, metadata)),
    )
    for what, before, after in pairs:
        assert before.rotation() == pytest.approx(-after.rotation()), f"{what} did not turn the other way"
        assert abs(before.rotation()) == pytest.approx(90.0), f"{what} is not a quarter turn"


def test_the_flag_can_be_forced_independently_of_the_template(qt_app):
    """`flipped` stays overridable so "which way round is this card" can be
    asserted directly, not only through a template with a hole in it."""
    natural_scene, natural, metadata = _built(_plain())  # noqa: F841
    forced_scene, forced, _ = _built(_plain(), flipped=True)  # noqa: F841

    assert _artwork(natural).rotation() == pytest.approx(-_artwork(forced).rotation())
    left, right, _, _ = _bounds_mm(_artwork(forced))
    assert left == pytest.approx(FOLDS[1], abs=0.2)


# --- the spine borders the foot of the content ----------------------------


@pytest.mark.parametrize("template_name", ["plain", "window"])
def test_the_spine_borders_the_foot_of_the_read_content(qt_app, template_name):
    """On both panels of both cards, the spine is at the *bottom* of the
    content as it is read -- never at its head.

    The track panel is the measurable one: place_back puts the heading at
    the top of its reading space and the footer at the bottom, so whichever
    of those ends up nearer the spine says which way the panel reads. Get
    the turn direction wrong for one panel and this flips.
    """
    template = _plain() if template_name == "plain" else _window()
    scene, card, metadata = _built(template)
    panels = scene.fold_panel_rects()
    from mdtools.constants import px_to_mm

    spine_mid = px_to_mm((panels[1].left() + panels[1].right()) / 2)

    def distance(item):
        left, right, _, _ = _bounds_mm(item)
        return abs((left + right) / 2 - spine_mid)

    heading = distance(_text_saying(card, metadata.artist))
    footer = distance(_footer(card, metadata))

    assert footer < heading, "the spine is bordering the head of the track list, not its foot"


def test_the_spine_logo_sits_at_the_read_foot_of_the_strip(qt_app):
    """place_spine puts the logo at the caption's foot. On a flipped card
    that is the strip's *top* edge on the sheet -- turning the caption and
    leaving the logo would put the logo above the text."""
    plain_scene, plain, metadata = _built(_plain())
    window_scene, flipped, _ = _built(_window())

    def spine_logo(scene, card):
        """The one pixmap whose centre falls inside the spine strip -- the
        artwork and the cover logo are both out on a face panel."""
        from mdtools.constants import px_to_mm

        spine = scene.fold_panel_rects()[1]
        low, high = px_to_mm(spine.left()), px_to_mm(spine.right())
        for item in card.items:
            if not isinstance(item, QGraphicsPixmapItem):
                continue
            left, right, _, _ = _bounds_mm(item)
            if low <= (left + right) / 2 <= high:
                return item
        raise AssertionError("no logo on the spine")

    _, _, plain_top, _ = _bounds_mm(spine_logo(plain_scene, plain))
    _, _, _, plain_caption_bottom = _bounds_mm(_text_saying(plain, spine_caption(metadata)))
    # Unflipped: the logo is below the caption on the sheet.
    assert plain_top >= plain_caption_bottom - 1.0

    _, _, _, flipped_bottom = _bounds_mm(spine_logo(window_scene, flipped))
    _, _, flipped_caption_top, _ = _bounds_mm(_text_saying(flipped, spine_caption(metadata)))
    # Flipped: it has moved to the other end, above the caption.
    assert flipped_bottom <= flipped_caption_top + 1.0


# --- the track list itself is unchanged -----------------------------------


def test_the_track_list_reads_the_same_on_both_cards(qt_app):
    """The flip moves the panel and turns it; it must not re-typeset it.
    Same tracks, same number of text layers, same footer."""
    plain_scene, plain, metadata = _built(_plain())  # noqa: F841
    window_scene, flipped, _ = _built(_window())  # noqa: F841

    assert {item.toPlainText() for item in _texts(plain)} == {item.toPlainText() for item in _texts(flipped)}
    assert len(plain.items) == len(flipped.items)
    assert plain.background == flipped.background
    assert plain.accent == flipped.accent
