"""The CD/CD-R disc label: an annulus, and the medium that selects it.

The geometry checks deliberately probe the *clip path* rather than only the
outline item's bounding box: a ring drawn as a plain circle with a circle
painted over it would look identical on screen and still let print content
be exported straight across the spindle hole.
"""

from PySide6.QtCore import QPointF

from mdtools.canvas.scene import DesignScene
from mdtools.constants import mm_to_px
from mdtools.project import MEDIUM_CD, MEDIUM_MD
from mdtools.templates.models import CoverTemplate, DiscTemplate


def _cd_label(**overrides) -> DiscTemplate:
    defaults = dict(
        name="CD label",
        width_mm=118.0,
        height_mm=118.0,
        shape="cd_label",
        outer_diameter_mm=118.0,
        hole_diameter_mm=41.0,
        medium=MEDIUM_CD,
    )
    defaults.update(overrides)
    return DiscTemplate(**defaults)


def test_cd_label_outline_is_one_cut_shape_the_size_of_the_disc(qt_app):
    scene = DesignScene(_cd_label())
    cut_items = scene.cut_items()
    assert len(cut_items) == 1

    rect = cut_items[0].path().boundingRect()
    assert rect.width() == mm_to_px(118.0)
    assert rect.height() == mm_to_px(118.0)


def test_the_spindle_hole_is_subtracted_from_the_label_not_drawn_over_it(qt_app):
    scene = DesignScene(_cd_label())
    clip = scene.template_clip_path()

    centre = QPointF(mm_to_px(59.0), mm_to_px(59.0))
    assert not clip.contains(centre), "print content must not land on the spindle hole"

    # a point on the ring itself: 40mm from the centre is outside the 41mm
    # hole's 20.5mm radius and well inside the 59mm outer radius.
    on_ring = QPointF(mm_to_px(59.0 + 40.0), mm_to_px(59.0))
    assert clip.contains(on_ring)


def test_the_hole_is_concentric_with_the_label(qt_app):
    scene = DesignScene(_cd_label())
    clip = scene.template_clip_path()

    radius = 15.0  # inside the 20.5mm hole radius in every direction
    for dx, dy in ((radius, 0.0), (-radius, 0.0), (0.0, radius), (0.0, -radius)):
        point = QPointF(mm_to_px(59.0 + dx), mm_to_px(59.0 + dy))
        assert not clip.contains(point), f"hole is off-centre towards {(dx, dy)}"


def test_a_label_with_no_hole_is_a_solid_disc(qt_app):
    scene = DesignScene(_cd_label(hole_diameter_mm=0.0))
    assert scene.template_clip_path().contains(QPointF(mm_to_px(59.0), mm_to_px(59.0)))


def test_a_cd_label_gets_no_minidisc_insertion_mark(qt_app):
    """The triangle says which end goes into the deck first, which is a
    cartridge's concept -- a disc dropped onto a spindle has no such end."""
    scene = DesignScene(_cd_label())
    scene.seed_disc_defaults()
    assert scene.print_items() == []


def test_a_minidisc_label_still_gets_its_insertion_mark(qt_app):
    scene = DesignScene(DiscTemplate(name="md", width_mm=37.0, height_mm=52.0))
    scene.seed_disc_defaults()
    assert len(scene.print_items()) == 2


def test_templates_default_to_the_minidisc_medium(qt_app):
    """Every template written before CD-R support existed is a MiniDisc one,
    so the default has to be that rather than something neutral."""
    assert DiscTemplate(name="d", width_mm=1.0, height_mm=1.0).medium == MEDIUM_MD
    assert CoverTemplate(name="c", width_mm=1.0, height_mm=1.0).medium == MEDIUM_MD
