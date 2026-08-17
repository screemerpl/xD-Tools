"""Where file dialogs start.

Every one of these used to pass an empty directory, which leaves Qt on the
process's working directory -- for a frozen build, the install folder. The
point of these tests is that no dialog goes back to doing that.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QStandardPaths
from PySide6.QtWidgets import QFileDialog

from mdtools import app_window as app_module
from mdtools import user_paths
from mdtools.app_window import MainWindow
from mdtools.project import ProjectMetadata, Track


@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    """QStandardPaths' own test mode redirects every standard location into
    a temp folder, so these never touch the real Documents."""
    QStandardPaths.setTestModeEnabled(True)
    documents = tmp_path / "Documents"
    pictures = tmp_path / "Pictures"
    music = tmp_path / "Music"
    documents.mkdir()
    pictures.mkdir()
    music.mkdir()
    monkeypatch.setattr(user_paths, "documents_dir", lambda: documents)
    monkeypatch.setattr(user_paths, "pictures_dir", lambda: pictures)
    monkeypatch.setattr(user_paths, "music_dir", lambda: music)
    yield tmp_path
    QStandardPaths.setTestModeEnabled(False)


# --- the folders themselves -------------------------------------------


def test_projects_live_in_a_named_subfolder_of_documents(fake_home):
    assert user_paths.projects_dir() == fake_home / "Documents" / "MiniDiscProjects"


def test_the_projects_folder_is_created_on_demand(fake_home):
    """A dialog pointed at a directory that does not exist falls back
    somewhere arbitrary, which is the whole thing being fixed."""
    assert not (fake_home / "Documents" / "MiniDiscProjects").exists()

    created = user_paths.projects_dir()

    assert created.is_dir()


def test_a_read_only_documents_falls_back_rather_than_raising(fake_home, monkeypatch):
    def refuse(*args, **kwargs):
        raise OSError("read-only")

    monkeypatch.setattr(Path, "mkdir", refuse)

    assert user_paths.projects_dir() == fake_home / "Documents"


def test_images_come_from_pictures(fake_home):
    assert user_paths.image_start_path() == str(fake_home / "Pictures")


def test_an_album_folder_is_looked_for_in_music(fake_home):
    assert user_paths.music_start_path() == str(fake_home / "Music")


def test_an_unset_standard_location_still_beats_the_working_directory(monkeypatch):
    """QStandardPaths returns "" when a location is not configured at all."""
    monkeypatch.setattr(QStandardPaths, "writableLocation", staticmethod(lambda location: ""))

    assert user_paths.documents_dir() == Path.home() / "Documents"


# --- which path a dialog opens on -------------------------------------


def test_an_unsaved_project_starts_in_the_projects_folder(fake_home):
    assert user_paths.project_start_path(None) == str(user_paths.projects_dir())


def test_a_saved_project_reopens_where_it_actually_lives(fake_home, tmp_path):
    """Moving a project out of the default folder should not keep sending
    its owner back to the default folder."""
    elsewhere = str(tmp_path / "elsewhere" / "thing.mdproj")
    assert user_paths.project_start_path(elsewhere) == elsewhere


def test_exports_land_beside_the_project_they_came_from(fake_home, tmp_path):
    project = str(tmp_path / "albums" / "thing.mdproj")
    assert user_paths.export_start_path(project) == str(tmp_path / "albums")


def test_exports_from_an_unsaved_project_fall_back_to_the_projects_folder(fake_home):
    assert user_paths.export_start_path(None) == str(user_paths.projects_dir())


# --- the suggested filename -------------------------------------------


def test_a_first_save_is_proposed_as_artist_album_and_year(fake_home):
    """The same string the deck is told, from the same function, so the
    file and the disc cannot end up named differently."""
    suggested = user_paths.project_start_path(None, "Skillet - Unleashed (2016)")

    assert suggested == str(user_paths.projects_dir() / "Skillet - Unleashed (2016).mdproj")


def test_characters_a_filesystem_refuses_are_replaced_not_dropped(fake_home):
    suggested = Path(user_paths.project_start_path(None, "AC/DC - Back?"))

    assert "/" not in suggested.name
    assert "?" not in suggested.name
    assert suggested.name.startswith("AC_DC - Back")


def test_a_trailing_dot_does_not_survive_into_the_name(fake_home):
    """Windows silently drops one, which would mean proposing a filename
    different from the one that gets created."""
    suggested = Path(user_paths.project_start_path(None, "Troublegum."))
    assert suggested.name == "Troublegum.mdproj"


def test_a_project_with_no_metadata_just_opens_the_folder(fake_home):
    """Nothing filled in means nothing to suggest -- proposing
    ".mdproj" would be worse than proposing nothing."""
    assert user_paths.project_start_path(None, "") == str(user_paths.projects_dir())


def test_the_suggestion_is_not_stripped_to_ascii_the_way_the_disc_title_is(fake_home):
    """The deck can only show ASCII; a filesystem has no such limit, so
    mangling a Polish title on disk would be carrying a hardware
    restriction somewhere it does not apply."""
    suggested = Path(user_paths.project_start_path(None, "Kult - Ostateczny Krach Systemu Korporacji"))
    assert "Ostateczny" in suggested.name

    accented = Path(user_paths.project_start_path(None, "Zażółć gęślą jaźń"))
    assert accented.name == "Zażółć gęślą jaźń.mdproj"


# --- through the real dialogs -----------------------------------------


def _capture(monkeypatch, target, attr):
    """Replaces a QFileDialog static method and records the directory it
    was opened on."""
    seen: list[str] = []

    def fake(parent, caption, directory="", filter="", *args, **kwargs):
        seen.append(directory)
        return ("", "") if attr != "getExistingDirectory" else ""

    monkeypatch.setattr(target, attr, staticmethod(fake))
    return seen


def test_save_as_proposes_the_album_in_the_projects_folder(qt_app, fake_home, monkeypatch):
    seen = _capture(monkeypatch, QFileDialog, "getSaveFileName")
    window = MainWindow(show_startup_dialog=False)
    window.project.metadata = ProjectMetadata(
        album="Unleashed", artist="Skillet", year=2016, tracks=[Track("Feel Invincible")]
    )

    window._save_project_as()

    assert seen == [str(user_paths.projects_dir() / "Skillet - Unleashed (2016).mdproj")]


def test_open_project_starts_in_the_projects_folder(qt_app, fake_home, monkeypatch):
    seen = _capture(monkeypatch, QFileDialog, "getOpenFileName")
    MainWindow(show_startup_dialog=False)._open_project()

    assert seen == [str(user_paths.projects_dir())]


def test_add_image_starts_in_pictures(qt_app, fake_home, monkeypatch):
    seen = _capture(monkeypatch, QFileDialog, "getOpenFileName")
    MainWindow(show_startup_dialog=False)._add_image()

    assert seen == [str(fake_home / "Pictures")]


def test_exports_start_beside_a_saved_project(qt_app, fake_home, monkeypatch, tmp_path):
    seen = _capture(monkeypatch, QFileDialog, "getSaveFileName")
    window = MainWindow(show_startup_dialog=False)
    window.current_project_path = str(tmp_path / "here" / "thing.mdproj")

    window._export_svg()

    assert seen == [str(tmp_path / "here")]


def test_the_album_folder_picker_starts_in_music(qt_app, fake_home, monkeypatch):
    """Record Folder's own picker. It is not reachable from MainWindow the
    way the others are -- it lives on its dialog -- so the blanket guard
    below cannot see it."""
    from mdtools.panels.folder_record_dialog import FolderRecordDialog

    seen = _capture(monkeypatch, QFileDialog, "getExistingDirectory")
    FolderRecordDialog()._browse()

    assert seen == [str(fake_home / "Music")]


def test_no_dialog_is_left_starting_on_the_working_directory(qt_app, fake_home, monkeypatch):
    """A blanket guard: an empty directory argument is exactly the bug this
    module exists to fix, so no entry point may reintroduce one."""
    saves = _capture(monkeypatch, QFileDialog, "getSaveFileName")
    opens = _capture(monkeypatch, QFileDialog, "getOpenFileName")
    window = MainWindow(show_startup_dialog=False)

    window._open_project()
    window._import_metadata()
    window._add_image()
    window._save_project_as()
    window._export_svg()
    window._export_png()

    assert all(directory for directory in saves + opens), (saves, opens)
