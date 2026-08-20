"""RegenerateFontDialog: Qt's own font dialog picks the face, a Preview
button reports it -- MainWindow does the actual regeneration (see
test_regenerate_with_font.py), this only has to ask the question and
report what was picked."""

from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QDialog

from mdtools import app_settings
from mdtools.panels.regenerate_font_dialog import RegenerateFontDialog

# app_settings is isolated to a per-test tmp file automatically by
# conftest.py's autouse _isolated_app_settings fixture.


def test_starts_on_the_dialogs_own_default_font_when_nothing_was_ever_chosen(qt_app):
    dialog = RegenerateFontDialog()

    assert dialog.selected_family == dialog.font().family()
    assert dialog.font_label.text() == dialog.selected_family


def test_starts_on_the_last_family_chosen_in_a_previous_dialog(qt_app):
    app_settings.set_last_regenerate_font_family("Courier New")

    dialog = RegenerateFontDialog()

    assert dialog.selected_family == "Courier New"
    assert dialog.font_label.text() == "Courier New"


def test_choosing_a_font_remembers_it_for_next_time(qt_app, monkeypatch):
    dialog = RegenerateFontDialog()
    monkeypatch.setattr(
        "mdtools.panels.regenerate_font_dialog.QFontDialog.getFont",
        staticmethod(lambda *a, **k: (True, QFont("Wingdings"))),
    )

    dialog.choose_btn.click()

    assert app_settings.last_regenerate_font_family() == "Wingdings"


def test_a_cancelled_regenerate_still_keeps_the_remembered_choice(qt_app, monkeypatch):
    """"remember the last *selected* font" -- not "last applied". Picking
    one and then closing the dialog without pressing OK must not lose it."""
    dialog = RegenerateFontDialog()
    monkeypatch.setattr(
        "mdtools.panels.regenerate_font_dialog.QFontDialog.getFont",
        staticmethod(lambda *a, **k: (True, QFont("Wingdings"))),
    )
    dialog.choose_btn.click()

    dialog.reject()

    assert app_settings.last_regenerate_font_family() == "Wingdings"


def test_choosing_a_font_updates_the_selected_family_and_label(qt_app, monkeypatch):
    dialog = RegenerateFontDialog()
    monkeypatch.setattr(
        "mdtools.panels.regenerate_font_dialog.QFontDialog.getFont",
        staticmethod(lambda *a, **k: (True, QFont("Courier New"))),
    )

    dialog.choose_btn.click()

    assert dialog.selected_family == "Courier New"
    assert dialog.font_label.text() == "Courier New"


def test_cancelling_the_font_dialog_leaves_the_family_unchanged(qt_app, monkeypatch):
    dialog = RegenerateFontDialog()
    before = dialog.selected_family
    monkeypatch.setattr(
        "mdtools.panels.regenerate_font_dialog.QFontDialog.getFont",
        staticmethod(lambda *a, **k: (False, QFont("Courier New"))),
    )

    dialog.choose_btn.click()

    assert dialog.selected_family == before


def test_only_the_family_is_kept_size_and_style_are_discarded(qt_app, monkeypatch):
    """"only font face is relevant" -- QFontDialog also returns a size and
    weight, and none of that should leak into what this dialog reports."""
    dialog = RegenerateFontDialog()
    fancy = QFont("Courier New", 40)
    fancy.setBold(True)
    fancy.setItalic(True)
    monkeypatch.setattr(
        "mdtools.panels.regenerate_font_dialog.QFontDialog.getFont",
        staticmethod(lambda *a, **k: (True, fancy)),
    )

    dialog.choose_btn.click()

    assert dialog.selected_family == "Courier New"
    assert isinstance(dialog.selected_family, str)


def test_clicking_preview_emits_the_currently_selected_family(qt_app, monkeypatch):
    dialog = RegenerateFontDialog()
    monkeypatch.setattr(
        "mdtools.panels.regenerate_font_dialog.QFontDialog.getFont",
        staticmethod(lambda *a, **k: (True, QFont("Courier New"))),
    )
    dialog.choose_btn.click()
    seen = []
    dialog.preview_requested.connect(seen.append)

    dialog.preview_btn.click()

    assert seen == ["Courier New"]


def test_ok_accepts_the_dialog(qt_app):
    dialog = RegenerateFontDialog()

    dialog.accept()

    assert dialog.result() == QDialog.DialogCode.Accepted


def test_cancel_rejects_the_dialog(qt_app):
    dialog = RegenerateFontDialog()

    dialog.reject()

    assert dialog.result() == QDialog.DialogCode.Rejected
