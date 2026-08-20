"""Toolbar > "Regenerate with Font...": pick a font family, then preview it
against the current page before committing to anything.

The face is picked through Qt's own font dialog (`QFontDialog.getFont()`)
rather than a combo box typed into -- only the *family* it returns is ever
read (`.family()`); size and style are discarded. That is deliberately the
only thing that matters here: auto-generated text already carries its own
size (fitted to its panel) and weight (bold where the layout wants bold),
and this feature substitutes the *face* those choices are made in, not any
one of them individually.

This dialog does no layout work itself -- Preview and the final regenerate
both run through MainWindow, over the exact same auto-layout code every
other design on a page already goes through (see canvas.scene.
font_family_override), so there is no separate "fake" preview renderer
that could show one thing and build another.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFontDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from mdtools import app_settings


class RegenerateFontDialog(QDialog):
    # Emitted with the currently chosen font family whenever "Preview" is
    # clicked -- MainWindow is the one that actually knows how to rebuild a
    # page, so it owns the slot connected to this.
    preview_requested = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Regenerate with Font"))
        # Opens on whatever was picked last time, not the application's own
        # default font -- settling on a face and then having to re-pick it
        # on every use would defeat the point of remembering it at all.
        self._family = app_settings.last_regenerate_font_family() or self.font().family()

        layout = QVBoxLayout(self)

        heading = QLabel(
            self.tr("Choose a font, then Preview it on the current page before applying it.")
        )
        heading.setWordWrap(True)
        layout.addWidget(heading)

        font_row = QHBoxLayout()
        self.font_label = QLabel(self._family)
        font_row.addWidget(self.font_label, 1)
        self.choose_btn = QPushButton(self.tr("Choose Font..."))
        self.choose_btn.clicked.connect(self._pick_font)
        font_row.addWidget(self.choose_btn)
        layout.addLayout(font_row)

        self.preview_btn = QPushButton(self.tr("Preview"))
        self.preview_btn.clicked.connect(self._on_preview_clicked)
        layout.addWidget(self.preview_btn)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def selected_family(self) -> str:
        return self._family

    def _pick_font(self) -> None:
        # PySide6's QFontDialog.getFont returns (ok, font) here, not
        # (font, ok) as older-Qt docs/intuition suggest -- see the
        # properties_panel.py Font... button, which hit this the hard way.
        ok, font = QFontDialog.getFont(QFont(self._family), self)
        if not ok:
            return
        self._family = font.family()
        self.font_label.setText(self._family)
        # Remembered as soon as it's picked, not only once the whole
        # regenerate is accepted -- "last selected" is what was asked for,
        # and a cancelled regenerate shouldn't lose the choice either.
        app_settings.set_last_regenerate_font_family(self._family)

    def _on_preview_clicked(self) -> None:
        self.preview_requested.emit(self._family)
