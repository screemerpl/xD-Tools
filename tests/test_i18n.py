import pytest
from PySide6.QtCore import QCoreApplication, QSettings

from mdtools import i18n


@pytest.fixture
def isolated_settings(tmp_path, monkeypatch):
    """Redirect i18n's persisted language choice to a throwaway file so
    tests don't read/write the real per-user settings.ini on this machine."""
    path = tmp_path / "settings.ini"
    monkeypatch.setattr(i18n, "_settings", lambda: QSettings(str(path), QSettings.Format.IniFormat))


@pytest.fixture
def restore_translator(qt_app):
    """qt_app (the QApplication) is session-scoped, so a translator
    installed by one test would otherwise leak into every later test in
    the same run -- always put the app back to English afterward."""
    yield qt_app
    i18n.install_translator(qt_app, "en")


def test_current_language_defaults_to_english_when_unset(isolated_settings):
    assert i18n.current_language() == "en"


def test_set_language_round_trips(isolated_settings):
    i18n.set_language("pl")
    assert i18n.current_language() == "pl"


def test_unknown_saved_language_falls_back_to_default(isolated_settings):
    i18n.set_language("xx")  # not one of AVAILABLE_LANGUAGES
    assert i18n.current_language() == "en"


def test_install_translator_for_polish_actually_translates(restore_translator):
    i18n.install_translator(restore_translator, "pl")
    assert QCoreApplication.translate("ToolPanel", "Add Text") == "Dodaj tekst"


def test_install_translator_for_japanese_actually_translates(restore_translator):
    i18n.install_translator(restore_translator, "ja")
    assert QCoreApplication.translate("ToolPanel", "Add Text") == "テキストを追加"


def test_install_translator_for_english_removes_any_active_translator(restore_translator):
    i18n.install_translator(restore_translator, "pl")
    i18n.install_translator(restore_translator, "en")
    assert QCoreApplication.translate("ToolPanel", "Add Text") == "Add Text"


def test_install_translator_with_unknown_code_is_a_safe_no_op(restore_translator):
    i18n.install_translator(restore_translator, "xx")  # must not raise
    assert QCoreApplication.translate("ToolPanel", "Add Text") == "Add Text"
