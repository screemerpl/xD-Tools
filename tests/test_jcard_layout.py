"""Laying out the three panels of a J-card.

The front panel is where the surprises live: the cover is rotated a quarter
turn *and* stretched, and Qt applies an item's transform() after its
rotation(), so the scale factors have to be crossed. On a square cover
getting that wrong is invisible in the artwork and only shows up as a panel
filled the wrong way round -- hence the explicit size assertions here.
"""

import io

from PIL import Image

from mdtools import jcard_layout
from mdtools.canvas.scene import DesignScene
from mdtools.jcard_layout import build_jcard, place_front_cover, place_front_logo, spine_caption
from mdtools.project import ProjectMetadata, Track
from mdtools.templates.models import CoverTemplate, DiscTemplate


def _jcard_template() -> CoverTemplate:
    return CoverTemplate(name="j-card", width_mm=126.0, height_mm=73.0, fold_offsets_mm=[58.85, 67.15])


def _cover_bytes(width: int = 600, height: int = 600) -> bytes:
    """Top band red, left band blue -- so where each edge ends up after the
    rotation can be checked, not just how big the result is."""
    image = Image.new("RGB", (width, height), (128, 128, 128))
    image.paste((255, 0, 0), (0, 0, width, max(1, height // 8)))
    image.paste((0, 0, 255), (0, 0, max(1, width // 8), height))
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


def _metadata(tracks: int = 5) -> ProjectMetadata:
    return ProjectMetadata(
        album="Popular Monster",
        artist="Falling In Reverse",
        year=2024,
        tracks=[Track(f"Song {i}", 200) for i in range(1, tracks + 1)],
        cover_art=_cover_bytes(),
    )


def _scene() -> DesignScene:
    return DesignScene(_jcard_template())


def _bounds(item):
    return item.mapToScene(item.boundingRect()).boundingRect()


def _logo_path() -> str:
    from mdtools.gallery import gallery_dir

    return str(gallery_dir() / "mdlogo.png")


# --- panels ----------------------------------------------------------------


def test_a_jcard_splits_into_front_spine_and_back(qt_app):
    panels = _scene().fold_panel_rects()

    assert len(panels) == 3
    assert panels[0].width() > panels[1].width(), "the spine is the narrow one"
    assert abs(panels[0].width() - panels[2].width()) < 1, "front and back match"


def test_a_disc_label_has_no_panels(qt_app):
    """Nothing to fold, so callers can treat "no panels" as "not a cover"."""
    scene = DesignScene(DiscTemplate(name="sticker", width_mm=37.0, height_mm=52.0))
    assert scene.fold_panel_rects() == []


# --- front -----------------------------------------------------------------


def test_the_cover_fills_the_front_panel_exactly(qt_app):
    scene = _scene()
    panel = scene.fold_panel_rects()[0]

    item = place_front_cover(scene, panel, _cover_bytes())

    placed = _bounds(item)
    assert abs(placed.width() - panel.width()) < 1
    assert abs(placed.height() - panel.height()) < 1


def test_the_cover_is_turned_a_quarter_anticlockwise(qt_app):
    """So the artwork's own top edge runs down the card's left side."""
    scene = _scene()
    item = place_front_cover(scene, scene.fold_panel_rects()[0], _cover_bytes())
    assert item.rotation() == -90


def test_a_non_square_cover_still_fills_the_panel(qt_app):
    """The crossed scale factors are what make this work; with them the
    wrong way round a wide cover overflows on one axis and falls short on
    the other."""
    scene = _scene()
    panel = scene.fold_panel_rects()[0]

    item = place_front_cover(scene, panel, _cover_bytes(1200, 400))

    placed = _bounds(item)
    assert abs(placed.width() - panel.width()) < 1
    assert abs(placed.height() - panel.height()) < 1


def test_the_front_logo_is_turned_with_the_cover(qt_app):
    """Left upright it read sideways once the card was in the case: the
    whole front is viewed turned, so anything on it with an "up" turns too."""
    scene = _scene()
    logo = place_front_logo(scene, scene.fold_panel_rects()[0], _logo_path())
    assert logo.rotation() == -90


def test_the_front_logo_sits_in_the_corner_the_reader_sees_as_bottom_right(qt_app):
    """Which is the flat sheet's *top* right, since the panel is turned a
    quarter turn anticlockwise to be read."""
    scene = _scene()
    panel = scene.fold_panel_rects()[0]

    placed = _bounds(place_front_logo(scene, panel, _logo_path()))

    assert placed.center().x() > panel.center().x(), "right on the sheet"
    assert placed.center().y() < panel.center().y(), "top on the sheet = bottom when read"
    assert panel.contains(placed)


def test_unreadable_cover_data_is_not_placed(qt_app):
    scene = _scene()
    assert place_front_cover(scene, scene.fold_panel_rects()[0], b"not an image") is None


# --- spine -----------------------------------------------------------------


def test_the_spine_caption_carries_year_album_and_artist(qt_app):
    caption = spine_caption(_metadata())
    assert "2024" in caption and "Popular Monster" in caption and "Falling In Reverse" in caption


def test_the_spine_caption_skips_whatever_is_missing(qt_app):
    assert spine_caption(ProjectMetadata(album="Only This")) == "Only This"
    assert spine_caption(ProjectMetadata()) == ""


def test_the_spine_caption_is_turned_to_read_down_it(qt_app):
    """The panel is 8.3mm wide and 73mm tall -- unrotated text has nowhere
    to go."""
    scene = _scene()
    card = build_jcard(scene, _metadata(), _logo_path())

    spine = scene.fold_panel_rects()[1]
    rotated = [item for item in card.items if item.rotation() == 90 and spine.contains(_bounds(item).center())]
    assert rotated, "the caption must be rotated onto the spine"


# --- back ------------------------------------------------------------------


def test_the_back_carries_the_track_list(qt_app):
    scene = _scene()
    card = build_jcard(scene, _metadata(4), _logo_path())

    back = scene.fold_panel_rects()[2]
    texts = [
        item.toPlainText()
        for item in card.items
        if hasattr(item, "toPlainText") and back.contains(_bounds(item).center())
    ]
    assert any("Song 1" in text and "Song 4" in text for text in texts)


def test_the_back_turns_the_opposite_way_to_the_front(qt_app):
    """The card wraps around the case, so turning it over to read the back
    puts that panel the other way up. Laying both out anticlockwise -- the
    obvious thing -- left the back upside down in the case."""
    scene = _scene()
    card = build_jcard(scene, _metadata(4), _logo_path())

    back = scene.fold_panel_rects()[2]
    texts = [
        item
        for item in card.items
        if hasattr(item, "toPlainText") and back.contains(_bounds(item).center())
    ]
    assert texts
    assert all(item.rotation() == 90 for item in texts)

    front_logo = place_front_logo(scene, scene.fold_panel_rects()[0], _logo_path())
    assert front_logo.rotation() == -90, "the front still turns the other way"


def test_the_back_carries_more_than_a_bare_list(qt_app):
    """A track list alone on a flat colour looked unfinished -- there is a
    heading, a rule in the accent colour, and a running-time footer."""
    scene = _scene()
    metadata = _metadata(4)
    card = build_jcard(scene, metadata, _logo_path())

    back = scene.fold_panel_rects()[2]
    texts = [
        item.toPlainText()
        for item in card.items
        if hasattr(item, "toPlainText") and back.contains(_bounds(item).center())
    ]
    assert any(text == metadata.artist for text in texts), "the artist heads the panel"
    assert any(text == metadata.album for text in texts)
    assert any("2024" in text and ":" in text for text in texts), "year and running time"


def test_the_running_time_adds_the_tracks_up(qt_app):
    assert jcard_layout.total_running_time(_metadata(3)) == "10:00"
    assert jcard_layout.total_running_time(ProjectMetadata(tracks=[Track("No time")])) == ""
    assert jcard_layout.total_running_time(ProjectMetadata()) == ""


def test_a_long_track_list_splits_into_two_columns(qt_app):
    """One column of fifteen tracks ends up either unreadably small or
    taller than the card."""
    scene = _scene()
    card = build_jcard(scene, _metadata(jcard_layout.TWO_COLUMN_THRESHOLD + 3), _logo_path())

    # The back also carries a heading, a rule and a footer, so count only
    # the items that actually hold track lines.
    columns = [
        item
        for item in card.items
        if hasattr(item, "toPlainText") and "Song" in item.toPlainText()
    ]
    assert len(columns) == 2


def test_everything_stays_inside_its_own_panel(qt_app):
    scene = _scene()
    card = build_jcard(scene, _metadata(12), _logo_path())
    panels = scene.fold_panel_rects()

    for item in card.items:
        bounds = _bounds(item)
        # A pen width of slack: the panel blocks are drawn with a stroke that
        # straddles the edge, and export clips to the cut shape anyway.
        assert any(panel.adjusted(-2, -2, 2, 2).contains(bounds) for panel in panels), item


# --- the whole card --------------------------------------------------------


def test_the_colours_all_come_from_the_cover(qt_app):
    scene = _scene()
    card = build_jcard(scene, _metadata(), _logo_path())

    assert card.background.startswith("#") and card.accent.startswith("#")
    assert card.background != card.accent


def test_without_cover_art_there_is_nothing_to_lay_out(qt_app):
    """Every colour on the card is derived from it."""
    metadata = _metadata()
    metadata.cover_art = None

    assert build_jcard(_scene(), metadata, _logo_path()).items == []


def test_a_page_that_does_not_fold_is_left_alone(qt_app):
    scene = DesignScene(DiscTemplate(name="sticker", width_mm=37.0, height_mm=52.0))
    assert build_jcard(scene, _metadata(), _logo_path()).items == []
