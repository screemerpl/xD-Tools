from __future__ import annotations

import copy

from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel

from mdtools.project import MEDIUM_CD, MEDIUM_MD
from mdtools.templates import registry


class NewDesignDialog(QDialog):
    """Picks the physical medium plus one disc template and one cover
    template to start a new project -- a project always has exactly one of
    each, switchable via the page dropdown in the main window.

    The medium comes first because it filters the other two: a MiniDisc
    project has no use for a 118mm circle and a CD project has no use for a
    J-card, so offering all of them together would only invite building a
    project whose two pages describe different physical objects.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("New Project"))
        self.resize(420, 190)
        self.selected_disc_template = None
        self.selected_cover_template = None
        # None means the project simply has no such page -- not an error,
        # and the normal case.
        self.selected_back_template = None
        self.selected_medium = MEDIUM_MD

        self._templates = registry.load_templates()

        layout = QFormLayout(self)

        self.medium_combo = QComboBox()
        self.medium_combo.addItem(self.tr("MiniDisc"), MEDIUM_MD)
        self.medium_combo.addItem(self.tr("CD-R"), MEDIUM_CD)
        self.medium_combo.currentIndexChanged.connect(self._on_medium_changed)
        layout.addRow(self.tr("Medium"), self.medium_combo)

        self.disc_combo = QComboBox()
        self.disc_label = QLabel(self.tr("Disc label template"))
        layout.addRow(self.disc_label, self.disc_combo)

        self.cover_combo = QComboBox()
        self.cover_label = QLabel(self.tr("Cover / J-card template"))
        layout.addRow(self.cover_label, self.cover_combo)

        # Optional, and empty by default: most projects are two pages, and
        # a case back nobody asked for is a blank page in the dropdown for
        # ever. "(none)" is the first entry rather than a checkbox beside a
        # combo, so there is one control and one state to read.
        self.back_combo = QComboBox()
        self.back_label = QLabel(self.tr("Case back (optional)"))
        layout.addRow(self.back_label, self.back_combo)

        self.empty_label = QLabel(
            self.tr("Add at least one disc and one cover template first (Templates > Manage Templates).")
        )
        self.empty_label.setWordWrap(True)
        layout.addRow(self.empty_label)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self._on_accept)
        self.buttons.rejected.connect(self.reject)
        layout.addRow(self.buttons)

        self._on_medium_changed()

    # -- medium filtering -------------------------------------------------

    def current_medium(self) -> str:
        return self.medium_combo.currentData()

    def _for_medium(self, kind: str) -> list:
        medium = self.current_medium()
        return [t for t in self._templates[kind] if getattr(t, "medium", MEDIUM_MD) == medium]

    def _on_medium_changed(self, *_args) -> None:
        discs = self._for_medium("disc")
        covers = self._for_medium("cover")

        for combo, templates in ((self.disc_combo, discs), (self.cover_combo, covers)):
            combo.clear()
            for t in templates:
                label = t.name + ("" if t.verified else self.tr("  (unverified dimensions)"))
                combo.addItem(label, t)

        # The back page takes cover-shaped templates like any other -- see
        # project.page_template_kind() -- so it is offered the same list,
        # with "(none)" in front.
        self.back_combo.clear()
        self.back_combo.addItem(self.tr("(none)"), None)
        for t in covers:
            label = t.name + ("" if t.verified else self.tr("  (unverified dimensions)"))
            self.back_combo.addItem(label, t)

        # A CD's second page is a case insert, not a J-card -- calling it one
        # would name a MiniDisc part on a project that has none.
        if self.current_medium() == MEDIUM_CD:
            self.cover_label.setText(self.tr("Case insert template"))
        else:
            self.cover_label.setText(self.tr("Cover / J-card template"))

        usable = bool(discs and covers)
        self.empty_label.setVisible(not usable)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(usable)

    def _on_accept(self) -> None:
        self.selected_medium = self.current_medium()
        self.selected_disc_template = copy.deepcopy(self.disc_combo.currentData())
        self.selected_cover_template = copy.deepcopy(self.cover_combo.currentData())
        self.selected_back_template = copy.deepcopy(self.back_combo.currentData())
        self.accept()
