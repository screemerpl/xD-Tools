"""Toolbar > "+": add one of the pages this project does not have yet.

One dialog, three questions -- which page, which template, and whether to
start it empty or build it from the project's metadata.

It used to be two dialogs and two of those questions: a `QInputDialog`
asking for the page, then a second one asking for the template, with no way
back from the second to the first and nothing offering to fill the page in.
Both were reported together ("two separate windows ... this should be
joined together", "the UI should ask if we want a blank one or generated"),
and they are really one report: the reason a page needed three prompts was
that nothing was holding the three answers at once.

The template list is filtered to whichever page is selected -- a page's
template family changes with it (see project.page_template_kind), so the
list is rebuilt on every page change rather than gathered once. The
generate option follows the *template*, not the page: whether an automatic
layout exists for it is the caller's question to answer, which is why
`can_generate` is passed in rather than worked out here -- that logic lives
in MainWindow._can_auto_generate_page and must not fork.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QRadioButton,
    QVBoxLayout,
)


class AddPageDialog(QDialog):
    def __init__(
        self,
        pages: Sequence[tuple[str, str]],
        templates_for: Callable[[str], list],
        can_generate: Callable[[str, object], bool],
        parent=None,
    ) -> None:
        """`pages` is (page key, display title) in the order to offer them,
        `templates_for` returns the templates a page may take, and
        `can_generate` says whether "Generated from Metadata" is a real
        option for a (page, template) pair."""
        super().__init__(parent)
        self.setWindowTitle(self.tr("Add Page"))
        self._templates_for = templates_for
        self._can_generate = can_generate

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.page_combo = QComboBox()
        for page, title in pages:
            self.page_combo.addItem(title, page)
        self.page_combo.currentIndexChanged.connect(self._refresh_templates)
        form.addRow(self.tr("Page:"), self.page_combo)

        self.template_combo = QComboBox()
        # The names differ a lot in length between page kinds ("sticker"
        # against "CD Jewel Case Back (Tray Card)"), and this combo's
        # contents change with the page selector -- Qt's default
        # AdjustToContentsOnFirstShow would lock its width to whatever was
        # in it first and truncate every longer name after that, the same
        # trap the toolbar's own Template dropdown documents.
        self.template_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.template_combo.currentIndexChanged.connect(self._refresh_content_options)
        form.addRow(self.tr("Template:"), self.template_combo)
        layout.addLayout(form)

        self.empty_radio = QRadioButton(self.tr("Start the page empty"))
        self.empty_radio.setChecked(True)
        layout.addWidget(self.empty_radio)

        self.generate_radio = QRadioButton(self.tr("Build it from the project's metadata"))
        layout.addWidget(self.generate_radio)

        self.generate_note = QLabel()
        self.generate_note.setWordWrap(True)
        self.generate_note.setEnabled(False)
        layout.addWidget(self.generate_note)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        self._refresh_templates()

    # -- state ---------------------------------------------------------------

    @property
    def selected_page(self) -> str | None:
        return self.page_combo.currentData()

    @property
    def selected_template(self):
        return self.template_combo.currentData()

    @property
    def generate(self) -> bool:
        """Whether to build the new page from the metadata.

        Reads the radio's *enabled* state as well as its checked one: the
        option is disabled for a template no automatic layout can build,
        and a disabled-but-checked radio would otherwise promise a layout
        that then silently did nothing.
        """
        return self.generate_radio.isEnabled() and self.generate_radio.isChecked()

    # -- wiring --------------------------------------------------------------

    def _refresh_templates(self) -> None:
        page = self.selected_page
        self.template_combo.blockSignals(True)
        self.template_combo.clear()
        for template in self._templates_for(page) if page else []:
            self.template_combo.addItem(template.name, template)
        self.template_combo.blockSignals(False)
        self._refresh_content_options()

    def _refresh_content_options(self) -> None:
        page = self.selected_page
        template = self.selected_template
        # No template at all means there is nothing to add -- OK would
        # create a page with no shape, so it is refused here rather than
        # left to fail later.
        has_template = template is not None
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(has_template)

        possible = bool(has_template and page and self._can_generate(page, template))
        self.generate_radio.setEnabled(possible)
        if not possible:
            # Falls back rather than leaving a disabled option selected --
            # see the `generate` property.
            self.empty_radio.setChecked(True)
        if not has_template:
            self.generate_note.setText(
                self.tr("There are no templates for that page (Templates > Manage Templates).")
            )
        elif possible:
            self.generate_note.setText(
                self.tr("The album's artwork, colours and track list, laid out on this template.")
            )
        else:
            self.generate_note.setText(
                self.tr("This template is not one the automatic layout knows how to build.")
            )
