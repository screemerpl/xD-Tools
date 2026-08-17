from mdtools import app_window as app_window_module
from mdtools import recent_projects
from mdtools.app_window import MainWindow
from mdtools.io.project_io import save_project
from mdtools.project import PAGE_DISC, ProjectMetadata


def _make_project_file(tmp_path, name: str, album: str):
    win = MainWindow(show_startup_dialog=False)
    win.project.metadata = ProjectMetadata(album=album, artist="Someone")
    path = tmp_path / name
    save_project(win.project, path)
    return str(path)


def test_opening_a_project_records_it_as_recent(qt_app, tmp_path):
    path = _make_project_file(tmp_path, "a.mdproj", "A")
    win = MainWindow(show_startup_dialog=False)

    assert win._open_project_path(path) is True
    assert recent_projects.recent_projects() == [path]
    assert win.project.metadata.album == "A"


def test_a_failed_open_does_not_record_the_path_as_recent(qt_app, tmp_path, monkeypatch):
    bad_path = tmp_path / "broken.mdproj"
    bad_path.write_text("not json", encoding="utf-8")
    monkeypatch.setattr(app_window_module.QMessageBox, "critical", lambda *a, **k: None)

    win = MainWindow(show_startup_dialog=False)
    assert win._open_project_path(str(bad_path)) is False
    assert recent_projects.recent_projects() == []


def test_open_recent_menu_is_empty_placeholder_with_no_history(qt_app):
    win = MainWindow(show_startup_dialog=False)
    win._populate_open_recent_menu()

    actions = win.open_recent_menu.actions()
    assert len(actions) == 1
    assert not actions[0].isEnabled()


def test_open_recent_menu_lists_paths_most_recent_first(qt_app, tmp_path):
    path_a = _make_project_file(tmp_path, "a.mdproj", "A")
    path_b = _make_project_file(tmp_path, "b.mdproj", "B")
    recent_projects.add_recent_project(path_a)
    recent_projects.add_recent_project(path_b)

    win = MainWindow(show_startup_dialog=False)
    win._populate_open_recent_menu()

    actions = win.open_recent_menu.actions()
    assert [a.toolTip() for a in actions] == [path_b, path_a]


def test_triggering_a_recent_project_action_opens_it(qt_app, tmp_path):
    path = _make_project_file(tmp_path, "a.mdproj", "Triggered Album")
    recent_projects.add_recent_project(path)

    win = MainWindow(show_startup_dialog=False)
    win._populate_open_recent_menu()
    win.open_recent_menu.actions()[0].trigger()

    assert win.project.metadata.album == "Triggered Album"
    assert win.current_project_path == path
