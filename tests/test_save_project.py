from mdtools import app_window as app_window_module
from mdtools import recent_projects
from mdtools.app_window import MainWindow


def test_save_without_a_known_path_falls_back_to_save_as(qt_app, tmp_path, monkeypatch):
    target = tmp_path / "new.mdproj"
    monkeypatch.setattr(
        app_window_module.QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(target), ""))
    )
    saved_paths = []
    monkeypatch.setattr(app_window_module, "save_project", lambda project, path: saved_paths.append(path))

    win = MainWindow(show_startup_dialog=False)
    assert win.current_project_path is None

    win._save_project()

    assert saved_paths == [str(target)]
    assert win.current_project_path == str(target)


def test_save_with_a_known_path_does_not_prompt(qt_app, tmp_path, monkeypatch):
    def _fail_if_called(*a, **k):
        raise AssertionError("Save should not open a dialog once a path is known")

    monkeypatch.setattr(app_window_module.QFileDialog, "getSaveFileName", staticmethod(_fail_if_called))
    saved_paths = []
    monkeypatch.setattr(app_window_module, "save_project", lambda project, path: saved_paths.append(path))

    win = MainWindow(show_startup_dialog=False)
    win.current_project_path = str(tmp_path / "existing.mdproj")

    win._save_project()

    assert saved_paths == [win.current_project_path]


def test_saving_records_the_path_as_a_recent_project(qt_app, tmp_path, monkeypatch):
    target = tmp_path / "recorded.mdproj"
    target.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(app_window_module, "save_project", lambda project, path: None)

    win = MainWindow(show_startup_dialog=False)
    win.current_project_path = str(target)

    win._save_project()

    assert recent_projects.recent_projects() == [str(target)]


def test_save_as_records_the_new_path_as_a_recent_project(qt_app, tmp_path, monkeypatch):
    target = tmp_path / "saved_as.mdproj"
    target.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        app_window_module.QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(target), ""))
    )
    monkeypatch.setattr(app_window_module, "save_project", lambda project, path: None)

    win = MainWindow(show_startup_dialog=False)
    win._save_project_as()

    assert recent_projects.recent_projects() == [str(target)]
