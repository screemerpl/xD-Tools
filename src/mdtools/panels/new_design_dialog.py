from __future__ import annotations

import copy

from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel

from mdtools.templates import registry


class NewDesignDialog(QDialog):
    """Picks one disc template and one cover template to start a new
    project -- a project always has exactly one of each, switchable via
    the page dropdown in the main window."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("New Project"))
        self.resize(380, 160)
        self.selected_disc_template = None
        self.selected_cover_template = None

        templates = registry.load_templates()

        layout = QFormLayout(self)

        self.disc_combo = QComboBox()
        for t in templates["disc"]:
            label = t.name + ("" if t.verified else self.tr("  (unverified dimensions)"))
            self.disc_combo.addItem(label, t)
        layout.addRow(self.tr("Disc label template"), self.disc_combo)

        self.cover_combo = QComboBox()
        for t in templates["cover"]:
            label = t.name + ("" if t.verified else self.tr("  (unverified dimensions)"))
            self.cover_combo.addItem(label, t)
        layout.addRow(self.tr("Cover / J-card template"), self.cover_combo)

        if not templates["disc"] or not templates["cover"]:
            layout.addRow(
                QLabel(self.tr("Add at least one disc and one cover template first (Templates > Manage Templates)."))
            )

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

        if not templates["disc"] or not templates["cover"]:
            buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)

    def _on_accept(self) -> None:
        self.selected_disc_template = copy.deepcopy(self.disc_combo.currentData())
        self.selected_cover_template = copy.deepcopy(self.cover_combo.currentData())
        self.accept()
