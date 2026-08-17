"""Window > Settings... -- global, user-level app settings (currently just
the DPI values used for the on-screen canvas, exports, and Bake Layers).
Deliberately separate from Project > Metadata...: these apply the same way
regardless of which project is open, so they're read/written straight
from mdtools.app_settings rather than living on the Project object.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QWidget,
)

from PySide6.QtCore import Qt

from mdtools import app_settings, foobar, mdrem

DPI_RANGE = (20.0, 4800.0)

_PORT_ROLE = Qt.ItemDataRole.UserRole


def _with_button(edit: QLineEdit, button: QPushButton) -> QWidget:
    """A line edit and its Browse button as one form field, the same
    packing the MDRem port row uses for its Detect button."""
    widget = QWidget()
    row = QHBoxLayout(widget)
    row.setContentsMargins(0, 0, 0, 0)
    row.addWidget(edit, 1)
    row.addWidget(button)
    return widget


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Settings"))

        layout = QFormLayout(self)

        self.screen_dpi_spin = QDoubleSpinBox()
        self.screen_dpi_spin.setRange(*DPI_RANGE)
        self.screen_dpi_spin.setDecimals(1)
        self.screen_dpi_spin.setValue(app_settings.screen_dpi())
        self.screen_dpi_spin.setToolTip(
            self.tr(
                "Dots per inch used to display the canvas on screen at 100% zoom. Not necessarily your "
                "monitor's real physical DPI -- adjust this if content looks the wrong physical size on screen."
            )
        )
        layout.addRow(self.tr("Screen DPI"), self.screen_dpi_spin)
        screen_dpi_note = QLabel(
            self.tr("Applies to newly created or reopened projects -- not the one currently open.")
        )
        screen_dpi_note.setWordWrap(True)
        layout.addRow(screen_dpi_note)

        self.export_dpi_spin = QDoubleSpinBox()
        self.export_dpi_spin.setRange(*DPI_RANGE)
        self.export_dpi_spin.setDecimals(1)
        self.export_dpi_spin.setValue(app_settings.default_export_dpi())
        self.export_dpi_spin.setToolTip(
            self.tr("Default DPI for Export Print PNG / Export Print PNG (Grayscale).")
        )
        layout.addRow(self.tr("Default Export DPI"), self.export_dpi_spin)

        self.bake_dpi_spin = QDoubleSpinBox()
        self.bake_dpi_spin.setRange(*DPI_RANGE)
        self.bake_dpi_spin.setDecimals(1)
        self.bake_dpi_spin.setValue(app_settings.bake_dpi())
        self.bake_dpi_spin.setToolTip(
            self.tr(
                "DPI Tools > Bake Layers renders at. Higher than the default export DPI by default, since a "
                "baked layer's resolution is locked in permanently, unlike a re-renderable vector layer."
            )
        )
        layout.addRow(self.tr("Bake DPI"), self.bake_dpi_spin)

        self._build_mdrem_rows(layout)

        restore_btn = QPushButton(self.tr("Restore Defaults"))
        restore_btn.clicked.connect(self._restore_defaults)
        layout.addRow(restore_btn)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _build_mdrem_rows(self, layout: QFormLayout) -> None:
        """MDRem is the RP2040 IR adapter that writes titles onto the disc
        itself. Everything about it is optional -- with the checkbox off,
        the Metadata dialog's Upload button and the startup screen's Remote
        button don't appear at all."""
        self.mdrem_check = QCheckBox(self.tr("Enable MDRem IR remote adapter"))
        self.mdrem_check.setChecked(app_settings.mdrem_enabled())
        self.mdrem_check.setToolTip(
            self.tr(
                "Adds Upload Tracklist to Project > Metadata... and a Remote window to the startup screen, "
                "for writing titles onto the MiniDisc itself over infrared."
            )
        )
        self.mdrem_check.toggled.connect(self._sync_mdrem_enabled)
        layout.addRow(self.mdrem_check)

        self.mdrem_port_combo = QComboBox()
        self.mdrem_port_combo.setToolTip(
            self.tr("Serial port the MDRem adapter is connected to.")
        )
        self.mdrem_detect_btn = QPushButton(self.tr("Detect"))
        self.mdrem_detect_btn.setToolTip(
            self.tr(
                "Asks every serial port whether an MDRem adapter answers on it. The board's USB ID is shared "
                "with its own bootloader and other boards, so it can only be identified by replying."
            )
        )
        self.mdrem_detect_btn.clicked.connect(self._detect_port)

        port_widget = QWidget()
        port_row = QHBoxLayout(port_widget)
        port_row.setContentsMargins(0, 0, 0, 0)
        port_row.addWidget(self.mdrem_port_combo, 1)
        port_row.addWidget(self.mdrem_detect_btn)
        self._mdrem_port_widget = port_widget
        layout.addRow(self.tr("MDRem port"), port_widget)

        self.foobar_url_edit = QLineEdit(app_settings.foobar_url())
        self.foobar_url_edit.setToolTip(
            self.tr(
                "Where foobar2000's Beefweb Remote Control component listens, used by Record to MiniDisc. "
                "Change it only if you moved Beefweb off its default port."
            )
        )
        layout.addRow(self.tr("foobar2000 (Beefweb) URL"), self.foobar_url_edit)

        self._build_cd_rows(layout)
        self._mdrem_form = layout

        self._populate_ports(app_settings.mdrem_port())
        self._sync_mdrem_enabled(self.mdrem_check.isChecked())

    def _build_cd_rows(self, layout: QFormLayout) -> None:
        """Settings for Record CD to MiniDisc.

        Neither is tied to the MDRem checkbox, for the same reason the
        Beefweb URL above is not: they describe foobar2000 and the
        filesystem, not the infrared adapter."""
        self.foobar_exe_edit = QLineEdit(app_settings.foobar_exe() or (foobar.find_foobar_exe() or ""))
        self.foobar_exe_edit.setToolTip(
            self.tr(
                "foobar2000's own program file. Ripped CD tracks are loaded through it rather than through "
                "Beefweb, which refuses files outside the music folders configured in foobar itself."
            )
        )
        browse_exe = QPushButton(self.tr("Browse..."))
        browse_exe.clicked.connect(self._browse_foobar_exe)
        layout.addRow(self.tr("foobar2000 program"), _with_button(self.foobar_exe_edit, browse_exe))

        self.cd_rip_folder_edit = QLineEdit(app_settings.cd_rip_folder())
        self.cd_rip_folder_edit.setToolTip(
            self.tr(
                "Where a ripped CD is written. One album is a few hundred megabytes; earlier rips are deleted "
                "when the next one starts, not when a recording ends, so they stay playable in the meantime."
            )
        )
        browse_folder = QPushButton(self.tr("Browse..."))
        browse_folder.clicked.connect(self._browse_rip_folder)
        layout.addRow(self.tr("CD rip folder"), _with_button(self.cd_rip_folder_edit, browse_folder))

    def _browse_foobar_exe(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("foobar2000 program"), self.foobar_exe_edit.text(), self.tr("Programs (*.exe);;All files (*)")
        )
        if path:
            self.foobar_exe_edit.setText(path)

    def _browse_rip_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, self.tr("CD rip folder"), self.cd_rip_folder_edit.text())
        if path:
            self.cd_rip_folder_edit.setText(path)

    def _populate_ports(self, selected: str) -> None:
        """Lists the ports currently present, but never drops `selected`.

        A saved port whose adapter happens to be unplugged right now must
        still survive opening and OK-ing this dialog -- silently resetting
        it to whatever else is connected would be worse than showing it as
        missing."""
        self.mdrem_port_combo.clear()
        names = []
        for candidate in mdrem.list_ports():
            self.mdrem_port_combo.addItem(candidate.label(), candidate.name)
            names.append(candidate.name)
        if selected and selected not in names:
            self.mdrem_port_combo.addItem(
                self.tr("{port} (not connected)").format(port=selected), selected
            )
        index = self.mdrem_port_combo.findData(selected)
        if index >= 0:
            self.mdrem_port_combo.setCurrentIndex(index)

    def _sync_mdrem_enabled(self, enabled: bool) -> None:
        """Only the port follows the checkbox. The foobar2000 address does
        not: reading a playlist (Project > Metadata's "Load from
        foobar2000") needs foobar, not the infrared adapter, so tying it to
        the adapter would disable a setting the user still needs."""
        self._mdrem_port_widget.setEnabled(enabled)

    def _detect_port(self) -> None:
        self.mdrem_detect_btn.setEnabled(False)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            found = mdrem.detect_port()
        finally:
            QApplication.restoreOverrideCursor()
            self.mdrem_detect_btn.setEnabled(True)

        if found is None:
            QMessageBox.information(
                self,
                self.tr("Detect MDRem"),
                self.tr("No MDRem adapter answered on any serial port. Check that it is plugged in."),
            )
            return
        self._populate_ports(found)

    def selected_port(self) -> str:
        return str(self.mdrem_port_combo.currentData() or "")

    def _restore_defaults(self) -> None:
        self.screen_dpi_spin.setValue(app_settings.DEFAULT_SCREEN_DPI)
        self.export_dpi_spin.setValue(app_settings.DEFAULT_EXPORT_DPI)
        self.bake_dpi_spin.setValue(app_settings.DEFAULT_BAKE_DPI)
        self.cd_rip_folder_edit.setText(app_settings.default_cd_rip_folder())

    def _on_accept(self) -> None:
        app_settings.set_screen_dpi(self.screen_dpi_spin.value())
        app_settings.set_default_export_dpi(self.export_dpi_spin.value())
        app_settings.set_bake_dpi(self.bake_dpi_spin.value())
        app_settings.set_mdrem_enabled(self.mdrem_check.isChecked())
        app_settings.set_mdrem_port(self.selected_port())
        app_settings.set_foobar_url(self.foobar_url_edit.text())
        app_settings.set_foobar_exe(self.foobar_exe_edit.text())
        app_settings.set_cd_rip_folder(self.cd_rip_folder_edit.text())
        self.accept()
