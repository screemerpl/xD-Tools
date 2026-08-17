"""The menu bar after the Project menu became Recording.

Two changes, one reason: the menu held the album metadata editor -- the one
dialog used while designing a label -- alongside three entries that drive a
tape deck. The editor moved to the Tools panel, next to the layers it feeds,
and the menu is now about recording only.

Menus are addressed through the actions MainWindow keeps on itself, never by
walking the menu bar afterwards: re-fetching a QMenu through the widget tree
some time after construction hands back a wrapper whose C++ object has been
collected, which is a known-flaky pattern in this codebase.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QDialog

from mdtools import app_settings
from mdtools import app_window as app_module
from mdtools.app_window import MainWindow
from mdtools.panels.tool_panel import ToolPanel
from mdtools.project import ProjectMetadata, Track


@pytest.fixture
def isolated_settings(tmp_path, monkeypatch):
    from PySide6.QtCore import QSettings

    path = tmp_path / "settings.ini"
    monkeypatch.setattr(
        app_settings, "_settings", lambda: QSettings(str(path), QSettings.Format.IniFormat)
    )
    return path


def _window() -> MainWindow:
    return MainWindow(show_startup_dialog=False)


def _menu_titles(window: MainWindow) -> list[str]:
    return [action.text() for action in window.menuBar().actions()]


def _entries(window: MainWindow) -> list[str]:
    """Every action text in the Recording menu, separators dropped."""
    menu = window.record_action.parent()
    return [action.text() for action in menu.actions() if not action.isSeparator()]


# --- the menu itself --------------------------------------------------


def test_the_menu_is_called_recording(qt_app):
    titles = _menu_titles(_window())
    assert "&Recording" in titles
    assert "&Project" not in titles


def test_it_holds_the_three_sources_a_recording_can_come_from(qt_app):
    """A CD, a folder of files, and whatever foobar2000 already has open.
    All three end in the same recording."""
    entries = _entries(_window())
    assert "Record CD to MiniDisc..." in entries
    assert "Record Folder to MiniDisc..." in entries
    assert "Record to MiniDisc from foobar2000..." in entries


def test_the_metadata_editor_is_no_longer_in_it(qt_app):
    assert not any("Metadata" in entry for entry in _entries(_window()))


def test_erasing_stays_here_rather_than_going_homeless(qt_app):
    """Not recording, strictly -- but it is what you do to a disc you are
    about to record over, through the same deck and the same adapter, and a
    menu of its own for one entry would be worse."""
    assert "Erase MiniDisc..." in _entries(_window())


# --- the editor's new home --------------------------------------------


def test_the_tools_panel_has_a_metadata_button(qt_app):
    panel = ToolPanel()
    received: list = []
    panel.edit_metadata_requested.connect(lambda: received.append(True))

    buttons = [b for b in panel._toolbar_buttons if "Metadata..." in b.toolTip()]
    assert buttons, "no button offers the metadata editor"
    buttons[0].click()

    assert received == [True]


def test_the_button_opens_the_metadata_dialog(qt_app, monkeypatch):
    """End to end through MainWindow's own wiring, since a signal nobody
    connected would still pass the test above."""
    opened: list = []

    class _FakeDialog:
        DialogCode = QDialog.DialogCode
        result_metadata = None

        def __init__(self, metadata, parent=None):
            opened.append(metadata)

        def exec(self):
            return QDialog.DialogCode.Rejected

    monkeypatch.setattr(app_module, "MetadataDialog", _FakeDialog)
    window = _window()
    window.project.metadata = ProjectMetadata(album="Unleashed", tracks=[Track("Feel Invincible")])

    window.tool_panel.edit_metadata_requested.emit()

    assert opened and opened[0].album == "Unleashed"


def test_the_metadata_button_matches_the_others_in_size(qt_app):
    """Same rule as every other Tools panel button -- one wider than the
    rest was a real report."""
    panel = ToolPanel()
    expected = panel.metadata_button.size()
    assert all(button.size() == expected for button in panel._toolbar_buttons)


# --- the new entry ----------------------------------------------------


def test_recording_a_folder_follows_the_adapter_setting(qt_app, isolated_settings):
    """Loading a folder into foobar needs no adapter, but this entry does
    not stop at loading -- it goes on to record, which does."""
    app_settings.set_mdrem_enabled(False)
    window = _window()
    assert window.record_folder_action.isVisible() is False

    app_settings.set_mdrem_enabled(True)
    window._sync_mdrem_actions()

    assert window.record_folder_action.isVisible()


def test_recording_a_folder_refuses_outright_without_the_adapter(qt_app, isolated_settings, monkeypatch):
    app_settings.set_mdrem_enabled(False)
    monkeypatch.setattr(
        app_module, "resolve_port", lambda *a, **k: pytest.fail("must not go looking for a port")
    )
    monkeypatch.setattr(
        app_module, "FolderRecordDialog", lambda *a, **k: pytest.fail("must not open the folder dialog")
    )

    _window()._record_folder()


def test_the_port_is_resolved_before_the_playlist_is_replaced(qt_app, isolated_settings, monkeypatch):
    """Replacing somebody's playlist for a recording that then cannot
    happen destroys what they had open for nothing."""
    app_settings.set_mdrem_enabled(True)
    monkeypatch.setattr(app_module, "resolve_port", lambda *a, **k: None)
    monkeypatch.setattr(
        app_module, "FolderRecordDialog", lambda *a, **k: pytest.fail("must not open the folder dialog")
    )

    _window()._record_folder()


def test_a_cancelled_folder_dialog_never_reaches_the_recording_dialog(qt_app, isolated_settings, monkeypatch):
    app_settings.set_mdrem_enabled(True)
    monkeypatch.setattr(app_module, "resolve_port", lambda *a, **k: "COM7")

    class _Rejected:
        result_metadata = None

        def __init__(self, *args, **kwargs):
            pass

        def exec(self):
            return QDialog.DialogCode.Rejected

    monkeypatch.setattr(app_module, "FolderRecordDialog", _Rejected)
    monkeypatch.setattr(
        app_module, "RecordDialog", lambda *a, **k: pytest.fail("must not start recording")
    )

    _window()._record_folder()


def test_the_folders_metadata_is_carried_into_the_recording(qt_app, isolated_settings, monkeypatch):
    """The one place a source hands metadata forward. A folder holds
    somebody else's files, which nothing rewrites, so an album name typed
    into that dialog reaches the disc no other way -- unlike a CD, whose
    titles are written into the files the rip created."""
    app_settings.set_mdrem_enabled(True)
    monkeypatch.setattr(app_module, "resolve_port", lambda *a, **k: "COM7")
    captured = ProjectMetadata(album="Unleashed", artist="Skillet", tracks=[Track("Feel Invincible")])

    class _Accepted:
        result_metadata = captured

        def __init__(self, *args, **kwargs):
            pass

        def exec(self):
            return QDialog.DialogCode.Accepted

    handed: list = []

    class _FakeRecord:
        result_metadata = None

        def __init__(self, port, url, parent=None, metadata=None):
            handed.append(metadata)

        def exec(self):
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(app_module, "FolderRecordDialog", _Accepted)
    monkeypatch.setattr(app_module, "RecordDialog", _FakeRecord)

    _window()._record_folder()

    assert handed == [captured]
