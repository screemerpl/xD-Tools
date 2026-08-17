import json

from PySide6.QtCore import QByteArray, QBuffer, QIODevice
from PySide6.QtGui import QColor, QImage

from mdtools.canvas.items import get_item_name, get_item_scale, set_item_name, set_item_scale
from mdtools.canvas.scene import DesignScene
from mdtools.io.project_io import load_project, save_project
from mdtools.project import PAGE_COVER, PAGE_DISC, GrayscaleAdjustment, Project, ProjectMetadata, TextStyle, Track
from mdtools.templates.models import CoverTemplate, DiscTemplate


def _fake_png_bytes() -> bytes:
    image = QImage(4, 4, QImage.Format.Format_ARGB32)
    image.fill(QColor("red"))
    buffer = QByteArray()
    device = QBuffer(buffer)
    device.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(device, "PNG")
    device.close()
    return bytes(buffer)


def _make_project() -> Project:
    disc_scene = DesignScene(DiscTemplate(name="Disc", width_mm=37.0, height_mm=52.0))
    text_item = disc_scene.add_text("Track 1")
    set_item_name(text_item, "Track Title")
    image_item = disc_scene.add_image_from_data(_fake_png_bytes())
    image_item.setRotation(15)
    set_item_scale(image_item, 1.5, 0.8)
    disc_scene.move_item_up(text_item)  # text should now be topmost, image behind it

    cover_scene = DesignScene(CoverTemplate(name="Cover", width_mm=145.0, height_mm=68.0, fold_offsets_mm=[68, 73]))
    cover_scene.add_rectangle()

    metadata = ProjectMetadata(
        album="Test Album",
        artist="Test Artist",
        year=2001,
        tracks=[Track(title="Intro", time_seconds=95), Track(title="Outro", time_seconds=None)],
        cover_art=_fake_png_bytes(),
    )
    return Project(metadata=metadata, pages={PAGE_DISC: disc_scene, PAGE_COVER: cover_scene})


def test_project_round_trip_is_a_single_self_contained_file(qt_app, tmp_path):
    project = _make_project()

    project_path = tmp_path / "design.mdproj"
    save_project(project, project_path)

    # nothing besides the single JSON file should be required to reload it
    assert list(tmp_path.iterdir()) == [project_path]

    reloaded = load_project(project_path)

    assert reloaded.metadata.album == "Test Album"
    assert reloaded.metadata.artist == "Test Artist"
    assert reloaded.metadata.year == 2001
    assert [t.title for t in reloaded.metadata.tracks] == ["Intro", "Outro"]
    assert reloaded.metadata.tracks[0].time_seconds == 95
    assert reloaded.metadata.tracks[1].time_seconds is None
    assert reloaded.metadata.cover_art == _fake_png_bytes()

    disc_items = reloaded.pages[PAGE_DISC].print_items()  # topmost first
    assert len(disc_items) == 2
    assert disc_items[0].toPlainText() == "Track 1"  # move_item_up brought text to the front
    assert get_item_name(disc_items[0]) == "Track Title"

    reloaded_images = [i for i in disc_items if hasattr(i, "pixmap")]
    assert len(reloaded_images) == 1
    assert reloaded_images[0].rotation() == 15
    assert get_item_scale(reloaded_images[0]) == (1.5, 0.8)
    assert not reloaded_images[0].pixmap().isNull()
    assert get_item_name(reloaded_images[0]) is None  # never renamed

    cover_items = reloaded.pages[PAGE_COVER].print_items()
    assert len(cover_items) == 1
    assert cover_items[0].rect().width() > 0  # the rectangle round-tripped


def test_text_item_font_style_round_trips_including_bold_italic_strikeout(qt_app, tmp_path):
    disc_scene = DesignScene(DiscTemplate(name="Disc", width_mm=37.0, height_mm=52.0))
    text_item = disc_scene.add_text("Styled")
    font = text_item.font()
    font.setBold(True)
    font.setItalic(True)
    font.setUnderline(True)
    font.setStrikeOut(True)
    text_item.setFont(font)

    cover_scene = DesignScene(CoverTemplate(name="Cover", width_mm=145.0, height_mm=68.0, fold_offsets_mm=[68, 73]))
    project = Project(metadata=ProjectMetadata(), pages={PAGE_DISC: disc_scene, PAGE_COVER: cover_scene})

    project_path = tmp_path / "styled.mdproj"
    save_project(project, project_path)
    reloaded = load_project(project_path)  # kept alive: GC'd otherwise, taking its items with it
    reloaded_font = reloaded.pages[PAGE_DISC].print_items()[0].font()

    assert reloaded_font.bold()
    assert reloaded_font.italic()
    assert reloaded_font.underline()
    assert reloaded_font.strikeOut()


def test_default_text_style_round_trips(qt_app, tmp_path):
    from PySide6.QtGui import QFont

    font = QFont("Courier New")
    font.setPointSizeF(18.0)
    font.setBold(True)
    font.setStrikeOut(True)
    font_spec = font.toString()

    project = _make_project()
    project.default_text_style = TextStyle(font_spec=font_spec, color="#00ff00")

    project_path = tmp_path / "design.mdproj"
    save_project(project, project_path)
    reloaded = load_project(project_path)

    assert reloaded.default_text_style == TextStyle(font_spec=font_spec, color="#00ff00")


def test_default_text_style_defaults_to_unset_when_missing_from_older_project_files(qt_app, tmp_path):
    project = _make_project()
    project_path = tmp_path / "design.mdproj"
    save_project(project, project_path)

    # simulate a project file saved before this field existed
    data = json.loads(project_path.read_text(encoding="utf-8"))
    del data["default_text_style"]
    project_path.write_text(json.dumps(data), encoding="utf-8")

    reloaded = load_project(project_path)
    assert reloaded.default_text_style == TextStyle()
    assert not reloaded.default_text_style.is_set()


def test_grayscale_adjustment_round_trips(qt_app, tmp_path):
    project = _make_project()
    project.grayscale_adjustment = GrayscaleAdjustment(brightness=25, contrast=-40)

    project_path = tmp_path / "design.mdproj"
    save_project(project, project_path)
    reloaded = load_project(project_path)

    assert reloaded.grayscale_adjustment == GrayscaleAdjustment(brightness=25, contrast=-40)


def test_grayscale_adjustment_defaults_to_unset_when_missing_from_older_project_files(qt_app, tmp_path):
    project = _make_project()
    project_path = tmp_path / "design.mdproj"
    save_project(project, project_path)

    # simulate a project file saved before this field existed
    data = json.loads(project_path.read_text(encoding="utf-8"))
    del data["grayscale_adjustment"]
    project_path.write_text(json.dumps(data), encoding="utf-8")

    reloaded = load_project(project_path)
    assert reloaded.grayscale_adjustment == GrayscaleAdjustment()


def test_cover_art_defaults_to_none_when_missing_from_older_project_files(qt_app, tmp_path):
    project = _make_project()
    project_path = tmp_path / "design.mdproj"
    save_project(project, project_path)

    # simulate a project file saved before cover_art_base64 existed
    data = json.loads(project_path.read_text(encoding="utf-8"))
    del data["metadata"]["cover_art_base64"]
    project_path.write_text(json.dumps(data), encoding="utf-8")

    reloaded = load_project(project_path)
    assert reloaded.metadata.cover_art is None


def test_no_cover_art_round_trips_as_none_not_an_error(qt_app, tmp_path):
    project = _make_project()
    project.metadata.cover_art = None
    project_path = tmp_path / "design.mdproj"
    save_project(project, project_path)

    reloaded = load_project(project_path)
    assert reloaded.metadata.cover_art is None


def test_item_name_defaults_to_none_when_missing_from_older_project_files(qt_app, tmp_path):
    project = _make_project()
    project_path = tmp_path / "design.mdproj"
    save_project(project, project_path)

    # simulate a project file saved before per-item "name" existed
    data = json.loads(project_path.read_text(encoding="utf-8"))
    for item_data in data["pages"][PAGE_DISC]["items"]:
        del item_data["name"]
    project_path.write_text(json.dumps(data), encoding="utf-8")

    reloaded = load_project(project_path)
    for item in reloaded.pages[PAGE_DISC].print_items():
        assert get_item_name(item) is None
