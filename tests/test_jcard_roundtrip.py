"""An automatically laid-out J-card has to survive a save and a reload.

Reported as "the track list looks wrong after reopening -- as if the font
were off". The font was innocent: it round-trips through
QFont.toString()/fromString() exactly, fractional point sizes included. Two
other things were being dropped.

These tests compare where each layer actually lands on the page --
mapToScene of its own bounding rect -- rather than comparing saved fields.
A field-by-field check is what let this through: every field that was being
saved round-tripped perfectly.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF

from mdtools import gallery
from mdtools.io.project_io import item_from_dict, item_to_dict, load_project, save_project
from mdtools.jcard_layout import build_jcard
from mdtools.project import PAGE_COVER, PAGE_DISC, Project, ProjectMetadata, Track
from mdtools.canvas.scene import DesignScene
from mdtools.templates.registry import load_templates


def _logo_path() -> str:
    return str(gallery.gallery_dir() / "mdlogo.png")


def _build(scene: DesignScene, metadata: ProjectMetadata) -> None:
    """build_jcard needs artwork to take its colours from; the bundled logo
    is a real image and keeps this test off the network."""
    metadata.cover_art = (gallery.gallery_dir() / "mdlogo.png").read_bytes()
    build_jcard(scene, metadata, _logo_path())
    assert scene.print_items(), "precondition: the layout produced something"


def _cover_template():
    return next(t for t in load_templates()["cover"] if not getattr(t, "window_cutout", False))


def _metadata() -> ProjectMetadata:
    return ProjectMetadata(
        album="Unleashed",
        artist="Skillet",
        year=2016,
        tracks=[
            Track("Feel Invincible", 230),
            Track("Back From the Dead", 213),
            Track("Stars", 225),
            Track("I Want to Live", 208),
            Track("Undefeated", 215),
            Track("Famous", 198),
            Track("Lions", 204),
            Track("Out of Hell", 214),
            Track("Burn It Down", 196),
            Track("Watching for Comets", 209),
        ],
    )


def _footprints(scene: DesignScene) -> list[tuple]:
    """Where every design layer actually sits on the page, rounded to a
    tenth of a pixel -- what the eye would compare."""
    prints = []
    for item in scene.print_items():
        rect = item.mapToScene(item.boundingRect()).boundingRect()
        prints.append(
            (round(rect.x(), 1), round(rect.y(), 1), round(rect.width(), 1), round(rect.height(), 1))
        )
    return sorted(prints)


def _text_widths(scene: DesignScene) -> list[float]:
    """Wrap widths of the text layers, in scene order. hasattr first: only
    text items have textWidth at all, and Python evaluates a comprehension's
    conditions left to right."""
    return [item.textWidth() for item in scene.print_items() if hasattr(item, "textWidth")]


def _rebuilt(scene: DesignScene) -> DesignScene:
    """The same page put through item_to_dict/item_from_dict, which is what
    saving and loading a project does to it."""
    copy = DesignScene(scene.template)
    for item in scene.print_items():
        item_from_dict(copy, item_to_dict(item))
    return copy


def test_a_wrapped_track_list_is_still_wrapped_after_a_reload(qt_app):
    """The direct cause of the report: jcard_layout wraps the track list to
    the panel width, that width was never saved, and Qt's default is not to
    wrap -- so it came back as long lines running off the card."""
    scene = DesignScene(_cover_template())
    _build(scene, _metadata())
    before = _text_widths(scene)
    assert any(width > 0 for width in before), "precondition: the layout wraps at least one text layer"

    # Held in a local: a DesignScene dropped as a temporary takes its C++
    # items down with it, and the Python wrappers then raise.
    rebuilt = _rebuilt(scene)

    assert _text_widths(rebuilt) == before


def test_every_jcard_layer_lands_in_exactly_the_same_place_after_a_reload(qt_app):
    """The real check. The panels are rotated a quarter turn, so anything
    that shifts the pivot moves the text somewhere else entirely."""
    scene = DesignScene(_cover_template())
    _build(scene, _metadata())

    assert _footprints(_rebuilt(scene)) == _footprints(scene)


def test_the_pivot_of_a_fitted_text_layer_survives(qt_app):
    """jcard_layout shrinks and wraps a text layer after creating it and
    never re-anchors the origin, so a live one pivots around a point from
    before the fitting. Recomputing the centre on load is a *different*
    point -- reproducing what was there is what keeps the two identical."""
    scene = DesignScene(_cover_template())
    _build(scene, _metadata())
    origins = [item.transformOriginPoint() for item in scene.print_items()]
    rebuilt = _rebuilt(scene)

    assert [item.transformOriginPoint() for item in rebuilt.print_items()] == origins


def test_a_full_project_survives_the_real_save_and_load(qt_app, tmp_path):
    """Not just item_to_dict in memory -- the actual file."""
    cover = DesignScene(_cover_template())
    _build(cover, _metadata())
    disc = DesignScene(load_templates()["disc"][0])
    project = Project(metadata=_metadata(), pages={PAGE_DISC: disc, PAGE_COVER: cover})

    path = tmp_path / "Skillet - Unleashed (2016).mdproj"
    save_project(project, str(path))
    reloaded = load_project(str(path))

    assert _footprints(reloaded.pages[PAGE_COVER]) == _footprints(cover)


def test_a_project_saved_before_these_fields_existed_still_loads(qt_app):
    """No text_width and no origin means an older file, which must keep
    loading exactly as it always did rather than raising on a missing key."""
    scene = DesignScene(_cover_template())
    older = {
        "type": "text",
        "text": "Track one",
        "font_spec": "Arial,9,-1,5,400,0,0,0,0,0",
        "color": "#000000",
        "x": 10.0,
        "y": 20.0,
        "rotation": 0.0,
        "scale_x": 1.0,
        "scale_y": 1.0,
        "z": 0.0,
        "name": None,
    }

    item = item_from_dict(scene, older)

    assert item is not None
    assert item.textWidth() == -1.0
    assert item.transformOriginPoint() == item.boundingRect().center()


def test_an_unwrapped_text_layer_is_not_given_a_width_by_the_round_trip(qt_app):
    """-1 means "do not wrap"; writing it back as a width would turn every
    ordinary text layer into a wrapped one."""
    scene = DesignScene(_cover_template())
    item = scene.add_text("a plain layer")

    assert item_to_dict(item)["text_width"] == -1.0
    assert item_from_dict(scene, item_to_dict(item)).textWidth() == -1.0


def test_a_hand_moved_origin_is_not_silently_recentred(qt_app):
    scene = DesignScene(_cover_template())
    item = scene.add_text("something")
    item.setTransformOriginPoint(QPointF(3.0, 4.0))

    assert item_from_dict(scene, item_to_dict(item)).transformOriginPoint() == QPointF(3.0, 4.0)
