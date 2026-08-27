"""The Record menu entry has to follow the adapter setting.

Every other MDRem entry point sits on a dialog that is rebuilt each time it
opens, so it reads the setting afresh for free. This one is an action built
once at startup, and it stayed visible after the adapter was switched off --
offering to record an album through hardware the user had just said they do
not have, and putting up the "mark tracks through the adapter" option along
with it.
"""

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QMessageBox

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

    assert _window().record_folder_action.isVisible() is False


def test_the_entry_appears_when_the_adapter_is_switched_on(qt_app, isolated_settings, monkeypatch):
    app_settings.set_mdrem_enabled(False)
    window = _window()
    _settings_returning(monkeypatch, True)

    window._show_settings()

    assert window.record_folder_action.isVisible()


def test_the_entry_disappears_when_the_adapter_is_switched_off(qt_app, isolated_settings, monkeypatch):
    """The actual report: recording stayed on offer, and with it the option
    to split tracks through an adapter that was no longer enabled."""
    app_settings.set_mdrem_enabled(True)
    window = _window()
    assert window.record_folder_action.isVisible(), "precondition"
    _settings_returning(monkeypatch, False)

    window._show_settings()

    assert window.record_folder_action.isVisible() is False


def test_recording_refuses_outright_without_the_adapter(qt_app, isolated_settings, monkeypatch):
    """A backstop behind the hidden menu entry: the flow arms the deck and
    marks the tracks over infrared, so there is nothing it can do without
    one."""
    app_settings.set_mdrem_enabled(False)
    monkeypatch.setattr(
        app_module, "resolve_port", lambda *a, **k: pytest.fail("must not go looking for a port")
    )

    _window()._record_folder()


def test_the_real_settings_dialog_keeps_the_menu_in_step(qt_app, isolated_settings, monkeypatch):
    """Not just the stand-in above -- the actual dialog writes the setting on
    OK, and the menu has to reflect that."""
    app_settings.set_mdrem_enabled(False)
    window = _window()
    monkeypatch.setattr(SettingsDialog, "exec", lambda self: (self.mdrem_check.setChecked(True), self._on_accept())[1])

    window._show_settings()

    assert app_settings.mdrem_enabled() is True
    assert window.record_folder_action.isVisible()


# --- and the Remote Control entry alongside it ------------------------------
#
# Reported directly: the software remote used to be reachable only from the
# startup screen, so using it while a project was open meant closing that
# project first.


def test_the_remote_entry_follows_the_adapter_too(qt_app, isolated_settings):
    app_settings.set_mdrem_enabled(False)
    assert _window().remote_action.isVisible() is False

    app_settings.set_mdrem_enabled(True)
    assert _window().remote_action.isVisible() is True


def test_opening_the_remote_resolves_a_port_and_shows_the_dialog(qt_app, isolated_settings, monkeypatch):
    app_settings.set_mdrem_enabled(True)
    window = _window()
    monkeypatch.setattr(app_module, "resolve_port", lambda parent: "COM_TEST")
    opened: list[str] = []

    class _FakeRemote:
        def __init__(self, port, parent=None):
            opened.append(port)

        def exec(self):
            return 1

    monkeypatch.setattr(app_module, "RemoteDialog", _FakeRemote)

    window._open_remote_control()

    assert opened == ["COM_TEST"]


def test_no_port_no_remote_dialog(qt_app, isolated_settings, monkeypatch):
    app_settings.set_mdrem_enabled(True)
    window = _window()
    monkeypatch.setattr(app_module, "resolve_port", lambda parent: None)
    monkeypatch.setattr(
        app_module, "RemoteDialog", lambda *a, **k: pytest.fail("must not open without a resolved port")
    )

    window._open_remote_control()


# --- and the rip alongside it -----------------------------------------------
#
# Source > "Rip Audio CD..." used to be Recording > "Record CD to
# MiniDisc...", and ripped and recorded in one unbroken run. Splitting the
# two was an explicit request, so what is left to test here is mostly what
# must *not* happen any more: no port is resolved, and no recording dialog
# is opened, however the rip ends.


class _FakeRip(QObject):
    """A CdRipDialog that has already finished. Real Signals, since
    _drive_recording_bar() connects to every one of them."""

    running_changed = Signal(bool)
    overall_progress_changed = Signal(float, str)
    track_progress_changed = Signal(float, str)
    visibility_changed = Signal(bool)

    result_metadata = None
    result_folder = None
    result_paths = ["01.flac"]
    code = None  # set per subclass/instance

    def __init__(self, *args, **kwargs):
        super().__init__()

    def exec(self):
        return self.code


def _rip_returning(monkeypatch, code, *, metadata=None, folder=None):
    class _Rip(_FakeRip):
        pass

    _Rip.code = code
    _Rip.result_metadata = metadata
    _Rip.result_folder = folder
    monkeypatch.setattr(app_module, "CdRipDialog", _Rip)


def _answer_question(monkeypatch, answer):
    monkeypatch.setattr(app_module.QMessageBox, "question", staticmethod(lambda *a, **k: answer))


def _never_records(monkeypatch):
    monkeypatch.setattr(
        app_module, "resolve_port", lambda *a, **k: pytest.fail("must not go looking for a port")
    )
    monkeypatch.setattr(
        app_module, "RecordDialog", lambda *a, **k: pytest.fail("must not start recording")
    )


def test_ripping_needs_no_adapter(qt_app, isolated_settings):
    """It ends at files in the audio folder, which no adapter is involved
    in producing -- so unlike the Recording menu's own entries this one is
    never hidden."""
    app_settings.set_mdrem_enabled(False)
    assert _window().rip_cd_action.isVisible()


def test_a_finished_rip_never_records_anything(qt_app, isolated_settings, monkeypatch):
    """The split itself: ripping used to hand its paths straight to
    RecordDialog. Recording is now a separate thing the user starts, from
    Recording > "Record from Rip/Download Folder to ...".""."""
    from PySide6.QtWidgets import QDialog

    app_settings.set_mdrem_enabled(True)
    _never_records(monkeypatch)
    _rip_returning(monkeypatch, QDialog.DialogCode.Accepted)
    _answer_question(monkeypatch, QMessageBox.StandardButton.No)
    monkeypatch.setattr(app_module.QMessageBox, "information", staticmethod(lambda *a, **k: None))

    _window()._rip_cd()


def test_a_cancelled_rip_says_nothing_at_all(qt_app, isolated_settings, monkeypatch):
    from PySide6.QtWidgets import QDialog

    app_settings.set_mdrem_enabled(True)
    _never_records(monkeypatch)
    _rip_returning(monkeypatch, QDialog.DialogCode.Rejected)
    monkeypatch.setattr(
        app_module.QMessageBox,
        "question",
        staticmethod(lambda *a, **k: pytest.fail("nothing was ripped -- nothing to offer")),
    )
    monkeypatch.setattr(
        app_module.QMessageBox,
        "information",
        staticmethod(lambda *a, **k: pytest.fail("nothing was ripped -- nothing to report")),
    )

    _window()._rip_cd()


def test_saying_yes_brings_the_ripped_albums_metadata_into_the_project(qt_app, isolated_settings, monkeypatch):
    """A rip is usable on its own: the label can be designed now and the
    disc recorded later, or never. What the metadata adds over the ripped
    files themselves is the artwork found while identifying the disc,
    which their tags do not carry here."""
    from PySide6.QtWidgets import QDialog

    from mdtools.project import ProjectMetadata

    app_settings.set_mdrem_enabled(True)
    _never_records(monkeypatch)
    identified = ProjectMetadata(album="Unleashed", artist="Skillet", cover_art=b"art")
    _rip_returning(monkeypatch, QDialog.DialogCode.Accepted, metadata=identified)
    _answer_question(monkeypatch, QMessageBox.StandardButton.Yes)

    window = _window()
    window._rip_cd()

    assert window.project.metadata is identified


def test_saying_no_leaves_the_project_exactly_as_it_was(qt_app, isolated_settings, monkeypatch):
    """Declining costs nothing but the typing -- the ripped files stay
    where they are either way."""
    from PySide6.QtWidgets import QDialog

    from mdtools.project import ProjectMetadata

    app_settings.set_mdrem_enabled(True)
    _never_records(monkeypatch)
    _rip_returning(
        monkeypatch,
        QDialog.DialogCode.Accepted,
        metadata=ProjectMetadata(album="Unleashed", artist="Skillet"),
    )
    _answer_question(monkeypatch, QMessageBox.StandardButton.No)

    window = _window()
    original = window.project.metadata

    window._rip_cd()

    assert window.project.metadata is original


def test_the_message_names_the_folder_and_the_entry_that_records_it(qt_app, isolated_settings, monkeypatch, tmp_path):
    """The one thing that replaced the hand-off: the user is told where
    the files are and which entry records them, since nothing does it for
    them any more."""
    from PySide6.QtWidgets import QDialog

    from mdtools.project import ProjectMetadata

    app_settings.set_mdrem_enabled(True)
    _never_records(monkeypatch)
    folder = tmp_path / "Skillet - Unleashed"
    _rip_returning(
        monkeypatch,
        QDialog.DialogCode.Accepted,
        metadata=ProjectMetadata(album="Unleashed"),
        folder=folder,
    )
    asked: list[str] = []
    monkeypatch.setattr(
        app_module.QMessageBox,
        "question",
        staticmethod(lambda *a, **k: asked.append(a[2]) or QMessageBox.StandardButton.No),
    )

    _window()._rip_cd()

    assert str(folder) in asked[0]
    assert "Record from Rip/Download Folder" in asked[0]


def test_a_rip_with_nothing_identified_still_says_where_the_files_went(qt_app, isolated_settings, monkeypatch, tmp_path):
    """No metadata to offer is not the same as nothing to say: the files
    exist, and where they are is the part the user needs."""
    from PySide6.QtWidgets import QDialog

    app_settings.set_mdrem_enabled(True)
    _never_records(monkeypatch)
    folder = tmp_path / "Track 01"
    _rip_returning(monkeypatch, QDialog.DialogCode.Accepted, metadata=None, folder=folder)
    monkeypatch.setattr(
        app_module.QMessageBox,
        "question",
        staticmethod(lambda *a, **k: pytest.fail("there is no metadata to offer")),
    )
    told: list[str] = []
    monkeypatch.setattr(
        app_module.QMessageBox, "information", staticmethod(lambda *a, **k: told.append(a[2]))
    )

    _window()._rip_cd()

    assert str(folder) in told[0]
