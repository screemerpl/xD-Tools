"""The Record menu entry has to follow the adapter setting.

Every other MDRem entry point sits on a dialog that is rebuilt each time it
opens, so it reads the setting afresh for free. This one is an action built
once at startup, and it stayed visible after the adapter was switched off --
offering to record an album through hardware the user had just said they do
not have, and putting up the "mark tracks through the adapter" option along
with it.
"""

import pytest

from mdtools import app_settings
from mdtools import app_window as app_module
from mdtools.app_window import MainWindow
from mdtools.panels.settings_dialog import SettingsDialog


@pytest.fixture
def isolated_settings(tmp_path, monkeypatch):
    """app_settings writes to a real per-user settings.ini -- without this,
    these tests would switch the adapter off in the user's own config."""
    from PySide6.QtCore import QSettings

    path = tmp_path / "settings.ini"
    monkeypatch.setattr(
        app_settings, "_settings", lambda: QSettings(str(path), QSettings.Format.IniFormat)
    )
    return path


def _window() -> MainWindow:
    return MainWindow(show_startup_dialog=False)


def _settings_returning(monkeypatch, enabled: bool):
    """A stand-in for the Settings dialog that only records the choice, so
    these tests are about the menu rather than about the dialog's widgets."""

    class _Fake:
        def __init__(self, parent=None):
            pass

        def exec(self):
            app_settings.set_mdrem_enabled(enabled)
            return 1

    monkeypatch.setattr(app_module, "SettingsDialog", _Fake)


def test_the_entry_is_hidden_without_the_adapter(qt_app, isolated_settings):
    app_settings.set_mdrem_enabled(False)

    assert _window().record_action.isVisible() is False


def test_the_entry_appears_when_the_adapter_is_switched_on(qt_app, isolated_settings, monkeypatch):
    app_settings.set_mdrem_enabled(False)
    window = _window()
    _settings_returning(monkeypatch, True)

    window._show_settings()

    assert window.record_action.isVisible()


def test_the_entry_disappears_when_the_adapter_is_switched_off(qt_app, isolated_settings, monkeypatch):
    """The actual report: recording stayed on offer, and with it the option
    to split tracks through an adapter that was no longer enabled."""
    app_settings.set_mdrem_enabled(True)
    window = _window()
    assert window.record_action.isVisible(), "precondition"
    _settings_returning(monkeypatch, False)

    window._show_settings()

    assert window.record_action.isVisible() is False


def test_recording_refuses_outright_without_the_adapter(qt_app, isolated_settings, monkeypatch):
    """A backstop behind the hidden menu entry: the flow arms the deck and
    marks the tracks over infrared, so there is nothing it can do without
    one."""
    app_settings.set_mdrem_enabled(False)
    monkeypatch.setattr(
        app_module, "resolve_port", lambda *a, **k: pytest.fail("must not go looking for a port")
    )

    _window()._record_from_foobar()


def test_the_real_settings_dialog_keeps_the_menu_in_step(qt_app, isolated_settings, monkeypatch):
    """Not just the stand-in above -- the actual dialog writes the setting on
    OK, and the menu has to reflect that."""
    app_settings.set_mdrem_enabled(False)
    window = _window()
    monkeypatch.setattr(SettingsDialog, "exec", lambda self: (self.mdrem_check.setChecked(True), self._on_accept())[1])

    window._show_settings()

    assert app_settings.mdrem_enabled() is True
    assert window.record_action.isVisible()
