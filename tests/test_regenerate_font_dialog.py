"""RegenerateFontDialog: Qt's own font dialog picks the face, live, as the
user browses it -- MainWindow does the actual regeneration (see
test_regenerate_with_font.py), this only has to ask the question and report
what was picked (and preview it along the way).

QFontDialog itself is faked as a small QDialog subclass rather than only
stubbing a static method: the dialog under test now constructs a real
*instance* and listens to its currentFontChanged signal to get a live
preview while the picker is still open, so the fake has to be able to fire
that signal from inside a fake exec() the same way a real font dialog would
while the user browses its list -- a plain monkeypatched staticmethod
returning a single (ok, font) tuple can no longer stand in for that.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QDialog

from mdtools import app_settings
from mdtools.panels.regenerate_font_dialog import RegenerateFontDialog

# app_settings is isolated to a per-test tmp file automatically by
# conftest.py's autouse _isolated_app_settings fixture.


def _install_fake_font_dialog(monkeypatch, *, accepted: bool, emit=()):
    """Replaces QFontDialog, as regenerate_font_dialog.py imports it, with a
    fake that fires `emit` (an iterable of QFont) through
    currentFontChanged from inside exec(), then returns Accepted/Rejected --
    simulating a user browsing the family list before closing the picker."""

    class _FakeFontDialog(QDialog):
        currentFontChanged = Signal(QFont)

        def __init__(self, initial=None, parent=None):
            super().__init__(parent)
            self._initial = initial

        def exec(self):
            for font in emit:
                self.currentFontChanged.emit(font)
            return QDialog.DialogCode.Accepted if accepted else QDialog.DialogCode.Rejected

    monkeypatch.setattr("mdtools.panels.regenerate_font_dialog.QFontDialog", _FakeFontDialog)
    return _FakeFontDialog


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
    _install_fake_font_dialog(monkeypatch, accepted=True, emit=[QFont("Wingdings")])

    dialog.choose_btn.click()

    assert app_settings.last_regenerate_font_family() == "Wingdings"


def test_a_cancelled_regenerate_still_keeps_the_remembered_choice(qt_app, monkeypatch):
    """"remember the last *selected* font" -- not "last applied". Picking
    one (accepting the font picker) and then closing the whole regenerate
    dialog without pressing OK must not lose it."""
    dialog = RegenerateFontDialog()
    _install_fake_font_dialog(monkeypatch, accepted=True, emit=[QFont("Wingdings")])
    dialog.choose_btn.click()

    dialog.reject()

    assert app_settings.last_regenerate_font_family() == "Wingdings"


def test_choosing_a_font_updates_the_selected_family_and_label(qt_app, monkeypatch):
    dialog = RegenerateFontDialog()
    _install_fake_font_dialog(monkeypatch, accepted=True, emit=[QFont("Courier New")])

    dialog.choose_btn.click()

    assert dialog.selected_family == "Courier New"
    assert dialog.font_label.text() == "Courier New"


def test_cancelling_the_font_dialog_leaves_the_family_unchanged(qt_app, monkeypatch):
    """Even after browsing (and so live-previewing) another face, cancelling
    the picker itself must land back on whatever was selected before it was
    opened -- not on whatever was merely glanced at along the way."""
    dialog = RegenerateFontDialog()
    before = dialog.selected_family
    _install_fake_font_dialog(monkeypatch, accepted=False, emit=[QFont("Courier New")])

    dialog.choose_btn.click()

    assert dialog.selected_family == before


def test_only_the_family_is_kept_size_and_style_are_discarded(qt_app, monkeypatch):
    """"only font face is relevant" -- QFontDialog also reports a size and
    weight, and none of that should leak into what this dialog reports."""
    dialog = RegenerateFontDialog()
    fancy = QFont("Courier New", 40)
    fancy.setBold(True)
    fancy.setItalic(True)
    _install_fake_font_dialog(monkeypatch, accepted=True, emit=[fancy])

    dialog.choose_btn.click()

    assert dialog.selected_family == "Courier New"
    assert isinstance(dialog.selected_family, str)


def test_clicking_preview_emits_the_currently_selected_family(qt_app, monkeypatch):
    dialog = RegenerateFontDialog()
    _install_fake_font_dialog(monkeypatch, accepted=True, emit=[QFont("Courier New")])
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


def test_picking_a_font_previews_it_straight_away(qt_app, monkeypatch):
    """Asked for directly. Picking a face *is* the decision this dialog
    exists for, so the page should show what it does without needing a
    second click on Preview."""
    dialog = RegenerateFontDialog()
    seen: list[str] = []
    dialog.preview_requested.connect(seen.append)
    _install_fake_font_dialog(monkeypatch, accepted=True, emit=[QFont("Courier New")])

    dialog._pick_font()

    assert seen == ["Courier New"]
    assert dialog.selected_family == "Courier New"


def test_browsing_the_font_list_previews_every_face_live_not_just_the_final_one(qt_app, monkeypatch):
    """The whole point of #12: a live preview as the family list is
    browsed, not only once the picker is closed. currentFontChanged fires
    once per face glanced at; each one should reach preview_requested in
    order, live."""
    dialog = RegenerateFontDialog()
    seen: list[str] = []
    dialog.preview_requested.connect(seen.append)
    _install_fake_font_dialog(
        monkeypatch, accepted=True, emit=[QFont("Arial"), QFont("Wingdings"), QFont("Courier New")]
    )

    dialog._pick_font()

    assert seen == ["Arial", "Wingdings", "Courier New"]
    assert dialog.selected_family == "Courier New"


def test_cancelling_the_font_dialog_with_no_browsing_previews_nothing(qt_app, monkeypatch):
    dialog = RegenerateFontDialog()
    seen: list[str] = []
    dialog.preview_requested.connect(seen.append)
    _install_fake_font_dialog(monkeypatch, accepted=False, emit=[])

    dialog._pick_font()

    assert seen == []


def test_cancelling_after_browsing_reverts_the_preview_to_the_original_family(qt_app, monkeypatch):
    """Browsing several faces live and then cancelling must not leave the
    real page showing whatever was merely glanced at last -- it has to be
    put back to what was selected before the picker opened."""
    dialog = RegenerateFontDialog()
    original = dialog.selected_family
    seen: list[str] = []
    dialog.preview_requested.connect(seen.append)
    _install_fake_font_dialog(monkeypatch, accepted=False, emit=[QFont("Arial"), QFont("Wingdings")])

    dialog._pick_font()

    assert seen == ["Arial", "Wingdings", original]
    assert dialog.selected_family == original


def test_the_preview_button_still_works_on_its_own(qt_app):
    """It stays for re-running a preview after an undo or after the font
    picker itself has already closed."""
    dialog = RegenerateFontDialog()
    seen: list[str] = []
    dialog.preview_requested.connect(seen.append)

    dialog._on_preview_clicked()

    assert seen == [dialog.selected_family]
