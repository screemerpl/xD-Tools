"""File > Print... -- lays N copies each of both design pages (disc +
cover) out on a single physical page (A4 or Letter), auto-arranged into a
grid that the user can still drag into position, then either sends the
result to a real printer (Print...) or saves exactly what's shown to a
standalone PDF/PNG file (Export PDF.../Export PNG...).

Also home to MultiprintDialog, launched from the startup screen instead
(see panels/startup_dialog.py's "Multiprint..." button) -- combines
disc/cover artwork from several different saved .mdproj files onto one
page, added/removed by hand (Add.../Delete) rather than auto-arranged
copies of a single project. Both dialogs share the page preview, the
grayscale/brightness/contrast controls, and the Print/Export PNG/
Export PDF machinery via a common `_PrintDialogBase` -- see its
docstring -- so that machinery (and this module's own) only exists once.

Grayscale/color and, when grayscale, brightness/contrast reuse the exact
same mdtools.grayscale.apply_grayscale() the canvas preview and Export
Print PNG (Grayscale) already use, so what's shown here can never look
different from Export Print PNG's own output for the same settings.
Physical accuracy is enforced by mdtools.printing.print_sheets() at
the moment of the real print, not by anything drawn in this dialog's own
(purely visual, fit-to-dialog) preview -- see image_physical_size_mm()'s
docstring for why the actual mm size is derived from the rendered image's
pixel count and DPI, not from on-screen scene coordinates.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QImage,
    QPageLayout,
    QPageSize,
    QPainter,
    QPen,
    QPixmap,
    QTransform,
)
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
)

from mdtools import app_settings, user_paths
from mdtools.grayscale import BRIGHTNESS_RANGE, CONTRAST_RANGE, apply_grayscale
from mdtools.io.png_export import render_scene_to_image
from mdtools.io.project_io import load_project
from mdtools.printing import (
    LANDSCAPE,
    MAX_COPIES,
    PAGE_SIZES_MM,
    PORTRAIT,
    PlacedCopies,
    PrintLayoutError,
    PrintPlacement,
    build_copies_layout,
    build_sheet_layout,
    crop_to_template_bounds,
    image_physical_size_mm,
    max_copies_on_sheet,
    max_copies_that_fit,
    oriented_page_size,
    print_sheets,
    render_page_to_image,
)
from mdtools.project import PAGE_COVER, PAGE_DISC, GrayscaleAdjustment, Project

_PAGE_SIZE_IDS = {
    "A4": QPageSize.PageSizeId.A4,
    "Letter": QPageSize.PageSizeId.Letter,
}


def _rotate_90(image: QImage) -> QImage:
    # a plain 90-degree rotation is axis-aligned -- every source pixel
    # maps exactly onto one destination pixel, so this loses no detail
    # (unlike a rotation at an arbitrary angle, which would need to
    # resample/blur at the edges).
    return image.transformed(QTransform().rotate(90))


class _LabelItem(QGraphicsPixmapItem):
    """One copy of a rendered label (disc or cover), draggable on the page
    preview -- and independently rotatable: right-click turns it 90
    degrees (see contextMenuEvent), since a simple auto-packed grid can't
    always match what a user can achieve by hand, rotating some copies
    but not others to nestle them into leftover space.

    `raw_image`/`base_width_mm`/`base_height_mm` are the canonical,
    never-rotated render and its true physical size -- never mutated.
    `width_mm`/`height_mm` report this item's *current* rotation-aware
    footprint (swapped while `rotated`), which is what's actually used
    for on-screen scaling and the final print/export placement.
    `display_image` (the current, possibly-grayscaled *and* possibly-
    rotated image actually shown/printed) changes whenever the Grayscale
    checkbox/sliders change, or this item is individually rotated.
    Multiple copies of the same label share the same `raw_image` object
    (see PrintDialog._make_item) -- read-only after render, so there's
    nothing to protect against multiple items referencing it."""

    def __init__(self, raw_image: QImage, base_width_mm: float, base_height_mm: float, rotated: bool = False):
        super().__init__()
        self.raw_image = raw_image
        self.display_image = raw_image
        self.base_width_mm = base_width_mm
        self.base_height_mm = base_height_mm
        self.rotated = rotated
        # Set by _PrintDialogBase._make_item -- called after a right-click
        # rotation so the dialog can recompute every item's grayscale/
        # brightness/contrast-adjusted display image and on-screen scale
        # for the new orientation. A plain callable attribute rather than
        # a Qt signal since QGraphicsItem isn't a QObject.
        self.on_rotated = None
        self.setFlag(QGraphicsPixmapItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsPixmapItem.GraphicsItemFlag.ItemIsSelectable, True)

    @property
    def width_mm(self) -> float:
        return self.base_height_mm if self.rotated else self.base_width_mm

    @property
    def height_mm(self) -> float:
        return self.base_width_mm if self.rotated else self.base_height_mm

    def oriented_raw_image(self) -> QImage:
        return _rotate_90(self.raw_image) if self.rotated else self.raw_image

    def set_display_image(self, image: QImage, preview_px_per_mm: float) -> None:
        self.display_image = image
        pixmap = QPixmap.fromImage(image)
        self.setPixmap(pixmap)
        if pixmap.width():
            self.setScale((self.width_mm * preview_px_per_mm) / pixmap.width())

    def contextMenuEvent(self, event) -> None:
        self.rotated = not self.rotated
        if self.on_rotated is not None:
            self.on_rotated()
        event.accept()


class _PageView(QGraphicsView):
    """Always fits the whole page in view, regardless of dialog size --
    the scene's own unit scale (PREVIEW_PX_PER_MM) is only there for
    internal consistency (translating a dragged item's pos() back to mm);
    actual on-screen size is whatever fits the widget."""

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self.scene() is not None:
            self.fitInView(self.scene().sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)


class _PrintDialogBase(QDialog):
    """Shared machinery for PrintDialog and MultiprintDialog: the page
    preview itself, grayscale/brightness/contrast controls, and the
    Print.../Export PDF.../Export PNG... actions -- everything that
    doesn't depend on *how* items get onto the page (PrintDialog's
    Copies-driven auto-layout vs MultiprintDialog's manual Add/Delete).

    Subclasses call the `_build_*` methods from their own `__init__`, in
    whatever order suits their own extra controls (e.g. PrintDialog's
    Copies spinbox, MultiprintDialog's Add/Delete buttons, both of which
    need to sit in `_options_form` alongside the shared Page Size row),
    and must implement `_all_items()`."""

    PREVIEW_PX_PER_MM = 4.0
    MARGIN_MM = 5.0

    def __init__(self, parent=None, start_dir: str = ""):
        super().__init__(parent)
        # Where Export PNG/PDF open. PrintDialog passes the project's own
        # folder; Multiprint has no single project to belong to, so it
        # falls back to the projects folder.
        self._start_dir = start_dir or user_paths.export_start_path(None)
        self._dpi = app_settings.default_export_dpi()
        self._layout = QVBoxLayout(self)
        self._options_form = QFormLayout()
        self._layout.addLayout(self._options_form)

        self.page_size_combo = QComboBox()
        self.page_size_combo.addItems(list(PAGE_SIZES_MM))
        self.page_size_combo.currentTextChanged.connect(self._on_page_size_changed)
        self._options_form.addRow(self.tr("Page Size"), self.page_size_combo)

        # Landscape was not offered at first. A CD project's folded insert
        # is 242mm wide, which no portrait sheet takes upright at all.
        self.orientation_combo = QComboBox()
        self.orientation_combo.addItem(self.tr("Portrait"), PORTRAIT)
        self.orientation_combo.addItem(self.tr("Landscape"), LANDSCAPE)
        self.orientation_combo.currentIndexChanged.connect(self._on_page_size_changed)
        self._options_form.addRow(self.tr("Orientation"), self.orientation_combo)

    def page_size_mm(self) -> tuple[float, float]:
        """The chosen page, already turned the way the user asked -- the one
        place that decides it, so a preview, a printer and a PNG can never
        disagree about which way round the paper is."""
        return oriented_page_size(
            PAGE_SIZES_MM[self.page_size_combo.currentText()], self.orientation_combo.currentData()
        )

    def sheets(self) -> list[list[_LabelItem]]:
        """The items grouped into physical pages. One page unless a
        subclass says otherwise (see PrintDialog's separate-sheets mode)."""
        return [self._all_items()]

    def _all_items(self) -> list[_LabelItem]:
        raise NotImplementedError

    def _build_grayscale_controls(self, grayscale_adjustment: GrayscaleAdjustment) -> None:
        self.grayscale_check = QCheckBox(self.tr("Print in Grayscale"))
        self.grayscale_check.toggled.connect(self._on_grayscale_toggled)
        self._options_form.addRow(self.grayscale_check)

        self.brightness_slider = QSlider(Qt.Orientation.Horizontal)
        self.brightness_slider.setRange(*BRIGHTNESS_RANGE)
        self.brightness_slider.setValue(grayscale_adjustment.brightness)
        self.brightness_slider.valueChanged.connect(self._update_displayed_images)
        self._options_form.addRow(self.tr("Brightness"), self.brightness_slider)

        self.contrast_slider = QSlider(Qt.Orientation.Horizontal)
        self.contrast_slider.setRange(*CONTRAST_RANGE)
        self.contrast_slider.setValue(grayscale_adjustment.contrast)
        self.contrast_slider.valueChanged.connect(self._update_displayed_images)
        self._options_form.addRow(self.tr("Contrast"), self.contrast_slider)

        self._sync_grayscale_rows_visible()

    def _build_page_view(self) -> None:
        self.page_scene = QGraphicsScene(self)
        self.page_view = _PageView(self.page_scene)
        self.page_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.page_view.setMinimumSize(320, 420)
        self._layout.addWidget(self.page_view)

        self._page_rect_item = QGraphicsRectItem()
        self._page_rect_item.setBrush(QBrush(QColor("white")))
        self._page_rect_item.setPen(QPen(QColor("black")))
        self.page_scene.addItem(self._page_rect_item)

        self._update_page_background()

    def _build_action_buttons(self) -> None:
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.export_png_button = buttons.addButton(self.tr("Export PNG..."), QDialogButtonBox.ButtonRole.ActionRole)
        self.export_png_button.clicked.connect(self._on_export_png)
        self.export_pdf_button = buttons.addButton(self.tr("Export PDF..."), QDialogButtonBox.ButtonRole.ActionRole)
        self.export_pdf_button.clicked.connect(self._on_export_pdf)
        self.print_button = buttons.addButton(self.tr("Print..."), QDialogButtonBox.ButtonRole.AcceptRole)
        self.print_button.clicked.connect(self._on_print)
        buttons.rejected.connect(self.reject)
        self._layout.addWidget(buttons)

    def _make_item(self, raw_image: QImage, size_mm: tuple[float, float], rotated: bool) -> _LabelItem:
        width_mm, height_mm = size_mm
        item = _LabelItem(raw_image, width_mm, height_mm, rotated=rotated)
        item.on_rotated = self._update_displayed_images
        return item

    def _on_page_size_changed(self) -> None:
        self._update_page_background()

    def _update_page_background(self) -> None:
        width_mm, height_mm = self.page_size_mm()
        width_px = width_mm * self.PREVIEW_PX_PER_MM
        height_px = height_mm * self.PREVIEW_PX_PER_MM
        self._page_rect_item.setRect(0, 0, width_px, height_px)
        self.page_scene.setSceneRect(-20, -20, width_px + 40, height_px + 40)
        self.page_view.fitInView(self.page_scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def _update_displayed_images(self) -> None:
        """Recomputes every item's displayed (rotated-if-needed, then
        possibly-grayscaled) image -- called on a Grayscale/slider change
        *and* after any single item's right-click rotation, since either
        can change what a given item should show. Caches by (source
        image, rotated) so identical copies of the same label in the same
        orientation only get oriented/grayscaled once per call."""
        grayscale = self.grayscale_check.isChecked()
        brightness = self.brightness_slider.value()
        contrast = self.contrast_slider.value()
        cache: dict[tuple[int, bool], QImage] = {}

        for item in self._all_items():
            key = (id(item.raw_image), item.rotated)
            image = cache.get(key)
            if image is None:
                oriented = item.oriented_raw_image()
                image = apply_grayscale(oriented, brightness, contrast) if grayscale else oriented
                cache[key] = image
            item.set_display_image(image, self.PREVIEW_PX_PER_MM)

    def _on_grayscale_toggled(self) -> None:
        self._sync_grayscale_rows_visible()
        self._update_displayed_images()

    def _sync_grayscale_rows_visible(self) -> None:
        checked = self.grayscale_check.isChecked()
        self._options_form.setRowVisible(self.brightness_slider, checked)
        self._options_form.setRowVisible(self.contrast_slider, checked)

    def _build_placements(self, items=None) -> list[PrintPlacement]:
        placements = []
        for item in self._all_items() if items is None else items:
            placements.append(
                PrintPlacement(
                    image=item.display_image,
                    x_mm=item.pos().x() / self.PREVIEW_PX_PER_MM,
                    y_mm=item.pos().y() / self.PREVIEW_PX_PER_MM,
                    width_mm=item.width_mm,
                    height_mm=item.height_mm,
                )
            )
        return placements

    def _new_printer(self) -> QPrinter:
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setPageSize(QPageSize(_PAGE_SIZE_IDS[self.page_size_combo.currentText()]))
        # The page size above is always the portrait one; this is what
        # turns the paper, and it has to agree with page_size_mm() or every
        # placement lands rotated against the sheet it was laid out on.
        printer.setPageOrientation(
            QPageLayout.Orientation.Landscape
            if self.orientation_combo.currentData() == LANDSCAPE
            else QPageLayout.Orientation.Portrait
        )
        printer.setFullPage(True)
        return printer

    def _sheet_placements(self) -> list[list[PrintPlacement]]:
        return [self._build_placements(items) for items in self.sheets()]

    def _maybe_save_grayscale_adjustment(self) -> None:
        """No-op by default -- overridden by PrintDialog, which has a
        single owning project to persist brightness/contrast onto.
        MultiprintDialog combines several unrelated, already-saved
        projects and has no single place to persist a new adjustment
        back to (and no license to silently rewrite someone else's
        .mdproj file just because Print... was clicked)."""

    def _on_print(self) -> None:
        printer = self._new_printer()

        print_dialog = QPrintDialog(printer, self)
        if print_dialog.exec() != QPrintDialog.DialogCode.Accepted:
            return

        print_sheets(printer, self._sheet_placements())
        self._maybe_save_grayscale_adjustment()
        self.accept()

    def _on_export_png(self) -> None:
        """Exports exactly what the page preview currently shows to a
        standalone, high-DPI PNG -- reusing printing.render_page_to_image(),
        which shares the exact same per-placement paint logic as
        print_sheets()/Export PDF..., so this can never visually
        diverge from either. Unlike a printed page or a PDF, a PNG has no
        physical "paper" to represent, so the page background is left
        fully transparent rather than painted white."""
        path, _ = QFileDialog.getSaveFileName(self, self.tr("Export PNG"), self._start_dir, self.tr("PNG (*.png)"))
        if not path:
            return
        if not path.lower().endswith(".png"):
            path += ".png"

        page_size_mm = self.page_size_mm()
        sheets = self._sheet_placements()
        # One file per sheet, numbered, because a PNG holds one page and
        # silently exporting only the first would lose half a CD project.
        written = []
        for index, placements in enumerate(sheets, start=1):
            if not placements:
                continue
            target = path if len(sheets) == 1 else f"{path[:-4]}-{index}.png"
            render_page_to_image(page_size_mm, placements, self._dpi).save(target, "PNG")
            written.append(target)
        self._maybe_save_grayscale_adjustment()

        QMessageBox.information(
            self, self.tr("Export PNG"), self.tr("Exported to {path}").format(path="\n".join(written))
        )

    def _on_export_pdf(self) -> None:
        """Exports exactly what the page preview currently shows -- same
        items, same dragged positions, same grayscale/color state -- to a
        standalone PDF file, without going through a system printer at
        all. Reuses printing.print_sheets() unchanged (a QPrinter
        aimed at a PDF file paints through the exact same QPainter API as
        one aimed at a real printer), so this can never visually diverge
        from what Print... would produce for the same settings. "High
        quality" here just means reusing the same DPI-rendered artwork
        (Window > Settings' Default Export DPI) every other export in
        this app already uses -- not a separate, heavier render path."""
        path, _ = QFileDialog.getSaveFileName(self, self.tr("Export PDF"), self._start_dir, self.tr("PDF (*.pdf)"))
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"

        printer = self._new_printer()
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(path)

        print_sheets(printer, self._sheet_placements())
        self._maybe_save_grayscale_adjustment()

        QMessageBox.information(self, self.tr("Export PDF"), self.tr("Exported to {path}").format(path=path))


class PrintDialog(_PrintDialogBase):
    def __init__(self, project: Project, parent=None, start_dir: str = ""):
        super().__init__(parent, start_dir)
        self.setWindowTitle(self.tr("Print"))
        self.project = project

        disc_scene = project.pages[PAGE_DISC]
        cover_scene = project.pages[PAGE_COVER]
        # Cropped to the template's own physical cut-shape bounds, not the
        # full padded render -- see crop_to_template_bounds()'s docstring
        # for why the discarded margin is safe to remove for packing
        # purposes (it's guaranteed-transparent and has no physical
        # cutting significance) and why this matters (it's what lets
        # Copies pack noticeably tighter than treating each label's full
        # padded render as its footprint).
        self._disc_raw = crop_to_template_bounds(disc_scene, render_scene_to_image(disc_scene, dpi=self._dpi), self._dpi)
        self._cover_raw = crop_to_template_bounds(
            cover_scene, render_scene_to_image(cover_scene, dpi=self._dpi), self._dpi
        )
        self._disc_size_mm = image_physical_size_mm(self._disc_raw, self._dpi)
        self._cover_size_mm = image_physical_size_mm(self._cover_raw, self._dpi)
        self._disc_items: list[_LabelItem] = []
        self._cover_items: list[_LabelItem] = []

        self.copies_spin = QSpinBox()
        self.copies_spin.setRange(1, MAX_COPIES)
        self.copies_spin.setValue(1)
        self.copies_spin.valueChanged.connect(self._relayout_copies)

        # A CD project cannot put both its pages on one sheet at all: the
        # folded insert is 242mm wide and the label 118mm, which exceeds
        # A4's 287mm printable length even laid side by side in landscape.
        # Rather than let that degrade into the overflow-corner fallback,
        # each label can have a sheet of its own.
        self.separate_sheets_check = QCheckBox(self.tr("Each label on its own sheet"))
        self.separate_sheets_check.toggled.connect(self._on_separate_sheets_toggled)
        self._options_form.addRow(self.separate_sheets_check)

        self.sheet_combo = QComboBox()
        self.sheet_combo.currentIndexChanged.connect(self._show_current_sheet)
        self._options_form.addRow(self.tr("Showing"), self.sheet_combo)
        self._options_form.setRowVisible(self.sheet_combo, False)
        self._options_form.addRow(self.tr("Copies"), self.copies_spin)

        self._build_grayscale_controls(project.grayscale_adjustment)
        self._build_page_view()
        self._build_action_buttons()

        self._relayout_copies()

    def _all_items(self) -> list[_LabelItem]:
        return self._disc_items + self._cover_items

    def sheets(self) -> list[list[_LabelItem]]:
        """One sheet, or one per label type.

        The preview shows a single sheet at a time (the one the Showing box
        names), but printing and both exports walk all of them -- so what
        is on screen is always *a* page that will come out, never a
        composite of pages that will not.
        """
        if not self.separate_sheets_check.isChecked():
            return [self._all_items()]
        return [list(self._disc_items), list(self._cover_items)]

    def _on_separate_sheets_toggled(self) -> None:
        separate = self.separate_sheets_check.isChecked()
        self._options_form.setRowVisible(self.sheet_combo, separate)
        self._relayout_copies()

    def _refresh_sheet_combo(self) -> None:
        previous = self.sheet_combo.currentIndex()
        self.sheet_combo.blockSignals(True)
        self.sheet_combo.clear()
        self.sheet_combo.addItem(self.tr("Sheet 1 -- disc label"))
        self.sheet_combo.addItem(self.tr("Sheet 2 -- cover"))
        self.sheet_combo.setCurrentIndex(max(0, min(previous, 1)))
        self.sheet_combo.blockSignals(False)

    def _show_current_sheet(self) -> None:
        """Hides the labels belonging to the other sheet.

        Hidden rather than removed: they keep their positions, their
        rotation and their images, so flipping back and forth costs
        nothing and cannot lose a copy.
        """
        if not self.separate_sheets_check.isChecked():
            for item in self._all_items():
                item.setVisible(True)
            return
        showing_disc = self.sheet_combo.currentIndex() == 0
        for item in self._disc_items:
            item.setVisible(showing_disc)
        for item in self._cover_items:
            item.setVisible(not showing_disc)

    def _maybe_save_grayscale_adjustment(self) -> None:
        if self.grayscale_check.isChecked():
            self.project.grayscale_adjustment = GrayscaleAdjustment(
                brightness=self.brightness_slider.value(), contrast=self.contrast_slider.value()
            )

    def _on_page_size_changed(self) -> None:
        super()._on_page_size_changed()
        self._relayout_copies()

    def _relayout_copies(self) -> None:
        """Re-packs Copies-many disc/cover copies into a fresh grid (see
        printing.build_copies_layout) every time the copy count or page
        size changes -- any manual dragging/rotation done before this
        point is discarded, since there's no way to know how a changed
        copy count should reuse a previous, different-count arrangement.

        A copy count that can't be arranged automatically (even after
        trying to rotate labels to fit, or arrange the disc/cover grids
        side by side instead of stacked -- see printing.py's
        _ARRANGEMENTS/_ROTATION_COMBOS) is never treated as a hard error:
        as many copies as *do* fit get the nice grid, via
        _layout_with_overflow_at_corner below, and the rest are simply
        placed in the page's top-left corner, stacked on top of each
        other, for the user to drag (and right-click to rotate) into
        place by hand -- a simple grid packer can't discover every tight,
        freeform arrangement a person can find manually, and there's no
        reason to block the user from reaching one themselves."""
        copies = self.copies_spin.value()
        page_size_mm = self.page_size_mm()

        if self.separate_sheets_check.isChecked():
            self._relayout_separate_sheets(copies, page_size_mm)
            return

        try:
            disc_copies, cover_copies = build_copies_layout(
                self._disc_size_mm, self._cover_size_mm, copies, page_size_mm, self.MARGIN_MM
            )
        except PrintLayoutError:
            fits = max_copies_that_fit(self._disc_size_mm, self._cover_size_mm, page_size_mm, self.MARGIN_MM)
            disc_copies, cover_copies = self._layout_with_overflow_at_corner(copies, fits, page_size_mm)
            QMessageBox.warning(
                self,
                self.tr("Print"),
                self.tr(
                    "Only {fits} of {copies} copies could be arranged automatically. The rest have been placed"
                    " in the top-left corner -- drag them into place, and right-click a label to rotate it 90"
                    " degrees."
                ).format(fits=fits, copies=copies),
            )

        self._rebuild_items(disc_copies, cover_copies)
        self._show_current_sheet()

    def _relayout_separate_sheets(self, copies: int, page_size_mm: tuple[float, float]) -> None:
        """Each label packed onto a page of its own.

        Simpler than the shared-sheet case in every way except one: a label
        can be too big for the page even on its own (a 242mm insert on a
        portrait A4 fits only turned a quarter turn, and would not fit at
        all if it were any wider). That is reported once, naming the label
        and suggesting the other orientation, rather than silently piling
        copies in the corner -- there is nothing to drag them into.
        """
        placed = []
        too_big = []
        for name, size_mm in (
            (self.tr("disc label"), self._disc_size_mm),
            (self.tr("cover"), self._cover_size_mm),
        ):
            try:
                placed.append(build_sheet_layout(size_mm, copies, page_size_mm, self.MARGIN_MM))
                continue
            except PrintLayoutError:
                pass
            fits = max_copies_on_sheet(size_mm, page_size_mm, self.MARGIN_MM)
            if fits:
                placed.append(build_sheet_layout(size_mm, fits, page_size_mm, self.MARGIN_MM))
            else:
                placed.append(PlacedCopies([], False))
            too_big.append((name, fits))

        self._rebuild_items(placed[0], placed[1])
        self._refresh_sheet_combo()
        self._show_current_sheet()

        if too_big:
            QMessageBox.warning(
                self,
                self.tr("Print"),
                self.tr(
                    "This page holds at most {fits} of the {label}, not {copies}. Try the other orientation, "
                    "or print fewer at a time."
                ).format(fits=too_big[0][1], label=too_big[0][0], copies=copies),
            )

    def _layout_with_overflow_at_corner(
        self, copies: int, fits: int, page_size_mm: tuple[float, float]
    ) -> tuple[PlacedCopies, PlacedCopies]:
        """The first `fits` copies of each label get printing.py's own
        best automatic arrangement; every copy beyond that is stacked at
        the page's top-left corner (MARGIN_MM, MARGIN_MM) rather than
        left unplaced -- overflow copies inherit the fitting grid's own
        rotation decision as a starting point (a reasonable default, and
        one right-click away from being changed if it doesn't suit that
        particular copy)."""
        if fits > 0:
            disc_copies, cover_copies = build_copies_layout(
                self._disc_size_mm, self._cover_size_mm, fits, page_size_mm, self.MARGIN_MM
            )
        else:
            disc_copies, cover_copies = PlacedCopies([], False), PlacedCopies([], False)

        overflow = copies - fits
        corner = (self.MARGIN_MM, self.MARGIN_MM)
        return (
            PlacedCopies(disc_copies.positions + [corner] * overflow, disc_copies.rotated),
            PlacedCopies(cover_copies.positions + [corner] * overflow, cover_copies.rotated),
        )

    def _rebuild_items(self, disc_copies: PlacedCopies, cover_copies: PlacedCopies) -> None:
        """Turns a fresh printing.build_copies_layout() (or
        _layout_with_overflow_at_corner()) result into actual scene
        items, each seeded with that grid's `rotated` flag as its
        starting orientation -- individually right-click-rotatable from
        there on (see _LabelItem.contextMenuEvent)."""
        for item in self._disc_items + self._cover_items:
            self.page_scene.removeItem(item)

        self._disc_items = [
            self._make_item(self._disc_raw, self._disc_size_mm, disc_copies.rotated) for _ in disc_copies.positions
        ]
        self._cover_items = [
            self._make_item(self._cover_raw, self._cover_size_mm, cover_copies.rotated)
            for _ in cover_copies.positions
        ]
        for item, (x_mm, y_mm) in zip(self._disc_items, disc_copies.positions):
            self.page_scene.addItem(item)
            item.setPos(x_mm * self.PREVIEW_PX_PER_MM, y_mm * self.PREVIEW_PX_PER_MM)
        for item, (x_mm, y_mm) in zip(self._cover_items, cover_copies.positions):
            self.page_scene.addItem(item)
            item.setPos(x_mm * self.PREVIEW_PX_PER_MM, y_mm * self.PREVIEW_PX_PER_MM)

        self._update_displayed_images()


class MultiprintDialog(_PrintDialogBase):
    """Launched from the startup screen (panels/startup_dialog.py's
    "Multiprint..." button), not from an already-open project -- lets the
    user combine disc+cover artwork from several *different* saved
    .mdproj files onto one physical page, e.g. batch-printing a handful
    of one-off leftover labels together instead of one project's Copies
    at a time.

    Starts with an empty page; Add.../Delete are what put items on it
    instead of a Copies spinbox -- there's deliberately no copy/clone
    concept here (per explicit request), since every added project's
    artwork is a one-off addition, not N copies of one fixed pair the way
    PrintDialog's Copies spinbox works. Each Add loads one .mdproj file
    and adds its disc *and* cover as two new, independently draggable/
    rotatable items (dropped at the page's top-left corner, same
    "overflow copy" convention PrintDialog uses -- see its own
    _layout_with_overflow_at_corner -- since there's no automatic
    arrangement to place them any more precisely than that); Delete
    removes whichever item(s) are currently selected. Print.../Export
    PDF.../Export PNG... and the grayscale/brightness/contrast controls
    are the exact same inherited machinery PrintDialog uses -- see
    _PrintDialogBase."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Multiprint"))
        self._items: list[_LabelItem] = []

        add_delete_row = QHBoxLayout()
        self.add_button = QPushButton(self.tr("Add..."))
        self.add_button.clicked.connect(self._on_add)
        self.delete_button = QPushButton(self.tr("Delete"))
        self.delete_button.clicked.connect(self._on_delete)
        add_delete_row.addWidget(self.add_button)
        add_delete_row.addWidget(self.delete_button)
        self._options_form.addRow(add_delete_row)

        self._build_grayscale_controls(GrayscaleAdjustment())
        self._build_page_view()
        self._build_action_buttons()

    def _all_items(self) -> list[_LabelItem]:
        return self._items

    def _on_add(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("Add Project"), user_paths.project_start_path(None), self.tr("MDTools Project (*.mdproj)")
        )
        if not path:
            return
        try:
            project = load_project(path)
        except Exception as exc:
            QMessageBox.critical(self, self.tr("Add Project"), self.tr("Could not open project:\n{error}").format(error=exc))
            return

        corner_px = (self.MARGIN_MM * self.PREVIEW_PX_PER_MM, self.MARGIN_MM * self.PREVIEW_PX_PER_MM)
        for scene in (project.pages[PAGE_DISC], project.pages[PAGE_COVER]):
            raw_image = crop_to_template_bounds(scene, render_scene_to_image(scene, dpi=self._dpi), self._dpi)
            size_mm = image_physical_size_mm(raw_image, self._dpi)
            item = self._make_item(raw_image, size_mm, rotated=False)
            self.page_scene.addItem(item)
            item.setPos(*corner_px)
            self._items.append(item)

        self._update_displayed_images()

    def _on_delete(self) -> None:
        for item in self.page_scene.selectedItems():
            if item in self._items:
                self.page_scene.removeItem(item)
                self._items.remove(item)
