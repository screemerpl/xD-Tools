"""The title bar names the project file that is open.

With two xD-Tools windows open, the title bar (and so the taskbar button
and alt-tab) is the only thing that says which project each one is.
"""

from __future__ import annotations

from mdtools.app_window import MainWindow
from mdtools.io.project_io import save_project
from mdtools.project import ProjectMetadata

PLAIN = "xD-Tools - Retro Media Studio"


def _window() -> MainWindow:
    return MainWindow(show_startup_dialog=False)


def _saved(tmp_path, name: str) -> str:
    window = _window()
    window.project.metadata = ProjectMetadata(album="Some Album")
    path = tmp_path / f"{name}.mdproj"
    save_project(window.project, path)
    return str(path)


def test_an_unsaved_project_keeps_the_plain_app_title(qt_app):
    """There is no file name to show yet."""
    assert _window().windowTitle() == PLAIN


def test_opening_a_project_puts_its_file_name_in_the_title(qt_app, tmp_path):
    window = _window()

    assert window._open_project_path(_saved(tmp_path, "Kind of Blue"))

    assert window.windowTitle() == "Kind of Blue - xD-Tools"


def test_the_title_shows_the_file_name_not_the_album(qt_app, tmp_path):
    """A title bar answers "which file is this?" -- the album is already
    on screen in the metadata panel, and the file is what Save writes
    back to."""
    window = _window()
    window._open_project_path(_saved(tmp_path, "disc-two-final"))

    assert window.windowTitle() == "disc-two-final - xD-Tools"


def test_the_extension_is_left_off(qt_app, tmp_path):
    window = _window()
    window._open_project_path(_saved(tmp_path, "Blue Train"))

    assert ".mdproj" not in window.windowTitle()


def test_saving_as_renames_the_window(qt_app, tmp_path, monkeypatch):
    import mdtools.app_window as app_module

    window = _window()
    target = tmp_path / "Renamed.mdproj"
    monkeypatch.setattr(
        app_module.QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(target), ""))
    )

    assert window._save_project_as()

    assert window.windowTitle() == "Renamed - xD-Tools"


def test_starting_a_new_project_goes_back_to_the_plain_title(qt_app, tmp_path, monkeypatch):
    """The new project has never been saved, so it has no name to show --
    the previous project's must not stay in the title bar."""
    import mdtools.app_window as app_module

    window = _window()
    window._open_project_path(_saved(tmp_path, "Kind of Blue"))
    # File > New, with its template picker answered for it.
    monkeypatch.setattr(app_module.NewDesignDialog, "exec", lambda self: 1)

    assert window._new_design(prompt=False)

    assert window.windowTitle() == PLAIN
