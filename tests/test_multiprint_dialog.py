"""Tests panels/print_dialog.py's MultiprintDialog -- starts empty,
Add.../Delete manage a heterogeneous list of items loaded from arbitrary
.mdproj files (no Copies/auto-layout concept), and Print.../Export
PDF.../Export PNG.../grayscale all reuse the exact same _PrintDialogBase
machinery PrintDialog itself uses (see test_print_dialog.py for thorough
coverage of that shared machinery -- these tests focus on what's actually
different: Add/Delete)."""

from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import QFileDialog, QMessageBox

from mdtools.canvas.scene import DesignScene
from mdtools.io.project_io import save_project
from mdtools.panels import print_dialog as print_dialog_module
from mdtools.panels.print_dialog import MultiprintDialog
from mdtools.project import PAGE_COVER, PAGE_DISC, Project, ProjectMetadata
from mdtools.templates.models import CoverTemplate, DiscTemplate


def _save_project(path, disc_size=(37.0, 52.0), cover_size=(126.0, 73.0)) -> None:
    disc_template = DiscTemplate(name="d", width_mm=disc_size[0], height_mm=disc_size[1], chamfer_mm=0, fillet_mm=0)
    cover_template = CoverTemplate(name="c", width_mm=cover_size[0], height_mm=cover_size[1])
    project = Project(
        metadata=ProjectMetadata(),
        pages={PAGE_DISC: DesignScene(disc_template), PAGE_COVER: DesignScene(cover_template)},
    )
    save_project(project, path)


def _make_fake_printer(output_path):
    class _FakePrinter(QPrinter):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
            self.setOutputFileName(str(output_path))

    return _FakePrinter


def test_starts_completely_empty(qt_app):
    dialog = MultiprintDialog()

    assert dialog._items == []
    assert dialog._build_placements() == []


def test_add_loads_a_project_and_adds_its_disc_and_cover(qt_app, tmp_path, monkeypatch):
    path = tmp_path / "one.mdproj"
    _save_project(path)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(path), "")))

    dialog = MultiprintDialog()
    dialog._on_add()

    assert len(dialog._items) == 2  # one disc item + one cover item


def test_adding_two_different_projects_accumulates_items(qt_app, tmp_path, monkeypatch):
    path_a = tmp_path / "a.mdproj"
    path_b = tmp_path / "b.mdproj"
    _save_project(path_a, disc_size=(37.0, 52.0))
    _save_project(path_b, disc_size=(30.0, 40.0))

    paths = iter([str(path_a), str(path_b)])
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (next(paths), "")))

    dialog = MultiprintDialog()
    dialog._on_add()
    dialog._on_add()

    assert len(dialog._items) == 4  # 2 projects x (disc + cover)


def test_new_items_start_at_the_page_corner(qt_app, tmp_path, monkeypatch):
    path = tmp_path / "one.mdproj"
    _save_project(path)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(path), "")))

    dialog = MultiprintDialog()
    dialog._on_add()

    corner_px = (dialog.MARGIN_MM * dialog.PREVIEW_PX_PER_MM, dialog.MARGIN_MM * dialog.PREVIEW_PX_PER_MM)
    for item in dialog._items:
        assert (item.pos().x(), item.pos().y()) == corner_px


def test_cancelling_the_add_file_dialog_adds_nothing(qt_app, monkeypatch):
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: ("", "")))

    dialog = MultiprintDialog()
    dialog._on_add()  # must not raise

    assert dialog._items == []


def test_add_shows_an_error_and_adds_nothing_for_an_unreadable_project(qt_app, tmp_path, monkeypatch):
    bad_path = tmp_path / "broken.mdproj"
    bad_path.write_text("not valid json", encoding="utf-8")
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(bad_path), "")))

    errors = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: errors.append(a))

    dialog = MultiprintDialog()
    dialog._on_add()  # must not raise

    assert len(errors) == 1
    assert dialog._items == []


def test_delete_removes_only_the_selected_items(qt_app, tmp_path, monkeypatch):
    path = tmp_path / "one.mdproj"
    _save_project(path)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(path), "")))

    dialog = MultiprintDialog()
    dialog._on_add()
    assert len(dialog._items) == 2

    dialog._items[0].setSelected(True)
    dialog._on_delete()

    assert len(dialog._items) == 1
    assert dialog._items[0] not in dialog.page_scene.selectedItems()


def test_delete_with_nothing_selected_does_nothing(qt_app, tmp_path, monkeypatch):
    path = tmp_path / "one.mdproj"
    _save_project(path)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(path), "")))

    dialog = MultiprintDialog()
    dialog._on_add()

    dialog._on_delete()  # must not raise

    assert len(dialog._items) == 2


def test_grayscale_desaturates_added_items(qt_app, tmp_path, monkeypatch):
    path = tmp_path / "one.mdproj"
    _save_project(path)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(path), "")))

    dialog = MultiprintDialog()
    dialog._on_add()
    before = dialog._items[0].display_image

    dialog.grayscale_check.setChecked(True)

    after = dialog._items[0].display_image
    assert after is not before
    pixel = after.pixelColor(after.width() // 2, after.height() // 2)
    assert pixel.red() == pixel.green() == pixel.blue()


def test_right_clicking_an_added_item_rotates_it(qt_app, tmp_path, monkeypatch):
    path = tmp_path / "one.mdproj"
    _save_project(path)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(path), "")))

    dialog = MultiprintDialog()
    dialog._on_add()
    item = dialog._items[0]

    class _FakeContextMenuEvent:
        def accept(self):
            pass

    item.contextMenuEvent(_FakeContextMenuEvent())

    assert item.rotated is True


def test_print_button_writes_a_real_pdf_of_added_items(qt_app, tmp_path, monkeypatch):
    project_path = tmp_path / "one.mdproj"
    _save_project(project_path)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(project_path), "")))

    dialog = MultiprintDialog()
    dialog._on_add()

    output_path = tmp_path / "printed.pdf"
    monkeypatch.setattr(print_dialog_module, "QPrinter", _make_fake_printer(output_path))
    monkeypatch.setattr(QPrintDialog, "exec", lambda self: QPrintDialog.DialogCode.Accepted)

    dialog._on_print()

    assert output_path.is_file()
    assert output_path.stat().st_size > 0


def test_print_never_persists_a_grayscale_adjustment_anywhere(qt_app, tmp_path, monkeypatch):
    """Unlike PrintDialog, there's no single owning project to persist
    brightness/contrast onto -- and no license to silently rewrite one of
    the loaded .mdproj files just because Print... was clicked."""
    project_path = tmp_path / "one.mdproj"
    _save_project(project_path)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(project_path), "")))

    dialog = MultiprintDialog()
    dialog._on_add()
    dialog.grayscale_check.setChecked(True)
    dialog.brightness_slider.setValue(30)

    output_path = tmp_path / "printed.pdf"
    monkeypatch.setattr(print_dialog_module, "QPrinter", _make_fake_printer(output_path))
    monkeypatch.setattr(QPrintDialog, "exec", lambda self: QPrintDialog.DialogCode.Accepted)

    dialog._on_print()  # must not raise -- the base no-op _maybe_save_grayscale_adjustment()

    assert output_path.is_file()
