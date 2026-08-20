"""Shown once at launch, before the New Project template pickers -- lets
the user jump straight back into one of their last few edited projects,
browse for a different one, or start a brand-new design.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from mdtools import app_settings, user_paths
from mdtools.panels.mdrem_port import resolve_port
from mdtools.panels.print_dialog import MultiprintDialog
from mdtools.panels.remote_dialog import RemoteDialog

_PATH_ROLE = Qt.ItemDataRole.UserRole


class StartupDialog(QDialog):
    """Result is read from `result_path` after a successful exec():
    - a path string -> the caller should open that project.
    - None -> the user chose "New Project...", the caller should fall
      through to the normal NewDesignDialog template-picker flow.
    A rejected dialog (Cancel/close) leaves result_path at its initial
    None too -- callers distinguish "cancelled entirely" from "chose New
    Project" via the dialog's own exec() return code, not this field."""

    def __init__(self, recent_paths: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Welcome to xD-Tools"))
        self.resize(420, 320)
        self.result_path: str | None = None

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(self.tr("Recent Projects:")))

        self.list_widget = QListWidget()
        for path in recent_paths:
            item = QListWidgetItem(Path(path).name)
            item.setData(_PATH_ROLE, path)
            item.setToolTip(path)
            self.list_widget.addItem(item)
        if not recent_paths:
            placeholder = QListWidgetItem(self.tr("(No recent projects)"))
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self.list_widget.addItem(placeholder)
        self.list_widget.itemDoubleClicked.connect(self._open_item)
        layout.addWidget(self.list_widget)

        button_row = QHBoxLayout()
        self.open_btn = QPushButton(self.tr("Open Selected"))
        self.open_btn.clicked.connect(self._open_selected)
        self.open_btn.setEnabled(bool(recent_paths))
        browse_btn = QPushButton(self.tr("Open Other Project..."))
        browse_btn.clicked.connect(self._browse)
        new_btn = QPushButton(self.tr("New Project..."))
        new_btn.clicked.connect(self._new_project)
        multiprint_btn = QPushButton(self.tr("Multiprint..."))
        multiprint_btn.clicked.connect(self._open_multiprint)
        for button in (self.open_btn, browse_btn, new_btn, multiprint_btn):
            button_row.addWidget(button)
        # Same "standalone action, not an outcome" role as Multiprint, and
        # like Upload Tracklist it only appears once the adapter is enabled
        # in Window > Settings... -- there is nothing it could usefully do
        # without hardware.
        self.remote_btn = QPushButton(self.tr("Remote..."))
        self.remote_btn.clicked.connect(self._open_remote)
        self.remote_btn.setVisible(app_settings.mdrem_enabled())
        button_row.addWidget(self.remote_btn)
        layout.addLayout(button_row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _open_item(self, item: QListWidgetItem) -> None:
        path = item.data(_PATH_ROLE)
        if not path:
            return
        self.result_path = path
        self.accept()

    def _open_selected(self) -> None:
        item = self.list_widget.currentItem()
        if item is not None:
            self._open_item(item)

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("Open Project"),
            user_paths.project_start_path(None),
            self.tr("xD-Tools Project (*.mdproj)"),
        )
        if not path:
            return
        self.result_path = path
        self.accept()

    def _new_project(self) -> None:
        self.result_path = None
        self.accept()

    def _open_multiprint(self) -> None:
        """Multiprint is a standalone action, not one of the "what should
        the main window do next" outcomes above -- it doesn't set
        result_path or accept()/reject() this dialog at all, so once the
        (modal) MultiprintDialog closes, the user is simply back at this
        startup screen to decide what to do next."""
        MultiprintDialog(self).exec()

    def _open_remote(self) -> None:
        """Like Multiprint, deliberately not one of the "what should the
        main window do next" outcomes -- controlling the deck has nothing
        to do with which project gets opened afterwards."""
        port = resolve_port(self)
        if port is None:
            return
        RemoteDialog(port, self).exec()
