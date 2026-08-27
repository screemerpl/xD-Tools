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
from PySide6.QtCore import QObject, Signal
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
    menu = window.record_folder_action.parent()
    return [action.text() for action in menu.actions() if not action.isSeparator()]


def _source_entries(window: MainWindow) -> list[str]:
    """The same for the Source menu -- where audio comes from, as against
    the Recording menu, where it goes."""
    menu = window.rip_cd_action.parent()
    return [action.text() for action in menu.actions() if not action.isSeparator()]


# --- the menu itself --------------------------------------------------


def test_the_menu_is_called_recording(qt_app):
    titles = _menu_titles(_window())
    assert "&Recording" in titles
    assert "&Project" not in titles


def test_it_holds_the_two_folders_a_recording_can_come_from(qt_app):
    """A folder the user browses to, and the one rips and downloads land
    in. Both are files already on disk -- getting them there is the Source
    menu's job now, not this one's."""
    entries = _entries(_window())
    assert "Record Folder to MiniDisc..." in entries
    assert any(entry.startswith("Record from Rip/Download Folder") for entry in entries)


def test_ripping_a_cd_is_no_longer_a_recording_entry(qt_app):
    """It used to be "Record CD to MiniDisc...", which ripped *and*
    recorded in one run -- so the rip could only be had by starting a
    recording. Splitting them was an explicit request; the rip is a
    Source now and ends at the files."""
    entries = _entries(_window())
    assert not any("CD" in entry for entry in entries), entries
    assert "Rip Audio CD..." in _source_entries(_window())


def test_the_metadata_editor_is_no_longer_in_it(qt_app):
    assert not any("Metadata" in entry for entry in _entries(_window()))


def test_erasing_moved_to_a_button_on_the_minidisc_record_dialog(qt_app):
    """No longer a standalone menu entry reachable independent of any open
    project -- see test_record_dialog.py's own erase_btn tests. Erasing the
    wrong disc is most likely to come up right before recording onto it."""
    assert "Erase MiniDisc..." not in _entries(_window())


def test_the_source_menu_holds_everything_audio_arrives_through(qt_app):
    """A CD, a bot download, and the tidying of what they leave behind --
    all three end with files in one folder, and none of them touch a deck.
    The sort entry is named for that folder, not for Telegram: rips land
    there too."""
    entries = _source_entries(_window())
    assert "Rip Audio CD..." in entries
    assert "Download Album from Telegram Bot..." in entries
    assert "Sort Rip/Download Folder into Albums..." in entries


def test_the_source_menu_comes_before_recording(qt_app):
    """Left to right, in the order the work happens."""
    titles = _menu_titles(_window())
    assert titles.index("&Source") < titles.index("&Recording")


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

    class _FakeDialog(QObject):
        DialogCode = QDialog.DialogCode
        result_metadata = None

        running_changed = Signal(bool)
        overall_progress_changed = Signal(float, str)
        visibility_changed = Signal(bool)

        def __init__(self, metadata, parent=None, medium="md", is_recording_busy=None):
            super().__init__()
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
        result_paths = ["01.flac"]

        def __init__(self, *args, **kwargs):
            pass

        def exec(self):
            return QDialog.DialogCode.Accepted

    handed: list = []

    class _FakeRecord(QObject):
        result_metadata = None

        running_changed = Signal(bool)
        overall_progress_changed = Signal(float, str)
        track_progress_changed = Signal(float, str)
        visibility_changed = Signal(bool)

        def __init__(self, port, paths, parent=None, metadata=None):
            super().__init__()
            handed.append(metadata)

        def exec(self):
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(app_module, "FolderRecordDialog", _Accepted)
    monkeypatch.setattr(app_module, "RecordDialog", _FakeRecord)

    _window()._record_folder()

    assert handed == [captured]


# --- _record_folder_dialog(initial_folder=...) -- the Telegram bot hand-off --


def test_a_given_initial_folder_is_preseeded_via_set_folder(qt_app, isolated_settings, monkeypatch, tmp_path):
    """The Telegram bot chat dialog already knows the folder it downloaded
    into -- it must not be asked to browse for something it already has."""
    app_settings.set_mdrem_enabled(True)
    monkeypatch.setattr(app_module, "resolve_port", lambda *a, **k: "COM7")
    seeded: list = []

    class _FakeFolderDialog:
        result_metadata = None
        result_paths = ["01.flac"]

        def __init__(self, *args, **kwargs):
            pass

        def set_folder(self, folder):
            seeded.append(folder)

        def exec(self):
            return QDialog.DialogCode.Accepted

    class _FakeRecord(QObject):
        result_metadata = None

        running_changed = Signal(bool)
        overall_progress_changed = Signal(float, str)
        track_progress_changed = Signal(float, str)
        visibility_changed = Signal(bool)

        def __init__(self, port, paths, parent=None, metadata=None):
            super().__init__()

        def exec(self):
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(app_module, "FolderRecordDialog", _FakeFolderDialog)
    monkeypatch.setattr(app_module, "RecordDialog", _FakeRecord)

    _window()._record_folder_dialog(tmp_path)

    assert seeded == [tmp_path]


def test_the_plain_menu_entry_has_nothing_to_preseed(qt_app, isolated_settings, monkeypatch):
    """_record_folder() -- the menu path -- must behave exactly as before
    this refactor: no folder known in advance, so set_folder() is never
    called at all."""
    app_settings.set_mdrem_enabled(True)
    monkeypatch.setattr(app_module, "resolve_port", lambda *a, **k: "COM7")

    class _FakeFolderDialog:
        result_metadata = None

        def __init__(self, *args, **kwargs):
            pass

        def set_folder(self, folder):
            pytest.fail("the plain menu entry has nothing to pre-seed")

        def exec(self):
            return QDialog.DialogCode.Rejected

    monkeypatch.setattr(app_module, "FolderRecordDialog", _FakeFolderDialog)

    _window()._record_folder()
