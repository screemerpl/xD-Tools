from __future__ import annotations

from PySide6.QtCore import QCoreApplication, Signal
from PySide6.QtWidgets import (
    QGraphicsTextItem,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mdtools.canvas.items import get_item_name


def _label_for(item) -> str:
    # QCoreApplication.translate(context, text) rather than `self.tr()`
    # since this is a plain function, not a QObject method.
    # hasattr guard: some tests refresh() the panel with plain sentinel
    # objects (not real QGraphicsItems) to test signal wiring only.
    name = get_item_name(item) if hasattr(item, "data") else None
    if name:
        return name
    if isinstance(item, QGraphicsTextItem):
        text = item.toPlainText().strip() or QCoreApplication.translate("LayersPanel", "(empty)")
        return QCoreApplication.translate("LayersPanel", "Text: {text}").format(text=text[:24])
    return type(item).__name__.replace("QGraphics", "").replace("Item", "")


class LayersPanel(QWidget):
    item_selected = Signal(object)
    delete_requested = Signal(object)
    move_up_requested = Signal(object)
    move_down_requested = Signal(object)
    rename_requested = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.list_widget = QListWidget()
        self.list_widget.currentRowChanged.connect(self._on_row_changed)
        layout.addWidget(self.list_widget)

        move_row = QHBoxLayout()
        self.move_up_btn = QPushButton(self.tr("Move Up"))
        self.move_up_btn.setEnabled(False)
        self.move_up_btn.clicked.connect(self._on_move_up_clicked)
        move_row.addWidget(self.move_up_btn)

        self.move_down_btn = QPushButton(self.tr("Move Down"))
        self.move_down_btn.setEnabled(False)
        self.move_down_btn.clicked.connect(self._on_move_down_clicked)
        move_row.addWidget(self.move_down_btn)
        layout.addLayout(move_row)

        self.rename_btn = QPushButton(self.tr("Rename..."))
        self.rename_btn.setEnabled(False)
        self.rename_btn.clicked.connect(self._on_rename_clicked)
        layout.addWidget(self.rename_btn)

        self.delete_btn = QPushButton(self.tr("Delete Layer"))
        self.delete_btn.setEnabled(False)
        self.delete_btn.clicked.connect(self._on_delete_clicked)
        layout.addWidget(self.delete_btn)

    def refresh(self, items: list, select: object = None) -> None:
        self.list_widget.blockSignals(True)
        self.list_widget.clear()
        select_row = -1
        for i, item in enumerate(items):
            list_item = QListWidgetItem(_label_for(item))
            list_item.setData(1, item)
            self.list_widget.addItem(list_item)
            if item is select:
                select_row = i
        if select_row >= 0:
            self.list_widget.setCurrentRow(select_row)
        self.list_widget.blockSignals(False)
        self._update_button_states(self.list_widget.currentRow())

    def select_item(self, item) -> None:
        """Sync the list's current row to `item` (e.g. after it was
        selected on the canvas, not through this panel), without
        re-emitting item_selected back at whoever's already handling it."""
        row = -1
        for i in range(self.list_widget.count()):
            if self.list_widget.item(i).data(1) is item:
                row = i
                break
        self.list_widget.blockSignals(True)
        self.list_widget.setCurrentRow(row)
        self.list_widget.blockSignals(False)
        self._update_button_states(row)

    def _update_button_states(self, row: int) -> None:
        count = self.list_widget.count()
        self.delete_btn.setEnabled(row >= 0)
        self.rename_btn.setEnabled(row >= 0)
        self.move_up_btn.setEnabled(row > 0)
        self.move_down_btn.setEnabled(0 <= row < count - 1)

    def _on_row_changed(self, row: int) -> None:
        self._update_button_states(row)
        if row < 0:
            self.item_selected.emit(None)
            return
        list_item = self.list_widget.item(row)
        self.item_selected.emit(list_item.data(1))

    def _on_delete_clicked(self) -> None:
        row = self.list_widget.currentRow()
        if row < 0:
            return
        self.delete_requested.emit(self.list_widget.item(row).data(1))

    def _on_rename_clicked(self) -> None:
        row = self.list_widget.currentRow()
        if row < 0:
            return
        self.rename_requested.emit(self.list_widget.item(row).data(1))

    def _on_move_up_clicked(self) -> None:
        row = self.list_widget.currentRow()
        if row < 0:
            return
        self.move_up_requested.emit(self.list_widget.item(row).data(1))

    def _on_move_down_clicked(self) -> None:
        row = self.list_widget.currentRow()
        if row < 0:
            return
        self.move_down_requested.emit(self.list_widget.item(row).data(1))
