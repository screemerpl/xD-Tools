"""A project may have any number of pages.

Nothing in the app creates a third page yet -- the planned one is a CD's
jewel case back. These tests build one by hand, which is the only honest
way to check that the two-page assumption is really gone: it was written
into the page dropdown, the template picker, saving and printing, and each
of those had to stop counting.
"""

import pytest
from PySide6.QtWidgets import QInputDialog, QMessageBox

from mdtools.app_window import MainWindow
from mdtools.canvas.scene import DesignScene
from mdtools.io.project_io import load_project, save_project
from mdtools.panels.print_dialog import PrintDialog
from mdtools.project import (
    MEDIUM_CD,
    PAGE_BACK,
    PAGE_COVER,
    PAGE_DISC,
    page_template_kind,
    page_title,
)
from mdtools.templates import registry
from mdtools.templates.models import CoverTemplate


@pytest.fixture(autouse=True)
def _isolated_templates(tmp_path, monkeypatch):
    """Only test_changing_the_third_pages_template_offers_case_back_templates
    actually reads the template registry (via _change_page_template()), but
    every other file that does keeps this isolated -- without it, that one
    test's result depends on whatever templates.json happens to already
    exist on the machine running it, real per-user file included."""
    monkeypatch.setattr(registry, "user_templates_path", lambda: tmp_path / "templates.json")


def _back_page() -> DesignScene:
    """Stands in for the jewel case tray card: 150x118mm with two spine
    folds, which is what that page will be when it is built."""
    return DesignScene(
        CoverTemplate(
            name="Jewel Case Back", width_mm=150.0, height_mm=118.0, fold_offsets_mm=[6.5, 143.5]
        )
    )


def _three_page_window(qt_app) -> MainWindow:
    window = MainWindow(show_startup_dialog=False)
    window.project.pages[PAGE_BACK] = _back_page()
    window._refresh_page_combo()
    return window


# -- the model -----------------------------------------------------------


def test_pages_are_listed_in_a_known_order_and_unknown_ones_still_appear(qt_app):
    window = _three_page_window(qt_app)
    window.project.pages["something-later"] = _back_page()

    order = window.project.ordered_pages()

    assert order[:3] == [PAGE_DISC, PAGE_COVER, PAGE_BACK]
    assert "something-later" in order, "an unrecognised page must not vanish"


def test_a_page_knows_which_template_family_it_takes():
    assert page_template_kind(PAGE_DISC) == "disc"
    assert page_template_kind(PAGE_COVER) == "cover"
    assert page_template_kind(PAGE_BACK) == "case_back"
    # anything unrecognised is treated as a cover rather than crashing
    assert page_template_kind("something-later") == "cover"


def test_a_pages_name_follows_the_medium(qt_app):
    from mdtools.project import MEDIUM_CD, MEDIUM_MD

    assert page_title(PAGE_COVER, MEDIUM_MD) != page_title(PAGE_COVER, MEDIUM_CD)
    assert "J-Card" not in page_title(PAGE_COVER, MEDIUM_CD)


# -- the window ----------------------------------------------------------


def test_the_dropdown_shows_every_page(qt_app):
    window = _three_page_window(qt_app)

    shown = [window.page_combo.itemData(i) for i in range(window.page_combo.count())]

    assert shown == [PAGE_DISC, PAGE_COVER, PAGE_BACK]


def test_switching_to_the_third_page_shows_its_scene(qt_app):
    window = _three_page_window(qt_app)

    window.page_combo.setCurrentIndex(window.page_combo.findData(PAGE_BACK))

    assert window.current_page == PAGE_BACK
    assert window.view.scene() is window.project.pages[PAGE_BACK]


def test_changing_the_third_pages_template_offers_case_back_templates(qt_app, monkeypatch):
    """It takes its own family (page_template_kind(PAGE_BACK) == "case_back"),
    not disc templates and not the front-cover/insert family either -- the
    two used to be conflated under "cover", which is exactly what let a
    slim-case insert be offered (and picked) as a case back."""
    window = _three_page_window(qt_app)
    window.project.medium = MEDIUM_CD  # case_back templates only exist for CD
    window.page_combo.setCurrentIndex(window.page_combo.findData(PAGE_BACK))

    offered: list[list[str]] = []
    monkeypatch.setattr(
        QInputDialog, "getItem", lambda *args: (offered.append(list(args[3])), ("", False))[1]
    )
    window._change_page_template()

    assert offered and all("Disc Label" not in name for name in offered[0])
    # The actual bug this split fixes: a slim-case insert must never be
    # offered as a case back (or vice versa), even though both are plain
    # CoverTemplate rectangles.
    assert all("Slim Case Insert" not in name for name in offered[0])


# -- saving --------------------------------------------------------------


def test_a_third_page_survives_save_and_load(qt_app, tmp_path):
    window = _three_page_window(qt_app)
    path = tmp_path / "three.mdproj"

    save_project(window.project, path)
    loaded = load_project(path)

    assert list(loaded.pages) == [PAGE_DISC, PAGE_COVER, PAGE_BACK]
    assert loaded.pages[PAGE_BACK].template.width_mm == 150.0


def test_a_file_without_a_disc_page_is_still_broken(qt_app, tmp_path):
    """Relaxing "exactly these two pages" must not relax it to nothing."""
    import json

    window = MainWindow(show_startup_dialog=False)
    path = tmp_path / "broken.mdproj"
    save_project(window.project, path)
    data = json.loads(path.read_text(encoding="utf-8"))
    del data["pages"][PAGE_DISC]
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError):
        load_project(path)


# -- printing ------------------------------------------------------------


def test_printing_offers_a_sheet_for_every_page(qt_app, monkeypatch):
    """Two labels can share a sheet if they fit; three have no arrangement
    search behind them, so each gets its own -- and the dialog must reach
    that by itself rather than dropping the third."""
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    window = _three_page_window(qt_app)

    dialog = PrintDialog(window.project)

    assert [label.page for label in dialog._labels] == [PAGE_DISC, PAGE_COVER, PAGE_BACK]
    assert len(dialog.sheets()) == 3
    assert dialog.sheet_combo.count() == 3


def test_each_sheet_of_three_prints_its_own_page(qt_app, monkeypatch):
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    window = _three_page_window(qt_app)
    dialog = PrintDialog(window.project)

    placements = dialog._sheet_placements()

    assert len(placements) == 3
    assert all(len(sheet) == 1 for sheet in placements), "one copy of each page"


def test_the_preview_still_shows_one_sheet_at_a_time_with_three(qt_app, monkeypatch):
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    window = _three_page_window(qt_app)
    dialog = PrintDialog(window.project)

    dialog.sheet_combo.setCurrentIndex(2)

    assert all(item.isVisible() for item in dialog.items_for(PAGE_BACK))
    assert not any(item.isVisible() for item in dialog.items_for(PAGE_DISC))
