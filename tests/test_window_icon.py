from mdtools import gallery
from mdtools.app_window import MainWindow


def test_main_window_has_a_non_null_icon(qt_app):
    win = MainWindow(show_startup_dialog=False)
    assert not win.windowIcon().isNull()


def test_the_logo_file_the_window_icon_is_built_from_exists():
    assert (gallery.gallery_dir() / "mdlogo.png").is_file()
