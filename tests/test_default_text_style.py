from PySide6.QtGui import QFont

from mdtools.app_window import MainWindow
from mdtools.project import TextStyle


def _font_spec(family: str, size: float, *, bold: bool = False, italic: bool = False) -> str:
    font = QFont(family)
    font.setPointSizeF(size)
    font.setBold(bold)
    font.setItalic(italic)
    return font.toString()


def test_new_text_item_picks_up_the_projects_default_style(qt_app):
    win = MainWindow(show_startup_dialog=False)
    win.project.default_text_style = TextStyle(
        font_spec=_font_spec("Courier New", 28.0, bold=True, italic=True), color="#ff00ff"
    )

    win._add_text()

    new_item = win._current_scene().print_items()[0]
    assert new_item.font().family() == "Courier New"
    assert new_item.font().pointSizeF() == 28.0
    assert new_item.font().bold()
    assert new_item.font().italic()
    assert new_item.defaultTextColor().name() == "#ff00ff"


def test_new_text_item_uses_normal_defaults_when_no_style_set_yet(qt_app):
    win = MainWindow(show_startup_dialog=False)

    win._add_text()

    new_item = win._current_scene().print_items()[0]
    assert new_item.defaultTextColor().name() == "#000000"


def test_metadata_insert_also_picks_up_the_projects_default_style(qt_app):
    win = MainWindow(show_startup_dialog=False)
    win.project.default_text_style = TextStyle(font_spec=_font_spec("Courier New", 28.0), color="#ff00ff")

    win._insert_metadata_text("Some Album Title")

    new_item = win._current_scene().print_items()[0]
    assert new_item.toPlainText() == "Some Album Title"
    assert new_item.font().family() == "Courier New"


def test_setting_font_on_properties_panel_becomes_the_new_project_default(qt_app):
    win = MainWindow(show_startup_dialog=False)
    win._add_text()
    first_item = win._current_scene().print_items()[0]

    win.properties_panel.set_item(first_item)
    win.properties_panel.font_size_spin.setValue(40)

    default_font = QFont()
    default_font.fromString(win.project.default_text_style.font_spec)
    assert default_font.pointSizeF() == 40

    win._add_text()
    items = win._current_scene().print_items()
    second_item = items[0] if items[0] is not first_item else items[1]
    assert second_item.font().pointSizeF() == 40


def test_new_project_starts_with_a_fresh_unset_default_style(qt_app):
    win = MainWindow(show_startup_dialog=False)
    win.project.default_text_style = TextStyle(font_spec=_font_spec("Courier New", 28.0), color="#ff00ff")

    win._new_design(prompt=False)

    assert not win.project.default_text_style.is_set()
