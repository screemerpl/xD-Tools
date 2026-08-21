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
from mdtools.app_window import CD_INSERT_FRONT_TEMPLATE, CD_INSERT_TEMPLATE, CD_LABEL_TEMPLATE, MainWindow
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


def test_the_labels_palette_is_computed_identically_to_the_case_inserts(qt_app):
    """Not just "the same rule" -- the exact same background/accent/ink
    values build_insert() computes for the case insert's back panel
    (jcard_layout.place_back). Scoring the disc label's own accent against
    a flat white instead used to give the two pages of one CD project
    visibly different accent colours for the same album -- reported
    directly, from a real cover."""
    from mdtools.palette import accent_colour, dominant_colour, readable_text_colour

    metadata = _metadata()
    scene = _label_scene()

    items = cd_layout.build_disc_label(scene, metadata, None)

    by_text = {item.toPlainText(): item for item in items if hasattr(item, "toPlainText")}
    expected_background = dominant_colour(metadata.cover_art)
    expected_accent = accent_colour(metadata.cover_art, against=expected_background)
    expected_ink = readable_text_colour(expected_background)

    assert by_text["Falling In Reverse"].defaultTextColor().name() == expected_accent
    assert by_text["Popular Monster"].defaultTextColor().name() == expected_ink
    assert by_text["2024"].defaultTextColor().name() == expected_ink


def test_the_disc_label_and_the_case_back_agree_on_the_artist_colour_for_one_album(qt_app):
    """The actual reported bug, reproduced end to end: build both pages
    for the same album and compare what actually landed on screen, not
    just the palette functions in isolation."""
    metadata = _metadata()

    disc_scene = _label_scene()
    disc_items = cd_layout.build_disc_label(disc_scene, metadata, None)
    disc_artist = next(
        item for item in disc_items if hasattr(item, "toPlainText") and item.toPlainText() == metadata.artist
    )

    back_scene = DesignScene(
        CoverTemplate(name="Tray Card", width_mm=151.0, height_mm=117.5, fold_offsets_mm=[6.5, 144.5])
    )
    back_items = cd_layout.build_case_back(back_scene, metadata, None)
    back_artist = next(
        item for item in back_items if hasattr(item, "toPlainText") and item.toPlainText() == metadata.artist
    )

    assert disc_artist.defaultTextColor().name() == back_artist.defaultTextColor().name()


def test_artist_stands_out_from_album_and_year(qt_app):
    """Artist (bold, the accent) is the one field visually distinct from
    the other two -- album and year deliberately share the plain ink."""
    scene = _label_scene()

    items = cd_layout.build_disc_label(scene, _metadata(), None)

    by_text = {item.toPlainText(): item for item in items if hasattr(item, "toPlainText")}
    artist_colour = by_text["Falling In Reverse"].defaultTextColor().name()
    album_colour = by_text["Popular Monster"].defaultTextColor().name()
    year_colour = by_text["2024"].defaultTextColor().name()

    assert album_colour == year_colour
    assert artist_colour != album_colour


def test_the_year_sits_at_the_very_bottom_of_the_label(qt_app):
    scene = _label_scene()
    disc = scene.cut_shape_rects()[0]

    items = cd_layout.build_disc_label(scene, _metadata(), None)

    year = next(item for item in items if hasattr(item, "toPlainText") and item.toPlainText() == "2024")
    footprint = _footprint(year)
    # Centred horizontally...
    assert abs(footprint.center().x() - disc.center().x()) < mm_to_px(1.0)
    # ...and in the bottom band, not merely somewhere below centre.
    bottom_band = cd_layout._chord_rect(disc, *cd_layout.BOTTOM_BAND, cd_layout.EDGE_MARGIN_MM)
    assert footprint.bottom() <= bottom_band.bottom() + 1
    assert footprint.bottom() > bottom_band.top()


def test_the_mark_and_the_year_no_longer_share_a_band(qt_app):
    """The whole point of moving the mark -- previously they shared the
    bottom band and the year had to dodge whichever logo happened to be
    there; now they occupy genuinely different parts of the label."""
    scene = _label_scene()
    logo = str(gallery.gallery_dir() / "cd_digital_audio.png")

    items = cd_layout.build_disc_label(scene, _metadata(), logo)

    mark = [item for item in items if isinstance(item, QGraphicsPixmapItem)][-1]
    year = next(item for item in items if hasattr(item, "toPlainText") and item.toPlainText() == "2024")
    assert not _footprint(mark).intersects(_footprint(year))


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


def test_the_mark_sits_to_the_right_of_the_label(qt_app):
    scene = _label_scene()
    disc = scene.cut_shape_rects()[0]

    items = cd_layout.build_disc_label(scene, _metadata(), str(gallery.gallery_dir() / "cd_digital_audio.png"))
    mark = [item for item in items if isinstance(item, QGraphicsPixmapItem)][-1]

    centre = _footprint(mark).center()
    assert centre.x() > disc.center().x()
    assert abs(centre.y() - disc.center().y()) < mm_to_px(2.0)


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


def test_a_case_back_project_gets_no_track_list_on_the_insert(qt_app):
    """The track list already lives on the tray card -- printing it again
    on the insert's own left panel would be the same list twice."""
    scene = _insert_scene()

    cd_layout.build_insert(scene, _metadata(), has_case_back=True)

    listed = [
        item
        for item in scene.print_items()
        if hasattr(item, "toPlainText") and "Zombified" in item.toPlainText()
    ]
    assert not listed


def test_a_case_back_project_shows_artist_and_year_instead(qt_app):
    scene = _insert_scene()
    metadata = _metadata()
    left, _right = scene.fold_panel_rects()

    cd_layout.build_insert(scene, metadata, has_case_back=True)

    by_text = {
        item.toPlainText(): item
        for item in scene.print_items()
        if hasattr(item, "toPlainText")
    }
    assert metadata.artist in by_text
    assert str(metadata.year) in by_text
    assert left.contains(_footprint(by_text[metadata.artist]).center())
    assert left.contains(_footprint(by_text[str(metadata.year)]).center())


def test_the_artist_takes_the_accent_and_the_year_takes_the_ink(qt_app):
    from mdtools.palette import accent_colour, dominant_colour, readable_text_colour

    scene = _insert_scene()
    metadata = _metadata()

    cd_layout.build_insert(scene, metadata, has_case_back=True)

    background = dominant_colour(metadata.cover_art)
    by_text = {
        item.toPlainText(): item
        for item in scene.print_items()
        if hasattr(item, "toPlainText")
    }
    assert by_text[metadata.artist].defaultTextColor().name() == accent_colour(
        metadata.cover_art, against=background
    )
    assert by_text[str(metadata.year)].defaultTextColor().name() == readable_text_colour(background)


def test_an_artist_photo_is_placed_when_one_is_given(qt_app):
    scene = _insert_scene()
    left, _right = scene.fold_panel_rects()
    photo_bytes = _cover(colour=(200, 100, 50), size=(300, 400))

    cd_layout.build_insert(scene, _metadata(), has_case_back=True, artist_photo=photo_bytes)

    # cover (right panel) + photo (left panel) == two pixmap items
    pixmaps = [item for item in scene.print_items() if isinstance(item, QGraphicsPixmapItem)]
    assert len(pixmaps) == 2
    photo = min(pixmaps, key=lambda item: _footprint(item).left())
    assert left.contains(_footprint(photo).center())


def test_the_artist_photos_aspect_ratio_is_preserved_not_stretched(qt_app):
    """Explicit request: place_insert_cover()'s own non-uniform stretch is
    fine for a nearly-square album cover but would visibly distort a
    person's face, so the photo is fitted (scaled by the smaller ratio)
    rather than stretched to exactly fill its panel."""
    scene = _insert_scene()
    photo_bytes = _cover(colour=(200, 100, 50), size=(300, 400))  # 3:4 portrait

    cd_layout.build_insert(scene, _metadata(), has_case_back=True, artist_photo=photo_bytes)

    pixmaps = [item for item in scene.print_items() if isinstance(item, QGraphicsPixmapItem)]
    photo = min(pixmaps, key=lambda item: _footprint(item).left())
    footprint = _footprint(photo)
    assert footprint.width() / footprint.height() == pytest.approx(300 / 400, rel=0.01)


def test_no_photo_is_placed_when_none_was_found(qt_app):
    scene = _insert_scene()

    cd_layout.build_insert(scene, _metadata(), has_case_back=True, artist_photo=None)

    # just the front cover -- no photo to place, and no fallback track list
    pixmaps = [item for item in scene.print_items() if isinstance(item, QGraphicsPixmapItem)]
    assert len(pixmaps) == 1


def test_without_a_case_back_the_insert_is_unchanged_from_before(qt_app):
    """has_case_back defaults to False -- every existing caller (and every
    project without one) keeps the plain track-list panel."""
    scene = _insert_scene()

    cd_layout.build_insert(scene, _metadata())

    listed = [
        item
        for item in scene.print_items()
        if hasattr(item, "toPlainText") and "Zombified" in item.toPlainText()
    ]
    assert listed


def test_the_insert_is_not_turned_the_way_a_jcard_is(qt_app):
    """A J-card goes into its case a quarter turn round; this does not."""
    scene = _insert_scene()

    cd_layout.build_insert(scene, _metadata())

    assert all(item.rotation() == 0 for item in scene.print_items())


def test_an_unfolded_sheet_is_refused(qt_app):
    scene = DesignScene(CoverTemplate(name="Flat", width_mm=120.0, height_mm=120.0, medium=MEDIUM_CD))

    with pytest.raises(cd_layout.CdLayoutError):
        cd_layout.build_insert(scene, _metadata())


# -- the front-only insert (build_front_insert) ---------------------------
#
# The slim case's front-only insert has no fold at all -- the back of that
# case is bare plastic tray, with nowhere for a second panel to go -- so
# build_front_insert() is build_insert()'s own right-panel cover placement
# (place_insert_cover(), unchanged), just stretched across the *whole*
# unfolded card instead of half of it.


def _front_scene() -> DesignScene:
    return DesignScene(CoverTemplate(name="Front", width_mm=120.0, height_mm=120.0, medium=MEDIUM_CD))


def test_the_front_only_cover_fills_the_whole_card(qt_app):
    scene = _front_scene()
    whole = scene.cut_shape_rects()[0]

    cd_layout.build_front_insert(scene, _metadata())
    cover = [item for item in scene.print_items() if isinstance(item, QGraphicsPixmapItem)][-1]

    footprint = _footprint(cover)
    assert footprint.left() == pytest.approx(whole.left(), abs=1.0)
    assert footprint.top() == pytest.approx(whole.top(), abs=1.0)
    assert footprint.width() == pytest.approx(whole.width(), abs=1.0)
    assert footprint.height() == pytest.approx(whole.height(), abs=1.0)


def test_the_front_only_insert_builds_nothing_but_the_cover(qt_app):
    """No fold means no left panel -- nowhere for a track list or an
    artist panel to go, unlike build_insert()'s own two-panel version."""
    scene = _front_scene()

    added = cd_layout.build_front_insert(scene, _metadata())

    assert len(added) == 1
    assert isinstance(added[0], QGraphicsPixmapItem)


def test_the_front_only_insert_refuses_a_folded_sheet(qt_app):
    """That is build_insert()'s job, not this one."""
    scene = _insert_scene()

    with pytest.raises(cd_layout.CdLayoutError):
        cd_layout.build_front_insert(scene, _metadata())


def test_the_front_only_insert_needs_cover_art(qt_app):
    scene = _front_scene()

    with pytest.raises(cd_layout.CdLayoutError):
        cd_layout.build_front_insert(scene, ProjectMetadata())


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


def test_the_front_only_insert_builds_through_the_application(qt_app, monkeypatch):
    """_auto_layout_cd_insert(template_name=CD_INSERT_FRONT_TEMPLATE) --
    the toolbar Template dropdown's "Generated from Metadata" path for
    this variant -- against the real bundled template, not a hand-built
    stand-in."""
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    window = MainWindow(show_startup_dialog=False)
    _cd_project(window)
    metadata = _metadata()
    window.project.metadata = metadata

    window._auto_layout_cd_insert(metadata, template_name=CD_INSERT_FRONT_TEMPLATE)

    scene = window.project.pages[PAGE_COVER]
    assert scene.template.name == CD_INSERT_FRONT_TEMPLATE
    items = scene.print_items()
    assert len(items) == 1
    assert isinstance(items[0], QGraphicsPixmapItem)


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


# -- the Digital Audio mark's colour ------------------------------------------
#
# It ships as pure black, so on a dark panel it was present and invisible --
# reported directly, for every place it is used. It is a mask (one opaque
# colour plus alpha), so recolouring it is lossless.


def _mark_colours(item):
    """Every opaque colour in a placed mark, sampled off its own pixmap."""
    image = item.pixmap().toImage()
    found = set()
    for y in range(0, image.height(), 3):
        for x in range(0, image.width(), 3):
            colour = image.pixelColor(x, y)
            if colour.alpha() > 200:
                found.add((colour.red(), colour.green(), colour.blue()))
    return found


def _smallest_pixmap(items):
    pixmaps = [i for i in items if hasattr(i, "pixmap")]
    assert pixmaps
    return min(pixmaps, key=lambda i: i.mapToScene(i.boundingRect()).boundingRect().width())


def test_the_disc_labels_mark_is_scored_against_the_artwork_as_placed(qt_app):
    """Not against the raw cover the rest of the palette comes from.

    What the mark sits on is the *lightened* sleeve: a mid-toned album's raw
    dominant colour is around 0.12 relative luminance while its lightened
    artwork is around 0.48, so scoring it the same way as the text hands a
    white mark to a pale grey background. The text survives that on its
    shadow; a bare mark has none.
    """
    logo = str(gallery.gallery_dir() / "cd_digital_audio.png")

    dark = _label_scene()
    mark = _smallest_pixmap(cd_layout.build_disc_label(dark, _metadata(cover_art=_cover((16, 22, 40))), logo))
    assert _mark_colours(mark) == {(255, 255, 255)}, "a dark sleeve lightens to a dark grey -- white reads"

    mid = _label_scene()
    mark = _smallest_pixmap(cd_layout.build_disc_label(mid, _metadata(cover_art=_cover((110, 96, 90))), logo))
    assert _mark_colours(mark) == {(0, 0, 0)}, "a mid sleeve lightens to a pale grey -- white would vanish"

    light = _label_scene()
    mark = _smallest_pixmap(cd_layout.build_disc_label(light, _metadata(cover_art=_cover((238, 232, 210))), logo))
    assert _mark_colours(mark) == {(0, 0, 0)}


def test_the_tray_cards_mark_takes_the_panel_it_is_printed_on(qt_app):
    """The tray card's middle panel is the cover's dominant colour itself,
    which for most sleeves is dark -- so this is the case that was reported."""
    logo = str(gallery.gallery_dir() / "cd_digital_audio.png")

    scene = DesignScene(
        CoverTemplate(name="Tray Card", width_mm=151.0, height_mm=117.5, fold_offsets_mm=[6.5, 144.5])
    )
    items = cd_layout.build_case_back(scene, _metadata(cover_art=_cover((16, 22, 40))), logo)
    marks = [i for i in items if hasattr(i, "pixmap")]
    assert marks

    # The panel mark: the widest of them (the two spine copies are narrower).
    panel_mark = max(marks, key=lambda i: i.mapToScene(i.boundingRect()).boundingRect().width())
    assert _mark_colours(panel_mark) == {(255, 255, 255)}

