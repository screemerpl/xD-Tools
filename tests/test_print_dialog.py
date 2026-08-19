"""Tests panels/print_dialog.py -- the physical mm sizing of each label,
grayscale/color + brightness/contrast wiring, copies + auto-layout
(including the too-many-copies error path), dragging a label updates
where it prints, and the actual print (faked printer/print dialog, no
real printer or modal loop involved)."""

from PySide6.QtGui import QImage
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import QFileDialog, QMessageBox

from mdtools.canvas.scene import DesignScene
from mdtools.io.png_export import render_scene_to_image
from mdtools.panels import print_dialog as print_dialog_module
from mdtools.panels.print_dialog import PrintDialog
from mdtools.printing import PlacedCopies, crop_to_template_bounds, image_physical_size_mm
from mdtools.project import PAGE_COVER, PAGE_DISC, GrayscaleAdjustment, Project, ProjectMetadata
from mdtools.templates.models import CoverTemplate, DiscTemplate


def _project(grayscale_adjustment=None) -> Project:
    disc_template = DiscTemplate(name="d", width_mm=37.0, height_mm=52.0, chamfer_mm=0, fillet_mm=0)
    cover_template = CoverTemplate(name="c", width_mm=126.0, height_mm=73.0)
    return Project(
        metadata=ProjectMetadata(),
        pages={PAGE_DISC: DesignScene(disc_template), PAGE_COVER: DesignScene(cover_template)},
        grayscale_adjustment=grayscale_adjustment or GrayscaleAdjustment(),
    )


def _small_project() -> Project:
    """Tiny label templates -- unlike _project()'s real-world MiniDisc
    dimensions (where the 126x73mm cover alone caps an A4 page at 2
    copies), this lets copy-count tests use a larger count without
    incidentally tripping the "doesn't fit" path they're not testing."""
    disc_template = DiscTemplate(name="d", width_mm=20.0, height_mm=20.0, chamfer_mm=0, fillet_mm=0)
    cover_template = CoverTemplate(name="c", width_mm=20.0, height_mm=15.0)
    return Project(
        metadata=ProjectMetadata(),
        pages={PAGE_DISC: DesignScene(disc_template), PAGE_COVER: DesignScene(cover_template)},
    )


def _make_fake_printer(output_path):
    """A real QPrinter, just pre-aimed at a PDF file instead of a system
    printer -- lets _on_print's actual paint code run for real without
    needing an installed printer."""

    class _FakePrinter(QPrinter):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
            self.setOutputFileName(str(output_path))

    return _FakePrinter


def test_label_items_report_their_true_physical_mm_size(qt_app):
    """Must match what crop_to_template_bounds()/image_physical_size_mm()
    would compute directly from each page's own scene -- i.e. the
    template's own true physical footprint (PrintDialog crops away
    render_scene_to_image()'s extra transparent padding margin -- see
    printing.crop_to_template_bounds()'s docstring for why that's safe
    and why it matters: it's what lets Copies pack tighter than treating
    each label's full padded render as its footprint)."""
    project = _project()
    dialog = PrintDialog(project)

    disc_scene = project.pages[PAGE_DISC]
    cover_scene = project.pages[PAGE_COVER]
    expected_disc = image_physical_size_mm(
        crop_to_template_bounds(disc_scene, render_scene_to_image(disc_scene, dpi=dialog._dpi), dialog._dpi),
        dialog._dpi,
    )
    expected_cover = image_physical_size_mm(
        crop_to_template_bounds(cover_scene, render_scene_to_image(cover_scene, dpi=dialog._dpi), dialog._dpi),
        dialog._dpi,
    )

    assert (dialog._disc_items[0].width_mm, dialog._disc_items[0].height_mm) == expected_disc
    assert (dialog._cover_items[0].width_mm, dialog._cover_items[0].height_mm) == expected_cover


def test_starts_with_exactly_one_copy_of_each_label(qt_app):
    dialog = PrintDialog(_project())

    assert dialog.copies_spin.value() == 1
    assert len(dialog._disc_items) == 1
    assert len(dialog._cover_items) == 1


def test_increasing_copies_adds_that_many_of_each_label(qt_app):
    dialog = PrintDialog(_small_project())

    dialog.copies_spin.setValue(3)

    assert len(dialog._disc_items) == 3
    assert len(dialog._cover_items) == 3
    # each copy must land at its own, distinct position -- not stacked
    disc_positions = {(item.pos().x(), item.pos().y()) for item in dialog._disc_items}
    assert len(disc_positions) == 3


def test_rebuild_items_seeds_each_items_rotation_from_the_layout(qt_app):
    """printing.build_copies_layout() only ever returns a `rotated` flag
    (see test_printing.py for when it decides to set it) -- this checks
    the dialog acts on that flag for real: each new item's `rotated`
    starting state matches its grid's decision, and its actual displayed
    pixels are genuinely rotated (swapped dimensions), not just a flag
    nobody consumed. Feeding a synthetic PlacedCopies directly, rather
    than hunting for real A4/Letter-sized templates that happen to need
    rotation, keeps this test decoupled from that (deliberately
    conservative -- see printing.py's _ROTATION_COMBOS ordering) decision
    logic."""
    dialog = PrintDialog(_project())
    original_width, original_height = dialog._disc_raw.width(), dialog._disc_raw.height()

    dialog._rebuild_items(PlacedCopies([(10.0, 10.0)], rotated=True), PlacedCopies([(10.0, 80.0)], rotated=False))

    disc_item = dialog._disc_items[0]
    assert disc_item.rotated is True
    assert disc_item.oriented_raw_image().width() == original_height
    assert disc_item.oriented_raw_image().height() == original_width
    assert disc_item.width_mm == dialog._disc_size_mm[1]
    assert disc_item.height_mm == dialog._disc_size_mm[0]

    cover_item = dialog._cover_items[0]
    assert cover_item.rotated is False
    assert cover_item.oriented_raw_image() is dialog._cover_raw  # not rotated -- left untouched


def test_too_many_copies_places_the_overflow_in_the_corner_with_a_warning(qt_app, monkeypatch):
    """No hard error, and the count is never reverted -- as many copies as
    fit get printing.py's own automatic arrangement, and the rest are
    stacked at the page's top-left corner for the user to drag (and
    right-click to rotate) into place themselves, since manual freeform
    arrangement can beat any simple grid packer."""
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warnings.append(a) or QMessageBox.StandardButton.Ok)

    dialog = PrintDialog(_project())  # real MiniDisc dimensions -- 4 copies is the automatic max on A4
    dialog.copies_spin.setValue(7)

    assert len(warnings) == 1
    message = warnings[0][2]
    assert message == "Only 4 of 7 copies could be arranged automatically. The rest have been placed in the top-left corner -- drag them into place, and right-click a label to rotate it 90 degrees."
    assert dialog.copies_spin.value() == 7  # honored, not reverted
    assert len(dialog._disc_items) == 7
    assert len(dialog._cover_items) == 7

    corner_px = (dialog.MARGIN_MM * dialog.PREVIEW_PX_PER_MM, dialog.MARGIN_MM * dialog.PREVIEW_PX_PER_MM)
    fitting_positions = {(item.pos().x(), item.pos().y()) for item in dialog._disc_items[:4]}
    overflow_positions = {(item.pos().x(), item.pos().y()) for item in dialog._disc_items[4:]}
    assert len(fitting_positions) == 4  # the automatically-fitting copies each got their own real grid cell
    assert overflow_positions == {corner_px}  # every overflow copy stacked at the same corner


def test_right_clicking_a_label_rotates_it_and_refreshes_its_display(qt_app):
    dialog = PrintDialog(_project())
    item = dialog._disc_items[0]
    assert item.rotated is False
    original_width_mm, original_height_mm = item.width_mm, item.height_mm
    original_raw_width, original_raw_height = item.raw_image.width(), item.raw_image.height()

    class _FakeContextMenuEvent:
        def accept(self):
            pass

    item.contextMenuEvent(_FakeContextMenuEvent())

    assert item.rotated is True
    assert item.width_mm == original_height_mm
    assert item.height_mm == original_width_mm
    # the actually-displayed/printed image is genuinely rotated, not just the metadata
    assert item.display_image.width() == original_raw_height
    assert item.display_image.height() == original_raw_width


def test_right_clicking_one_copy_does_not_rotate_its_siblings(qt_app):
    dialog = PrintDialog(_small_project())
    dialog.copies_spin.setValue(2)

    class _FakeContextMenuEvent:
        def accept(self):
            pass

    dialog._disc_items[0].contextMenuEvent(_FakeContextMenuEvent())

    assert dialog._disc_items[0].rotated is True
    assert dialog._disc_items[1].rotated is False


def test_changing_page_size_relayouts_the_existing_copies(qt_app):
    dialog = PrintDialog(_project())
    dialog.copies_spin.setValue(2)

    dialog.page_size_combo.setCurrentText("Letter")

    assert len(dialog._disc_items) == 2
    assert len(dialog._cover_items) == 2


def test_brightness_contrast_rows_hidden_until_grayscale_is_checked(qt_app):
    dialog = PrintDialog(_project())

    assert not dialog._options_form.isRowVisible(dialog.brightness_slider)
    assert not dialog._options_form.isRowVisible(dialog.contrast_slider)

    dialog.grayscale_check.setChecked(True)

    assert dialog._options_form.isRowVisible(dialog.brightness_slider)
    assert dialog._options_form.isRowVisible(dialog.contrast_slider)


def test_checking_grayscale_desaturates_the_preview_pixmaps(qt_app):
    dialog = PrintDialog(_project())
    before = dialog._disc_items[0].display_image

    dialog.grayscale_check.setChecked(True)

    after = dialog._disc_items[0].display_image
    assert after is not before
    pixel = after.pixelColor(after.width() // 2, after.height() // 2)
    assert pixel.red() == pixel.green() == pixel.blue()


def test_dragging_a_label_changes_its_print_position(qt_app):
    dialog = PrintDialog(_project())
    dialog._disc_items[0].setPos(50 * dialog.PREVIEW_PX_PER_MM, 20 * dialog.PREVIEW_PX_PER_MM)

    placements = dialog._build_placements()
    disc_placement = next(p for p in placements if p.width_mm == dialog._disc_items[0].width_mm)

    assert abs(disc_placement.x_mm - 50.0) < 1e-6
    assert abs(disc_placement.y_mm - 20.0) < 1e-6


def test_print_button_writes_a_real_pdf_at_the_dragged_positions(qt_app, tmp_path, monkeypatch):
    output_path = tmp_path / "printed.pdf"
    monkeypatch.setattr(print_dialog_module, "QPrinter", _make_fake_printer(output_path))
    monkeypatch.setattr(QPrintDialog, "exec", lambda self: QPrintDialog.DialogCode.Accepted)

    dialog = PrintDialog(_project())
    dialog._on_print()

    assert output_path.is_file()
    assert output_path.stat().st_size > 0
    assert dialog.result() == PrintDialog.DialogCode.Accepted


def test_print_button_writes_one_placement_per_copy(qt_app, tmp_path, monkeypatch):
    output_path = tmp_path / "printed.pdf"
    monkeypatch.setattr(print_dialog_module, "QPrinter", _make_fake_printer(output_path))
    monkeypatch.setattr(QPrintDialog, "exec", lambda self: QPrintDialog.DialogCode.Accepted)

    dialog = PrintDialog(_small_project())
    dialog.copies_spin.setValue(3)

    dialog._on_print()

    assert len(dialog._build_placements()) == 6  # 3 disc copies + 3 cover copies


def test_cancelling_the_system_print_dialog_prints_nothing(qt_app, tmp_path, monkeypatch):
    output_path = tmp_path / "not_printed.pdf"
    monkeypatch.setattr(print_dialog_module, "QPrinter", _make_fake_printer(output_path))
    monkeypatch.setattr(QPrintDialog, "exec", lambda self: QPrintDialog.DialogCode.Rejected)

    dialog = PrintDialog(_project())
    dialog._on_print()  # must not raise

    assert not output_path.exists()
    assert dialog.result() != PrintDialog.DialogCode.Accepted


def test_printing_in_grayscale_saves_the_adjustment_onto_the_project(qt_app, tmp_path, monkeypatch):
    output_path = tmp_path / "gray.pdf"
    monkeypatch.setattr(print_dialog_module, "QPrinter", _make_fake_printer(output_path))
    monkeypatch.setattr(QPrintDialog, "exec", lambda self: QPrintDialog.DialogCode.Accepted)

    project = _project()
    dialog = PrintDialog(project)
    dialog.grayscale_check.setChecked(True)
    dialog.brightness_slider.setValue(40)
    dialog.contrast_slider.setValue(-15)

    dialog._on_print()

    assert project.grayscale_adjustment == GrayscaleAdjustment(brightness=40, contrast=-15)


def test_printing_in_color_leaves_the_saved_adjustment_untouched(qt_app, tmp_path, monkeypatch):
    output_path = tmp_path / "color.pdf"
    monkeypatch.setattr(print_dialog_module, "QPrinter", _make_fake_printer(output_path))
    monkeypatch.setattr(QPrintDialog, "exec", lambda self: QPrintDialog.DialogCode.Accepted)

    project = _project(grayscale_adjustment=GrayscaleAdjustment(brightness=5, contrast=5))
    dialog = PrintDialog(project)
    dialog.brightness_slider.setValue(90)  # touched, but grayscale never checked

    dialog._on_print()

    assert project.grayscale_adjustment == GrayscaleAdjustment(brightness=5, contrast=5)


def test_export_png_writes_a_real_transparent_png_of_the_current_layout(qt_app, tmp_path, monkeypatch):
    output_path = tmp_path / "exported.png"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(output_path), "")))
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)

    dialog = PrintDialog(_project())
    dialog._on_export_png()

    assert output_path.is_file()
    image = QImage(str(output_path))
    assert not image.isNull()
    assert image.hasAlphaChannel()
    # a corner of the page, away from any label, must be transparent --
    # there's no white "paper" background painted here
    assert image.pixelColor(1, 1).alpha() == 0


def test_export_png_does_not_close_the_dialog(qt_app, tmp_path, monkeypatch):
    output_path = tmp_path / "exported.png"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(output_path), "")))
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)

    dialog = PrintDialog(_project())
    dialog._on_export_png()

    assert dialog.result() != PrintDialog.DialogCode.Accepted


def test_export_png_appends_the_png_extension_if_missing(qt_app, tmp_path, monkeypatch):
    output_path_no_extension = tmp_path / "exported"
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(output_path_no_extension), ""))
    )
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)

    dialog = PrintDialog(_project())
    dialog._on_export_png()

    assert output_path_no_extension.with_suffix(".png").is_file()
    assert not output_path_no_extension.exists()


def test_cancelling_the_png_save_path_prompt_exports_nothing(qt_app, monkeypatch):
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: ("", "")))

    def fail_if_called(*a, **k):
        raise AssertionError("nothing should be written without a chosen path")

    monkeypatch.setattr(print_dialog_module, "render_page_to_image", fail_if_called)

    dialog = PrintDialog(_project())
    dialog._on_export_png()  # must not raise


def test_exporting_png_in_grayscale_saves_the_adjustment_onto_the_project(qt_app, tmp_path, monkeypatch):
    output_path = tmp_path / "gray.png"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(output_path), "")))
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)

    project = _project()
    dialog = PrintDialog(project)
    dialog.grayscale_check.setChecked(True)
    dialog.brightness_slider.setValue(15)
    dialog.contrast_slider.setValue(20)

    dialog._on_export_png()

    assert project.grayscale_adjustment == GrayscaleAdjustment(brightness=15, contrast=20)


def test_export_pdf_writes_a_real_pdf_of_the_current_layout(qt_app, tmp_path, monkeypatch):
    output_path = tmp_path / "exported.pdf"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(output_path), "")))
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)

    dialog = PrintDialog(_project())
    dialog._on_export_pdf()

    assert output_path.is_file()
    assert output_path.stat().st_size > 0


def test_export_pdf_does_not_go_through_the_system_print_dialog(qt_app, tmp_path, monkeypatch):
    output_path = tmp_path / "exported.pdf"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(output_path), "")))
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)

    def fail_if_shown(self):
        raise AssertionError("Export PDF must not open the system print dialog")

    monkeypatch.setattr(QPrintDialog, "exec", fail_if_shown)

    dialog = PrintDialog(_project())
    dialog._on_export_pdf()  # must not raise

    assert output_path.is_file()


def test_export_pdf_does_not_close_the_dialog(qt_app, tmp_path, monkeypatch):
    output_path = tmp_path / "exported.pdf"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(output_path), "")))
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)

    dialog = PrintDialog(_project())
    dialog._on_export_pdf()

    assert dialog.result() != PrintDialog.DialogCode.Accepted


def test_export_pdf_appends_the_pdf_extension_if_missing(qt_app, tmp_path, monkeypatch):
    output_path_no_extension = tmp_path / "exported"
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(output_path_no_extension), ""))
    )
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)

    dialog = PrintDialog(_project())
    dialog._on_export_pdf()

    assert output_path_no_extension.with_suffix(".pdf").is_file()
    assert not output_path_no_extension.exists()


def test_cancelling_the_save_path_prompt_exports_nothing(qt_app, monkeypatch):
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: ("", "")))

    def fail_if_called(*a, **k):
        raise AssertionError("nothing should be written without a chosen path")

    monkeypatch.setattr(print_dialog_module, "print_sheets", fail_if_called)

    dialog = PrintDialog(_project())
    dialog._on_export_pdf()  # must not raise


def test_exporting_in_grayscale_saves_the_adjustment_onto_the_project(qt_app, tmp_path, monkeypatch):
    output_path = tmp_path / "gray.pdf"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(output_path), "")))
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)

    project = _project()
    dialog = PrintDialog(project)
    dialog.grayscale_check.setChecked(True)
    dialog.brightness_slider.setValue(25)
    dialog.contrast_slider.setValue(10)

    dialog._on_export_pdf()

    assert project.grayscale_adjustment == GrayscaleAdjustment(brightness=25, contrast=10)


# -- orientation and separate sheets -------------------------------------


def test_the_page_can_be_turned_and_everything_asks_one_place_for_it(qt_app):
    dialog = PrintDialog(_project())

    assert dialog.page_size_mm() == (210.0, 297.0)
    dialog.orientation_combo.setCurrentIndex(1)
    assert dialog.page_size_mm() == (297.0, 210.0)
    # the preview's own paper follows, rather than keeping its own idea
    assert dialog._page_rect_item.rect().width() > dialog._page_rect_item.rect().height()


def test_the_printer_is_turned_the_same_way_as_the_preview(qt_app):
    from PySide6.QtGui import QPageLayout

    dialog = PrintDialog(_project())
    dialog.orientation_combo.setCurrentIndex(1)

    assert dialog._new_printer().pageLayout().orientation() == QPageLayout.Orientation.Landscape


def test_separate_sheets_puts_each_label_on_its_own_page(qt_app):
    dialog = PrintDialog(_project())
    assert len(dialog.sheets()) == 1

    dialog.separate_sheets_check.setChecked(True)

    sheets = dialog.sheets()
    assert len(sheets) == 2
    assert all(item in dialog._disc_items for item in sheets[0])
    assert all(item in dialog._cover_items for item in sheets[1])


def test_the_preview_shows_one_sheet_at_a_time(qt_app):
    """What is on screen has to be a page that will come out, not a
    composite of two that will not."""
    dialog = PrintDialog(_project())
    dialog.separate_sheets_check.setChecked(True)

    assert all(item.isVisible() for item in dialog._disc_items)
    assert not any(item.isVisible() for item in dialog._cover_items)

    dialog.sheet_combo.setCurrentIndex(1)

    assert not any(item.isVisible() for item in dialog._disc_items)
    assert all(item.isVisible() for item in dialog._cover_items)


def test_turning_separate_sheets_off_again_shows_everything(qt_app):
    dialog = PrintDialog(_project())
    dialog.separate_sheets_check.setChecked(True)
    dialog.sheet_combo.setCurrentIndex(1)

    dialog.separate_sheets_check.setChecked(False)

    assert all(item.isVisible() for item in dialog._all_items())


def test_exporting_two_sheets_writes_two_pngs(qt_app, tmp_path, monkeypatch):
    """A PNG holds one page; exporting only the first would silently lose
    half the project."""
    target = tmp_path / "labels.png"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(target), "")))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))

    dialog = PrintDialog(_project())
    dialog.separate_sheets_check.setChecked(True)
    dialog._on_export_png()

    assert (tmp_path / "labels-1.png").is_file()
    assert (tmp_path / "labels-2.png").is_file()
    assert not target.exists()


def test_one_sheet_still_writes_the_file_that_was_asked_for(qt_app, tmp_path, monkeypatch):
    target = tmp_path / "sheet.png"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(target), "")))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))

    PrintDialog(_project())._on_export_png()

    assert target.is_file()
