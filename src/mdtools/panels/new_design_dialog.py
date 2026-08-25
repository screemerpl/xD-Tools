from __future__ import annotations

import copy

from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel

from mdtools import app_settings
from mdtools.project import (
    MEDIUM_CD,
    MEDIUM_MD,
    MEDIUM_TAPE,
    PAGE_BACK,
    PAGE_COVER,
    PAGE_DISC,
    medium_pages,
    page_template_kind,
    page_title,
)
from mdtools.templates import registry


class NewDesignDialog(QDialog):
    """Picks the physical medium and a template for each page it has.

    The medium comes first because it decides everything else: which pages
    a project of that kind has at all (project.MEDIUM_PAGES), and which
    templates fit them. A MiniDisc project has no use for a 118mm circle, a
    CD project none for a J-card, and a cassette has no disc page at all --
    offering everything together would only invite building a project whose
    pages describe different physical objects.

    The rows are built from that declaration rather than written out here,
    which is what let compact cassette arrive as data: a medium, three
    pages, two templates.

    Opens on whatever medium and templates were chosen last time
    (app_settings.last_new_project_medium()/last_new_project_template()) --
    creating one project after another is normally the same medium and the
    same house style each time, so re-picking all of it on every single New
    Project would be pure repetition. Matched by template *name*, not
    identity or index: the registry is reloaded fresh on every open, so a
    remembered name has to be looked up among whatever's on offer for the
    now-current medium/page rather than trusted as still being at the same
    position -- and a name that no longer exists (template deleted/renamed
    since) simply falls back to this row's own ordinary default, same as
    if nothing had ever been remembered.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("New Project"))
        self.resize(460, 240)
        self.selected_medium = MEDIUM_MD
        # page -> template, for whatever pages the chosen medium has. An
        # optional page left at "(none)" is simply absent from this.
        self.selected_templates: dict[str, object] = {}

        self._templates = registry.load_templates()
        self._rows: dict[str, tuple[QLabel, QComboBox]] = {}

        self._layout = QFormLayout(self)

        self.medium_combo = QComboBox()
        self.medium_combo.addItem(self.tr("MiniDisc"), MEDIUM_MD)
        self.medium_combo.addItem(self.tr("CD-R"), MEDIUM_CD)
        self.medium_combo.addItem(self.tr("Compact Cassette"), MEDIUM_TAPE)
        self.medium_combo.currentIndexChanged.connect(self._on_medium_changed)
        self._layout.addRow(self.tr("Medium"), self.medium_combo)

        # One row per page, built once for every page any medium can have
        # and shown only for the pages the chosen medium actually uses --
        # QFormLayout has no way to reorder rows, so they are created in
        # PAGE_ORDER and hidden rather than rebuilt.
        for page in self._every_page():
            label = QLabel()
            combo = QComboBox()
            self._layout.addRow(label, combo)
            self._rows[page] = (label, combo)

        self.empty_label = QLabel(
            self.tr("Add a template for every page of this medium first (Templates > Manage Templates).")
        )
        self.empty_label.setWordWrap(True)
        self._layout.addRow(self.empty_label)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self._on_accept)
        self.buttons.rejected.connect(self.reject)
        self._layout.addRow(self.buttons)

        # Opens on the medium remembered from the last New Project, if it
        # still exists as a choice -- setCurrentIndex() only actually fires
        # _on_medium_changed (via the signal connected above) when this
        # differs from the combo's own default, so the explicit call below
        # covers every other case (including this one, harmlessly a second
        # time when it did fire).
        last_medium = app_settings.last_new_project_medium()
        if last_medium:
            index = self.medium_combo.findData(last_medium)
            if index >= 0:
                self.medium_combo.setCurrentIndex(index)
        self._on_medium_changed()

    # -- what this medium has ---------------------------------------------

    @staticmethod
    def _every_page() -> list[str]:
        seen: list[str] = []
        for medium in (MEDIUM_MD, MEDIUM_CD, MEDIUM_TAPE):
            for entry in medium_pages(medium):
                if entry.page not in seen:
                    seen.append(entry.page)
        return seen

    def current_medium(self) -> str:
        return self.medium_combo.currentData()

    def _for_medium(self, kind: str) -> list:
        medium = self.current_medium()
        return [t for t in self._templates[kind] if getattr(t, "medium", MEDIUM_MD) == medium]

    def _on_medium_changed(self, *_args) -> None:
        medium = self.current_medium()
        wanted = {entry.page: entry for entry in medium_pages(medium)}

        usable = True
        for page, (label, combo) in self._rows.items():
            entry = wanted.get(page)
            self._layout.setRowVisible(combo, entry is not None)
            if entry is None:
                continue

            label.setText(page_title(page, medium))
            templates = self._for_medium(page_template_kind(page))
            combo.clear()
            if entry.optional:
                # First and default: most projects do not want the extra
                # page, and one control with a "(none)" entry beats a
                # checkbox beside a combo.
                combo.addItem(self.tr("(none)"), None)
            for template in templates:
                name = template.name + ("" if template.verified else self.tr("  (unverified dimensions)"))
                combo.addItem(name, template)
            if not templates and not entry.optional:
                usable = False

            remembered = app_settings.last_new_project_template(medium, page)
            if remembered:
                for index in range(combo.count()):
                    data = combo.itemData(index)
                    if data is not None and data.name == remembered:
                        combo.setCurrentIndex(index)
                        break

        self.empty_label.setVisible(not usable)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(usable)

    def _on_accept(self) -> None:
        medium = self.current_medium()
        self.selected_medium = medium
        self.selected_templates = {}
        app_settings.set_last_new_project_medium(medium)
        for entry in medium_pages(medium):
            template = self._rows[entry.page][1].currentData()
            if template is not None:
                self.selected_templates[entry.page] = copy.deepcopy(template)
            app_settings.set_last_new_project_template(medium, entry.page, template.name if template else "")
        self.accept()

    # -- named rows --------------------------------------------------------
    #
    # The rows are built from a declaration, but the three pages this app
    # had before that declaration existed are still worth naming: reading
    # (and testing) "the disc row" beats indexing a dict by a string in
    # every call site that only ever means one page.

    @property
    def disc_combo(self) -> QComboBox:
        return self._rows[PAGE_DISC][1]

    @property
    def cover_combo(self) -> QComboBox:
        return self._rows[PAGE_COVER][1]

    @property
    def back_combo(self) -> QComboBox:
        return self._rows[PAGE_BACK][1]

    @property
    def disc_label(self) -> QLabel:
        return self._rows[PAGE_DISC][0]

    @property
    def cover_label(self) -> QLabel:
        return self._rows[PAGE_COVER][0]
