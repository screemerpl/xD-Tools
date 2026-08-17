from PySide6.QtWidgets import QPushButton, QToolButton

from mdtools.panels.tool_panel import ToolPanel


def test_all_buttons_are_icon_only_with_a_tooltip(qt_app):
    panel = ToolPanel()
    for btn in panel.findChildren(QPushButton) + panel.findChildren(QToolButton):
        assert btn.text() == "", f"{btn.toolTip()!r} button should be icon-only, not show text"
        assert not btn.icon().isNull(), f"{btn.toolTip()!r} button has no icon"
        assert btn.toolTip(), "icon-only button must have a tooltip so it's still discoverable"


def test_all_toolbar_buttons_are_the_same_size_as_the_metadata_button(qt_app):
    """Regression test: a plain QPushButton (used previously for every
    button except Insert from Metadata, which was already a QToolButton)
    reserves extra horizontal padding for its "3D" look even with no
    visible text, making those buttons noticeably wider than the
    metadata button -- reported as "other buttons are wider and it looks
    wrong"."""
    panel = ToolPanel()
    expected = panel.metadata_button.size()
    for btn in panel.findChildren(QToolButton):
        assert btn.size() == expected, f'"{btn.toolTip()}" button size {btn.size()} != {expected}'


def test_no_metadata_shows_the_fill_in_hint(qt_app):
    panel = ToolPanel()
    panel.set_metadata_entries([], [])
    actions = panel.metadata_menu.actions()
    assert len(actions) == 1
    assert not actions[0].isEnabled()


def test_single_text_entries_emit_metadata_text_requested(qt_app):
    panel = ToolPanel()
    panel.set_metadata_entries([("Album Title", "Mix Tape")], [])

    received = []
    panel.metadata_text_requested.connect(received.append)
    panel.metadata_menu.actions()[0].trigger()

    assert received == ["Mix Tape"]


def test_column_entries_emit_metadata_columns_requested(qt_app):
    panel = ToolPanel()
    panel.set_metadata_entries([], [("Full Track List (2 Columns)", ["col1", "col2"])])

    received = []
    panel.metadata_columns_requested.connect(received.append)
    panel.metadata_menu.actions()[0].trigger()

    assert received == [["col1", "col2"]]


def test_both_kinds_of_entries_appear_together_with_a_separator(qt_app):
    panel = ToolPanel()
    panel.set_metadata_entries([("Album Title", "Mix Tape")], [("Full Track List (2 Columns)", ["a", "b"])])

    actions = panel.metadata_menu.actions()
    labels = [a.text() for a in actions if not a.isSeparator()]
    assert labels == ["Album Title", "Full Track List (2 Columns)"]
    assert any(a.isSeparator() for a in actions)
