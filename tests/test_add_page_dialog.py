"""AddPageDialog: page, template and empty-or-generated in one window.

It replaced two sequential QInputDialogs that asked the first two of those
and never asked the third. Both halves were reported together, so both are
covered here: that the template list follows the page selector, and that
the generate option follows the *template* -- disabled, and never silently
selected, for a template no automatic layout can build.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QDialogButtonBox

from mdtools.panels.add_page_dialog import AddPageDialog
from mdtools.templates.models import CoverTemplate


def _cover(name, **kw) -> CoverTemplate:
    return CoverTemplate(name=name, width_mm=126.0, height_mm=73.0, **kw)


def _tray(name="Tray Card") -> CoverTemplate:
    return CoverTemplate(name=name, width_mm=151.0, height_mm=117.5, fold_offsets_mm=[6.5, 144.5])


PAGES = [("cover", "Case Insert"), ("back", "Case Back")]

TEMPLATES = {
    "cover": [_cover("Insert A"), _cover("Insert B")],
    "back": [_tray()],
}


def _dialog(can_generate=lambda page, template: True, templates=None, pages=None) -> AddPageDialog:
    table = TEMPLATES if templates is None else templates
    return AddPageDialog(
        pages=pages if pages is not None else PAGES,
        templates_for=lambda page: table.get(page, []),
        can_generate=can_generate,
    )


# -- one dialog, all the questions ------------------------------------------


def test_it_offers_every_missing_page(qt_app):
    dialog = _dialog()

    assert [dialog.page_combo.itemText(i) for i in range(dialog.page_combo.count())] == [
        "Case Insert",
        "Case Back",
    ]
    assert dialog.selected_page == "cover"


def test_the_template_list_follows_the_page_selector(qt_app):
    """A page's template family changes with it (project.page_template_kind),
    so the list is rebuilt on every page change rather than gathered once."""
    dialog = _dialog()

    assert [dialog.template_combo.itemText(i) for i in range(dialog.template_combo.count())] == [
        "Insert A",
        "Insert B",
    ]

    dialog.page_combo.setCurrentIndex(dialog.page_combo.findData("back"))

    assert [dialog.template_combo.itemText(i) for i in range(dialog.template_combo.count())] == ["Tray Card"]
    assert dialog.selected_template.name == "Tray Card"


def test_it_reports_the_template_object_not_just_its_name(qt_app):
    """The caller deep-copies it straight into the new page, so it needs the
    template itself rather than a name to look up again."""
    dialog = _dialog()

    assert isinstance(dialog.selected_template, CoverTemplate)
    assert dialog.selected_template.name == "Insert A"


# -- empty or generated ------------------------------------------------------


def test_it_starts_on_empty(qt_app):
    """Adding a page is not a request to have it filled in -- the safe
    answer is the default, matching the Template dropdown's own dialog."""
    dialog = _dialog()

    assert dialog.empty_radio.isChecked()
    assert dialog.generate is False


def test_choosing_generate_is_reported(qt_app):
    dialog = _dialog()
    dialog.generate_radio.setChecked(True)

    assert dialog.generate is True


def test_generate_is_disabled_for_a_template_nothing_can_build(qt_app):
    dialog = _dialog(can_generate=lambda page, template: False)

    assert not dialog.generate_radio.isEnabled()
    assert dialog.generate is False
    assert "not one the automatic layout" in dialog.generate_note.text()


def test_a_disabled_generate_option_can_never_be_reported_as_chosen(qt_app):
    """Belt and braces on the property: a disabled-but-checked radio would
    otherwise promise a layout that then silently did nothing."""
    dialog = _dialog(can_generate=lambda page, template: False)
    dialog.generate_radio.setChecked(True)

    assert dialog.generate is False


def test_the_generate_option_is_re_evaluated_when_the_page_changes(qt_app):
    """It follows the template, and the template follows the page -- so a
    page whose template can be built and one whose cannot must not share an
    answer."""
    dialog = _dialog(can_generate=lambda page, template: page == "back")

    assert not dialog.generate_radio.isEnabled()

    dialog.page_combo.setCurrentIndex(dialog.page_combo.findData("back"))

    assert dialog.generate_radio.isEnabled()


def test_switching_back_to_an_unbuildable_page_clears_the_choice(qt_app):
    dialog = _dialog(can_generate=lambda page, template: page == "back")
    dialog.page_combo.setCurrentIndex(dialog.page_combo.findData("back"))
    dialog.generate_radio.setChecked(True)

    dialog.page_combo.setCurrentIndex(dialog.page_combo.findData("cover"))

    assert dialog.empty_radio.isChecked()
    assert dialog.generate is False


# -- a page with no templates at all ----------------------------------------


def test_ok_is_refused_when_the_page_has_no_templates(qt_app):
    """OK would otherwise create a page with no shape. The old flow showed a
    warning and gave up; this says so in place and keeps the dialog open so
    another page can be picked instead."""
    dialog = _dialog(templates={"cover": [], "back": [_tray()]})

    assert not dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).isEnabled()
    assert "no templates" in dialog.generate_note.text()
    assert dialog.selected_template is None

    dialog.page_combo.setCurrentIndex(dialog.page_combo.findData("back"))

    assert dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).isEnabled()


def test_generate_is_off_when_there_is_no_template_to_build(qt_app):
    dialog = _dialog(templates={"cover": [], "back": []})

    assert dialog.generate is False
    assert not dialog.generate_radio.isEnabled()
