"""Laying a disc label out automatically: cover art across the label,
MiniDisc logo on the slider sticker.

The two placements pull in opposite directions on purpose -- the cover must
*cover* the label (its overhang is what Clip Layers then trims), the logo
must *fit inside* the slider -- so both directions are pinned down here.
"""

from PySide6.QtCore import QBuffer, QByteArray
from PySide6.QtGui import QColor, QPainter, QPixmap

from mdtools.auto_layout import (
    LOGO_FILL,
    LOGO_RIGHT_MARGIN,
    insertion_mark_colour,
    place_cover_on_label,
    place_logo_on_slider,
    recolour_insertion_mark,
)
from mdtools.canvas.scene import DesignScene
from mdtools.templates.models import DiscTemplate


def _full_label(with_slider: bool = True) -> DiscTemplate:
    fields = dict(
        name="full label",
        width_mm=69.4,
        height_mm=66.4,
        shape="full_label",
        corner_radius_mm=4.0,
        slider_notch_width_mm=27.5,
        slider_notch_height_mm=17.5,
        slider_notch_corner_radius_mm=2.5,
        slider_notch_top_mm=24.3,
        slider_notch_buffer_mm=0.8,
        slider_travel_mm=19.4,
    )
    if with_slider:
        fields.update(slider_width_mm=27.5, slider_height_mm=17.5, slider_corner_radius_mm=2.5)
    return DiscTemplate(**fields)


def _image_bytes(width: int = 600, height: int = 600) -> bytes:
    """Note the named `storage`: QBuffer does not keep the QByteArray it
    was handed alive, so passing a temporary crashes the interpreter -- the
    same class of lifetime gotcha as QTranslator/setGraphicsEffect."""
    pixmap = QPixmap(width, height)
    pixmap.fill(QColor("red"))
    storage = QByteArray()
    buffer = QBuffer(storage)
    buffer.open(QBuffer.OpenModeFlag.WriteOnly)
    pixmap.save(buffer, "PNG")
    buffer.close()
    return bytes(storage)


def _two_band_image(top: str, bottom: str, size: int = 600) -> bytes:
    """An image whose top and bottom halves are deliberately different, so a
    colour taken from the whole thing can be told apart from one taken from
    the band the insertion mark actually sits over."""
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(bottom))
    painter = QPainter(pixmap)
    painter.fillRect(0, 0, size, size // 2, QColor(top))
    painter.end()

    storage = QByteArray()
    buffer = QBuffer(storage)
    buffer.open(QBuffer.OpenModeFlag.WriteOnly)
    pixmap.save(buffer, "PNG")
    buffer.close()
    return bytes(storage)


def _scene_rect_of(item):
    return item.mapToScene(item.boundingRect()).boundingRect()


# --- cover -----------------------------------------------------------------


def test_the_cover_covers_the_label_rather_than_fitting_inside_it(qt_app):
    """Fitting inside would leave the label's corners bare. The overhang is
    intentional -- Clip Layers trims it back to the cut shape."""
    scene = DesignScene(_full_label())
    label = scene.cut_shape_rects()[0]

    item = place_cover_on_label(scene, _image_bytes())

    placed = _scene_rect_of(item)
    assert placed.width() >= label.width() - 1
    assert placed.height() >= label.height() - 1


def test_the_cover_is_centred_on_the_label(qt_app):
    scene = DesignScene(_full_label())
    label = scene.cut_shape_rects()[0]

    item = place_cover_on_label(scene, _image_bytes())

    placed = _scene_rect_of(item)
    assert abs(placed.center().x() - label.center().x()) < 1
    assert abs(placed.center().y() - label.center().y()) < 1


def test_a_wide_cover_still_covers_the_full_height(qt_app):
    """Scaling by the larger ratio is what guarantees this -- the smaller
    one would leave the label short on the other axis."""
    scene = DesignScene(_full_label())
    label = scene.cut_shape_rects()[0]

    item = place_cover_on_label(scene, _image_bytes(1200, 300))

    assert _scene_rect_of(item).height() >= label.height() - 1


def test_unreadable_cover_data_is_not_placed(qt_app):
    scene = DesignScene(_full_label())
    assert place_cover_on_label(scene, b"not an image") is None


# --- logo ------------------------------------------------------------------


def test_the_logo_fits_inside_the_slider_with_room_to_spare(qt_app):
    """It is decoration on a sticker that still has to read as a slider
    label, so it must not fill it edge to edge."""
    scene = DesignScene(_full_label())
    slider = scene.cut_shape_rects()[1]
    logo = scene.add_image_from_data(_image_bytes(200, 200))

    place_logo_on_slider(scene, logo)

    placed = _scene_rect_of(logo)
    assert placed.width() <= slider.width() * LOGO_FILL + 1
    assert placed.height() <= slider.height() * LOGO_FILL + 1


def test_the_logo_sits_against_the_sliders_right_edge_not_in_the_middle(qt_app):
    """It leaves the rest of the sticker free rather than splitting it."""
    scene = DesignScene(_full_label())
    slider = scene.cut_shape_rects()[1]
    logo = scene.add_image_from_data(_image_bytes(200, 200))

    place_logo_on_slider(scene, logo)

    placed = _scene_rect_of(logo)
    expected_margin = slider.width() * LOGO_RIGHT_MARGIN
    assert abs((slider.right() - placed.right()) - expected_margin) < 1
    assert placed.center().x() > slider.center().x(), "it must sit right of centre"


def test_the_logo_stays_inside_the_slider_and_vertically_centred(qt_app):
    scene = DesignScene(_full_label())
    slider = scene.cut_shape_rects()[1]
    logo = scene.add_image_from_data(_image_bytes(200, 200))

    place_logo_on_slider(scene, logo)

    placed = _scene_rect_of(logo)
    assert abs(placed.center().y() - slider.center().y()) < 1
    assert placed.left() >= slider.left() - 1
    assert placed.right() <= slider.right() + 1


def test_a_template_without_a_slider_gets_no_logo(qt_app):
    scene = DesignScene(_full_label(with_slider=False))
    logo = scene.add_image_from_data(_image_bytes(200, 200))

    assert place_logo_on_slider(scene, logo) is None


# --- how it composes with the re-seeded insertion mark ---------------------


def test_the_cover_goes_behind_the_seeded_insertion_mark(qt_app, monkeypatch):
    """Changing the template re-seeds the triangle and its label, and a
    full-bleed cover laid on top would bury them where they'd never be
    noticed. Hidden layers are a worse starting point than ones that need
    restyling."""
    from mdtools.app_window import MainWindow
    from mdtools.project import PAGE_DISC, ProjectMetadata
    from mdtools.templates import registry

    from mdtools.templates.models import CoverTemplate

    template = _full_label()
    # A cover template has to be there too: MainWindow refuses to build a
    # project without one of each kind.
    monkeypatch.setattr(
        registry,
        "load_templates",
        lambda: {"disc": [template], "cover": [CoverTemplate(name="plain", width_mm=126.0, height_mm=73.0)]},
    )
    monkeypatch.setattr("mdtools.app_window.FULL_LABEL_TEMPLATE", template.name)

    window = MainWindow(show_startup_dialog=False)
    window._auto_layout_disc_label(ProjectMetadata(album="A", artist="B", cover_art=_image_bytes()))

    items = window.project.pages[PAGE_DISC].print_items()
    texts = [item for item in items if hasattr(item, "toPlainText")]
    pixmaps = [item for item in items if not hasattr(item, "toPlainText")]
    assert texts, "the insertion mark must survive the layout"
    cover = max(pixmaps, key=lambda item: item.boundingRect().width())
    assert all(text.zValue() > cover.zValue() for text in texts)


# --- the "Full disc label" (no slider) variant ------------------------------
#
# app_window._auto_layout_disc_label() takes an optional template_name so it
# can build either "Full disc label (with Slider)" (the default, used by the
# full-project layout / Tools panel magic wand / post-recording layout -- see
# _auto_layout_project) or the plain "Full disc label" -- same layout, minus
# a slider shape for the logo to land on. See app_window.py's own notes on
# _auto_layout_template_names_for_page/_auto_layout_method_for_page for how
# the Template dropdown and "Regenerate with Font..." pick which one to
# rebuild.


def _window_with_both_full_labels(monkeypatch):
    """A MainWindow with *both* full-label variants registered, so a test
    can switch between them the way the Template dropdown would."""
    from mdtools.app_window import MainWindow
    from mdtools.templates import registry
    from mdtools.templates.models import CoverTemplate

    with_slider = _full_label(with_slider=True)
    no_slider = _full_label(with_slider=False)
    no_slider.name = "Full disc label"
    monkeypatch.setattr(
        registry,
        "load_templates",
        lambda: {
            "disc": [with_slider, no_slider],
            "cover": [CoverTemplate(name="plain", width_mm=126.0, height_mm=73.0)],
        },
    )
    monkeypatch.setattr("mdtools.app_window.FULL_LABEL_TEMPLATE", with_slider.name)
    monkeypatch.setattr("mdtools.app_window.FULL_LABEL_NO_SLIDER_TEMPLATE", no_slider.name)
    return MainWindow(show_startup_dialog=False), with_slider, no_slider


def test_the_no_slider_variant_is_offered_as_a_second_generatable_template(qt_app, monkeypatch):
    window, with_slider, no_slider = _window_with_both_full_labels(monkeypatch)
    from mdtools.project import PAGE_DISC

    names = window._auto_layout_template_names_for_page(PAGE_DISC)

    # A subset check, not equality: the small sticker label family (see
    # test_sticker_disc_label.py) also lives on PAGE_DISC and has its own
    # two generatable names alongside these full-face ones.
    assert {with_slider.name, no_slider.name} <= names
    assert window._can_auto_generate_page(PAGE_DISC, no_slider)
    assert window._can_auto_generate_page(PAGE_DISC, with_slider)


def test_passing_the_no_slider_template_name_builds_that_template(qt_app, monkeypatch):
    from mdtools.project import PAGE_DISC, ProjectMetadata

    window, with_slider, no_slider = _window_with_both_full_labels(monkeypatch)

    window._auto_layout_disc_label(
        ProjectMetadata(album="A", artist="B", cover_art=_image_bytes()), template_name=no_slider.name
    )

    assert window.project.pages[PAGE_DISC].template.name == no_slider.name


def test_the_no_slider_variant_gets_no_orphan_logo_item(qt_app, monkeypatch):
    """Regression: scene.add_image() was being called unconditionally
    before checking whether there was actually a slider to place the logo
    on, leaving an unpositioned, un-undo-tracked image sitting on the page
    whenever there wasn't one."""
    from mdtools.project import PAGE_DISC, ProjectMetadata

    window, with_slider, no_slider = _window_with_both_full_labels(monkeypatch)

    window._auto_layout_disc_label(
        ProjectMetadata(album="A", artist="B", cover_art=_image_bytes()), template_name=no_slider.name
    )

    items = window.project.pages[PAGE_DISC].print_items()
    pixmaps = [item for item in items if not hasattr(item, "toPlainText")]
    # Just the cover -- no second image for a logo with nowhere to go.
    assert len(pixmaps) == 1


def test_the_no_slider_variant_still_gets_the_cover_and_insertion_mark(qt_app, monkeypatch):
    from mdtools.project import PAGE_DISC, ProjectMetadata

    window, with_slider, no_slider = _window_with_both_full_labels(monkeypatch)

    window._auto_layout_disc_label(
        ProjectMetadata(album="A", artist="B", cover_art=_image_bytes()), template_name=no_slider.name
    )

    items = window.project.pages[PAGE_DISC].print_items()
    texts = [item for item in items if hasattr(item, "toPlainText")]
    assert texts, "the insertion mark must still be there"


def test_leaving_template_name_unset_still_defaults_to_the_slider_variant(qt_app, monkeypatch):
    """Every caller that doesn't know about the no-slider variant at all
    (_auto_layout_project, the Tools panel's magic wand, the post-recording
    layout) must keep building exactly what it always has."""
    from mdtools.project import PAGE_DISC, ProjectMetadata

    window, with_slider, no_slider = _window_with_both_full_labels(monkeypatch)

    window._auto_layout_disc_label(ProjectMetadata(album="A", artist="B", cover_art=_image_bytes()))

    assert window.project.pages[PAGE_DISC].template.name == with_slider.name


# --- the insertion mark's colour -------------------------------------------


def test_a_dark_cover_gets_a_light_insertion_mark(qt_app):
    assert insertion_mark_colour(_two_band_image("#101018", "#101018")) == "#ffffff"


def test_a_light_cover_gets_a_dark_insertion_mark(qt_app):
    assert insertion_mark_colour(_two_band_image("#f2f0e8", "#f2f0e8")) == "#000000"


def test_the_colour_comes_from_the_top_of_the_cover_not_its_average(qt_app):
    """The mark sits in the top quarter of the label. A sleeve that is pale
    up there and dark below averages to a mid-tone describing neither, and
    the mark has to be legible where it actually is."""
    assert insertion_mark_colour(_two_band_image(top="#f5f3ee", bottom="#0a0a0c")) == "#000000"
    assert insertion_mark_colour(_two_band_image(top="#0a0a0c", bottom="#f5f3ee")) == "#ffffff"


def test_recolouring_leaves_a_page_without_cover_art_alone(qt_app):
    scene = DesignScene(_full_label())
    scene.seed_disc_defaults()
    before = [item.defaultTextColor().name() for item in scene.print_items()]

    assert recolour_insertion_mark(scene, b"") == []
    assert [item.defaultTextColor().name() for item in scene.print_items()] == before


def test_the_layout_makes_the_insertion_mark_visible_on_a_dark_cover(qt_app, monkeypatch):
    """The whole point: default black text over a full-bleed dark sleeve is
    there but unreadable."""
    from mdtools.project import PAGE_DISC, ProjectMetadata

    window = _window_with_full_label(monkeypatch)
    window._auto_layout_disc_label(
        ProjectMetadata(album="A", artist="B", cover_art=_two_band_image("#101018", "#101018"))
    )

    texts = [i for i in window.project.pages[PAGE_DISC].print_items() if hasattr(i, "toPlainText")]
    assert texts, "the insertion mark must survive the layout"
    assert all(item.defaultTextColor().name() == "#ffffff" for item in texts)


# --- the Tools panel button ------------------------------------------------


def _window_with_full_label(monkeypatch):
    """A MainWindow whose only disc template is the one the layout targets,
    so this never depends on the real per-user templates.json."""
    from mdtools.app_window import MainWindow
    from mdtools.templates import registry
    from mdtools.templates.models import CoverTemplate

    template = _full_label()
    monkeypatch.setattr(
        registry,
        "load_templates",
        lambda: {"disc": [template], "cover": [CoverTemplate(name="plain", width_mm=126.0, height_mm=73.0)]},
    )
    monkeypatch.setattr("mdtools.app_window.FULL_LABEL_TEMPLATE", template.name)
    return MainWindow(show_startup_dialog=False)


def _accept(monkeypatch, module):
    monkeypatch.setattr(module.QMessageBox, "warning", lambda *a, **k: module.QMessageBox.StandardButton.Ok)


def test_the_button_lays_the_label_out_from_existing_metadata(qt_app, monkeypatch):
    """The same layout the record flow produces, for a project that was
    never recorded -- previously this code was reachable only by recording."""
    from mdtools import app_window as app_module
    from mdtools.project import PAGE_DISC, ProjectMetadata

    window = _window_with_full_label(monkeypatch)
    window.project.metadata = ProjectMetadata(album="A", artist="B", cover_art=_image_bytes())
    _accept(monkeypatch, app_module)

    window._auto_layout_from_metadata()

    assert window.project.pages[PAGE_DISC].template.name == "full label"
    assert len(window.project.pages[PAGE_DISC].print_items()) > 1


def test_declining_the_confirmation_leaves_the_page_alone(qt_app, monkeypatch):
    """A single toolbar click must not be able to wipe a page being worked
    on -- unlike the post-recording path, which has already asked plenty."""
    from mdtools import app_window as app_module
    from mdtools.project import PAGE_DISC, ProjectMetadata

    window = _window_with_full_label(monkeypatch)
    window.project.metadata = ProjectMetadata(album="A", artist="B", cover_art=_image_bytes())
    before = window.project.pages[PAGE_DISC]
    monkeypatch.setattr(
        app_module.QMessageBox, "warning", lambda *a, **k: app_module.QMessageBox.StandardButton.Cancel
    )

    window._auto_layout_from_metadata()

    assert window.project.pages[PAGE_DISC] is before


def test_empty_metadata_is_explained_rather_than_laid_out(qt_app, monkeypatch):
    from mdtools import app_window as app_module
    from mdtools.project import PAGE_DISC, ProjectMetadata

    window = _window_with_full_label(monkeypatch)
    window.project.metadata = ProjectMetadata()
    before = window.project.pages[PAGE_DISC]
    told: list = []
    monkeypatch.setattr(app_module.QMessageBox, "information", lambda *a, **k: told.append(a))

    window._auto_layout_from_metadata()

    assert told
    assert window.project.pages[PAGE_DISC] is before


def test_a_missing_cover_is_looked_up_before_giving_up(qt_app, monkeypatch):
    from mdtools import app_window as app_module
    from mdtools.metadata_lookup import AlbumCandidate
    from mdtools.project import PAGE_DISC, ProjectMetadata

    window = _window_with_full_label(monkeypatch)
    window.project.metadata = ProjectMetadata(album="A", artist="B")
    candidate = AlbumCandidate(collection_id=1, artist_name="B", collection_name="A", year=2001, track_count=1)
    monkeypatch.setattr(app_module, "find_cover", lambda *a, **k: (_image_bytes(), candidate))
    monkeypatch.setattr(app_module, "save_downloaded_cover", lambda *a, **k: None)
    _accept(monkeypatch, app_module)

    window._auto_layout_from_metadata()

    assert window.project.metadata.cover_art is not None
    assert window.project.metadata.year == 2001, "a missing year comes along with the cover"
    assert window.project.pages[PAGE_DISC].template.name == "full label"


def test_no_cover_anywhere_stops_short_of_wiping_the_page(qt_app, monkeypatch):
    """The whole layout is built around the cover, so without one there is
    nothing to gain by clearing the page first."""
    from mdtools import app_window as app_module
    from mdtools.project import PAGE_DISC, ProjectMetadata

    window = _window_with_full_label(monkeypatch)
    window.project.metadata = ProjectMetadata(album="A", artist="B")
    before = window.project.pages[PAGE_DISC]
    monkeypatch.setattr(app_module, "find_cover", lambda *a, **k: (None, None))
    warned: list = []
    monkeypatch.setattr(app_module.QMessageBox, "warning", lambda *a, **k: warned.append(a))

    window._auto_layout_from_metadata()

    assert warned
    assert window.project.pages[PAGE_DISC] is before


# --- the rects these rely on ----------------------------------------------


def test_cut_shapes_are_reported_separately_not_as_their_union(qt_app):
    """template_clip_path() unions them, which would size the cover to a
    rectangle spanning both the label and the slider."""
    scene = DesignScene(_full_label())
    rects = scene.cut_shape_rects()

    assert len(rects) == 2
    assert rects[0].width() > rects[1].width()
    union = scene.template_clip_path().boundingRect()
    assert rects[0].width() <= union.width()
