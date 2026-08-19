from mdtools import app_settings
from mdtools.panels.experimental_settings_dialog import ExperimentalSettingsDialog


def test_no_api_credential_fields_are_shown_at_all(qt_app):
    """Reported directly ("wciaz w eksperymentalnych ustawieniach widze
    parametery API"): MDTools carries its own registered API ID/Hash, so
    there is nothing here for the user to obtain or enter, and two
    pre-filled credential boxes only raised the question of what they were
    for. They stay overridable through settings.ini, not through a row in
    this dialog."""
    dialog = ExperimentalSettingsDialog()

    assert not hasattr(dialog, "api_id_edit")
    assert not hasattr(dialog, "api_hash_edit")


def test_dialog_seeds_fields_from_current_settings(qt_app):
    app_settings.set_telegram_bot_username("@my_bot")
    app_settings.set_telegram_download_folder(r"C:\downloads")

    dialog = ExperimentalSettingsDialog()

    assert dialog.bot_username_edit.text() == "@my_bot"
    assert dialog.download_folder_edit.text() == r"C:\downloads"


def test_accepting_saves_the_edited_values(qt_app, tmp_path):
    dialog = ExperimentalSettingsDialog()
    dialog.bot_username_edit.setText("@another_bot")
    dialog.download_folder_edit.setText(str(tmp_path / "dl"))

    dialog._on_accept()

    assert app_settings.telegram_bot_username() == "@another_bot"
    assert app_settings.telegram_download_folder() == str(tmp_path / "dl")


def test_accepting_leaves_the_api_credentials_untouched(qt_app, tmp_path):
    """The dialog no longer writes them at all, so an override someone put
    in settings.ini by hand has to survive an OK here."""
    app_settings.set_telegram_api_id("my-own-id")
    app_settings.set_telegram_api_hash("my-own-hash")
    dialog = ExperimentalSettingsDialog()
    dialog.download_folder_edit.setText(str(tmp_path / "dl"))

    dialog._on_accept()

    assert app_settings.telegram_api_id() == "my-own-id"
    assert app_settings.telegram_api_hash() == "my-own-hash"


def test_cancelling_does_not_save_anything(qt_app):
    app_settings.set_telegram_bot_username("@original")
    dialog = ExperimentalSettingsDialog()
    dialog.bot_username_edit.setText("@changed")

    dialog.reject()

    assert app_settings.telegram_bot_username() == "@original"


def test_accepting_creates_the_download_folder(qt_app, tmp_path):
    target = tmp_path / "downloads" / "here"
    dialog = ExperimentalSettingsDialog()
    dialog.download_folder_edit.setText(str(target))

    dialog._on_accept()

    assert target.is_dir()


# --- status label -------------------------------------------------------------


def test_status_reports_not_signed_in_when_no_session_file_exists(qt_app):
    dialog = ExperimentalSettingsDialog()
    assert dialog.status_label.text() == "Not signed in yet."


def test_status_reports_a_saved_sign_in_when_the_session_file_exists(qt_app):
    session_path = app_settings.telegram_session_path()
    session_path.parent.mkdir(parents=True, exist_ok=True)
    session_path.write_bytes(b"fake session data")

    dialog = ExperimentalSettingsDialog()

    assert dialog.status_label.text() == "A saved sign-in exists locally."


# --- sign-in button -------------------------------------------------------------


def test_sign_in_button_refuses_without_api_id_or_hash(qt_app, monkeypatch):
    """Unreachable through the UI now that the credentials are built in and
    have no fields to clear -- it only fires for someone who deliberately
    blanked them in settings.ini, which is exactly why the guard stays."""
    from mdtools.panels import experimental_settings_dialog as module

    warned: list = []
    monkeypatch.setattr(module.QMessageBox, "warning", staticmethod(lambda *a, **k: warned.append(True)))
    monkeypatch.setattr(module.app_settings, "telegram_api_id", lambda: "")
    monkeypatch.setattr(module.app_settings, "telegram_api_hash", lambda: "")

    ExperimentalSettingsDialog()._sign_in()

    assert warned


def test_sign_in_button_opens_the_login_dialog_with_the_configured_credentials(qt_app, monkeypatch):
    """Straight from app_settings, since there are no fields to read them
    from -- which is what makes the build-time-injected pair the one actually
    used for a normal sign-in."""
    from mdtools.panels import experimental_settings_dialog as module

    opened: list = []

    class FakeLogin:
        def __init__(self, api_id, api_hash, parent=None):
            opened.append((api_id, api_hash))

        def exec(self):
            return 0

    monkeypatch.setattr(module, "TelegramLoginDialog", FakeLogin)
    monkeypatch.setattr(module.app_settings, "telegram_api_id", lambda: "bundled-id")
    monkeypatch.setattr(module.app_settings, "telegram_api_hash", lambda: "bundled-hash")

    ExperimentalSettingsDialog()._sign_in()

    assert opened == [("bundled-id", "bundled-hash")]
