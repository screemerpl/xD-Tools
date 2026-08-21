"""The small chamfered "sticker" disc label's own content generator --
auto_layout.build_sticker_label() -- built from a real example project the
user prepared and laid out by hand (a Taylor Swift MiniDisc template),
using the same background/accent/ink palette and heading+rule motif
jcard_layout.place_back() uses for the case's own back panel: a top band
carrying the insertion mark, cover art across the face, and a bottom band
carrying Artist / a rule / Album + the year. With a slider shape, the
slider gets a snippet of the same cover plus the MiniDisc logo; without
one, nothing is placed there at all -- the same no-slider handling
auto_layout.build_...() 's full-face twin already established (see
test_auto_layout.py's own "Full disc label" tests).
"""

from __future__ import annotations

from PySide6.QtCore import QBuffer, QByteArray
from PySide6.QtGui import QColor, QPixmap

from mdtools.auto_layout import build_sticker_label, place_cover_on_slider
from mdtools.canvas.scene import DesignScene
from mdtools.project import ProjectMetadata, Track
from mdtools.templates.models import DiscTemplate


def _sticker(with_slider: bool = True) -> DiscTemplate:
    fields = dict(name="sticker", width_mm=37.0, height_mm=52.0)
    if with_slider:
        fields.update(slider_width_mm=27.5, slider_height_mm=17.5, slider_corner_radius_mm=2.5)
    return DiscTemplate(**fields)


def _image_bytes(width: int = 600, height: int = 600, colour: str = "red") -> bytes:
    pixmap = QPixmap(width, height)
    pixmap.fill(QColor(colour))
    storage = QByteArray()
    buffer = QBuffer(storage)
    buffer.open(QBuffer.OpenModeFlag.WriteOnly)
    pixmap.save(buffer, "PNG")
    buffer.close()
    return bytes(storage)


def _metadata(**overrides) -> ProjectMetadata:
    fields = dict(
        album="The Life of a Showgirl",
        artist="Taylor Swift",
        year=2025,
        tracks=[Track(title="Track 1", time_seconds=200)],
        cover_art=_image_bytes(),
    )
    fields.update(overrides)
    return ProjectMetadata(**fields)


def _scene_rect_of(item):
    return item.mapToScene(item.boundingRect()).boundingRect()


def _texts(scene) -> list[str]:
    return [i.toPlainText() for i in scene.print_items() if hasattr(i, "toPlainText")]


def _seeded_scene(with_slider: bool = True) -> DesignScene:
    scene = DesignScene(_sticker(with_slider))
    scene.seed_disc_defaults()
    return scene


# -- basic shape / return value ----------------------------------------------


def test_no_cover_art_builds_nothing(qt_app):
    scene = _seeded_scene()
    assert build_sticker_label(scene, _metadata(cover_art=b"")) == []


def test_unfolded_but_unseeded_template_still_builds(qt_app):
    """A page nobody ran seed_disc_defaults() on (a plain DesignScene) has
    no insertion mark to fit -- build_sticker_label() must not choke on
    that, it just has nothing to fit."""
    scene = DesignScene(_sticker())
    added = build_sticker_label(scene, _metadata())
    assert added, "the cover and bands still have to be built"


def _middle_rect(scene):
    """The gap between the top and bottom bands -- what the cover is
    fitted to (see build_sticker_label's own docstring on why it's this
    rect and not the whole label)."""
    from mdtools.auto_layout import STICKER_BOTTOM_BAND_MM, STICKER_TOP_BAND_MM
    from mdtools.constants import mm_to_px

    label = scene.cut_shape_rects()[0]
    top = label.top() + mm_to_px(STICKER_TOP_BAND_MM)
    bottom = label.bottom() - mm_to_px(STICKER_BOTTOM_BAND_MM)
    return label, top, bottom


def test_the_cover_covers_the_gap_between_the_bands_not_the_whole_label(qt_app):
    """Explicit request: an earlier version covered the whole label (with
    the bands' own opaque fill painted over its top and bottom), which
    left however much of a square cover happened to land in that narrow
    strip up to the label's own overall proportions -- unrelated to the
    strip's own shape. Fitting straight to the gap keeps the crop honest
    to what's actually visible."""
    from PySide6.QtWidgets import QGraphicsPixmapItem

    scene = _seeded_scene()
    label, top, bottom = _middle_rect(scene)

    build_sticker_label(scene, _metadata())

    cover = min((i for i in scene.print_items() if isinstance(i, QGraphicsPixmapItem)), key=lambda i: i.zValue())
    footprint = _scene_rect_of(cover)
    assert footprint.width() >= label.width() - 1
    assert footprint.height() >= (bottom - top) - 1
    # And not dramatically taller than that -- covering by a huge margin
    # would mean it's still sized to the whole label rather than the gap.
    assert footprint.height() <= (bottom - top) * 1.5


# -- z-order: the mark and the bands must show through correctly -------------


def test_the_cover_sits_behind_both_bands(qt_app):
    from PySide6.QtWidgets import QGraphicsPixmapItem, QGraphicsRectItem

    scene = _seeded_scene()

    build_sticker_label(scene, _metadata())

    items = scene.print_items()
    # The *main* cover specifically -- not the slider's own snippet, which
    # this scene also has one of (default with_slider=True) and is under
    # no such z-order constraint relative to the bands.
    cover = min((i for i in items if isinstance(i, QGraphicsPixmapItem)), key=lambda i: i.zValue())
    bands = [i for i in items if isinstance(i, QGraphicsRectItem)]
    assert bands, "there should be at least the top and bottom band fills"
    assert all(cover.zValue() < band.zValue() for band in bands)


def test_the_seeded_mark_sits_on_top_of_the_top_band(qt_app):
    from PySide6.QtWidgets import QGraphicsRectItem

    scene = _seeded_scene()
    marks_before = [i for i in scene.print_items() if hasattr(i, "toPlainText")]
    assert marks_before, "seed_disc_defaults() should have added the mark already"

    build_sticker_label(scene, _metadata())

    top_band = min((i for i in scene.print_items() if isinstance(i, QGraphicsRectItem)), key=lambda i: i.zValue())
    assert all(mark.zValue() > top_band.zValue() for mark in marks_before)


def test_the_seeded_mark_is_not_returned_as_a_new_item(qt_app):
    """It already existed -- pushing it through AddItemCommand as if it
    were new would be a double-add."""
    scene = _seeded_scene()
    marks = [i for i in scene.print_items() if hasattr(i, "toPlainText")]

    added = build_sticker_label(scene, _metadata())

    assert not any(item in marks for item in added)


def test_the_seeded_mark_shrinks_to_fit_the_top_band(qt_app):
    """Its default size (see DesignScene.seed_disc_defaults) assumes the
    full-face label's generous top area -- on the 37x52mm sticker it has
    to come down a lot to fit at all."""
    scene = _seeded_scene()
    marks = [i for i in scene.print_items() if hasattr(i, "toPlainText")]
    before = [_scene_rect_of(m).height() for m in marks]

    build_sticker_label(scene, _metadata())

    after = [_scene_rect_of(m).height() for m in marks]
    assert all(a < b for a, b in zip(after, before))


def test_the_seeded_mark_is_laid_out_side_by_side_not_stacked(qt_app):
    """Explicit request: the triangle on the left, the text on the right,
    each free to use the whole band height -- stacking them (the original
    layout) split that height between the two, leaving both smaller than
    they needed to be."""
    scene = _seeded_scene()
    marks = sorted((i for i in scene.print_items() if hasattr(i, "toPlainText")), key=lambda i: i.y())
    triangle, label_text = marks

    build_sticker_label(scene, _metadata())

    triangle_fp = _scene_rect_of(triangle)
    label_fp = _scene_rect_of(label_text)
    # Side by side: close to the same vertical centre, not one stacked
    # above the other -- and the triangle to the left of the label.
    assert abs(triangle_fp.center().y() - label_fp.center().y()) < max(triangle_fp.height(), label_fp.height())
    assert triangle_fp.center().x() < label_fp.center().x()


# -- the bottom band's content -----------------------------------------------


def test_the_bottom_band_carries_artist_album_and_year(qt_app):
    scene = _seeded_scene()

    build_sticker_label(scene, _metadata(artist="Taylor Swift", album="Showgirl", year=2025))

    texts = _texts(scene)
    assert "Taylor Swift" in texts
    assert "Showgirl" in texts
    assert "2025" in texts


def test_no_year_omits_the_year_text(qt_app):
    scene = _seeded_scene()

    build_sticker_label(scene, _metadata(year=None))

    assert "None" not in _texts(scene)


def test_artist_and_year_use_the_accent_colour_album_uses_ink(qt_app):
    """The same background/accent/ink roles jcard_layout.place_back() and
    cd_layout.build_disc_label() already use -- not a separate scoring."""
    from mdtools.palette import accent_colour, dominant_colour, readable_text_colour

    scene = _seeded_scene()
    metadata = _metadata()

    build_sticker_label(scene, metadata)

    background = dominant_colour(metadata.cover_art)
    accent = accent_colour(metadata.cover_art, against=background)
    ink = readable_text_colour(background)

    by_text = {i.toPlainText(): i.defaultTextColor().name() for i in scene.print_items() if hasattr(i, "toPlainText")}
    assert by_text[metadata.artist] == accent
    assert by_text[str(metadata.year)] == accent
    assert by_text[metadata.album] == ink


def test_the_rule_and_top_band_also_use_the_accent_colour(qt_app):
    from PySide6.QtWidgets import QGraphicsRectItem

    from mdtools.palette import accent_colour, dominant_colour

    scene = _seeded_scene()
    metadata = _metadata()

    build_sticker_label(scene, metadata)

    background = dominant_colour(metadata.cover_art)
    accent = accent_colour(metadata.cover_art, against=background)
    rects = [i for i in scene.print_items() if isinstance(i, QGraphicsRectItem)]
    accent_rects = [r for r in rects if r.brush().color().name() == accent]
    # The top band and the thin rule between Artist and Album/Year -- the
    # bottom band's own background fill is the *background* colour, not
    # the accent, so it must not be counted here.
    assert len(accent_rects) >= 2


def test_the_bottom_band_background_is_the_dominant_colour(qt_app):
    from PySide6.QtWidgets import QGraphicsRectItem

    from mdtools.palette import dominant_colour

    scene = _seeded_scene()
    metadata = _metadata()
    label = scene.cut_shape_rects()[0]

    build_sticker_label(scene, metadata)

    background = dominant_colour(metadata.cover_art)
    rects = [i for i in scene.print_items() if isinstance(i, QGraphicsRectItem)]
    # The bottom band is the widest/tallest rect sitting at the bottom of
    # the label with the background colour.
    bottom = [r for r in rects if r.brush().color().name() == background]
    assert bottom, "the bottom band itself must use the background colour"
    assert any(_scene_rect_of(r).bottom() >= label.bottom() - 1 for r in bottom)


# -- background_art override --------------------------------------------------


def test_background_art_is_used_for_the_cover_instead_of_the_raw_metadata_cover(qt_app):
    """Same convention place_cover_on_label()'s own callers rely on: the
    CoverFilterDialog picker's result, not metadata.cover_art directly."""
    from PySide6.QtWidgets import QGraphicsPixmapItem

    scene = _seeded_scene()
    metadata = _metadata(cover_art=_image_bytes(colour="red"))
    filtered = _image_bytes(colour="blue")

    build_sticker_label(scene, metadata, background_art=filtered)

    cover = min(
        (i for i in scene.print_items() if isinstance(i, QGraphicsPixmapItem)),
        key=lambda i: i.zValue(),
    )
    pixel = cover.pixmap().toImage().pixelColor(0, 0)
    assert pixel.blue() > pixel.red()


def test_the_palette_still_comes_from_the_real_cover_not_the_filtered_one(qt_app):
    """The filtered artwork is only what gets *drawn* -- the colours the
    text and bands use are scored against the real cover, same as every
    other auto-generated label in this app."""
    from mdtools.palette import accent_colour, dominant_colour

    scene = _seeded_scene()
    real_cover = _image_bytes(colour="#204060")
    metadata = _metadata(cover_art=real_cover)
    filtered = _image_bytes(colour="#ffffff")

    build_sticker_label(scene, metadata, background_art=filtered)

    background = dominant_colour(real_cover)
    accent = accent_colour(real_cover, against=background)
    artist_item = next(i for i in scene.print_items() if hasattr(i, "toPlainText") and i.toPlainText() == metadata.artist)
    assert artist_item.defaultTextColor().name() == accent


# -- the slider ---------------------------------------------------------------


def test_a_template_without_a_slider_gets_no_slider_content(qt_app):
    scene = _seeded_scene(with_slider=False)

    added = build_sticker_label(scene, _metadata())

    from PySide6.QtWidgets import QGraphicsPixmapItem

    images = [i for i in added if isinstance(i, QGraphicsPixmapItem)]
    assert len(images) == 1, "just the main cover -- no slider to put a second one on"


def test_a_template_with_a_slider_gets_a_cover_snippet_on_it(qt_app):
    scene = _seeded_scene(with_slider=True)

    added = build_sticker_label(scene, _metadata())

    from PySide6.QtWidgets import QGraphicsPixmapItem

    images = [i for i in added if isinstance(i, QGraphicsPixmapItem)]
    assert len(images) == 2, "the main cover plus a snippet on the slider"


def test_place_cover_on_slider_covers_the_slider_completely(qt_app):
    scene = DesignScene(_sticker(with_slider=True))
    slider = scene.cut_shape_rects()[1]

    item = place_cover_on_slider(scene, _image_bytes())

    footprint = _scene_rect_of(item)
    assert footprint.width() >= slider.width() - 1
    assert footprint.height() >= slider.height() - 1


def test_place_cover_on_slider_refuses_a_template_with_no_slider(qt_app):
    scene = DesignScene(_sticker(with_slider=False))
    assert place_cover_on_slider(scene, _image_bytes()) is None
