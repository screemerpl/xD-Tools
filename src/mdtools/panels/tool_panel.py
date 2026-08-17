from __future__ import annotations

from PySide6.QtCore import QSize, Signal
from PySide6.QtWidgets import QFrame, QMenu, QToolButton, QVBoxLayout, QWidget

from mdtools.panels import icons

ICON_SIZE = QSize(24, 24)


class ToolPanel(QWidget):
    add_text_requested = Signal()
    add_rectangle_requested = Signal()
    add_image_requested = Signal()
    insert_asset_requested = Signal()
    clip_layers_requested = Signal()
    bake_layers_requested = Signal()
    save_as_template_requested = Signal()
    auto_layout_requested = Signal()
    edit_metadata_requested = Signal()
    metadata_text_requested = Signal(str)  # emits the text to insert
    metadata_columns_requested = Signal(list)  # emits column texts to insert as side-by-side layers

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self._toolbar_buttons: list[QToolButton] = []

        text_btn = self._icon_button(icons.text_icon(), self.tr("Add Text"))
        text_btn.clicked.connect(self.add_text_requested)
        layout.addWidget(text_btn)

        rect_btn = self._icon_button(icons.rectangle_icon(), self.tr("Add Rectangle"))
        rect_btn.clicked.connect(self.add_rectangle_requested)
        layout.addWidget(rect_btn)

        image_btn = self._icon_button(icons.image_icon(), self.tr("Add Image..."))
        image_btn.clicked.connect(self.add_image_requested)
        layout.addWidget(image_btn)

        asset_btn = self._icon_button(icons.gallery_icon(), self.tr("Insert Asset..."))
        asset_btn.clicked.connect(self.insert_asset_requested)
        layout.addWidget(asset_btn)

        # Next to Insert from Metadata rather than in a menu: the album
        # details and the layers built out of them are one job, and the menu
        # this used to live in is now about recording only.
        edit_metadata_btn = self._icon_button(
            icons.edit_metadata_icon(),
            self.tr("Metadata..."),
            self.tr("The album title, artist, year and track list this project describes"),
        )
        edit_metadata_btn.clicked.connect(self.edit_metadata_requested)
        layout.addWidget(edit_metadata_btn)

        self.metadata_button = QToolButton()
        self.metadata_button.setIcon(icons.metadata_icon())
        self.metadata_button.setIconSize(ICON_SIZE)
        self.metadata_button.setToolTip(self.tr("Insert from Metadata"))
        self.metadata_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.metadata_menu = QMenu(self.metadata_button)
        self.metadata_button.setMenu(self.metadata_menu)
        self._toolbar_buttons.append(self.metadata_button)
        layout.addWidget(self.metadata_button)

        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(separator)

        clip_layers_btn = self._icon_button(
            icons.crop_icon(),
            self.tr("Clip Layers"),
            self.tr(
                "Remove layers entirely outside the printable area; clip images that are only partially outside"
            ),
        )
        clip_layers_btn.clicked.connect(self.clip_layers_requested)
        layout.addWidget(clip_layers_btn)

        bake_layers_btn = self._icon_button(
            icons.bake_icon(),
            self.tr("Bake Layers"),
            self.tr("Flatten every layer into a single image, exactly as Export Print PNG would render it"),
        )
        bake_layers_btn.clicked.connect(self.bake_layers_requested)
        layout.addWidget(bake_layers_btn)

        save_template_btn = self._icon_button(
            icons.save_icon(),
            self.tr("Save as Template..."),
            self.tr("Save this page's template shape and everything on it as a new template for File > New"),
        )
        save_template_btn.clicked.connect(self.save_as_template_requested)
        layout.addWidget(save_template_btn)

        auto_layout_btn = self._icon_button(
            icons.autolayout_icon(),
            self.tr("Auto-Layout Disc Label"),
            self.tr(
                "Build the disc label from the project's metadata: the full-face template, the cover art "
                "cropped to it, and the MiniDisc logo on the slider. Replaces the whole page."
            ),
        )
        auto_layout_btn.clicked.connect(self.auto_layout_requested)
        layout.addWidget(auto_layout_btn)

        layout.addStretch(1)

        # All buttons the same size as Insert from Metadata's -- a plain
        # QPushButton (used here previously) reserves extra horizontal
        # padding for its "3D" look even with no visible text, making it
        # noticeably wider than a QToolButton with the same icon; using
        # QToolButton throughout (see _icon_button) mostly fixes that on
        # its own, but forcing every button to the exact same
        # sizeHint() -- rather than trusting that different QToolButton
        # instances/tooltips naturally end up pixel-identical -- is what
        # actually guarantees it.
        button_size = self.metadata_button.sizeHint()
        for button in self._toolbar_buttons:
            button.setFixedSize(button_size)

    def _icon_button(self, icon, tooltip: str, extra_tooltip: str | None = None) -> QToolButton:
        """Icon-only button (no visible text) -- the label always lives in
        the tooltip instead, so hovering still tells you what it does."""
        btn = QToolButton()
        btn.setIcon(icon)
        btn.setIconSize(ICON_SIZE)
        btn.setToolTip(f"{tooltip}\n{extra_tooltip}" if extra_tooltip else tooltip)
        self._toolbar_buttons.append(btn)
        return btn

    def set_metadata_entries(
        self,
        entries: list[tuple[str, str]],
        column_entries: list[tuple[str, list[str]]] | None = None,
    ) -> None:
        """entries: (menu label, text to insert) pairs, each inserting one
        text layer. column_entries: (menu label, column texts) pairs, each
        inserting that many text layers side by side (e.g. a track list
        split into two columns). Rebuilt each time the menu is about to
        open so it always reflects the current project metadata."""
        self.metadata_menu.clear()
        column_entries = column_entries or []
        if not entries and not column_entries:
            action = self.metadata_menu.addAction(self.tr("(fill the metadata in first)"))
            action.setEnabled(False)
            return
        for label, text in entries:
            self.metadata_menu.addAction(label, lambda checked=False, t=text: self.metadata_text_requested.emit(t))
        if entries and column_entries:
            self.metadata_menu.addSeparator()
        for label, columns in column_entries:
            self.metadata_menu.addAction(
                label, lambda checked=False, c=columns: self.metadata_columns_requested.emit(c)
            )
