"""Help > About xD-Tools."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout

APP_NAME = "xD-Tools"
APP_VERSION = "0.2.0"
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
                "A desktop workbench for MiniDisc and CD-R.\n\n"
                "Design the labels for either: a MiniDisc's sticker and J-card, or a CD's ring "
                "label and slim-case insert -- and export them as cut-ready SVG and print-ready "
                "PNG, for a Cricut cutting machine plus a regular printer.\n\n"
                "Burn an audio CD-R from a folder or from foobar2000's playlist, with CD-Text "
                "titles, resampling anything that is not already 44.1 kHz / 16-bit on the way.\n\n"
                "With an MDRem infrared adapter it also drives a MiniDisc deck: record an album "
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
