from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QDialog

from mdtools import app_window as app_window_module
from mdtools.app_window import MainWindow
from mdtools.io.project_io import save_project
from mdtools.project import PAGE_COVER, PAGE_DISC, ProjectMetadata, Track


class _FakeMetadataDialog(QObject):
    """Stands in for the real MetadataDialog -- a real one's exec() would
    block forever under the offscreen platform with no user to click OK.
    Captures what it was shown, and reports it back as the result, same
    shape as the real dialog's own result_metadata. Accepts by default;
    a test wanting Cancel overrides `exec` on the class itself.

    A QObject with the real signals MainWindow's own
    _drive_recording_bar() connects to (#27) -- none of them ever fire
    here (nothing to upload), but the connection itself must not raise."""

    DialogCode = QDialog.DialogCode
    instances: list["_FakeMetadataDialog"] = []

    running_changed = Signal(bool)
    overall_progress_changed = Signal(float, str)
    visibility_changed = Signal(bool)

    def __init__(self, metadata, parent=None, medium="md", is_recording_busy=None):
        super().__init__()
        self.shown_metadata = metadata
        self.result_metadata = metadata
        _FakeMetadataDialog.instances.append(self)

    def exec(self):
        return QDialog.DialogCode.Accepted


def _import(tmp_path, monkeypatch, other_metadata: ProjectMetadata):
    """Builds the two projects and wires the file picker + the fake
    MetadataDialog (see _FakeMetadataDialog.instances for what it saw)."""
    _FakeMetadataDialog.instances = []
    monkeypatch.setattr(app_window_module, "MetadataDialog", _FakeMetadataDialog)

    win = MainWindow(show_startup_dialog=False)
    disc_scene = win.project.pages[PAGE_DISC]
    marker_item = disc_scene.add_text("KEEP ME")
    win.project.metadata = ProjectMetadata(album="Old Album", artist="Old Artist", year=1999)

    other_win = MainWindow(show_startup_dialog=False)
    other_win.project.metadata = other_metadata
    other_path = tmp_path / "other.mdproj"
    save_project(other_win.project, other_path)

    monkeypatch.setattr(
        app_window_module.QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(other_path), ""))
    )

    return win, marker_item


def test_import_metadata_opens_it_for_review_before_applying(qt_app, tmp_path, monkeypatch):
    """Reported directly: importing used to apply the other project's
    metadata silently, with no chance to look it over or correct it --
    the same review-then-apply shape every other MetadataDialog entry
    point (Edit Metadata, a CD rip hand-off, ...) already follows."""
    imported = ProjectMetadata(
        album="Imported Album", artist="Imported Artist", year=2024, tracks=[Track(title="Only Track")]
    )
    win, marker_item = _import(tmp_path, monkeypatch, imported)

    win._import_metadata()

    assert len(_FakeMetadataDialog.instances) == 1
    shown = _FakeMetadataDialog.instances[0].shown_metadata
    assert shown.album == "Imported Album"  # shown for review, not applied blindly

    assert win.project.metadata.album == "Imported Album"
    assert win.project.metadata.artist == "Imported Artist"
    assert win.project.metadata.year == 2024
    assert [t.title for t in win.project.metadata.tracks] == ["Only Track"]

    # the artwork/pages must be untouched by a metadata-only import
    assert marker_item in win.project.pages[PAGE_DISC].print_items()
    assert win.project.pages[PAGE_COVER] is not None


def test_cancelling_the_review_dialog_leaves_the_project_untouched(qt_app, tmp_path, monkeypatch):
    imported = ProjectMetadata(album="Imported Album", artist="Imported Artist", year=2024)
    win, _marker_item = _import(tmp_path, monkeypatch, imported)
    monkeypatch.setattr(_FakeMetadataDialog, "exec", lambda self: QDialog.DialogCode.Rejected)

    win._import_metadata()

    assert win.project.metadata.album == "Old Album"


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
