"""Working out which serial port the MDRem adapter is on, shared by every
UI entry point that needs one (Upload Tracklist, the Remote window).

Kept separate from mdrem.py because it shows dialogs -- mdrem.py stays
importable and testable with no QApplication, matching how grayscale.py /
app_settings.py stay UI-free.
"""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtWidgets import QApplication, QMessageBox, QWidget

from mdtools import app_settings, mdrem


def resolve_port(parent: QWidget | None = None) -> str | None:
    """The port from Settings, or a probe for one, or None after telling
    the user why.

    Probing on a miss rather than refusing outright means a first run does
    not dead-end at "go and configure it first"; a port found this way is
    saved, so the probe happens at most once."""
    port = app_settings.mdrem_port()
    if port:
        return port

    QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
    try:
        port = mdrem.detect_port()
    finally:
        QApplication.restoreOverrideCursor()

    if port is None:
        QMessageBox.warning(
            parent,
            QCoreApplication.translate("MDRem", "MDRem"),
            QCoreApplication.translate(
                "MDRem",
                "No MDRem adapter was found on any serial port. Connect it, or choose its port in "
                "Window > Settings...",
            ),
        )
        return None

    app_settings.set_mdrem_port(port)
    return port
