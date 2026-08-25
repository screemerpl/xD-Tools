from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QDoubleSpinBox,
    QFontDialog,
    QFormLayout,
    QGraphicsEllipseItem,
    QGraphicsRectItem,
    QGraphicsTextItem,
    QHBoxLayout,
    QPlainTextEdit,
    QPushButton,
    QWidget,
)

from mdtools.canvas.items import (
    get_item_scale,
    get_text_glow,
    get_text_shadow,
    set_item_scale,
    set_text_glow,
    set_text_shadow,
)
from mdtools.canvas.scene import DEFAULT_RECT_FILL_HEX
from mdtools.commands import PropertyEditCommand
from mdtools.constants import px_to_mm, mm_to_px
from mdtools.project import TextStyle

FILLABLE_SHAPES = (QGraphicsEllipseItem, QGraphicsRectItem)

EXTRA_MINIMUM_WIDTH_PX = 40


# -- apply callbacks for PropertyEditCommand --------------------------------
# Each is called both for live editing (directly, by the handler below) and
# for actual undo()/redo() navigation later -- see PropertyEditCommand.


def _set_pos(item, value: tuple[float, float]) -> None:
    item.setPos(*value)


def _set_rotation(item, value: float) -> None:
    item.setRotation(value)


def _set_text(item, value: str) -> None:
    item.setPlainText(value)
    item.setTransformOriginPoint(item.boundingRect().center())


def _set_font_size(item, value: float) -> None:
    font = item.font()
    font.setPointSizeF(value)
    item.setFont(font)
    item.setTransformOriginPoint(item.boundingRect().center())


def _set_font(item, value: QFont) -> None:
    item.setFont(QFont(value))
    item.setTransformOriginPoint(item.boundingRect().center())


def _set_text_color(item, value: str) -> None:
    item.setDefaultTextColor(QColor(value))


def _set_fill_color(item, value: str) -> None:
    color = QColor(value)
    brush = item.brush()
    brush.setColor(color)
    brush.setStyle(Qt.BrushStyle.SolidPattern)
    item.setBrush(brush)
    # the frame always matches the fill -- there's no separate "frame
    # color" control, so keep the two from ever visibly diverging.
    pen = item.pen()
    pen.setColor(color)
    item.setPen(pen)


def _snapshot_for_reset(item) -> dict:
    snap = {"rotation": item.rotation(), "scale": get_item_scale(item)}
    if isinstance(item, QGraphicsTextItem):
        snap["font_spec"] = item.font().toString()
        snap["color"] = item.defaultTextColor().name()
    elif isinstance(item, QGraphicsRectItem):
        snap["brush_color"] = item.brush().color().name()
        snap["pen_color"] = item.pen().color().name()
    elif isinstance(item, QGraphicsEllipseItem):
        snap["brush_style"] = item.brush().style()
        snap["pen_color"] = item.pen().color().name()
    return snap


def _apply_reset_snapshot(item, snap: dict) -> None:
    item.setRotation(snap["rotation"])
    set_item_scale(item, *snap["scale"])
    if isinstance(item, QGraphicsTextItem) and "font_spec" in snap:
        font = QFont()
        font.fromString(snap["font_spec"])
        item.setFont(font)
        item.setDefaultTextColor(QColor(snap["color"]))
        item.setTransformOriginPoint(item.boundingRect().center())
    elif isinstance(item, QGraphicsRectItem) and "brush_color" in snap:
        brush = item.brush()
        brush.setColor(QColor(snap["brush_color"]))
        brush.setStyle(Qt.BrushStyle.SolidPattern)
        item.setBrush(brush)
        pen = item.pen()
        pen.setColor(QColor(snap["pen_color"]))
        item.setPen(pen)
    elif isinstance(item, QGraphicsEllipseItem) and "brush_style" in snap:
        brush = item.brush()
        brush.setStyle(snap["brush_style"])
        item.setBrush(brush)
        pen = item.pen()
        pen.setColor(QColor(snap["pen_color"]))
        item.setPen(pen)


class PropertiesPanel(QWidget):
    """Editor for the currently selected item's position/rotation and,
    for supported item types, its text/font/color -- only the rows that
    actually apply to the selected item's type are shown."""

    # Emitted whenever the user changes a text item's font/size/color here,
    # so MainWindow can remember it as the project's new default for the
    # *next* text layer created (see app_window._apply_default_text_style).
    text_style_changed = Signal(object)  # TextStyle

    # Emitted when "Probe..." is clicked; MainWindow wires this to
    # DesignView.start_color_probe(), and DesignView.color_probed back to
    # apply_probed_color() below -- PropertiesPanel doesn't reach into the
    # view directly, matching how every other cross-widget interaction in
    # this app is wired through MainWindow rather than direct references.
    probe_color_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._item = None
        self._updating = False
        self._default_text_style = TextStyle()
        # Set by MainWindow after construction; None means "no undo history"
        # (matches DesignView.undo_stack -- standalone/test usage still works).
        self.undo_stack = None

        self.form = QFormLayout(self)

        self.x_spin = QDoubleSpinBox()
        self.x_spin.setRange(-1000, 1000)
        self.x_spin.setSuffix(" mm")
        self.x_spin.valueChanged.connect(self._apply_position)
        self.form.addRow(self.tr("X"), self.x_spin)

        self.y_spin = QDoubleSpinBox()
        self.y_spin.setRange(-1000, 1000)
        self.y_spin.setSuffix(" mm")
        self.y_spin.valueChanged.connect(self._apply_position)
        self.form.addRow(self.tr("Y"), self.y_spin)

        self.rotation_spin = QDoubleSpinBox()
        self.rotation_spin.setRange(-360, 360)
        self.rotation_spin.setSuffix(" deg")
        self.rotation_spin.valueChanged.connect(self._apply_rotation)
        self.form.addRow(self.tr("Rotation"), self.rotation_spin)

        self.text_edit = QPlainTextEdit()
        self.text_edit.setMaximumHeight(80)  # a few lines -- text items are usually short labels, not essays
        self.text_edit.textChanged.connect(self._apply_text)
        self.form.addRow(self.tr("Text"), self.text_edit)

        self.font_size_spin = QDoubleSpinBox()
        self.font_size_spin.setRange(1, 500)
        self.font_size_spin.setSuffix(" pt")
        self.font_size_spin.valueChanged.connect(self._apply_font_size)
        self.form.addRow(self.tr("Font size"), self.font_size_spin)

        self.font_btn = QPushButton(self.tr("Font..."))
        self.font_btn.clicked.connect(self._pick_font)
        self.form.addRow(self.tr("Font"), self.font_btn)

        self.color_btn = QPushButton(self.tr("Color..."))
        self.color_btn.clicked.connect(self._pick_color)
        self.probe_btn = QPushButton(self.tr("Probe..."))
        self.probe_btn.setToolTip(self.tr("Click, then pick any color straight off the canvas"))
        self.probe_btn.clicked.connect(self.probe_color_requested)
        self.color_row = QWidget()
        color_row_layout = QHBoxLayout(self.color_row)
        color_row_layout.setContentsMargins(0, 0, 0, 0)
        color_row_layout.addWidget(self.color_btn)
        color_row_layout.addWidget(self.probe_btn)
        self.form.addRow(self.tr("Color"), self.color_row)

        self.shadow_check = QCheckBox()
        self.shadow_check.toggled.connect(self._apply_shadow)
        self.form.addRow(self.tr("Shadow"), self.shadow_check)

        self.glow_check = QCheckBox()
        self.glow_check.toggled.connect(self._apply_glow)
        self.form.addRow(self.tr("Glow"), self.glow_check)

        self.reset_btn = QPushButton(self.tr("Reset to Default"))
        self.reset_btn.clicked.connect(self._reset_to_default)
        self.form.addRow(self.reset_btn)

        self.setEnabled(False)
        # 40px wider than the layout would otherwise settle on -- some rows
        # (e.g. the X/Y spinboxes with an " mm" suffix) were cramped enough
        # to make setting a precise value fiddly at the panel's natural
        # minimum width.
        self.setMinimumWidth(self.minimumSizeHint().width() + EXTRA_MINIMUM_WIDTH_PX)

    def set_default_text_style(self, style: TextStyle) -> None:
        """Called by MainWindow whenever the project's default text style
        changes (including on project load/new-project), so "Reset to
        Default" resets to the *current* project default, not a stale one."""
        self._default_text_style = style

    def set_item(self, item) -> None:
        self._item = item
        self._updating = True
        try:
            if item is None:
                self.setEnabled(False)
                return
            self.setEnabled(True)
            self.x_spin.setValue(px_to_mm(item.x()))
            self.y_spin.setValue(px_to_mm(item.y()))
            self.rotation_spin.setValue(item.rotation())

            is_text = isinstance(item, QGraphicsTextItem)
            is_fillable = isinstance(item, FILLABLE_SHAPES)

            self.form.setRowVisible(self.text_edit, is_text)
            self.form.setRowVisible(self.font_size_spin, is_text)
            self.form.setRowVisible(self.font_btn, is_text)
            self.form.setRowVisible(self.color_row, is_text or is_fillable)
            self.form.setRowVisible(self.shadow_check, is_text)
            self.form.setRowVisible(self.glow_check, is_text)

            if is_text:
                self.text_edit.setPlainText(item.toPlainText())
                self.font_size_spin.setValue(item.font().pointSizeF())
                self.shadow_check.setChecked(get_text_shadow(item))
                self.glow_check.setChecked(get_text_glow(item))
        finally:
            self._updating = False

    def _push(self, field: str, apply_fn, before, after, text: str) -> None:
        if self.undo_stack is None or before == after:
            return
        self.undo_stack.push(PropertyEditCommand(self._item, field, apply_fn, before, after, text))

    def _apply_position(self) -> None:
        if self._updating or self._item is None:
            return
        before = (self._item.x(), self._item.y())
        after = (mm_to_px(self.x_spin.value()), mm_to_px(self.y_spin.value()))
        _set_pos(self._item, after)
        self._push("pos", _set_pos, before, after, self.tr("Move"))

    def _apply_rotation(self) -> None:
        if self._updating or self._item is None:
            return
        before = self._item.rotation()
        after = self.rotation_spin.value()
        _set_rotation(self._item, after)
        self._push("rotation", _set_rotation, before, after, self.tr("Rotate"))

    def _apply_text(self) -> None:
        if self._updating or self._item is None:
            return
        if isinstance(self._item, QGraphicsTextItem):
            before = self._item.toPlainText()
            after = self.text_edit.toPlainText()
            _set_text(self._item, after)
            self._push("text", _set_text, before, after, self.tr("Edit Text"))

    def _apply_font_size(self) -> None:
        if self._updating or self._item is None:
            return
        if isinstance(self._item, QGraphicsTextItem):
            before = self._item.font().pointSizeF()
            after = self.font_size_spin.value()
            _set_font_size(self._item, after)
            self._push("font_size", _set_font_size, before, after, self.tr("Change Font Size"))
            self._emit_text_style_changed()

    def _pick_font(self) -> None:
        if self._item is None or not isinstance(self._item, QGraphicsTextItem):
            return
        # PySide6's QFontDialog.getFont returns (ok, font) here, not (font, ok)
        # as PyQt/older-Qt docs might suggest -- confirmed empirically.
        ok, font = QFontDialog.getFont(self._item.font(), self)
        if not ok:
            return
        before = QFont(self._item.font())
        after = QFont(font)
        _set_font(self._item, after)
        self._push("font", _set_font, before, after, self.tr("Change Font"))
        self._updating = True
        try:
            self.font_size_spin.setValue(font.pointSizeF())
        finally:
            self._updating = False
        self._emit_text_style_changed()

    def _pick_color(self) -> None:
        if self._item is None:
            return
        if isinstance(self._item, QGraphicsTextItem):
            current = self._item.defaultTextColor()
        elif isinstance(self._item, FILLABLE_SHAPES):
            current = self._item.brush().color()
        else:
            return

        color = QColorDialog.getColor(current, self)
        if not color.isValid():
            return
        self._apply_color(color)

    def apply_probed_color(self, color: QColor) -> None:
        """Slot for DesignView.color_probed, wired up by MainWindow after
        probe_color_requested -- see that signal's docstring above."""
        if self._item is None or not isinstance(self._item, (QGraphicsTextItem, *FILLABLE_SHAPES)):
            return
        self._apply_color(color)

    def _apply_color(self, color: QColor) -> None:
        if isinstance(self._item, QGraphicsTextItem):
            before = self._item.defaultTextColor().name()
            after = color.name()
            _set_text_color(self._item, after)
            self._push("text_color", _set_text_color, before, after, self.tr("Change Text Color"))
            self._emit_text_style_changed()
        else:
            before = self._item.brush().color().name()
            after = color.name()
            _set_fill_color(self._item, after)
            self._push("fill_color", _set_fill_color, before, after, self.tr("Change Fill Color"))

    def _apply_shadow(self) -> None:
        if self._updating or self._item is None or not isinstance(self._item, QGraphicsTextItem):
            return
        before = get_text_shadow(self._item)
        after = self.shadow_check.isChecked()
        set_text_shadow(self._item, after)
        self._push("shadow", set_text_shadow, before, after, self.tr("Toggle Shadow"))

    def _apply_glow(self) -> None:
        if self._updating or self._item is None or not isinstance(self._item, QGraphicsTextItem):
            return
        before = get_text_glow(self._item)
        after = self.glow_check.isChecked()
        set_text_glow(self._item, after)
        self._push("glow", set_text_glow, before, after, self.tr("Toggle Glow"))

    def _emit_text_style_changed(self) -> None:
        """The user just set a text item's font/size/color explicitly --
        remember it as the project's new default for the *next* text layer
        created (see app_window._apply_default_text_style)."""
        if not isinstance(self._item, QGraphicsTextItem):
            return
        style = TextStyle(
            font_spec=self._item.font().toString(),
            color=self._item.defaultTextColor().name(),
        )
        self._default_text_style = style
        self.text_style_changed.emit(style)

    def _reset_to_default(self) -> None:
        if self._item is None:
            return
        item = self._item
        before = _snapshot_for_reset(item)

        item.setRotation(0.0)
        set_item_scale(item, 1.0, 1.0)

        if isinstance(item, QGraphicsTextItem):
            style = self._default_text_style
            font = QFont()
            if style.font_spec:
                font.fromString(style.font_spec)
            item.setFont(font)
            item.setDefaultTextColor(QColor(style.color) if style.color else QColor("black"))
            item.setTransformOriginPoint(item.boundingRect().center())
        elif isinstance(item, QGraphicsRectItem):
            fill = QColor(DEFAULT_RECT_FILL_HEX)
            item.setBrush(QBrush(fill))
            item.setPen(QPen(fill))
        elif isinstance(item, QGraphicsEllipseItem):
            item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            item.setPen(QPen())

        after = _snapshot_for_reset(item)
        self._push("reset", _apply_reset_snapshot, before, after, self.tr("Reset to Default"))
        self.set_item(item)
