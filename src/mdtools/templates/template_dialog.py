"""Template Manager: view/edit the disc & cover templates used for "New"."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mdtools.project import MEDIUM_CD, MEDIUM_MD
from mdtools.templates import registry
from mdtools.templates.models import CoverTemplate, DiscTemplate


class TemplateManagerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Template Manager"))
        self.resize(560, 380)

        self.templates = registry.load_templates()

        root = QHBoxLayout(self)

        left = QVBoxLayout()
        self.list_widget = QListWidget()
        self.list_widget.currentRowChanged.connect(self._on_selection_changed)
        left.addWidget(self.list_widget)

        btn_row = QHBoxLayout()
        add_disc_btn = QPushButton(self.tr("+ Disc"))
        add_disc_btn.clicked.connect(self._add_disc)
        add_cover_btn = QPushButton(self.tr("+ Cover"))
        add_cover_btn.clicked.connect(self._add_cover)
        self.del_btn = QPushButton(self.tr("Delete"))
        self.del_btn.clicked.connect(self._delete_selected)
        btn_row.addWidget(add_disc_btn)
        btn_row.addWidget(add_cover_btn)
        btn_row.addWidget(self.del_btn)
        left.addLayout(btn_row)
        root.addLayout(left, 1)

        self.editor_container = QWidget()
        self.editor_layout = QVBoxLayout(self.editor_container)
        self.editor_layout.addWidget(QLabel(self.tr("Select a template to edit.")))
        root.addWidget(self.editor_container, 2)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        outer = QVBoxLayout()
        outer.addLayout(root)
        outer.addWidget(buttons)
        self.setLayout(outer)

        self._refresh_list()

    def _builtin_suffix(self, builtin: bool) -> str:
        return self.tr(" [built-in]") if builtin else ""

    def _refresh_list(self, select_index: int | None = None) -> None:
        self.list_widget.blockSignals(True)
        self.list_widget.clear()
        for t in self.templates["disc"]:
            item = QListWidgetItem(self.tr("Disc: {name}").format(name=t.name) + self._builtin_suffix(t.builtin))
            item.setData(1, ("disc", t))
            self.list_widget.addItem(item)
        for t in self.templates["cover"]:
            item = QListWidgetItem(self.tr("Cover: {name}").format(name=t.name) + self._builtin_suffix(t.builtin))
            item.setData(1, ("cover", t))
            self.list_widget.addItem(item)
        self.list_widget.blockSignals(False)
        if select_index is not None and 0 <= select_index < self.list_widget.count():
            self.list_widget.setCurrentRow(select_index)

    def _add_disc(self) -> None:
        self.templates["disc"].append(DiscTemplate(name=self.tr("New Disc"), width_mm=37.0, height_mm=52.0))
        # discs are listed before covers, so the new disc's row is its index within the disc list
        self._refresh_list(select_index=len(self.templates["disc"]) - 1)

    def _add_cover(self) -> None:
        self.templates["cover"].append(CoverTemplate(name=self.tr("New Cover"), width_mm=100.0, height_mm=60.0))
        # covers are listed after all discs, so the new cover's row comes after the full disc list
        self._refresh_list(select_index=len(self.templates["disc"]) + len(self.templates["cover"]) - 1)

    def _delete_selected(self) -> None:
        row = self.list_widget.currentRow()
        if row < 0:
            return
        kind, template = self.list_widget.item(row).data(1)
        if template.builtin:
            QMessageBox.information(
                self, self.tr("Can't Delete"), self.tr("Built-in templates can't be deleted, only edited.")
            )
            return
        self.templates[kind].remove(template)
        self._refresh_list()

    def _on_selection_changed(self, row: int) -> None:
        while self.editor_layout.count():
            child = self.editor_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        if row < 0:
            self.editor_layout.addWidget(QLabel(self.tr("Select a template to edit.")))
            self.del_btn.setEnabled(False)
            return
        kind, template = self.list_widget.item(row).data(1)
        self.del_btn.setEnabled(not template.builtin)
        form_widget = QWidget()
        form = QFormLayout(form_widget)

        name_edit = QLineEdit(template.name)
        name_edit.textChanged.connect(lambda v: (setattr(template, "name", v), self._relabel(row, kind, v)))
        form.addRow(self.tr("Name"), name_edit)

        # Which medium's File > New offers this template at all. Selected by
        # data rather than index for the same reason the shape combo below
        # is: setting the index fires the change signal, so a lookup that
        # missed would rewrite the value it was meant to display.
        medium_combo = QComboBox()
        medium_combo.addItem(self.tr("MiniDisc"), MEDIUM_MD)
        medium_combo.addItem(self.tr("CD-R"), MEDIUM_CD)
        medium_index = medium_combo.findData(template.medium)
        medium_combo.setCurrentIndex(medium_index if medium_index >= 0 else 0)
        medium_combo.currentIndexChanged.connect(
            lambda index: setattr(template, "medium", medium_combo.itemData(index))
        )
        form.addRow(self.tr("Medium"), medium_combo)

        if template.items:
            form.addRow(
                self.tr("Layers"),
                QLabel(self.tr("{count} pre-made layer(s) included").format(count=len(template.items))),
            )

        def spin(value: float, minimum=0.0, maximum=500.0) -> QDoubleSpinBox:
            box = QDoubleSpinBox()
            box.setRange(minimum, maximum)
            box.setDecimals(2)
            box.setSuffix(" mm")
            box.setValue(value)
            return box

        if kind == "disc":
            width = spin(template.width_mm, maximum=200.0)
            width.valueChanged.connect(lambda v: setattr(template, "width_mm", v))
            form.addRow(self.tr("Width"), width)

            height = spin(template.height_mm, maximum=200.0)
            height.valueChanged.connect(lambda v: setattr(template, "height_mm", v))
            form.addRow(self.tr("Height"), height)

            shape_combo = QComboBox()
            shape_combo.addItem(self.tr("Sticker (chamfer + fillet)"), "sticker")
            shape_combo.addItem(self.tr("Full disc label (rounded rect + slider notch)"), "full_label")
            shape_combo.addItem(self.tr("CD disc label (circle + spindle hole)"), "cd_label")
            # Selected by data, never by index: picking "whatever isn't
            # sticker" would land a cd_label template on the full_label entry
            # and -- because setting the index fires currentIndexChanged --
            # rewrite its shape to match, turning a CD label into a MiniDisc
            # one just by opening this dialog.
            shape_index = shape_combo.findData(template.shape)
            shape_combo.setCurrentIndex(shape_index if shape_index >= 0 else 0)
            form.addRow(self.tr("Shape"), shape_combo)

            chamfer = spin(template.chamfer_mm, maximum=20.0)
            chamfer.valueChanged.connect(lambda v: setattr(template, "chamfer_mm", v))
            form.addRow(self.tr("Top-left chamfer"), chamfer)

            fillet = spin(template.fillet_mm, maximum=20.0)
            fillet.valueChanged.connect(lambda v: setattr(template, "fillet_mm", v))
            form.addRow(self.tr("Other corners' fillet"), fillet)

            slider_w = spin(template.slider_width_mm, maximum=100.0)
            slider_w.valueChanged.connect(lambda v: setattr(template, "slider_width_mm", v))
            form.addRow(self.tr("Slider label width (0 = none)"), slider_w)

            slider_h = spin(template.slider_height_mm, maximum=100.0)
            slider_h.valueChanged.connect(lambda v: setattr(template, "slider_height_mm", v))
            form.addRow(self.tr("Slider label height (0 = none)"), slider_h)

            slider_r = spin(template.slider_corner_radius_mm, maximum=50.0)
            slider_r.valueChanged.connect(lambda v: setattr(template, "slider_corner_radius_mm", v))
            form.addRow(self.tr("Slider label corner radius (left corners)"), slider_r)

            slider_gap = spin(template.slider_gap_mm, maximum=100.0)
            slider_gap.valueChanged.connect(lambda v: setattr(template, "slider_gap_mm", v))
            form.addRow(self.tr("Slider label gap from disc"), slider_gap)

            full_label_radius = spin(template.corner_radius_mm, maximum=50.0)
            full_label_radius.valueChanged.connect(lambda v: setattr(template, "corner_radius_mm", v))
            form.addRow(self.tr("Corner radius (full disc label)"), full_label_radius)

            notch_w = spin(template.slider_notch_width_mm, maximum=100.0)
            notch_w.valueChanged.connect(lambda v: setattr(template, "slider_notch_width_mm", v))
            form.addRow(self.tr("Slider notch width (0 = none)"), notch_w)

            notch_h = spin(template.slider_notch_height_mm, maximum=100.0)
            notch_h.valueChanged.connect(lambda v: setattr(template, "slider_notch_height_mm", v))
            form.addRow(self.tr("Slider notch height (0 = none)"), notch_h)

            notch_r = spin(template.slider_notch_corner_radius_mm, maximum=50.0)
            notch_r.valueChanged.connect(lambda v: setattr(template, "slider_notch_corner_radius_mm", v))
            form.addRow(self.tr("Slider notch corner radius (left corners)"), notch_r)

            notch_top = spin(template.slider_notch_top_mm, maximum=200.0)
            notch_top.valueChanged.connect(lambda v: setattr(template, "slider_notch_top_mm", v))
            form.addRow(self.tr("Slider notch distance from top"), notch_top)

            notch_buffer = spin(template.slider_notch_buffer_mm, maximum=20.0)
            notch_buffer.valueChanged.connect(lambda v: setattr(template, "slider_notch_buffer_mm", v))
            form.addRow(self.tr("Slider notch clearance buffer"), notch_buffer)

            travel = spin(template.slider_travel_mm, maximum=200.0)
            travel.valueChanged.connect(lambda v: setattr(template, "slider_travel_mm", v))
            form.addRow(self.tr("Slider travel channel length"), travel)

            outer_diameter = spin(template.outer_diameter_mm, maximum=200.0)
            outer_diameter.valueChanged.connect(lambda v: setattr(template, "outer_diameter_mm", v))
            form.addRow(self.tr("Outer diameter (CD label)"), outer_diameter)

            hole_diameter = spin(template.hole_diameter_mm, maximum=200.0)
            hole_diameter.valueChanged.connect(lambda v: setattr(template, "hole_diameter_mm", v))
            form.addRow(self.tr("Spindle hole diameter (0 = none)"), hole_diameter)

            # slider_w/h/r are shared: for "sticker" they size the shape
            # placed beside the disc; for "full_label" they size the shape
            # nested inside the notch -- so they stay visible either way.
            sticker_rows = [chamfer, fillet, slider_gap]
            full_label_rows = [full_label_radius, notch_w, notch_h, notch_r, notch_top, notch_buffer, travel]
            cd_rows = [outer_diameter, hole_diameter]
            # A CD has no cartridge, so nothing about a slider applies to it.
            slider_rows = [slider_w, slider_h, slider_r]

            def update_shape_visibility(shape: str) -> None:
                for row_widget in sticker_rows:
                    form.setRowVisible(row_widget, shape == "sticker")
                for row_widget in full_label_rows:
                    form.setRowVisible(row_widget, shape == "full_label")
                for row_widget in cd_rows:
                    form.setRowVisible(row_widget, shape == "cd_label")
                for row_widget in slider_rows:
                    form.setRowVisible(row_widget, shape != "cd_label")

            def on_shape_changed(index: int) -> None:
                shape = shape_combo.itemData(index)
                template.shape = shape
                update_shape_visibility(shape)

            shape_combo.currentIndexChanged.connect(on_shape_changed)
            update_shape_visibility(template.shape)
        else:
            width = spin(template.width_mm, maximum=1000.0)
            width.valueChanged.connect(lambda v: setattr(template, "width_mm", v))
            form.addRow(self.tr("Width"), width)

            height = spin(template.height_mm, maximum=1000.0)
            height.valueChanged.connect(lambda v: setattr(template, "height_mm", v))
            form.addRow(self.tr("Height"), height)

            radius = spin(template.corner_radius_mm, maximum=50.0)
            radius.valueChanged.connect(lambda v: setattr(template, "corner_radius_mm", v))
            form.addRow(self.tr("Corner radius"), radius)

            folds_edit = QLineEdit(", ".join(str(v) for v in template.fold_offsets_mm))
            folds_edit.setPlaceholderText(self.tr("e.g. 68, 73  (fold-line positions from the left edge)"))

            def apply_folds(text: str) -> None:
                try:
                    template.fold_offsets_mm = [float(v.strip()) for v in text.split(",") if v.strip()]
                except ValueError:
                    pass

            folds_edit.textChanged.connect(apply_folds)
            form.addRow(self.tr("Fold lines (mm)"), folds_edit)

            cutout_w = spin(template.cutout_width_mm, maximum=200.0)
            cutout_w.valueChanged.connect(lambda v: setattr(template, "cutout_width_mm", v))
            form.addRow(self.tr("Cutout width (0 = none)"), cutout_w)

            cutout_h = spin(template.cutout_height_mm, maximum=200.0)
            cutout_h.valueChanged.connect(lambda v: setattr(template, "cutout_height_mm", v))
            form.addRow(self.tr("Cutout height (0 = none)"), cutout_h)

            cutout_r = spin(template.cutout_radius_mm, maximum=50.0)
            cutout_r.valueChanged.connect(lambda v: setattr(template, "cutout_radius_mm", v))
            form.addRow(self.tr("Cutout corner radius"), cutout_r)

            cutout_side = QComboBox()
            cutout_side.addItem(self.tr("Left of left fold"), "left")
            cutout_side.addItem(self.tr("Right of right fold"), "right")
            cutout_side.setCurrentIndex(0 if template.cutout_side == "left" else 1)
            cutout_side.currentIndexChanged.connect(
                lambda i: setattr(template, "cutout_side", cutout_side.itemData(i))
            )
            form.addRow(self.tr("Cutout side"), cutout_side)

            cutout_from_fold = spin(template.cutout_from_fold_mm, minimum=-500.0, maximum=500.0)
            cutout_from_fold.valueChanged.connect(lambda v: setattr(template, "cutout_from_fold_mm", v))
            form.addRow(self.tr("Cutout distance from that fold"), cutout_from_fold)

            cutout_from_bottom = spin(template.cutout_from_bottom_mm, minimum=-500.0, maximum=500.0)
            cutout_from_bottom.valueChanged.connect(lambda v: setattr(template, "cutout_from_bottom_mm", v))
            form.addRow(self.tr("Cutout distance from bottom"), cutout_from_bottom)

        verified = QCheckBox(self.tr("Verified against real media/case"))
        verified.setChecked(template.verified)
        verified.toggled.connect(lambda v: setattr(template, "verified", v))
        form.addRow(verified)

        self.editor_layout.addWidget(form_widget)

    def _relabel(self, row: int, kind: str, name: str) -> None:
        _, template = self.list_widget.item(row).data(1)
        suffix = self._builtin_suffix(template.builtin)
        label = self.tr("Disc: {name}") if kind == "disc" else self.tr("Cover: {name}")
        self.list_widget.item(row).setText(label.format(name=name) + suffix)

    def _on_accept(self) -> None:
        registry.save_templates(self.templates)
        self.accept()
