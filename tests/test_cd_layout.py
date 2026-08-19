"""The automatic layout for a CD project: the ring and the folded insert.

Several of these exist because looking at the first render caught what
reading the code did not -- the Digital Audio mark placed half off the disc
and then silently removed by Clip Layers, and a cover that sat in the
middle of its panel instead of filling it. Both came from the same mistake
(an item scaled by set_item_scale carries a transform anchored at its own
centre, so pos() is not its visible corner), so the tests here check where
things actually *land*, never what was passed to them.
"""

import io

import pytest
from PIL import Image
from PySide6.QtCore import QRectF
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QGraphicsPixmapItem, QMessageBox

from mdtools import cd_layout, gallery
from mdtools.app_window import CD_INSERT_TEMPLATE, CD_LABEL_TEMPLATE, MainWindow
from mdtools.canvas.scene import DesignScene
from mdtools.constants import mm_to_px
from mdtools.project import MEDIUM_CD, PAGE_COVER, PAGE_DISC, ProjectMetadata, Track
from mdtools.templates import registry
from mdtools.templates.models import CoverTemplate, DiscTemplate


@pytest.fixture(autouse=True)
def _isolated_templates(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "user_templates_path", lambda: tmp_path / "templates.json")


def _cover(colour=(20, 30, 60), size=(240, 240)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, colour).save(out, format="PNG")
    return out.getvalue()


def _metadata(**overrides) -> ProjectMetadata:
    defaults = dict(
        album="Popular Monster",
        artist="Falling In Reverse",
        year=2024,
        tracks=[Track(title="Zombified", time_seconds=209), Track(title="Ronald", time_seconds=241)],
        cover_art=_cover(),
    )
    defaults.update(overrides)
    return ProjectMetadata(**defaults)


def _label_scene() -> DesignScene:
    return DesignScene(
        DiscTemplate(
            name="CD",
            width_mm=118.0,
            height_mm=118.0,
            shape="cd_label",
            outer_diameter_mm=118.0,
            hole_diameter_mm=41.0,
            medium=MEDIUM_CD,
        )
    )


def _insert_scene() -> DesignScene:
    return DesignScene(
        CoverTemplate(
            name="Insert", width_mm=242.0, height_mm=120.0, fold_offsets_mm=[121.0], medium=MEDIUM_CD
        )
    )


def _footprint(item) -> QRectF:
    return item.mapToScene(item.boundingRect()).boundingRect()


# -- lightening ----------------------------------------------------------


def test_lightening_moves_every_pixel_towards_white():
    """A dark sleeve with text over it is a label nobody can read; this is
    what buys the text a background."""
    original = _cover(colour=(20, 30, 60))

    lightened = cd_layout.lighten(original, 0.5)

    before = Image.open(io.BytesIO(original)).convert("RGB").getpixel((5, 5))
    after = Image.open(io.BytesIO(lightened)).convert("RGB").getpixel((5, 5))
    assert all(a > b for a, b in zip(after, before))
    assert after == (137, 142, 157)  # halfway to white, channel by channel


def test_lightening_by_nothing_leaves_the_picture_alone():
    original = _cover(colour=(20, 30, 60))

    after = Image.open(io.BytesIO(cd_layout.lighten(original, 0.0))).convert("RGB").getpixel((5, 5))

    assert after == (20, 30, 60)


# -- the bands text can use ----------------------------------------------


def test_a_band_never_reaches_outside_the_circle():
    """The label is cut along that circle, so a band wider than the chord
    would put text over the edge -- on the disc's clamping area or on
    nothing at all."""
    disc = QRectF(0, 0, mm_to_px(118), mm_to_px(118))
    centre = disc.center()
    radius = disc.width() / 2

    for top, bottom in (cd_layout.TOP_BAND, cd_layout.BOTTOM_BAND, (0.4, 0.6)):
        band = _chord = cd_layout._chord_rect(disc, top, bottom, cd_layout.EDGE_MARGIN_MM)
        for corner in (band.topLeft(), band.topRight(), band.bottomLeft(), band.bottomRight()):
            distance = ((corner.x() - centre.x()) ** 2 + (corner.y() - centre.y()) ** 2) ** 0.5
            assert distance <= radius, f"{top}-{bottom} band reaches past the cut edge"


def test_the_bands_keep_clear_of_the_hub():
    """Nothing can be printed across the spindle hole."""
    disc = QRectF(0, 0, mm_to_px(118), mm_to_px(118))
    hole_top = disc.center().y() - mm_to_px(41) / 2
    hole_bottom = disc.center().y() + mm_to_px(41) / 2

    top = cd_layout._chord_rect(disc, *cd_layout.TOP_BAND, cd_layout.EDGE_MARGIN_MM)
    bottom = cd_layout._chord_rect(disc, *cd_layout.BOTTOM_BAND, cd_layout.EDGE_MARGIN_MM)

    assert top.bottom() <= hole_top
    assert bottom.top() >= hole_bottom


# -- the disc label ------------------------------------------------------


def test_the_label_carries_the_cover_the_album_and_the_mark(qt_app):
    scene = _label_scene()
    logo = str(gallery.gallery_dir() / "cd_digital_audio.png")

    items = cd_layout.build_disc_label(scene, _metadata(), logo)

    texts = [item.toPlainText() for item in items if hasattr(item, "toPlainText")]
    assert "Falling In Reverse" in texts
    assert "Popular Monster" in texts
    assert "2024" in texts
    # the cover and the mark, both images
    assert sum(1 for item in items if isinstance(item, QGraphicsPixmapItem)) == 2


def test_everything_on_the_label_lands_inside_the_disc(qt_app):
    """The regression that mattered: the mark was placed half off the edge,
    where Clip Layers removed it outright rather than clipping it -- so it
    did not look wrong, it was simply missing."""
    scene = _label_scene()
    disc = scene.cut_shape_rects()[0]
    logo = str(gallery.gallery_dir() / "cd_digital_audio.png")

    items = cd_layout.build_disc_label(scene, _metadata(), logo)

    for item in items:
        if isinstance(item, QGraphicsPixmapItem) and _footprint(item).width() > disc.width() * 0.9:
            continue  # the cover overshoots on purpose; Clip Layers trims it
        assert disc.contains(_footprint(item)), f"{item} is not fully on the disc"


def test_the_mark_sits_at_the_foot_of_the_label(qt_app):
    scene = _label_scene()
    disc = scene.cut_shape_rects()[0]

    items = cd_layout.build_disc_label(scene, _metadata(), str(gallery.gallery_dir() / "cd_digital_audio.png"))
    mark = [item for item in items if isinstance(item, QGraphicsPixmapItem)][-1]

    assert _footprint(mark).center().y() > disc.center().y()


def test_the_label_is_built_without_a_mark_when_there_is_no_logo_file(qt_app):
    items = cd_layout.build_disc_label(_label_scene(), _metadata(), None)

    assert sum(1 for item in items if isinstance(item, QGraphicsPixmapItem)) == 1


def test_a_label_needs_cover_art(qt_app):
    with pytest.raises(cd_layout.CdLayoutError):
        cd_layout.build_disc_label(_label_scene(), _metadata(cover_art=None), None)


def test_the_insert_page_is_not_a_disc_label(qt_app):
    with pytest.raises(cd_layout.CdLayoutError):
        cd_layout.build_insert(_label_scene(), _metadata())


# -- the folded insert ---------------------------------------------------


def test_the_cover_fills_the_right_hand_panel(qt_app):
    """It sat in the middle of the panel with white either side until the
    placement stopped using pos() -- see this module's own header."""
    scene = _insert_scene()
    left, right = scene.fold_panel_rects()

    cd_layout.build_insert(scene, _metadata())
    cover = [item for item in scene.print_items() if isinstance(item, QGraphicsPixmapItem)][-1]

    footprint = _footprint(cover)
    assert footprint.left() == pytest.approx(right.left(), abs=1.0)
    assert footprint.width() == pytest.approx(right.width(), abs=1.0)
    assert footprint.height() == pytest.approx(right.height(), abs=1.0)
    assert footprint.left() > left.right() - 1.0


def test_the_track_list_goes_on_the_left_hand_panel(qt_app):
    scene = _insert_scene()
    left, _right = scene.fold_panel_rects()

    cd_layout.build_insert(scene, _metadata())

    listed = [
        item
        for item in scene.print_items()
        if hasattr(item, "toPlainText") and "Zombified" in item.toPlainText()
    ]
    assert listed, "the track list is missing"
    assert left.contains(_footprint(listed[0]).center())


def test_the_insert_is_not_turned_the_way_a_jcard_is(qt_app):
    """A J-card goes into its case a quarter turn round; this does not."""
    scene = _insert_scene()

    cd_layout.build_insert(scene, _metadata())

    assert all(item.rotation() == 0 for item in scene.print_items())


def test_an_unfolded_sheet_is_refused(qt_app):
    scene = DesignScene(CoverTemplate(name="Flat", width_mm=120.0, height_mm=120.0, medium=MEDIUM_CD))

    with pytest.raises(cd_layout.CdLayoutError):
        cd_layout.build_insert(scene, _metadata())


# -- through the application ---------------------------------------------


def _cd_project(window: MainWindow) -> None:
    templates = registry.load_templates()
    window.project.medium = MEDIUM_CD
    window.apply_template(PAGE_DISC, next(t for t in templates["disc"] if t.name == CD_LABEL_TEMPLATE))
    window.apply_template(PAGE_COVER, next(t for t in templates["cover"] if t.name == CD_INSERT_TEMPLATE))


def test_laying_out_a_cd_project_builds_both_pages(qt_app, monkeypatch):
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    window = MainWindow(show_startup_dialog=False)
    _cd_project(window)
    metadata = _metadata()
    window.project.metadata = metadata

    window._auto_layout_project(metadata)

    assert window.project.pages[PAGE_DISC].template.name == CD_LABEL_TEMPLATE
    assert window.project.pages[PAGE_COVER].template.name == CD_INSERT_TEMPLATE
    assert window.project.pages[PAGE_DISC].print_items()
    assert window.project.pages[PAGE_COVER].print_items()


def test_the_mark_survives_the_trip_through_clip_layers(qt_app, monkeypatch):
    """End to end, because that is where it went missing: the layout added
    it, Clip Layers removed it, and only the rendered page showed it."""
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    window = MainWindow(show_startup_dialog=False)
    _cd_project(window)
    metadata = _metadata()
    window.project.metadata = metadata

    window._auto_layout_project(metadata)

    images = [
        item for item in window.project.pages[PAGE_DISC].print_items() if isinstance(item, QGraphicsPixmapItem)
    ]
    assert len(images) == 2, "the cover and the Digital Audio mark should both be on the label"


def test_a_cd_project_is_never_rebuilt_with_minidisc_templates(qt_app, monkeypatch):
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    window = MainWindow(show_startup_dialog=False)
    _cd_project(window)
    metadata = _metadata()

    window._auto_layout_project(metadata)

    for page in (PAGE_DISC, PAGE_COVER):
        assert window.project.pages[page].template.medium == MEDIUM_CD


def test_the_bundled_mark_is_a_real_image(qt_app):
    """It is generated from an SVG by a script; a broken render would show
    up as a label with nothing at the bottom."""
    pixmap = QPixmap(str(gallery.gallery_dir() / "cd_digital_audio.png"))

    assert not pixmap.isNull()
    assert pixmap.width() > 200
