"""Window > Settings... -- global, user-level app settings: the DPI values
used for the on-screen canvas/exports/Bake Layers, the audio output
devices, MDRem, the shared audio folder, and the Telegram bot account.
Deliberately separate from the Metadata dialog: these apply the same way
regardless of which project is open, so they're read/written straight
from mdtools.app_settings rather than living on the Project object.

**One window, a list of groups down the left.** Settings used to be a
single long form here plus a second dialog of their own for the Telegram
account, reached from the Experimental menu -- so the same question ("what
is xD-Tools configured to do?") had two different answers in two places,
and finding the Telegram one meant knowing it was filed under
Experimental at all. The groups are pages of one QStackedWidget behind a
QListWidget, with a single OK/Cancel underneath: whichever group is on
screen, OK saves all of them, because they are one settings window.
"""

from __future__ import annotations

from pathlib import Path

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
    QListWidget,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from PySide6.QtCore import Qt

from mdtools import app_settings, audio_engine, cdrip, mdrem
from mdtools.panels.telegram_login_dialog import TelegramLoginDialog

DPI_RANGE = (20.0, 4800.0)

# Group list entries, by position in the stack -- see _build_groups().
GROUP_GENERAL = 0
GROUP_TELEGRAM = 1

_GROUP_LIST_WIDTH = 150

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
        self.resize(680, 560)

        outer = QVBoxLayout(self)

        body = QHBoxLayout()
        self.group_list = QListWidget()
        self.group_list.setFixedWidth(_GROUP_LIST_WIDTH)
        self.group_list.addItem(self.tr("General"))
        self.group_list.addItem(self.tr("Telegram"))
        body.addWidget(self.group_list)

        self.pages = QStackedWidget()
        body.addWidget(self.pages, 1)
        outer.addLayout(body, 1)

        self.group_list.currentRowChanged.connect(self.pages.setCurrentIndex)

        general = QWidget()
        layout = QFormLayout(general)

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

        self._build_audio_output_row(layout)
        self._build_experimental_row(layout)
        self._build_mdrem_rows(layout)

        restore_btn = QPushButton(self.tr("Restore Defaults"))
        restore_btn.clicked.connect(self._restore_defaults)
        layout.addRow(restore_btn)
        self.pages.addWidget(general)

        telegram = QWidget()
        self._build_telegram_page(QFormLayout(telegram))
        self.pages.addWidget(telegram)

        # One OK/Cancel for the whole window, not one per group: these are
        # pages of a single settings dialog, so OK saves every group's
        # fields whichever one happens to be on screen (see _on_accept).
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

        self.group_list.setCurrentRow(GROUP_GENERAL)

    def show_group(self, index: int) -> None:
        """Opens on a particular group -- used by the Telegram chat's own
        "Sign in..." button, which has one specific page to send the user
        to and no reason to drop them on General to find it."""
        self.group_list.setCurrentRow(index)

    def _build_audio_output_row(self, layout: QFormLayout) -> None:
        """Which device xD-Tools' own audio engine plays recording source
        material through -- e.g. an interface's line/S/PDIF output feeding
        a MiniDisc deck or a CD burner's monitor path. Unrelated to the
        MDRem checkbox below: this has nothing to do with the infrared
        adapter. This is what replaced foobar2000's own output device
        setting once recording stopped driving foobar2000 at all -- see
        audio_engine.py's own module docstring.

        Two independent rows, not one -- explicit request: a MiniDisc deck
        typically wants a digital (S/PDIF) output and a cassette deck an
        analogue line output, which are routinely two different physical
        interfaces (or two different outputs on the same one). See
        app_settings.audio_output_device()/tape_audio_output_device()."""
        self.audio_device_combo = self._build_device_combo_row(
            layout,
            self.tr("MiniDisc audio output device"),
            app_settings.audio_output_device(),
            self.tr(
                "The output device audio is played through while recording to MiniDisc -- typically a "
                "digital (S/PDIF) output feeding the deck. Leave as \"System default\" to use whatever "
                "the operating system currently considers the default output."
            ),
        )
        self.tape_audio_device_combo = self._build_device_combo_row(
            layout,
            self.tr("Cassette audio output device"),
            app_settings.tape_audio_output_device(),
            self.tr(
                "The output device audio is played through while recording to cassette -- typically an "
                "analogue line output feeding the deck. Leave as \"System default\" to use whatever the "
                "operating system currently considers the default output."
            ),
        )

        self.recording_gain_spin = QDoubleSpinBox()
        self.recording_gain_spin.setRange(-24.0, 0.0)
        self.recording_gain_spin.setDecimals(1)
        self.recording_gain_spin.setSuffix(self.tr(" dB"))
        self.recording_gain_spin.setValue(app_settings.recording_gain_db())
        self.recording_gain_spin.setToolTip(
            self.tr(
                "Headroom below full scale while recording, so a hot digital source has no chance to clip "
                "on the way in. Does not affect preview playback."
            )
        )
        layout.addRow(self.tr("Recording gain"), self.recording_gain_spin)

    def _build_device_combo_row(
        self, layout: QFormLayout, label: str, selected: str, tooltip: str
    ) -> QComboBox:
        """One "device combo + Refresh button" row -- factored out so the
        MiniDisc and Cassette rows (see _build_audio_output_row) are built
        identically rather than as two hand-copied blocks."""
        combo = QComboBox()
        combo.setToolTip(tooltip)
        refresh_btn = QPushButton(self.tr("Refresh"))
        refresh_btn.setToolTip(self.tr("Re-lists the currently available output devices."))
        refresh_btn.clicked.connect(lambda: self._populate_audio_devices(combo, self._selected_audio_device(combo)))

        device_widget = QWidget()
        device_row = QHBoxLayout(device_widget)
        device_row.setContentsMargins(0, 0, 0, 0)
        device_row.addWidget(combo, 1)
        device_row.addWidget(refresh_btn)
        layout.addRow(label, device_widget)

        self._populate_audio_devices(combo, selected)
        return combo

    def _populate_audio_devices(self, combo: QComboBox, selected: str) -> None:
        """Lists the output devices currently present, but never drops
        `selected` -- same "a saved choice survives even when its device
        happens to be unplugged right now" rule _populate_ports() follows
        for the MDRem port, just for a sound card/interface instead of a
        serial adapter."""
        combo.clear()
        combo.addItem(self.tr("System default"), "")
        names = []
        try:
            devices = audio_engine.list_output_devices()
        except audio_engine.AudioEngineError:
            devices = []
        for device in devices:
            combo.addItem(device.name, device.name)
            names.append(device.name)
        if selected and selected not in names:
            combo.addItem(self.tr("{device} (not connected)").format(device=selected), selected)
        index = combo.findData(selected)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _selected_audio_device(self, combo: QComboBox) -> str:
        return str(combo.currentData() or "")

    def _build_experimental_row(self, layout: QFormLayout) -> None:
        """Gates work-in-progress features that aren't ready for everyone --
        currently just the (empty, for now) Experimental menu. Kept separate
        from the MDRem checkbox below: that one gates hardware support,
        this one gates in-development software features, and the two have
        nothing to do with each other."""
        self.experimental_check = QCheckBox(self.tr("Show experimental features"))
        self.experimental_check.setChecked(app_settings.experimental_features_enabled())
        self.experimental_check.setToolTip(
            self.tr("Shows in-development features that aren't finished yet.")
        )
        layout.addRow(self.experimental_check)

    def _build_mdrem_rows(self, layout: QFormLayout) -> None:
        """MDRem is the RP2040 IR adapter that writes titles onto the disc
        itself. Everything about it is optional -- with the checkbox off,
        the Metadata dialog's Upload button and the startup screen's Remote
        button don't appear at all."""
        self.mdrem_check = QCheckBox(self.tr("Enable MDRem IR remote adapter"))
        self.mdrem_check.setChecked(app_settings.mdrem_enabled())
        self.mdrem_check.setToolTip(
            self.tr(
                "Adds Upload Tracklist to the Metadata dialog, the Recording menu's entries, and a Remote "
                "window to the startup screen, for writing titles onto the MiniDisc itself over infrared."
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

        self._build_cd_rows(layout)
        self._mdrem_form = layout

        self._populate_ports(app_settings.mdrem_port())
        self._sync_mdrem_enabled(self.mdrem_check.isChecked())

    def _build_cd_rows(self, layout: QFormLayout) -> None:
        """Settings for Record CD to MiniDisc.

        Not tied to the MDRem checkbox: this describes the filesystem, not
        the infrared adapter."""
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

    def _browse_rip_folder(self) -> None:
        """Creates the configured folder before browsing to it.

        Before the first rip it does not exist yet -- that is the normal
        state, not a mistake -- and a picker opened on a directory that is
        not there does not politely fall back: it complains. Creating it
        first is also what the user asked for in so many words: if the
        folder is missing, make it."""
        start = self.cd_rip_folder_edit.text().strip()
        if start:
            try:
                cdrip.ensure_folder(Path(start))
            except cdrip.CdRipError:
                # Not worth a dialog on the way to a dialog: the picker
                # simply opens wherever it can, and OK will explain.
                start = ""
        path = QFileDialog.getExistingDirectory(self, self.tr("CD rip folder"), start)
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

    def _build_telegram_page(self, layout: QFormLayout) -> None:
        """The Telegram bot account -- moved here wholesale from what used
        to be its own "Experimental Settings..." dialog under the
        Experimental menu.

        See mdtools.telegram_bot for why this needs a real Telegram user
        login rather than a bot token."""
        # self.tr(...) has to be called outside the f-string --
        # pyside6-lupdate's static scanner does not see a tr() call nested
        # inside an f-string's {...} interpolation at all.
        title = self.tr("Telegram bot")
        header = QLabel(f"<b>{title}</b>")
        layout.addRow(header)

        note = QLabel(
            self.tr(
                "Downloading an album from a Telegram bot is still in development. Once signed in, its "
                "window appears in the Source menu, which needs \"Show experimental features\" turned on "
                "in General."
            )
        )
        note.setWordWrap(True)
        layout.addRow(note)

        # No API ID/Hash fields at all: a build carries its own registered
        # pair (injected at build time -- see
        # app_settings._bundled_telegram_credentials()), so there is nothing
        # here for the user to obtain, enter or keep track of -- showing two
        # pre-filled credential boxes only invited the question of what they
        # were for. They stay overridable for anyone who wants their own
        # registered app, just through settings.ini rather than a permanent
        # row in this dialog (see app_settings.telegram_api_id()).
        self.bot_username_edit = QLineEdit(app_settings.telegram_bot_username())
        self.bot_username_edit.setPlaceholderText("@your_bot")
        layout.addRow(self.tr("Bot username"), self.bot_username_edit)

        # No "Download folder" row -- merged with the CD rip folder in
        # General, since a downloaded album and a CD rip are both just
        # audio on their way into the same recording flow, and keeping two
        # separately-configurable folders for the same purpose only invited
        # them to drift apart.

        self.telegram_status_label = QLabel()
        layout.addRow(self.tr("Status"), self.telegram_status_label)

        sign_in_btn = QPushButton(self.tr("Sign in to Telegram..."))
        sign_in_btn.clicked.connect(self._sign_in)
        layout.addRow(sign_in_btn)

        self.sign_out_btn = QPushButton(self.tr("Sign out"))
        self.sign_out_btn.clicked.connect(self._sign_out)
        layout.addRow(self.sign_out_btn)

        self._refresh_telegram_status()

    def _refresh_telegram_status(self) -> None:
        """Local file presence only -- no network round trip just to open
        this dialog. Same deliberately-optimistic convention the MDRem port
        combo already uses for a saved-but-maybe-unplugged port: this can't
        promise the session is still valid, only that one was saved."""
        signed_in = app_settings.telegram_session_path().exists()
        if signed_in:
            self.telegram_status_label.setText(self.tr("A saved sign-in exists locally."))
        else:
            self.telegram_status_label.setText(self.tr("Not signed in yet."))
        self.sign_out_btn.setEnabled(signed_in)

    def _sign_in(self) -> None:
        """Reads the credentials straight from app_settings rather than from
        dialog fields -- there are none (see _build_telegram_page). They can
        still be empty in principle, if someone deliberately blanked them in
        settings.ini, so the guard stays."""
        api_id = app_settings.telegram_api_id().strip()
        api_hash = app_settings.telegram_api_hash().strip()
        if not api_id or not api_hash:
            QMessageBox.warning(
                self,
                self.tr("Sign in to Telegram"),
                self.tr("No Telegram API credentials are configured."),
            )
            return
        dialog = TelegramLoginDialog(api_id, api_hash, self)
        dialog.exec()
        self._refresh_telegram_status()

    def _sign_out(self) -> None:
        """Deletes the local Telethon session file -- the same file a
        fresh sign-in creates, and the same one _refresh_telegram_status()
        checks for. This is a local, offline operation: nothing is revoked
        on Telegram's own servers, it just forgets the session on this
        machine, same as forgetting a browser's saved login."""
        app_settings.telegram_session_path().unlink(missing_ok=True)
        self._refresh_telegram_status()

    def _restore_defaults(self) -> None:
        self.screen_dpi_spin.setValue(app_settings.DEFAULT_SCREEN_DPI)
        self.export_dpi_spin.setValue(app_settings.DEFAULT_EXPORT_DPI)
        self.bake_dpi_spin.setValue(app_settings.DEFAULT_BAKE_DPI)
        self.cd_rip_folder_edit.setText(app_settings.default_cd_rip_folder())
        self._populate_audio_devices(self.audio_device_combo, "")
        self._populate_audio_devices(self.tape_audio_device_combo, "")
        self.recording_gain_spin.setValue(app_settings.DEFAULT_RECORDING_GAIN_DB)

    def _on_accept(self) -> None:
        app_settings.set_screen_dpi(self.screen_dpi_spin.value())
        app_settings.set_default_export_dpi(self.export_dpi_spin.value())
        app_settings.set_bake_dpi(self.bake_dpi_spin.value())
        app_settings.set_audio_output_device(self._selected_audio_device(self.audio_device_combo))
        app_settings.set_tape_audio_output_device(self._selected_audio_device(self.tape_audio_device_combo))
        app_settings.set_recording_gain_db(self.recording_gain_spin.value())
        app_settings.set_experimental_features_enabled(self.experimental_check.isChecked())
        app_settings.set_mdrem_enabled(self.mdrem_check.isChecked())
        app_settings.set_mdrem_port(self.selected_port())
        app_settings.set_cd_rip_folder(self.cd_rip_folder_edit.text())
        # Every group, not only the one on screen -- see __init__.
        app_settings.set_telegram_bot_username(self.bot_username_edit.text())
        self._create_rip_folder()
        self.accept()

    def _create_rip_folder(self) -> None:
        """Makes the chosen folder now, so a rip never trips over it.

        A failure warns but does not block OK, the same rule the MDRem port
        follows: a drive that is not plugged in right now is a reason to say
        so, not a reason to refuse the setting."""
        folder = self.cd_rip_folder_edit.text().strip()
        if not folder:
            return
        try:
            cdrip.ensure_folder(Path(folder))
        except cdrip.CdRipError as exc:
            QMessageBox.warning(
                self,
                self.tr("CD rip folder"),
                self.tr(
                    "That folder could not be created: {error}\n\nThe setting has been saved anyway, but a "
                    "CD cannot be ripped there until it exists."
                ).format(error=exc),
            )
