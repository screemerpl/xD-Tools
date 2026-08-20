import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from mdtools import app_settings, recent_projects


@pytest.fixture(scope="session")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def _isolated_recent_projects_settings(tmp_path, monkeypatch):
    """Every test that opens/saves a project (most that construct a
    MainWindow) would otherwise write into the real per-user settings.ini
    via recent_projects.add_recent_project() -- autouse so no individual
    test file has to remember to isolate this itself."""
    path = tmp_path / "_recent_projects_settings.ini"
    monkeypatch.setattr(recent_projects, "_settings", lambda: QSettings(str(path), QSettings.Format.IniFormat))


@pytest.fixture(autouse=True)
def _isolated_app_settings(tmp_path, monkeypatch):
    """mm_to_px()/px_to_mm() (used constantly, by nearly every test that
    builds a DesignScene) read app_settings.screen_dpi() on every call --
    without isolation, tests would read/write the real per-user
    settings.ini, and a non-default screen_dpi saved there by a real user
    would silently break geometry assertions that assume the 96 dpi
    default. Autouse for the same reason as the fixture above."""
    path = tmp_path / "_app_settings.ini"
    monkeypatch.setattr(app_settings, "_settings", lambda: QSettings(str(path), QSettings.Format.IniFormat))


@pytest.fixture(autouse=True)
def _auto_accept_cover_filter_dialog(monkeypatch):
    """CoverFilterDialog.exec() opens a real modal event loop -- under
    QT_QPA_PLATFORM=offscreen there is nothing to click a tile and answer
    it, so any test exercising an auto-layout path that shows it (the MD/CD
    disc label, the cassette shell labels) would otherwise hang forever.

    Autouse, defaulting to "No Filter" -- the artwork comes back byte-for-
    byte unchanged, which is the closest thing to how every one of these
    builders behaved before this dialog existed, so existing behavioural
    assertions about the resulting cover item keep meaning what they always
    meant. A test that cares about a specific filter choice (or about
    cancelling) can still override this with its own monkeypatch after this
    fixture has run."""
    from mdtools import cover_filters
    from mdtools.panels.cover_filter_dialog import CoverFilterDialog

    def _fake_exec(self):
        self.result_filter_id = cover_filters.FILTER_NONE
        return CoverFilterDialog.DialogCode.Accepted

    monkeypatch.setattr(CoverFilterDialog, "exec", _fake_exec)


@pytest.fixture(autouse=True)
def _no_real_artist_photo_lookups(monkeypatch):
    """app_window._auto_layout_cd_insert() calls metadata_lookup.
    find_artist_photo() -- a real network request -- for any CD project
    that has a case back. Without this, the test suite's reliability would
    depend on live internet access and Deezer's search API being up, the
    same class of problem the CoverFilterDialog fixture above solves for a
    modal dialog instead of a network call.

    Defaults to "no photo found" (None), which is a real, already-handled
    outcome (see place_artist_panel's own docstring) rather than a special
    test-only state -- so this changes no assertion's meaning, it just
    keeps the network out of it. A test that cares about an actual photo
    can override this with its own monkeypatch after this fixture runs."""
    monkeypatch.setattr("mdtools.app_window.find_artist_photo", lambda artist: None)
