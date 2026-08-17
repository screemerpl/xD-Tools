"""Help > About MDTools."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout

APP_NAME = "MDTools"
APP_VERSION = "0.1.0"
APP_AUTHOR = 'Artur "Screemer" Jakubowicz'


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("About {name}").format(name=APP_NAME))

        layout = QVBoxLayout(self)

        title = QLabel(f"<h2>{APP_NAME}</h2>")
        layout.addWidget(title)

        version_label = QLabel(self.tr("Version {version}").format(version=APP_VERSION))
        layout.addWidget(version_label)

        description = QLabel(
            self.tr(
                "A desktop workbench for MiniDisc.\n\n"
                "Design disc labels and cover/J-card inserts and export them as cut-ready SVG "
                "and print-ready PNG, for a Cricut cutting machine plus a regular printer.\n\n"
                "With an MDRem infrared adapter it also drives the deck itself: record an album "
                "straight from foobar2000 with a track mark at every song, write the disc and "
                "track titles onto the MiniDisc, and stand in for the remote."
            )
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        author_label = QLabel(self.tr("Author: {author}").format(author=APP_AUTHOR))
        layout.addWidget(author_label)

        icon_credit = QLabel(
            self.tr(
                'Tool icons: <a href="https://github.com/twitter/twemoji">Twemoji</a>, '
                "CC-BY 4.0, Copyright Twitter, Inc and other contributors."
            )
        )
        icon_credit.setOpenExternalLinks(True)
        icon_credit.setWordWrap(True)
        layout.addWidget(icon_credit)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setDefault(True)
        layout.addWidget(buttons, alignment=Qt.AlignmentFlag.AlignRight)
