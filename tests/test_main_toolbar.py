"""The ordinary File/Edit strip along the top of the window.

The point of it is that it shows the *same* QAction objects the menus
do, rather than parallel copies -- one action carries one enabled state,
one shortcut and one handler wherever it is shown from, so a toolbar
button cannot drift out of step with its menu entry.
"""

from __future__ import annotations

import pytest

from mdtools.app_window import MainWindow

EXPECTED = ["New...", "Open Project...", "Save", "Print...", None, "&Undo", "&Redo", None,
            "Cut", "Copy", "Paste", "Delete"]


def _window() -> MainWindow:
    return MainWindow(show_startup_dialog=False)


def _layout(window) -> list:
    return [None if a.isSeparator() else a.text() for a in window.main_toolbar.actions()]


def test_it_offers_the_usual_file_and_edit_operations_in_the_usual_order(qt_app):
    assert _layout(_window()) == EXPECTED


def test_every_button_has_an_icon(qt_app):
    """It is an icon-only toolbar -- an action with no icon would be a
    blank gap with only a tooltip to explain it."""
    window = _window()
    for action in window.main_toolbar.actions():
        if not action.isSeparator():
            assert not action.icon().isNull(), f"{action.text()} has no icon"


@pytest.mark.parametrize(
    "attribute, menu",
    [("new_action", "file"), ("open_action", "file"), ("save_action", "file"),
     ("print_action", "file"), ("cut_action", "edit"), ("copy_action", "edit"),
     ("paste_action", "edit"), ("delete_action", "edit")],
)
def test_the_toolbar_shows_the_menu_s_own_action_not_a_copy(qt_app, attribute, menu):
    window = _window()
    action = getattr(window, attribute)

    assert action in window.main_toolbar.actions()
    menus = {m.title(): m for m in window.menuBar().findChildren(type(window.file_menu))}
    owner = window.file_menu if menu == "file" else menus["&Edit"]
    assert action in owner.actions(), "the toolbar and the menu must share one action"


def test_undo_and_redo_follow_the_undo_stack(qt_app):
    """They come from the QUndoGroup itself, so the toolbar gets their
    enabled state for free -- nothing here has to keep them in step."""
    window = _window()
    assert not window.undo_action.isEnabled()
    assert not window.redo_action.isEnabled()

    scene = window._current_scene()
    window._add_text()

    assert window.undo_action.isEnabled()
    window.undo_action.trigger()
    assert window.redo_action.isEnabled()


def test_it_sits_on_its_own_row_above_the_page_toolbar(qt_app):
    """These act on the project; the page toolbar acts on the page being
    edited. Sharing one long row would read as a single set of controls."""
    window = _window()

    assert window.toolBarBreak(window.page_toolbar), "the page toolbar must start a new row"
    areas = (window.toolBarArea(window.main_toolbar), window.toolBarArea(window.page_toolbar))
    assert areas[0] == areas[1], "both belong in the same (top) area"


def test_the_menu_entries_carry_the_icons_too(qt_app):
    """Setting the icon on the shared action puts it in the menu as well,
    which is what a menu looks like on this platform anyway."""
    window = _window()
    assert not window.save_action.icon().isNull()
    assert window.save_action in window.file_menu.actions()
