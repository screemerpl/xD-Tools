import math

import pytest
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtPrintSupport import QPrinter

from mdtools import printing
from mdtools.canvas.scene import DesignScene
from mdtools.io.png_export import render_scene_to_image
from mdtools.printing import (
    PAGE_SIZES_MM,
    PrintLayoutError,
    PrintPlacement,
    build_copies_layout,
    crop_to_template_bounds,
    image_physical_size_mm,
    max_copies_that_fit,
    print_placements,
    render_page_to_image,
)
from mdtools.templates.models import CoverTemplate, DiscTemplate


def _solid_png(size: int, color: str) -> bytes:
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(QColor(color))
    buffer = QByteArray()
    device = QBuffer(buffer)
    device.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(device, "PNG")
    device.close()
    return bytes(buffer)


def test_image_physical_size_mm_recovers_the_original_mm_size(qt_app):
    """render_scene_to_image() bakes width_px == width_mm * dpi / 25.4 into
    every image it produces -- this must invert that losslessly, at
    whatever DPI was used."""
    dpi = 300.0
    width_mm, height_mm = 37.0, 52.0
    image = QImage(round(width_mm * dpi / 25.4), round(height_mm * dpi / 25.4), QImage.Format.Format_ARGB32)

    got_w, got_h = image_physical_size_mm(image, dpi)

    # recovers the mm size losslessly modulo the single-pixel rounding
    # already baked into the image's own pixel count -- not an
    # independent source of error introduced by this function.
    assert got_w == round(width_mm * dpi / 25.4) / dpi * 25.4
    assert got_h == round(height_mm * dpi / 25.4) / dpi * 25.4
    assert abs(got_w - width_mm) < 0.1
    assert abs(got_h - height_mm) < 0.1


def test_page_sizes_are_in_millimeters_and_portrait(qt_app):
    for width_mm, height_mm in PAGE_SIZES_MM.values():
        assert width_mm < height_mm


def test_build_copies_layout_gives_each_copy_a_distinct_non_overlapping_slot():
    disc_size_mm = (40.0, 50.0)
    cover_size_mm = (150.0, 70.0)
    page_size_mm = (210.0, 297.0)  # A4

    disc_copies, cover_copies = build_copies_layout(disc_size_mm, cover_size_mm, 3, page_size_mm, 10.0)

    assert len(disc_copies.positions) == 3
    assert len(cover_copies.positions) == 3
    assert len(set(disc_copies.positions)) == 3  # no two copies stacked on top of each other
    assert len(set(cover_copies.positions)) == 3

    # every disc copy must sit strictly above every cover copy -- the two
    # label types are laid out as two separate stacked blocks, never
    # interleaved
    disc_height_mm = disc_size_mm[1] if not disc_copies.rotated else disc_size_mm[0]
    assert max(y for _, y in disc_copies.positions) + disc_height_mm <= min(y for _, y in cover_copies.positions)


def test_build_copies_layout_wraps_into_multiple_rows_once_a_row_is_full():
    disc_size_mm = (40.0, 50.0)
    cover_size_mm = (80.0, 40.0)  # small enough that 5 copies of both still fit the page
    page_size_mm = (210.0, 297.0)

    # at 40mm wide with 5mm gaps, 4 columns fit in a 190mm-wide printable
    # area (4*40 + 3*5 = 175mm) but a 5th would not (215mm) -- so 5 copies
    # must wrap into a second row
    disc_copies, _ = build_copies_layout(disc_size_mm, cover_size_mm, 5, page_size_mm, 10.0)

    assert disc_copies.rotated is False  # this scenario fits upright -- no need to rotate
    rows = {round(y, 3) for _, y in disc_copies.positions}
    assert len(rows) == 2


def test_build_copies_layout_does_not_rotate_when_upright_already_fits():
    """Rotation must only ever kick in as a fallback to make a requested
    count fit -- never as a "more compact anyway" default, or a single
    copy could come out sideways for no visible reason just because it's
    marginally shorter that way."""
    disc_size_mm = (42.0, 57.0)  # taller than wide -- rotating it is always "shorter"
    cover_size_mm = (131.0, 78.0)
    page_size_mm = (210.0, 297.0)

    disc_copies, cover_copies = build_copies_layout(disc_size_mm, cover_size_mm, 1, page_size_mm, 10.0)

    assert disc_copies.rotated is False
    assert cover_copies.rotated is False


def test_build_copies_layout_rotates_a_label_to_fit_a_height_constrained_page():
    """cover_size_mm (80x30) is wide-but-short -- upright it only fits one
    column (80mm eats almost the whole 100mm-wide printable area), so 2
    copies stack into 2 rows and blow this tightly height-constrained
    page's budget alongside the disc grid. Turned on its side (30x80) it
    fits both copies in a single row instead, using far less height --
    exactly the kind of "doesn't fit -> optimize by rotating" case the
    Copies spinbox needs. (Page chosen tightly enough that neither a
    smaller gap nor the horizontal side-by-side arrangement alone rescues
    it without rotation -- see test_printing.py's other layout tests for
    those.)"""
    disc_size_mm = (30.0, 40.0)
    cover_size_mm = (80.0, 30.0)
    page_size_mm = (120.0, 110.0)  # -> 100mm x 90mm printable area at margin 10

    disc_copies, cover_copies = build_copies_layout(disc_size_mm, cover_size_mm, 2, page_size_mm, 10.0)

    assert disc_copies.rotated is False
    assert cover_copies.rotated is True
    assert len(cover_copies.positions) == 2
    assert len({round(y, 3) for _, y in cover_copies.positions}) == 1  # both fit in a single row once rotated


def test_build_copies_layout_uses_horizontal_arrangement_when_stacking_does_not_fit():
    """The real bug report this generalization fixes: with real MiniDisc
    dimensions (a 145x68mm cover, once cropped to its template bounds --
    see test_crop_to_template_bounds_* below), stacking the disc grid
    directly above the cover grid (the original, vertical-only model)
    cannot fit 4 copies of each on an A4 page even trying every rotation
    -- a user reported manually fitting them anyway, by placing the disc
    copies *beside* the cover column instead of below it. This is exactly
    that arrangement, discovered automatically without any rotation."""
    disc_size_mm = (37.084, 52.07)
    cover_size_mm = (145.034, 68.072)
    page_size_mm = (210.0, 297.0)  # A4

    disc_copies, cover_copies = build_copies_layout(disc_size_mm, cover_size_mm, 4, page_size_mm, 5.0)

    assert len(disc_copies.positions) == 4
    assert len(cover_copies.positions) == 4
    assert disc_copies.rotated is False
    assert cover_copies.rotated is False
    # the two blocks must sit side by side (same x-extent order), not
    # stacked -- i.e. at least one disc copy shares a row (y position)
    # with a cover copy, which a purely-vertical stack could never do
    disc_ys = {round(y, 3) for _, y in disc_copies.positions}
    cover_ys = {round(y, 3) for _, y in cover_copies.positions}
    assert disc_ys & cover_ys


def test_crop_to_template_bounds_removes_the_render_padding_but_keeps_content(qt_app):
    """render_scene_to_image() pads its output with a small transparent
    margin around the template's own cut outline (see
    DesignScene._build_disc_outline's -10/+20 scene-rect convention) --
    crop_to_template_bounds() must remove exactly that margin (recovering
    close to the template's own width_mm/height_mm) without cutting into
    actual printed content."""
    template = DiscTemplate(name="d", width_mm=37.0, height_mm=52.0, chamfer_mm=0, fillet_mm=0)
    scene = DesignScene(template)
    image_item = scene.add_image_from_data(_solid_png(30, "blue"))
    image_item.setPos(5, 5)  # near the template's own top-left corner, in scene px

    dpi = 150.0
    full = render_scene_to_image(scene, dpi=dpi)
    cropped = crop_to_template_bounds(scene, full, dpi)

    assert cropped.width() < full.width()
    assert cropped.height() < full.height()
    cropped_width_mm, cropped_height_mm = image_physical_size_mm(cropped, dpi)
    assert abs(cropped_width_mm - template.width_mm) < 0.5
    assert abs(cropped_height_mm - template.height_mm) < 0.5
    # the blue square must have survived the crop, landing near the
    # cropped image's own top-left corner (matching where it was placed
    # relative to the template's own top-left, once the outer render
    # padding is trimmed away)
    assert cropped.pixelColor(20, 20).blue() > 0


def test_crop_to_template_bounds_handles_the_disc_slider_variant(qt_app):
    """The slider variant's own sceneRect spans the disc *and* the
    adjacent slider shape (see _build_disc_outline's `total_w`) -- the
    crop must keep both, not just the main disc."""
    template = DiscTemplate(
        name="d",
        width_mm=37.0,
        height_mm=52.0,
        chamfer_mm=0,
        fillet_mm=0,
        slider_width_mm=27.5,
        slider_height_mm=17.5,
        slider_corner_radius_mm=2.5,
        slider_gap_mm=3.0,
    )
    scene = DesignScene(template)
    dpi = 150.0
    full = render_scene_to_image(scene, dpi=dpi)
    cropped = crop_to_template_bounds(scene, full, dpi)

    expected_total_width_mm = template.width_mm + template.slider_gap_mm + template.slider_width_mm
    cropped_width_mm, _ = image_physical_size_mm(cropped, dpi)
    assert abs(cropped_width_mm - expected_total_width_mm) < 0.5


def test_render_page_to_image_has_a_transparent_background(qt_app):
    page_size_mm = (50.0, 40.0)
    image = QImage(20, 20, QImage.Format.Format_ARGB32)
    image.fill(QColor("red"))
    placement = PrintPlacement(image=image, x_mm=5.0, y_mm=5.0, width_mm=10.0, height_mm=10.0)

    page_image = render_page_to_image(page_size_mm, [placement], dpi=150.0)

    # a corner of the page, away from the placed label, must be fully
    # transparent -- there's no "paper" being painted white here
    assert page_image.pixelColor(1, 1).alpha() == 0
    # the placement itself must actually be there and opaque
    center_x = round((5.0 + 5.0) / 25.4 * 150.0)
    center_y = round((5.0 + 5.0) / 25.4 * 150.0)
    pixel = page_image.pixelColor(center_x, center_y)
    assert pixel.alpha() > 0
    assert pixel.red() > pixel.green()  # sanity: it's actually the red square


def test_render_page_to_image_size_matches_the_page_at_the_given_dpi(qt_app):
    page_size_mm = (210.0, 297.0)
    dpi = 150.0

    page_image = render_page_to_image(page_size_mm, [], dpi)

    assert page_image.width() == math.ceil(210.0 / 25.4 * 150.0)
    assert page_image.height() == math.ceil(297.0 / 25.4 * 150.0)


def test_crop_to_template_bounds_works_for_the_cover_template_too(qt_app):
    template = CoverTemplate(name="c", width_mm=126.0, height_mm=73.0)
    scene = DesignScene(template)
    dpi = 150.0
    full = render_scene_to_image(scene, dpi=dpi)
    cropped = crop_to_template_bounds(scene, full, dpi)

    cropped_width_mm, cropped_height_mm = image_physical_size_mm(cropped, dpi)
    assert abs(cropped_width_mm - template.width_mm) < 0.5
    assert abs(cropped_height_mm - template.height_mm) < 0.5


def test_build_copies_layout_raises_when_too_tall_to_fit():
    disc_size_mm = (40.0, 50.0)
    cover_size_mm = (150.0, 70.0)
    page_size_mm = (210.0, 297.0)

    with pytest.raises(PrintLayoutError):
        build_copies_layout(disc_size_mm, cover_size_mm, 50, page_size_mm, 10.0)


def test_build_copies_layout_raises_when_a_single_copy_is_wider_than_the_page_in_either_orientation():
    disc_size_mm = (40.0, 50.0)
    oversized_cover_mm = (500.0, 500.0)
    page_size_mm = (210.0, 297.0)

    with pytest.raises(PrintLayoutError):
        build_copies_layout(disc_size_mm, oversized_cover_mm, 1, page_size_mm, 10.0)


def test_max_copies_that_fit_is_exactly_the_boundary_build_copies_layout_accepts():
    disc_size_mm = (40.0, 50.0)
    cover_size_mm = (150.0, 70.0)
    page_size_mm = (210.0, 297.0)

    fits = max_copies_that_fit(disc_size_mm, cover_size_mm, page_size_mm, 10.0)

    assert fits >= 1
    build_copies_layout(disc_size_mm, cover_size_mm, fits, page_size_mm, 10.0)  # must not raise
    with pytest.raises(PrintLayoutError):
        build_copies_layout(disc_size_mm, cover_size_mm, fits + 1, page_size_mm, 10.0)


def test_print_placements_writes_a_real_pdf(qt_app, tmp_path):
    """No real printer needed -- QPrinter can target a PDF file directly,
    which is enough to prove the paint routine actually runs and produces
    real output at the expected physical page size."""
    output_path = tmp_path / "out.pdf"
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(str(output_path))
    printer.setFullPage(True)

    image = QImage(50, 50, QImage.Format.Format_ARGB32)
    image.fill(QColor("red"))
    placement = PrintPlacement(image=image, x_mm=10.0, y_mm=10.0, width_mm=37.0, height_mm=52.0)

    print_placements(printer, [placement])

    assert output_path.is_file()
    assert output_path.stat().st_size > 0


# -- landscape, and a sheet per label ------------------------------------


def test_turning_the_page_swaps_its_sides():
    assert printing.oriented_page_size((210.0, 297.0), printing.LANDSCAPE) == (297.0, 210.0)
    assert printing.oriented_page_size((210.0, 297.0), printing.PORTRAIT) == (210.0, 297.0)


def test_a_cd_insert_only_fits_a_portrait_sheet_turned_sideways():
    """242mm wide against A4's 200mm of printable width: upright it does
    not go, which is what forced landscape to be offered at all."""
    a4 = printing.PAGE_SIZES_MM["A4"]

    portrait = printing.build_sheet_layout((242.0, 120.0), 1, a4, 5.0)
    landscape = printing.build_sheet_layout(
        (242.0, 120.0), 1, printing.oriented_page_size(a4, printing.LANDSCAPE), 5.0
    )

    assert portrait.rotated is True
    assert landscape.rotated is False, "there is no reason to turn it when it fits as it is"


def test_a_label_that_fits_upright_is_never_turned():
    """Rotation stays a fallback here, exactly as in the two-label
    layout."""
    placed = printing.build_sheet_layout((118.0, 118.0), 2, printing.PAGE_SIZES_MM["A4"], 5.0)

    assert placed.rotated is False
    assert len(placed.positions) == 2


def test_a_label_too_big_for_the_page_is_refused_rather_than_placed_off_it():
    with pytest.raises(printing.PrintLayoutError):
        printing.build_sheet_layout((400.0, 400.0), 1, printing.PAGE_SIZES_MM["A4"], 5.0)


def test_how_many_of_one_label_a_sheet_holds():
    a4 = printing.PAGE_SIZES_MM["A4"]

    assert printing.max_copies_on_sheet((118.0, 118.0), a4, 5.0) == 2
    assert printing.max_copies_on_sheet((242.0, 120.0), a4, 5.0) == 1
    assert printing.max_copies_on_sheet((400.0, 400.0), a4, 5.0) == 0


def test_printing_several_sheets_produces_several_pages(qt_app, tmp_path):
    """The whole point of the separate-sheets mode, and not something to
    take on trust: the PDF is read back and its pages counted."""
    output = tmp_path / "two.pdf"
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(str(output))
    printer.setFullPage(True)

    image = QImage(10, 10, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.red)
    sheet = [printing.PrintPlacement(image=image, x_mm=5, y_mm=5, width_mm=50, height_mm=50)]

    printing.print_sheets(printer, [sheet, sheet])

    assert output.is_file()
    assert output.read_bytes().count(b"/Type /Page\n") == 2 or output.read_bytes().count(b"/Type/Page") == 2


def test_an_empty_sheet_is_skipped_rather_than_printed_blank(qt_app, tmp_path):
    output = tmp_path / "one.pdf"
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(str(output))
    printer.setFullPage(True)

    image = QImage(10, 10, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.red)
    sheet = [printing.PrintPlacement(image=image, x_mm=5, y_mm=5, width_mm=50, height_mm=50)]

    printing.print_sheets(printer, [sheet, []])

    data = output.read_bytes()
    assert data.count(b"/Type /Page\n") <= 1 and data.count(b"/Type/Page") <= 1
