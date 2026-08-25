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

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
)

from mdtools import app_settings
from mdtools.panels.telegram_login_dialog import TelegramLoginDialog


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

        # No "Download folder" row any more -- merged with the CD rip
        # folder (Window > Settings), since a downloaded album and a CD rip
        # are both just audio on their way into the same recording flow,
        # and keeping two separately-configurable folders for the same
        # purpose only invited them to drift apart.

        self.status_label = QLabel()
        layout.addRow(self.tr("Status"), self.status_label)

        sign_in_btn = QPushButton(self.tr("Sign in to Telegram..."))
        sign_in_btn.clicked.connect(self._sign_in)
        layout.addRow(sign_in_btn)

        self.sign_out_btn = QPushButton(self.tr("Sign out"))
        self.sign_out_btn.clicked.connect(self._sign_out)
        layout.addRow(self.sign_out_btn)

        self._refresh_status()

    def _refresh_status(self) -> None:
        """Local file presence only -- no network round trip just to open
        this dialog. Same deliberately-optimistic convention the MDRem port
        combo already uses for a saved-but-maybe-unplugged port: this can't
        promise the session is still valid, only that one was saved."""
        signed_in = app_settings.telegram_session_path().exists()
        if signed_in:
            self.status_label.setText(self.tr("A saved sign-in exists locally."))
        else:
            self.status_label.setText(self.tr("Not signed in yet."))
        self.sign_out_btn.setEnabled(signed_in)

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

    def _sign_out(self) -> None:
        """Deletes the local Telethon session file -- the same file a
        fresh sign-in creates, and the same one _refresh_status() checks
        for. This is a local, offline operation: nothing is revoked on
        Telegram's own servers, it just forgets the session on this
        machine, same as forgetting a browser's saved login."""
        app_settings.telegram_session_path().unlink(missing_ok=True)
        self._refresh_status()

    def _on_accept(self) -> None:
        app_settings.set_telegram_bot_username(self.bot_username_edit.text())
        self.accept()
