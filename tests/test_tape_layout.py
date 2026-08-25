"""The cassette's three pages, laid out from an album.

The J-card is jcard_layout's own card with a cassette's proportions, so
what is worth pinning down here is the pair of shell labels: one per side,
each carrying its own half of the running order.
"""

import copy
import io

import pytest
from PIL import Image

from mdtools import tape, tape_layout
from mdtools.canvas.scene import DesignScene
from mdtools.project import ProjectMetadata, Track
from mdtools.templates import registry

J_CARD = "Cassette J-Card"
SHELL_LABEL = "Cassette Shell Label"


@pytest.fixture(autouse=True)
def _isolated_templates(tmp_path, monkeypatch):
    """A fresh per-test templates.json, seeded from the bundled defaults --
    without it these read whatever the developer's own real install
    happens to hold, which predates every cassette template."""
    monkeypatch.setattr(registry, "user_templates_path", lambda: tmp_path / "templates.json")


def _cover(colour=(20, 60, 140)) -> bytes:
    image = Image.new("RGB", (300, 300), colour)
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


def _template(name: str, kind: str = "cover"):
    template = next(t for t in registry.load_templates()[kind] if t.name == name)
    return copy.deepcopy(template)


def _album(count: int = 8) -> ProjectMetadata:
    return ProjectMetadata(
        album="Unleashed",
        artist="Skillet",
        year=2016,
        tracks=[Track(title=f"Track {i}", time_seconds=200) for i in range(1, count + 1)],
        cover_art=_cover(),
    )


def _texts(items) -> list[str]:
    return [item.toPlainText() for item in items if hasattr(item, "toPlainText")]


# -- the templates themselves --------------------------------------------


def test_the_j_card_folds_into_three_panels(qt_app):
    scene = DesignScene(_template(J_CARD))

    panels = scene.fold_panel_rects()

    assert len(panels) == 3
    front, spine, flap = panels
    # front, then the narrow spine, then a flap wider than the spine but
    # nothing like the front -- the shape of a real cassette inlay
    assert front.width() > flap.width() > spine.width()


def test_a_shell_label_has_no_folds(qt_app):
    assert DesignScene(_template(SHELL_LABEL, "label")).fold_panel_rects() == []


# -- the J-card ----------------------------------------------------------


def test_the_j_card_lists_the_whole_album_not_one_side(qt_app):
    scene = DesignScene(_template(J_CARD))
    metadata = _album(6)

    tape_layout.build_jcard(scene, metadata)

    printed = "\n".join(_texts(scene.print_items()))
    for track in metadata.tracks:
        assert track.title in printed


def test_the_j_card_refuses_a_page_that_is_not_a_three_panel_card(qt_app):
    scene = DesignScene(_template(SHELL_LABEL, "label"))

    with pytest.raises(tape_layout.TapeLayoutError):
        tape_layout.build_jcard(scene, _album())


def test_the_j_card_needs_cover_art(qt_app):
    scene = DesignScene(_template(J_CARD))
    metadata = _album()
    metadata.cover_art = None

    with pytest.raises(tape_layout.TapeLayoutError):
        tape_layout.build_jcard(scene, metadata)


# -- the shell labels ----------------------------------------------------


def test_each_side_label_carries_only_its_own_tracks(qt_app):
    metadata = _album(6)
    plan = tape.split_sides(metadata.tracks, 60)
    assert len(plan.sides[0].tracks) == 3, "sanity: an even split to tell the halves apart"

    scene = DesignScene(_template(SHELL_LABEL, "label"))
    tape_layout.build_side_label(scene, metadata, plan.sides[0])
    printed = "\n".join(_texts(scene.print_items()))

    for track in plan.sides[0].tracks:
        assert track.title in printed
    for track in plan.sides[1].tracks:
        assert track.title not in printed


def test_a_side_label_says_which_side_it_is(qt_app):
    metadata = _album(4)
    plan = tape.split_sides(metadata.tracks, 60)

    for side in plan.sides:
        scene = DesignScene(_template(SHELL_LABEL, "label"))
        tape_layout.build_side_label(scene, metadata, side)
        assert side.label in _texts(scene.print_items())


def test_the_shell_labels_accent_matches_the_j_cards_own(qt_app):
    """Same fix as the CD disc label: accent_colour()'s result depends on
    what it's scored against, so scoring the shell label's own accent
    against a flat white (as it used to) meant it could never actually
    agree with the J-card's spine accent for the same album -- even though
    both claim to be "the accent colour". This locks the two to the exact
    same computation (dominant_colour -> accent_colour(against=that)),
    not just a similarly-shaped one.
    """
    from mdtools.palette import accent_colour, dominant_colour

    metadata = _album(4)
    plan = tape.split_sides(metadata.tracks, 60)

    label_scene = DesignScene(_template(SHELL_LABEL, "label"))
    tape_layout.build_side_label(label_scene, metadata, plan.sides[0])
    letter = next(
        item for item in label_scene.print_items() if hasattr(item, "toPlainText") and item.toPlainText() == "A"
    )

    background = dominant_colour(metadata.cover_art)
    expected_accent = accent_colour(metadata.cover_art, against=background)
    assert letter.defaultTextColor().name() == expected_accent


def test_the_side_letter_is_the_biggest_thing_on_the_label(qt_app):
    """It is read while the tape is halfway into the deck."""
    metadata = _album(6)
    plan = tape.split_sides(metadata.tracks, 60)
    scene = DesignScene(_template(SHELL_LABEL, "label"))

    tape_layout.build_side_label(scene, metadata, plan.sides[0])

    texts = [item for item in scene.print_items() if hasattr(item, "toPlainText")]
    letter = next(item for item in texts if item.toPlainText() == "A")
    others = [item for item in texts if item is not letter]
    assert others, "sanity: there is other text to be bigger than"
    assert all(letter.font().pointSizeF() > item.font().pointSizeF() for item in others)


def test_a_side_labels_tracks_are_numbered_from_one(qt_app):
    """Side B's first track is track 1 of side B -- what the deck's own
    counter will say when it plays it."""
    metadata = _album(6)
    plan = tape.split_sides(metadata.tracks, 60)
    scene = DesignScene(_template(SHELL_LABEL, "label"))

    tape_layout.build_side_label(scene, metadata, plan.sides[1])

    printed = "\n".join(_texts(scene.print_items()))
    first_on_b = plan.sides[1].tracks[0].title
    assert f"1. {first_on_b}" in printed or f"1 {first_on_b}" in printed


def test_every_word_on_a_side_label_lands_on_the_sticker(qt_app):
    metadata = _album(8)
    plan = tape.split_sides(metadata.tracks, 60)
    scene = DesignScene(_template(SHELL_LABEL, "label"))

    items = tape_layout.build_side_label(scene, metadata, plan.sides[0])

    cut = scene.cut_shape_rects()[0]
    for item in items:
        if not hasattr(item, "toPlainText"):
            continue  # the sleeve overhangs on purpose -- see below
        placed = item.mapToScene(item.boundingRect()).boundingRect()
        # a hair of tolerance for antialiased text bounds, not a whole
        # millimetre of it
        assert cut.adjusted(-1, -1, 1, 1).contains(placed), item.toPlainText()


def test_nothing_is_printed_where_the_reel_holes_are(qt_app):
    """The openings the deck's spindles come up through are cut out of the
    label, so anything laid over one is printed onto a hole."""
    metadata = _album(8)
    plan = tape.split_sides(metadata.tracks, 60)
    scene = DesignScene(_template(SHELL_LABEL, "label"))
    template = scene.template
    assert template.hub_diameter_mm > 0, "sanity: this label has holes in it"

    items = tape_layout.build_side_label(scene, metadata, plan.sides[0])

    clip = scene.template_clip_path()
    for item in items:
        if not hasattr(item, "toPlainText"):
            continue
        placed = item.mapToScene(item.boundingRect()).boundingRect()
        assert not clip.intersects(_hole_paths(scene, placed)), item.toPlainText()


def _hole_paths(scene, rect):
    """The part of `rect` that falls outside the label's own cut shape --
    empty when everything on it is on material."""
    from PySide6.QtGui import QPainterPath

    box = QPainterPath()
    box.addRect(rect)
    return box.subtracted(scene.template_clip_path())


def test_the_sleeve_covers_the_whole_sticker(qt_app):
    """Deliberately oversized: the overhang is what Clip Layers trims, and
    trimming is also what punches the hub holes through the artwork."""
    metadata = _album(6)
    plan = tape.split_sides(metadata.tracks, 60)
    scene = DesignScene(_template(SHELL_LABEL, "label"))

    items = tape_layout.build_side_label(scene, metadata, plan.sides[0])

    cut = scene.cut_shape_rects()[0]
    art = next(item for item in items if not hasattr(item, "toPlainText"))
    placed = art.mapToScene(art.boundingRect()).boundingRect()
    # a hair of tolerance: a square sleeve scaled to cover a wider label
    # matches its width exactly, and exactly is not "contains"
    assert placed.adjusted(-0.5, -0.5, 0.5, 0.5).contains(cut)


def test_a_folded_page_is_refused_as_a_shell_label(qt_app):
    scene = DesignScene(_template(J_CARD))
    plan = tape.split_sides(_album().tracks, 60)

    with pytest.raises(tape_layout.TapeLayoutError):
        tape_layout.build_side_label(scene, _album(), plan.sides[0])


def test_the_inlay_lists_each_side_under_its_own_heading(qt_app):
    """A cassette's running order is two running orders, and the card is
    the only thing that knows where the tape is turned over."""
    scene = DesignScene(_template(J_CARD))
    metadata = _album(8)
    plan = tape.split_sides(metadata.tracks, 60)

    tape_layout.build_jcard(scene, metadata, plan=plan)

    printed = _texts(scene.print_items())
    side_a = next(text for text in printed if "SIDE A" in text)
    side_b = next(text for text in printed if "SIDE B" in text)
    for track in plan.sides[0].tracks:
        assert track.title in side_a and track.title not in side_b
    for track in plan.sides[1].tracks:
        assert track.title in side_b and track.title not in side_a


def test_each_sides_block_is_numbered_from_one(qt_app):
    scene = DesignScene(_template(J_CARD))
    metadata = _album(8)
    plan = tape.split_sides(metadata.tracks, 60)

    tape_layout.build_jcard(scene, metadata, plan=plan)

    side_b = next(text for text in _texts(scene.print_items()) if "SIDE B" in text)
    assert side_b.splitlines()[2].startswith("1."), side_b


def test_without_a_plan_the_inlay_still_lists_the_whole_album(qt_app):
    """Which is the right answer only for a card whose tape nobody has
    decided on yet -- but it must not be an empty flap."""
    scene = DesignScene(_template(J_CARD))
    metadata = _album(6)

    tape_layout.build_jcard(scene, metadata)

    printed = "\n".join(_texts(scene.print_items()))
    assert "SIDE A" not in printed
    for track in metadata.tracks:
        assert track.title in printed


# -- the measured shape --------------------------------------------------


def test_the_shell_label_is_the_measured_one(qt_app):
    template = _template(SHELL_LABEL, "label")

    assert (template.width_mm, template.height_mm) == (90.0, 40.8)
    assert template.top_chamfer_mm == 6.0
    assert template.corner_radius_mm == 1.5
    assert (template.hub_diameter_mm, template.hub_spacing_mm) == (16.0, 43.0)
    assert template.hub_centre_from_top_mm == 23.5
    # 15.5 above the opening, 16 of opening, 9.3 below -- which is what the
    # height is, and how it was measured
    assert template.hub_centre_from_top_mm - template.hub_diameter_mm / 2 == 15.5
    assert round(template.height_mm - template.hub_centre_from_top_mm - template.hub_diameter_mm / 2, 2) == 9.3


def test_the_reels_and_the_tape_window_are_one_opening(qt_app):
    """Not two holes: the gap between the reels is the window the tape is
    watched through, so a label bridging it would cover the tape."""
    scene = DesignScene(_template(SHELL_LABEL, "label"))
    clip = scene.template_clip_path()

    from PySide6.QtCore import QPointF

    from mdtools.constants import mm_to_px

    cut = scene.cut_shape_rects()[0]
    middle = QPointF(cut.center().x(), cut.top() + mm_to_px(23.5))
    assert not clip.contains(middle), "the middle of the label is cut away"
    # ...and both reel centres with it
    for offset in (-21.5, 21.5):
        assert not clip.contains(QPointF(cut.center().x() + mm_to_px(offset), middle.y()))


def test_the_top_corners_are_chamfered_and_the_bottom_ones_rounded(qt_app):
    scene = DesignScene(_template(SHELL_LABEL, "label"))
    clip = scene.template_clip_path()

    from PySide6.QtCore import QPointF

    from mdtools.constants import mm_to_px

    cut = scene.cut_shape_rects()[0]
    inset = mm_to_px(1.0)  # inside the chamfer's own triangle
    for x in (cut.left() + inset, cut.right() - inset):
        assert not clip.contains(QPointF(x, cut.top() + inset)), "a chamfered corner is not material"
    # the bottom ones are only rounded by 1.5mm, so a millimetre in is solid
    for x in (cut.left() + mm_to_px(2), cut.right() - mm_to_px(2)):
        assert clip.contains(QPointF(x, cut.bottom() - mm_to_px(2)))
