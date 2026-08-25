"""A project knows which physical medium it is for, and that choice filters
the templates it can ever be shown.

The point of the filtering tests is not tidiness: a project holds exactly
one disc page and one cover page, so letting a J-card onto a CD project
would produce a project describing two different physical objects with no
way to notice until something got cut.
"""

import pytest

from mdtools.app_window import MainWindow
from mdtools.io.project_io import load_project, project_to_dict, save_project
from mdtools.panels.new_design_dialog import NewDesignDialog
from mdtools.project import MEDIUM_CD, MEDIUM_MD, MEDIUM_PAGES, PAGE_COVER, PAGE_DISC
from mdtools.templates import registry


@pytest.fixture(autouse=True)
def _isolated_templates(tmp_path, monkeypatch):
    """conftest.py isolates settings.ini but not templates.json, so without
    this these tests would read whichever per-user template file the machine
    happens to have -- which, on a machine that has run an older build, is
    one seeded before the CD templates existed (they only reach it via
    registry.sync_builtin_templates() at app start)."""
    monkeypatch.setattr(registry, "user_templates_path", lambda: tmp_path / "templates.json")


def _cd_templates():
    templates = registry.load_templates()
    disc = next(t for t in templates["disc"] if t.medium == MEDIUM_CD)
    cover = next(t for t in templates["cover"] if t.medium == MEDIUM_CD)
    return disc, cover


# -- the built-in CD templates ------------------------------------------


def test_builtin_defaults_include_a_cd_disc_label():
    label = next(t for t in registry.load_templates()["disc"] if t.shape == "cd_label")
    assert label.outer_diameter_mm == 117.0
    assert label.hole_diameter_mm == 35.0
    # width/height stay equal to the outer diameter so everything that
    # reasons about a template's physical footprint keeps working.
    assert (label.width_mm, label.height_mm) == (117.0, 117.0)
    assert label.medium == MEDIUM_CD
    assert label.builtin is True


def test_builtin_defaults_include_both_slim_case_inserts():
    covers = [t for t in registry.load_templates()["cover"] if t.medium == MEDIUM_CD]

    flat = next(t for t in covers if not t.fold_offsets_mm)
    assert (flat.width_mm, flat.height_mm) == (120.0, 120.0)

    # A slim case has no tray card -- the folded insert is what gives the
    # track list somewhere to live, read through the clear back of the case.
    folded = next(t for t in covers if t.fold_offsets_mm)
    assert (folded.width_mm, folded.height_mm) == (240.0, 120.0)
    assert folded.fold_offsets_mm == [120.0]


def test_every_builtin_template_declares_a_medium():
    templates = registry.load_templates()
    for template in templates["disc"] + templates["cover"]:
        assert template.medium in MEDIUM_PAGES, template.name


# -- the medium on the project itself -----------------------------------


def test_a_projects_medium_survives_save_and_load(qt_app, tmp_path):
    win = MainWindow(show_startup_dialog=False)
    win.project.medium = MEDIUM_CD
    path = tmp_path / "cd.mdproj"
    save_project(win.project, path)

    assert load_project(path).medium == MEDIUM_CD


def test_a_project_saved_before_cd_support_loads_as_a_minidisc_project(qt_app, tmp_path):
    """Those projects were MiniDisc projects -- reading them as such is the
    truth about them, not a fallback."""
    win = MainWindow(show_startup_dialog=False)
    data = project_to_dict(win.project)
    del data["medium"]

    import json

    path = tmp_path / "old.mdproj"
    path.write_text(json.dumps(data), encoding="utf-8")

    assert load_project(path).medium == MEDIUM_MD


# -- File > New ----------------------------------------------------------


def test_the_new_project_dialog_offers_only_the_chosen_mediums_templates(qt_app):
    dialog = NewDesignDialog()

    dialog.medium_combo.setCurrentIndex(dialog.medium_combo.findData(MEDIUM_CD))
    names = [dialog.disc_combo.itemData(i).name for i in range(dialog.disc_combo.count())]
    assert names and all(dialog.disc_combo.itemData(i).medium == MEDIUM_CD for i in range(dialog.disc_combo.count()))
    assert not any("MiniDisc" in name for name in names)

    dialog.medium_combo.setCurrentIndex(dialog.medium_combo.findData(MEDIUM_MD))
    assert all(dialog.cover_combo.itemData(i).medium == MEDIUM_MD for i in range(dialog.cover_combo.count()))


def test_the_cover_row_is_not_called_a_j_card_for_a_cd(qt_app):
    dialog = NewDesignDialog()
    dialog.medium_combo.setCurrentIndex(dialog.medium_combo.findData(MEDIUM_CD))
    assert "J-card" not in dialog.cover_label.text()


def test_accepting_reports_the_chosen_medium(qt_app):
    dialog = NewDesignDialog()
    dialog.medium_combo.setCurrentIndex(dialog.medium_combo.findData(MEDIUM_CD))
    dialog._on_accept()

    assert dialog.selected_medium == MEDIUM_CD
    assert dialog.selected_templates[PAGE_DISC].shape == "cd_label"


def test_creating_a_cd_project_records_its_medium_and_pages(qt_app, monkeypatch):
    disc, cover = _cd_templates()

    def fake_exec(self):
        self.selected_templates = {PAGE_DISC: disc, PAGE_COVER: cover}
        self.selected_medium = MEDIUM_CD
        return NewDesignDialog.DialogCode.Accepted

    monkeypatch.setattr(NewDesignDialog, "exec", fake_exec)

    win = MainWindow(show_startup_dialog=False)
    assert win._new_design(prompt=True) is True

    assert win.project.medium == MEDIUM_CD
    assert win.project.pages[PAGE_DISC].template.shape == "cd_label"
    assert win.project.pages[PAGE_COVER].template.name == cover.name
    # no MiniDisc insertion mark on a CD label
    assert win.project.pages[PAGE_DISC].print_items() == []


def test_the_unprompted_fallback_project_is_still_a_minidisc_one(qt_app):
    """A cancelled startup screen falls back to default templates -- picking
    a medium out of template file order would be arbitrary."""
    win = MainWindow(show_startup_dialog=False)
    assert win.project.medium == MEDIUM_MD
    assert win.project.pages[PAGE_DISC].template.medium == MEDIUM_MD


# -- the toolbar's Template dropdown --------------------------------------


def test_changing_a_pages_template_offers_only_this_projects_medium(qt_app):
    """Exercised through the toolbar's Template dropdown rather than the
    retired Templates > "Change Template for This Page..." menu action --
    same underlying filtering (_template_choices_for_current_page()),
    reached a different way now.

    A real CD disc template is applied first (matching how NewDesignDialog
    actually builds a CD project) so the page's own current template is
    itself one of the offered choices -- just poking `.medium` alone would
    leave the disc page on its original MiniDisc template, which
    _refresh_template_combo() then has to show as an *extra* entry beyond
    the medium-filtered list (see the "still shows as the current choice"
    test in test_page_template_dropdown.py) rather than the single-CD-
    template list this test is actually about."""
    win = MainWindow(show_startup_dialog=False)
    win.project.medium = MEDIUM_CD
    cd_disc_template = next(t for t in registry.load_templates()["disc"] if t.medium == MEDIUM_CD)
    win.apply_template(PAGE_DISC, cd_disc_template)

    offered = [win.template_combo.itemData(i) for i in range(win.template_combo.count())]

    assert offered == ["CD Disc Label (Standard Hub)"]


def test_automatic_layout_refuses_a_cd_project_instead_of_rebuilding_it_as_a_minidisc(qt_app, monkeypatch):
    """The layout targets templates named for MiniDisc parts, so on a CD
    project it would silently replace both pages with the wrong medium's
    shapes."""
    from PySide6.QtWidgets import QMessageBox

    win = MainWindow(show_startup_dialog=False)
    win.project.medium = MEDIUM_CD
    disc_template = win.project.pages[PAGE_DISC].template.name

    shown: list[str] = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: shown.append(a[2] if len(a) > 2 else ""))
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not reach the destructive confirmation")),
    )

    win._auto_layout_from_metadata()

    assert shown, "the user was told nothing"
    assert win.project.pages[PAGE_DISC].template.name == disc_template


# -- Template Manager ----------------------------------------------------


def test_the_template_manager_shows_a_cd_label_as_itself_and_lets_it_be_measured(qt_app):
    """Before the cd_label shape existed here, the shape combo only knew two
    entries and picked "whatever isn't sticker" by index, so a CD label was
    displayed as a full MiniDisc label -- with the slider notch fields on
    show and no way at all to correct the two dimensions that actually
    define it. (It did not rewrite the shape: the combo's signal is only
    connected further down. Displaying it wrongly was the whole bug.)
    """
    from PySide6.QtWidgets import QComboBox, QDoubleSpinBox

    from mdtools.templates.template_dialog import TemplateManagerDialog

    dialog = TemplateManagerDialog()
    row = next(
        i
        for i in range(dialog.list_widget.count())
        if dialog.list_widget.item(i).data(1)[1].name == "CD Disc Label (Standard Hub)"
    )
    dialog.list_widget.setCurrentRow(row)

    template = dialog.list_widget.item(row).data(1)[1]
    assert template.shape == "cd_label"
    assert template.medium == MEDIUM_CD

    combo_values = [c.currentData() for c in dialog.findChildren(QComboBox)]
    assert "cd_label" in combo_values, "the shape combo does not show this template's own shape"
    assert MEDIUM_CD in combo_values, "the medium is not shown at all"

    spin_values = {round(s.value(), 2) for s in dialog.findChildren(QDoubleSpinBox)}
    assert 117.0 in spin_values and 35.0 in spin_values, "the label's defining dimensions are not editable"
