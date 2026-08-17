from mdtools import app_window as app_window_module
from mdtools.app_window import MainWindow
from mdtools.io.project_io import save_project
from mdtools.project import PAGE_COVER, PAGE_DISC, ProjectMetadata, Track


def test_import_metadata_replaces_metadata_but_not_pages(qt_app, tmp_path, monkeypatch):
    win = MainWindow(show_startup_dialog=False)

    # give the current project some distinctive artwork we expect to survive the import
    disc_scene = win.project.pages[PAGE_DISC]
    marker_item = disc_scene.add_text("KEEP ME")
    win.project.metadata = ProjectMetadata(album="Old Album", artist="Old Artist", year=1999)

    # a separate project file on disk with different metadata to import
    other_win = MainWindow(show_startup_dialog=False)
    other_win.project.metadata = ProjectMetadata(
        album="Imported Album", artist="Imported Artist", year=2024, tracks=[Track(title="Only Track")]
    )
    other_path = tmp_path / "other.mdproj"
    save_project(other_win.project, other_path)

    monkeypatch.setattr(
        app_window_module.QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(other_path), ""))
    )

    win._import_metadata()

    assert win.project.metadata.album == "Imported Album"
    assert win.project.metadata.artist == "Imported Artist"
    assert win.project.metadata.year == 2024
    assert [t.title for t in win.project.metadata.tracks] == ["Only Track"]

    # the artwork/pages must be untouched by a metadata-only import
    assert marker_item in win.project.pages[PAGE_DISC].print_items()
    assert win.project.pages[PAGE_COVER] is not None


def test_import_metadata_reports_unreadable_file(qt_app, tmp_path, monkeypatch):
    win = MainWindow(show_startup_dialog=False)
    original_metadata = win.project.metadata

    bad_path = tmp_path / "not_a_project.mdproj"
    bad_path.write_text("not json at all", encoding="utf-8")

    monkeypatch.setattr(
        app_window_module.QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(bad_path), ""))
    )
    errors = []
    monkeypatch.setattr(
        app_window_module.QMessageBox, "critical", staticmethod(lambda *a, **k: errors.append(a))
    )

    win._import_metadata()

    assert errors  # a critical dialog was shown instead of crashing
    assert win.project.metadata is original_metadata  # untouched on failure
