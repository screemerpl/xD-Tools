"""Typing a whole track list into the metadata dialog's table with no
mouse: pressing Enter while editing a track's Title should move straight
to the next row's Title cell (appending a fresh row past the last one),
ready to keep typing.

Confirmed directly (not from memory) that Qt's own default handling closes
an editor on Enter with the *same* EndEditHint.SubmitModelCache a plain
click on a different cell produces -- see _TitleColumnDelegate's own
docstring in metadata_dialog.py for why this has to be intercepted on the
editor's key event itself, not reacted to afterwards.
"""

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from mdtools.panels.metadata_dialog import ARTIST_COL, TITLE_COL, MetadataDialog
from mdtools.project import ProjectMetadata, Track


def _edit_title(dialog: MetadataDialog, row: int):
    dialog.show()  # a real editor only gets real focus once the view is shown
    dialog.table.setCurrentCell(row, TITLE_COL)
    dialog.table.editItem(dialog.table.item(row, TITLE_COL))
    QApplication.processEvents()
    return QApplication.focusWidget()


def test_enter_on_the_last_row_appends_a_new_row_and_starts_editing_it(qt_app):
    dialog = MetadataDialog(ProjectMetadata(tracks=[Track(title="Track 1")]))
    assert dialog.table.rowCount() == 1

    editor = _edit_title(dialog, 0)
    editor.setText("Track 1")
    QTest.keyClick(editor, Qt.Key.Key_Return)
    QApplication.processEvents()

    assert dialog.table.rowCount() == 2
    assert dialog.table.item(0, TITLE_COL).text() == "Track 1"
    assert dialog.table.currentRow() == 1
    assert dialog.table.currentColumn() == TITLE_COL
    assert isinstance(QApplication.focusWidget(), type(editor)), "the new row's title cell should be editing"


def test_enter_with_a_row_already_below_moves_there_without_adding_one(qt_app):
    dialog = MetadataDialog(
        ProjectMetadata(tracks=[Track(title="Track 1"), Track(title="Track 2")])
    )
    assert dialog.table.rowCount() == 2

    editor = _edit_title(dialog, 0)
    QTest.keyClick(editor, Qt.Key.Key_Return)
    QApplication.processEvents()

    assert dialog.table.rowCount() == 2, "a row already existed below -- nothing should be added"
    assert dialog.table.currentRow() == 1
    assert dialog.table.currentColumn() == TITLE_COL
    # The second track's own title survived -- moving to it must not have
    # clobbered what was already there.
    assert dialog.table.item(1, TITLE_COL).text() == "Track 2"


def test_tab_from_the_title_column_still_moves_to_artist_as_normal(qt_app):
    """The Title column's own delegate must not interfere with anything
    other than Enter/Return."""
    dialog = MetadataDialog(ProjectMetadata(tracks=[Track(title="Track 1")]))

    editor = _edit_title(dialog, 0)
    QTest.keyClick(editor, Qt.Key.Key_Tab)
    QApplication.processEvents()

    assert dialog.table.rowCount() == 1
    assert dialog.table.currentRow() == 0
    assert dialog.table.currentColumn() == ARTIST_COL


def test_escape_from_the_title_column_reverts_without_adding_a_row(qt_app):
    dialog = MetadataDialog(ProjectMetadata(tracks=[Track(title="Track 1")]))

    editor = _edit_title(dialog, 0)
    editor.setText("something typed then abandoned")
    QTest.keyClick(editor, Qt.Key.Key_Escape)
    QApplication.processEvents()

    assert dialog.table.rowCount() == 1
    assert dialog.table.item(0, TITLE_COL).text() == "Track 1"
