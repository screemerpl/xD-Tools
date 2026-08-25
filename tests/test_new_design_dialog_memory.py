"""File > New remembers the medium and per-page templates chosen last
time (#20), so creating one project after another doesn't mean re-picking
the same choices from scratch on every single New Project.

app_settings is isolated to a per-test tmp file automatically by
conftest.py's autouse _isolated_app_settings fixture. templates.json is
NOT isolated the same way (registry.py reads the real per-user file, same
as every other test touching NewDesignDialog in this suite) -- so
assertions here match by the underlying template's own `.name`, never by
a combo's display text, which can carry a "(unverified dimensions)" suffix
that depends on whatever is actually on the real disk this happens to run
against.
"""

from __future__ import annotations

from mdtools import app_settings
from mdtools.panels.new_design_dialog import NewDesignDialog
from mdtools.project import MEDIUM_CD, MEDIUM_MD, MEDIUM_TAPE, PAGE_COVER, PAGE_DISC


def _current_name(combo) -> str | None:
    data = combo.currentData()
    return data.name if data is not None else None


def _select_by_name(combo, name: str) -> None:
    for index in range(combo.count()):
        data = combo.itemData(index)
        if data is not None and data.name == name:
            combo.setCurrentIndex(index)
            return
    raise AssertionError(f"no item named {name!r} in this combo")


def test_a_fresh_install_opens_on_minidisc_with_default_templates(qt_app):
    dialog = NewDesignDialog()

    assert dialog.current_medium() == MEDIUM_MD
    assert _current_name(dialog.disc_combo) == "MiniDisc Disc Label"


def test_accepting_remembers_the_chosen_medium_for_next_time(qt_app):
    dialog = NewDesignDialog()
    dialog.medium_combo.setCurrentIndex(dialog.medium_combo.findData(MEDIUM_CD))

    dialog._on_accept()

    assert app_settings.last_new_project_medium() == MEDIUM_CD


def test_the_next_dialog_opens_on_the_remembered_medium(qt_app):
    app_settings.set_last_new_project_medium(MEDIUM_CD)

    dialog = NewDesignDialog()

    assert dialog.current_medium() == MEDIUM_CD


def test_accepting_remembers_the_chosen_template_for_each_page(qt_app):
    dialog = NewDesignDialog()
    _select_by_name(dialog.disc_combo, "MiniDisc Disc Label (with Slider)")

    dialog._on_accept()

    assert app_settings.last_new_project_template(MEDIUM_MD, PAGE_DISC) == "MiniDisc Disc Label (with Slider)"


def test_the_next_dialog_opens_with_the_remembered_template_selected(qt_app):
    app_settings.set_last_new_project_medium(MEDIUM_MD)
    app_settings.set_last_new_project_template(MEDIUM_MD, PAGE_DISC, "MiniDisc Disc Label (with Slider)")

    dialog = NewDesignDialog()

    assert _current_name(dialog.disc_combo) == "MiniDisc Disc Label (with Slider)"


def test_a_remembered_template_that_no_longer_exists_falls_back_to_the_ordinary_default(qt_app):
    """A template can be renamed or deleted since it was last chosen -- the
    row should behave exactly as if nothing had ever been remembered, not
    error out or land on the wrong entry."""
    app_settings.set_last_new_project_medium(MEDIUM_MD)
    app_settings.set_last_new_project_template(MEDIUM_MD, PAGE_DISC, "No Such Template Any More")

    dialog = NewDesignDialog()

    assert _current_name(dialog.disc_combo) == "MiniDisc Disc Label"


def test_an_optional_page_left_on_none_is_remembered_as_none(qt_app):
    dialog = NewDesignDialog()
    dialog.medium_combo.setCurrentIndex(dialog.medium_combo.findData(MEDIUM_CD))
    assert dialog.back_combo.currentData() is None  # "(none)" is the default already

    dialog._on_accept()
    reopened = NewDesignDialog()
    reopened.medium_combo.setCurrentIndex(reopened.medium_combo.findData(MEDIUM_CD))

    assert reopened.back_combo.currentData() is None


def test_an_optional_page_explicitly_chosen_is_remembered_too(qt_app):
    dialog = NewDesignDialog()
    dialog.medium_combo.setCurrentIndex(dialog.medium_combo.findData(MEDIUM_CD))
    _select_by_name(dialog.back_combo, "CD Jewel Case Back (Tray Card)")

    dialog._on_accept()
    reopened = NewDesignDialog()
    reopened.medium_combo.setCurrentIndex(reopened.medium_combo.findData(MEDIUM_CD))

    assert _current_name(reopened.back_combo) == "CD Jewel Case Back (Tray Card)"


def test_remembered_templates_are_kept_separately_per_medium(qt_app):
    """A MiniDisc project and a cassette project don't share a disc/cover
    row at all -- but nothing here should let one medium's remembered
    choice bleed into another's page of the same *kind* (both "cover")."""
    app_settings.set_last_new_project_template(MEDIUM_MD, PAGE_COVER, "MiniDisc Cover (J-Card + Window)")
    app_settings.set_last_new_project_template(MEDIUM_TAPE, PAGE_COVER, "Cassette J-Card")

    md_dialog = NewDesignDialog()
    assert _current_name(md_dialog.cover_combo) == "MiniDisc Cover (J-Card + Window)"

    tape_dialog = NewDesignDialog()
    tape_dialog.medium_combo.setCurrentIndex(tape_dialog.medium_combo.findData(MEDIUM_TAPE))
    assert _current_name(tape_dialog.cover_combo) == "Cassette J-Card"
