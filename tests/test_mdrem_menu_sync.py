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


# --- and the CD entry alongside it ------------------------------------------


def _answer_record_choice(monkeypatch, label: str):
    """Drives _offer_recording_the_rip()'s own QMessageBox by button text
    ("Record Now" / "Just Metadata" / "Cancel") -- confirmed directly that
    QMessageBox.buttons() does *not* preserve addButton()'s own insertion
    order (it reorders by role for platform convention: AcceptRole,
    RejectRole, then ActionRole here), so indexing into it positionally is
    not reliable."""

    def fake_exec(self):
        self._clicked = next(b for b in self.buttons() if b.text() == label)
        return 0

    def fake_clicked_button(self):
        return self._clicked

    monkeypatch.setattr(app_module.QMessageBox, "exec", fake_exec)
    monkeypatch.setattr(app_module.QMessageBox, "clickedButton", fake_clicked_button)


def test_the_cd_entry_no_longer_needs_the_adapter(qt_app, isolated_settings):
    """Ripping needs no adapter at all any more -- "Record Now" is only one
    of two things a finished rip can be used for, "Just Metadata" needs
    nothing beyond the CD drive itself (see _offer_recording_the_rip)."""
    app_settings.set_mdrem_enabled(False)
    assert _window().record_cd_action.isVisible()


def test_choosing_record_now_without_the_adapter_refuses_to_record(qt_app, isolated_settings, monkeypatch):
    """Ripping itself still needs no adapter -- only the "Record Now"
    choice does, and only once it is actually made."""
    from PySide6.QtWidgets import QDialog

    app_settings.set_mdrem_enabled(False)

    class _AcceptedRip(QObject):
        running_changed = Signal(bool)
        overall_progress_changed = Signal(float, str)
        track_progress_changed = Signal(float, str)
        visibility_changed = Signal(bool)

        result_metadata = None
        result_paths = ["01.flac"]

        def __init__(self, *args, **kwargs):
            super().__init__()

        def exec(self):
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(app_module, "CdRipDialog", _AcceptedRip)
    monkeypatch.setattr(
        app_module, "resolve_port", lambda *a, **k: pytest.fail("must not go looking for a port")
    )
    monkeypatch.setattr(
        app_module, "RecordDialog", lambda *a, **k: pytest.fail("must not start recording")
    )
    _answer_record_choice(monkeypatch, "Record Now")

    _window()._record_cd()  # must not raise -- _resolve_recording_port() itself declines


def test_the_port_is_resolved_only_after_record_now_is_chosen(qt_app, isolated_settings, monkeypatch):
    """The rip happens regardless -- the adapter is only checked once the
    user has actually asked to record, not before ripping the way it used
    to be (ripping needs no adapter at all)."""
    from PySide6.QtWidgets import QDialog

    app_settings.set_mdrem_enabled(True)
    resolved: list = []
    monkeypatch.setattr(app_module, "resolve_port", lambda *a, **k: resolved.append(1) or "COM7")

    class _AcceptedRip(QObject):
        running_changed = Signal(bool)
        overall_progress_changed = Signal(float, str)
        track_progress_changed = Signal(float, str)
        visibility_changed = Signal(bool)

        result_metadata = None
        result_paths = ["01.flac"]

        def __init__(self, *args, **kwargs):
            super().__init__()

        def exec(self):
            return QDialog.DialogCode.Accepted

    class _FakeRecord(QObject):
        result_metadata = None

        running_changed = Signal(bool)
        overall_progress_changed = Signal(float, str)
        track_progress_changed = Signal(float, str)
        visibility_changed = Signal(bool)

        def __init__(self, *args, **kwargs):
            super().__init__()

        def exec(self):
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(app_module, "CdRipDialog", _AcceptedRip)
    monkeypatch.setattr(app_module, "RecordDialog", _FakeRecord)
    _answer_record_choice(monkeypatch, "Record Now")

    _window()._record_cd()

    assert resolved == [1]


def test_a_cancelled_rip_never_reaches_the_recording_dialog(qt_app, isolated_settings, monkeypatch):
    from PySide6.QtWidgets import QDialog

    app_settings.set_mdrem_enabled(True)
    monkeypatch.setattr(
        app_module, "resolve_port", lambda *a, **k: pytest.fail("must not go looking for a port")
    )

    class _RejectedRip(QObject):
        running_changed = Signal(bool)
        overall_progress_changed = Signal(float, str)
        track_progress_changed = Signal(float, str)
        visibility_changed = Signal(bool)

        def __init__(self, *args, **kwargs):
            super().__init__()

        def exec(self):
            return QDialog.DialogCode.Rejected

    monkeypatch.setattr(app_module, "CdRipDialog", _RejectedRip)
    monkeypatch.setattr(
        app_module, "RecordDialog", lambda *a, **k: pytest.fail("must not start recording")
    )

    _window()._record_cd()


def test_choosing_record_now_hands_straight_over_to_the_recording_dialog(qt_app, isolated_settings, monkeypatch):
    """The whole point of the feature: once the playlist holds the CD, the
    existing record flow takes over unchanged and unaware a CD was ever
    involved."""
    from PySide6.QtWidgets import QDialog

    app_settings.set_mdrem_enabled(True)
    monkeypatch.setattr(app_module, "resolve_port", lambda *a, **k: "COM7")

    from mdtools.project import ProjectMetadata

    identified = ProjectMetadata(album="Unleashed", artist="Skillet", cover_art=b"art")

    class _AcceptedRip(QObject):
        running_changed = Signal(bool)
        overall_progress_changed = Signal(float, str)
        track_progress_changed = Signal(float, str)
        visibility_changed = Signal(bool)

        result_metadata = identified
        result_paths = ["01.flac"]

        def __init__(self, *args, **kwargs):
            super().__init__()

        def exec(self):
            return QDialog.DialogCode.Accepted

    recorded: list = []

    class _FakeRecord(QObject):
        result_metadata = None

        running_changed = Signal(bool)
        overall_progress_changed = Signal(float, str)
        track_progress_changed = Signal(float, str)
        visibility_changed = Signal(bool)

        def __init__(self, port, paths, parent=None, metadata=None):
            super().__init__()
            recorded.append((port, paths, metadata))

        def exec(self):
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(app_module, "CdRipDialog", _AcceptedRip)
    monkeypatch.setattr(app_module, "RecordDialog", _FakeRecord)
    _answer_record_choice(monkeypatch, "Record Now")

    window = _window()
    window._record_cd()

    # The rip's own metadata goes with it. Its titles are the ones it wrote
    # into the files, so they say what the files say; what it adds is the
    # artwork found while identifying the disc, which a tag does not carry.
    assert recorded == [("COM7", ["01.flac"], identified)]
    # "Record Now" does not also apply the metadata to the open project
    # directly -- RecordDialog's own hand-off (_run_record_dialog) is what
    # does that, same as every other recording source.
    assert window.project.metadata.album != "Unleashed"


def test_choosing_just_metadata_applies_it_without_recording(qt_app, isolated_settings, monkeypatch):
    """Explicit request: a rip should be usable on its own, ending with
    nothing more than the album's metadata landing in the project, for
    whoever wants the label right without recording right now."""
    from PySide6.QtWidgets import QDialog

    app_settings.set_mdrem_enabled(True)
    monkeypatch.setattr(
        app_module, "resolve_port", lambda *a, **k: pytest.fail("must not go looking for a port")
    )
    monkeypatch.setattr(
        app_module, "RecordDialog", lambda *a, **k: pytest.fail("must not start recording")
    )

    from mdtools.project import ProjectMetadata

    identified = ProjectMetadata(album="Unleashed", artist="Skillet", cover_art=b"art")

    class _AcceptedRip(QObject):
        running_changed = Signal(bool)
        overall_progress_changed = Signal(float, str)
        track_progress_changed = Signal(float, str)
        visibility_changed = Signal(bool)

        result_metadata = identified
        result_paths = ["01.flac"]

        def __init__(self, *args, **kwargs):
            super().__init__()

        def exec(self):
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(app_module, "CdRipDialog", _AcceptedRip)
    _answer_record_choice(monkeypatch, "Just Metadata")

    window = _window()
    window._record_cd()

    assert window.project.metadata is identified


def test_cancelling_the_record_choice_leaves_the_project_untouched(qt_app, isolated_settings, monkeypatch):
    from PySide6.QtWidgets import QDialog

    app_settings.set_mdrem_enabled(True)
    monkeypatch.setattr(
        app_module, "resolve_port", lambda *a, **k: pytest.fail("must not go looking for a port")
    )
    monkeypatch.setattr(
        app_module, "RecordDialog", lambda *a, **k: pytest.fail("must not start recording")
    )

    from mdtools.project import ProjectMetadata

    class _AcceptedRip(QObject):
        running_changed = Signal(bool)
        overall_progress_changed = Signal(float, str)
        track_progress_changed = Signal(float, str)
        visibility_changed = Signal(bool)

        result_metadata = ProjectMetadata(album="Unleashed", artist="Skillet")
        result_paths = ["01.flac"]

        def __init__(self, *args, **kwargs):
            super().__init__()

        def exec(self):
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(app_module, "CdRipDialog", _AcceptedRip)
    _answer_record_choice(monkeypatch, "Cancel")

    window = _window()
    original = window.project.metadata

    window._record_cd()

    assert window.project.metadata is original
