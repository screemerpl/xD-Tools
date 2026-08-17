from PySide6.QtWidgets import QLabel

from mdtools.app_window import MainWindow
from mdtools.panels.about_dialog import APP_AUTHOR, APP_NAME, APP_VERSION, AboutDialog


def test_about_dialog_shows_name_version_and_author(qt_app):
    dialog = AboutDialog()

    all_text = " ".join(label.text() for label in dialog.findChildren(QLabel))
    assert APP_NAME in all_text
    assert APP_VERSION in all_text
    assert APP_AUTHOR in all_text


def test_show_about_opens_the_about_dialog(qt_app, monkeypatch):
    # Deliberately not re-querying the Help menu's QMenu/QAction after
    # construction to find "About MDTools..." -- see the documented
    # "re-fetching a QMenu can raise 'already deleted'" gotcha. Testing
    # MainWindow._show_about directly instead is the thing that actually
    # matters (that it shows an AboutDialog), and is what the menu action
    # is wired to (a one-line addAction() call, not worth re-deriving here).
    from mdtools import app_window as app_window_module

    win = MainWindow(show_startup_dialog=False)

    opened = []

    class _StubDialog:
        def __init__(self, parent=None):
            opened.append(parent)

        def exec(self):
            opened.append("exec")

    monkeypatch.setattr(app_window_module, "AboutDialog", _StubDialog)
    win._show_about()

    assert opened == [win, "exec"]
