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


# --- and the CD entry alongside it ------------------------------------------


def test_the_cd_entry_follows_the_adapter_too(qt_app, isolated_settings, monkeypatch):
    """Ripping a CD needs no adapter, but this entry does not stop at
    ripping -- it goes straight on to record what it ripped, which does."""
    app_settings.set_mdrem_enabled(False)
    window = _window()
    assert window.record_cd_action.isVisible() is False

    _settings_returning(monkeypatch, True)
    window._show_settings()

    assert window.record_cd_action.isVisible()


def test_recording_a_cd_refuses_outright_without_the_adapter(qt_app, isolated_settings, monkeypatch):
    app_settings.set_mdrem_enabled(False)
    monkeypatch.setattr(
        app_module, "resolve_port", lambda *a, **k: pytest.fail("must not go looking for a port")
    )
    monkeypatch.setattr(
        app_module, "CdRipDialog", lambda *a, **k: pytest.fail("must not open the rip dialog")
    )

    _window()._record_cd()


def test_the_port_is_resolved_before_the_rip_not_after_it(qt_app, isolated_settings, monkeypatch):
    """The rip is the expensive half. Discovering there is no adapter to
    record through afterwards would waste every minute of it."""
    app_settings.set_mdrem_enabled(True)
    monkeypatch.setattr(app_module, "resolve_port", lambda *a, **k: None)
    monkeypatch.setattr(
        app_module, "CdRipDialog", lambda *a, **k: pytest.fail("must not open the rip dialog")
    )

    _window()._record_cd()


def test_a_cancelled_rip_never_reaches_the_recording_dialog(qt_app, isolated_settings, monkeypatch):
    from PySide6.QtWidgets import QDialog

    app_settings.set_mdrem_enabled(True)
    monkeypatch.setattr(app_module, "resolve_port", lambda *a, **k: "COM7")

    class _RejectedRip:
        def __init__(self, *args, **kwargs):
            pass

        def exec(self):
            return QDialog.DialogCode.Rejected

    monkeypatch.setattr(app_module, "CdRipDialog", _RejectedRip)
    monkeypatch.setattr(
        app_module, "RecordDialog", lambda *a, **k: pytest.fail("must not start recording")
    )

    _window()._record_cd()


def test_a_finished_rip_hands_straight_over_to_the_recording_dialog(qt_app, isolated_settings, monkeypatch):
    """The whole point of the feature: once the playlist holds the CD, the
    existing record flow takes over unchanged and unaware a CD was ever
    involved."""
    from PySide6.QtWidgets import QDialog

    app_settings.set_mdrem_enabled(True)
    monkeypatch.setattr(app_module, "resolve_port", lambda *a, **k: "COM7")

    class _AcceptedRip:
        def __init__(self, *args, **kwargs):
            pass

        def exec(self):
            return QDialog.DialogCode.Accepted

    recorded: list = []

    class _FakeRecord:
        result_metadata = None

        def __init__(self, port, url, parent=None, metadata=None):
            recorded.append((port, metadata))

        def exec(self):
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(app_module, "CdRipDialog", _AcceptedRip)
    monkeypatch.setattr(app_module, "RecordDialog", _FakeRecord)

    _window()._record_cd()

    # No metadata is handed over: the rip wrote its titles into the files
    # themselves, so the playlist already carries them, and one source of
    # truth beats two that can disagree. Record Folder is the case that has
    # to pass them -- see test_folder_record_dialog.py.
    assert recorded == [("COM7", None)]
