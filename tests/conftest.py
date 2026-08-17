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
