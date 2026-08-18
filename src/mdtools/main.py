from __future__ import annotations

import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from mdtools import gallery, i18n, theme
from mdtools.app_window import MainWindow
from mdtools.templates import registry


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("MDTools")
    theme.apply_theme(app)
    # Sets the icon for every window in the app (title bar, taskbar,
    # alt-tab) unless a window overrides it -- the .exe's own icon (shown
    # in File Explorer/taskbar for the executable itself) is set
    # separately, via PyInstaller's --icon flag (see
    # scripts/build_windows.ps1), since that has to be baked into the .exe
    # at build time, not set at runtime.
    app.setWindowIcon(QIcon(str(gallery.gallery_dir() / "mdlogo.png")))
    i18n.install_translator(app, i18n.current_language())
    registry.sync_builtin_templates()
    window = MainWindow()
    if window.startup_cancelled:
        # Cancel/close on the very first StartupDialog -- leave the same
        # way File > Exit does, without ever painting a window at all.
        return 0
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
