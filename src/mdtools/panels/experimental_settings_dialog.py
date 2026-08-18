"""Settings for whatever lives in the Experimental menu -- reached from its
own "Experimental Settings..." entry, deliberately **not** rows bolted onto
the main Window > Settings dialog (explicit user decision: experimental
features get their own settings surface, so the stable dialog never has to
carry half-finished feature configuration, and later experimental features
land here too instead of in either dialog growing an unrelated pile of
checkboxes).

Currently holds just the Telegram bot integration's account block -- see
mdtools.telegram_bot for why this needs a real Telegram user login rather
than a bot token.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QWidget,
)

from mdtools import app_settings, cdrip
from mdtools.panels.telegram_login_dialog import TelegramLoginDialog


def _with_button(edit: QLineEdit, button: QPushButton) -> QWidget:
    """Own copy of settings_dialog.py's identical helper -- nine lines is
    the cheaper side of the trade against pulling settings_dialog.py's
    private helper across module boundaries for it (same reasoning
    user_paths.sanitize_filename gives for its own copy of cdrip's)."""
    widget = QWidget()
    row = QHBoxLayout(widget)
    row.setContentsMargins(0, 0, 0, 0)
    row.addWidget(edit, 1)
    row.addWidget(button)
    return widget


class ExperimentalSettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Experimental Settings"))

        layout = QFormLayout(self)

        note = QLabel(
            self.tr(
                "Settings for in-development features shown only while \"Show experimental features\" is "
                "enabled in Window > Settings."
            )
        )
        note.setWordWrap(True)
        layout.addRow(note)

        self._build_telegram_rows(layout)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _build_telegram_rows(self, layout: QFormLayout) -> None:
        # self.tr(...) has to be called outside the f-string -- pyside6-lupdate's
        # static scanner does not see a tr() call nested inside an f-string's
        # {...} interpolation at all (confirmed: it silently skipped both this
        # and telegram_chat_dialog.py's near-identical "Downloads" header
        # until they were pulled out like this).
        title = self.tr("Telegram bot")
        header = QLabel(f"<b>{title}</b>")
        layout.addRow(header)

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

        self.download_folder_edit = QLineEdit(app_settings.telegram_download_folder())
        self.download_folder_edit.setToolTip(
            self.tr("Where an album downloaded from the bot is saved before being recorded.")
        )
        browse_btn = QPushButton(self.tr("Browse..."))
        browse_btn.clicked.connect(self._browse_download_folder)
        layout.addRow(self.tr("Download folder"), _with_button(self.download_folder_edit, browse_btn))

        self.status_label = QLabel()
        layout.addRow(self.tr("Status"), self.status_label)
        self._refresh_status()

        sign_in_btn = QPushButton(self.tr("Sign in to Telegram..."))
        sign_in_btn.clicked.connect(self._sign_in)
        layout.addRow(sign_in_btn)

    def _refresh_status(self) -> None:
        """Local file presence only -- no network round trip just to open
        this dialog. Same deliberately-optimistic convention the MDRem port
        combo already uses for a saved-but-maybe-unplugged port: this can't
        promise the session is still valid, only that one was saved."""
        if app_settings.telegram_session_path().exists():
            self.status_label.setText(self.tr("A saved sign-in exists locally."))
        else:
            self.status_label.setText(self.tr("Not signed in yet."))

    def _browse_download_folder(self) -> None:
        start = self.download_folder_edit.text().strip()
        if start:
            try:
                cdrip.ensure_folder(Path(start))
            except cdrip.CdRipError:
                start = ""
        path = QFileDialog.getExistingDirectory(self, self.tr("Download folder"), start)
        if path:
            self.download_folder_edit.setText(path)

    def _sign_in(self) -> None:
        """Reads the credentials straight from app_settings rather than from
        dialog fields -- there are none any more (see _build_telegram_rows).
        They can still be empty in principle, if someone deliberately blanked
        them in settings.ini, so the guard stays."""
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
        self._refresh_status()

    def _on_accept(self) -> None:
        app_settings.set_telegram_bot_username(self.bot_username_edit.text())
        app_settings.set_telegram_download_folder(self.download_folder_edit.text())
        self._create_download_folder()
        self.accept()

    def _create_download_folder(self) -> None:
        """Same "warn, don't block OK" rule SettingsDialog's CD rip folder
        follows: a drive that isn't there right now is worth saying, not a
        reason to refuse the setting."""
        folder = self.download_folder_edit.text().strip()
        if not folder:
            return
        try:
            cdrip.ensure_folder(Path(folder))
        except cdrip.CdRipError as exc:
            QMessageBox.warning(
                self,
                self.tr("Download folder"),
                self.tr(
                    "That folder could not be created: {error}\n\nThe setting has been saved anyway, but a "
                    "download cannot be saved there until it exists."
                ).format(error=exc),
            )
