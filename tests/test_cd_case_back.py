"""The CD case back: a jewel case tray card, and the fact that it is
optional.

Optional is the part with teeth. A project without one is the normal case,
so nothing may assume it exists -- and the automatic layout must not create
it, replace its template, or complain about its absence.
"""

import io

import pytest
from PIL import Image
from PySide6.QtWidgets import QInputDialog, QMessageBox

from mdtools import cd_layout
from mdtools.app_window import CD_INSERT_TEMPLATE, CD_LABEL_TEMPLATE, MainWindow
from mdtools.canvas.scene import DesignScene
from mdtools.io.project_io import load_project, save_project
from mdtools.panels.new_design_dialog import NewDesignDialog
from mdtools.project import MEDIUM_CD, PAGE_BACK, PAGE_COVER, PAGE_DISC, ProjectMetadata, Track
from mdtools.templates import registry
from mdtools.templates.models import CoverTemplate

TRAY_CARD = "CD Jewel Case Back (Tray Card)"


@pytest.fixture(autouse=True)
def _isolated_templates(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "user_templates_path", lambda: tmp_path / "templates.json")


def _tray_template():
    return next(t for t in registry.load_templates()["cover"] if t.name == TRAY_CARD)


def _metadata() -> ProjectMetadata:
    out = io.BytesIO()
    Image.new("RGB", (240, 240), (20, 30, 60)).save(out, format="PNG")
    return ProjectMetadata(
        album="Popular Monster",
        artist="Falling In Reverse",
        year=2024,
        tracks=[Track(title="Zombified", time_seconds=209), Track(title="Ronald", time_seconds=241)],
        cover_art=out.getvalue(),
    )


def _cd_window(with_back: bool) -> MainWindow:
    templates = registry.load_templates()
    window = MainWindow(show_startup_dialog=False)
    window.project.medium = MEDIUM_CD
    window.apply_template(PAGE_DISC, next(t for t in templates["disc"] if t.name == CD_LABEL_TEMPLATE))
    window.apply_template(PAGE_COVER, next(t for t in templates["cover"] if t.name == CD_INSERT_TEMPLATE))
    if with_back:
        window.project.pages[PAGE_BACK] = DesignScene(_tray_template())
        window._refresh_page_combo()
    return window


# -- the template --------------------------------------------------------


def test_the_tray_card_is_a_138mm_panel_between_two_spines():
    """Measured off a real case: the outer strips show down the sides of
    the closed case, and the panel between them -- 138mm fold to fold --
    sits behind the disc."""
    template = _tray_template()

    assert (template.width_mm, template.height_mm) == (151.0, 117.5)
    assert template.fold_offsets_mm == [6.5, 144.5]
    first, second = template.fold_offsets_mm
    assert first == 6.5 and template.width_mm - second == 6.5, "the spines"
    assert second - first == 138.0, "the panel behind the disc"
    assert template.medium == MEDIUM_CD
    assert template.verified is False, "nobody has held a ruler to it yet"


def test_the_tray_card_has_three_panels(qt_app):
    scene = DesignScene(_tray_template())

    panels = scene.fold_panel_rects()

    assert len(panels) == 3
    # the middle panel is the wide one, the spines are the strips
    assert panels[1].width() > panels[0].width() * 10


# -- choosing it, or not -------------------------------------------------


def test_a_new_project_has_no_case_back_unless_one_is_chosen(qt_app):
    dialog = NewDesignDialog()
    dialog.medium_combo.setCurrentIndex(dialog.medium_combo.findData(MEDIUM_CD))

    assert dialog.back_combo.currentData() is None, "the default must be no third page"
    dialog._on_accept()
    assert PAGE_BACK not in dialog.selected_templates


def test_choosing_a_case_back_gives_the_project_three_pages(qt_app, monkeypatch):
    def fake_exec(self):
        self.medium_combo.setCurrentIndex(self.medium_combo.findData(MEDIUM_CD))
        self.back_combo.setCurrentIndex(
            next(i for i in range(self.back_combo.count()) if TRAY_CARD in self.back_combo.itemText(i))
        )
        self._on_accept()
        return NewDesignDialog.DialogCode.Accepted

    monkeypatch.setattr(NewDesignDialog, "exec", fake_exec)
    window = MainWindow(show_startup_dialog=False)

    assert window._new_design(prompt=True) is True

    assert window.project.ordered_pages() == [PAGE_DISC, PAGE_COVER, PAGE_BACK]
    assert window.project.pages[PAGE_BACK].template.name == TRAY_CARD


def test_a_case_back_can_be_added_to_an_open_project(qt_app, monkeypatch):
    window = _cd_window(with_back=False)
    answers = iter([("Case Back", True), (TRAY_CARD, True)])
    monkeypatch.setattr(QInputDialog, "getItem", staticmethod(lambda *a, **k: next(answers)))

    window._add_page()

    assert PAGE_BACK in window.project.pages
    assert window.current_page == PAGE_BACK, "the new page is what you want to look at"


def test_the_disc_and_cover_pages_cannot_be_removed(qt_app, monkeypatch):
    window = _cd_window(with_back=True)
    window.current_page = PAGE_COVER
    told = []
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: told.append(a)))
    monkeypatch.setattr(
        QMessageBox, "warning", staticmethod(lambda *a, **k: pytest.fail("must not offer to remove it"))
    )

    window._remove_page()

    assert told
    assert PAGE_COVER in window.project.pages


def test_removing_the_case_back_asks_first_and_then_removes_it(qt_app, monkeypatch):
    window = _cd_window(with_back=True)
    window.current_page = PAGE_BACK
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok))

    window._remove_page()

    assert PAGE_BACK not in window.project.pages
    assert window.current_page == PAGE_DISC


def test_a_case_back_survives_save_and_load(qt_app, tmp_path):
    window = _cd_window(with_back=True)
    path = tmp_path / "with-back.mdproj"

    save_project(window.project, path)

    assert load_project(path).pages[PAGE_BACK].template.name == TRAY_CARD


# -- laying it out -------------------------------------------------------


def test_the_tray_card_gets_spines_and_a_track_list(qt_app):
    scene = DesignScene(_tray_template())

    items = cd_layout.build_case_back(scene, _metadata())

    texts = [item.toPlainText() for item in items if hasattr(item, "toPlainText")]
    assert any("Zombified" in text for text in texts), "the track list is missing"
    # the album name runs down *both* spines: which side of the case is
    # visible depends on how it was shelved
    captions = [text for text in texts if "Popular Monster" in text and "Falling In Reverse" in text]
    assert len(captions) == 2


def test_a_page_that_is_not_a_three_panel_card_is_refused(qt_app):
    flat = DesignScene(CoverTemplate(name="Flat", width_mm=120.0, height_mm=120.0, medium=MEDIUM_CD))

    with pytest.raises(cd_layout.CdLayoutError):
        cd_layout.build_case_back(flat, _metadata())


def test_the_automatic_layout_fills_the_case_back_when_there_is_one(qt_app, monkeypatch):
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    window = _cd_window(with_back=True)
    metadata = _metadata()
    window.project.metadata = metadata

    window._auto_layout_project(metadata)

    assert window.project.pages[PAGE_BACK].print_items()


def test_the_automatic_layout_leaves_the_case_backs_own_template_alone(qt_app, monkeypatch):
    """The other two pages are re-templated by the layout; this one is not.
    The page exists because the user added it and chose its shape."""
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    window = _cd_window(with_back=True)

    window._auto_layout_project(_metadata())

    assert window.project.pages[PAGE_BACK].template.name == TRAY_CARD


def test_a_project_without_a_case_back_lays_out_the_other_two_quietly(qt_app, monkeypatch):
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    window = _cd_window(with_back=False)

    window._auto_layout_project(_metadata())

    assert PAGE_BACK not in window.project.pages
    assert window.project.pages[PAGE_DISC].print_items()


def test_the_auto_layout_warning_names_the_pages_this_project_has(qt_app):
    """It used to say "both pages -- the disc label and the J-card"
    whatever the project was: a MiniDisc part a CD project does not have,
    and the wrong count as soon as a case back existed."""
    window = _cd_window(with_back=False)

    without = window._auto_layout_page_names()
    assert "J-Card" not in without
    assert "Case Insert" in without

    window.project.pages[PAGE_BACK] = DesignScene(_tray_template())
    with_back = window._auto_layout_page_names()

    assert "Case Back" in with_back
    assert with_back.count(",") == 1, "three pages should read as a list, not a pair"


def test_the_track_list_does_not_fill_the_whole_tray_card(qt_app):
    """138mm of tracks across a tray card read as a poster, not a sleeve --
    reported directly. The list is fitted into a share of the panel and
    then centred in all of it, so the slack is shared top and bottom."""
    scene = DesignScene(_tray_template())

    cd_layout.build_case_back(scene, _metadata())

    panel = scene.fold_panel_rects()[1]
    tracks = max(
        (item for item in scene.print_items() if hasattr(item, "toPlainText")),
        key=lambda item: item.boundingRect().height(),
    )
    used = item_height = tracks.mapToScene(tracks.boundingRect()).boundingRect().height()
    assert used < panel.height() * cd_layout.BACK_TRACK_FILL + 1, "it still fills everything"
    assert item_height > 0


def test_the_digital_audio_mark_takes_the_corner_the_footer_does_not(qt_app, tmp_path):
    """The bottom-left of that panel already carries the year and the
    running time."""
    from PIL import Image

    logo = tmp_path / "cdda.png"
    Image.new("RGBA", (120, 40), (0, 0, 0, 255)).save(logo)
    scene = DesignScene(_tray_template())

    items = cd_layout.build_case_back(scene, _metadata(), str(logo))

    # The pixmap items are the marks -- the panel blocks and the accent
    # rule are filled rects, and the spines' own blocks sit further right
    # than the middle panel does.
    from PySide6.QtWidgets import QGraphicsPixmapItem

    panel = scene.fold_panel_rects()[1]
    marks = [item for item in items if isinstance(item, QGraphicsPixmapItem)]
    assert marks, "no mark was placed at all"
    placed = marks[0].mapToScene(marks[0].boundingRect()).boundingRect()

    assert panel.contains(placed), "the mark hangs off the panel"
    assert placed.center().x() > panel.center().x(), "it belongs on the right"
    assert placed.center().y() > panel.center().y(), "...at the foot"
    footer = min(
        (
            item.mapToScene(item.boundingRect()).boundingRect()
            for item in items
            if hasattr(item, "toPlainText") and item.toPlainText().strip()
        ),
        key=lambda r: -r.bottom(),
    )
    assert footer.left() < placed.left(), "the year and running time keep the other corner"
