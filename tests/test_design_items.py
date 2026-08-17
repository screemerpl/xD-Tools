from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsTextItem,
)

from mdtools.canvas.items import DesignEllipseItem, DesignPixmapItem, DesignRectItem, DesignTextItem


def _rendered_selected(item_cls, configure) -> QImage:
    """Renders `item_cls()` (selected, nothing else drawn -- see
    `configure`) alone on an otherwise blank white canvas."""
    scene = QGraphicsScene()
    item = item_cls()
    configure(item)
    item.setFlag(item.GraphicsItemFlag.ItemIsSelectable, True)
    item.setSelected(True)
    scene.addItem(item)

    image = QImage(60, 60, QImage.Format.Format_ARGB32)
    image.fill(QColor("white"))
    painter = QPainter(image)
    scene.render(painter)
    painter.end()
    return image


def _is_blank(image: QImage) -> bool:
    for y in range(image.height()):
        for x in range(image.width()):
            if image.pixelColor(x, y) != QColor("white"):
                return False
    return True


def _no_paint(item) -> None:
    item.setRect(5, 5, 40, 40)
    item.setPen(Qt.PenStyle.NoPen)
    item.setBrush(Qt.BrushStyle.NoBrush)


def test_plain_qgraphicsrectitem_shows_the_default_selection_decoration(qt_app):
    """Baseline/control: confirms the thing being suppressed below is real
    -- a plain, unmodified QGraphicsRectItem really does paint something
    when selected, even with no pen/brush of its own."""
    assert not _is_blank(_rendered_selected(QGraphicsRectItem, _no_paint))


def test_design_rect_item_suppresses_the_default_selection_decoration(qt_app):
    assert _is_blank(_rendered_selected(DesignRectItem, _no_paint))


def test_design_ellipse_item_suppresses_the_default_selection_decoration(qt_app):
    assert _is_blank(_rendered_selected(DesignEllipseItem, _no_paint))


def test_design_pixmap_item_suppresses_the_default_selection_decoration(qt_app):
    from PySide6.QtGui import QPixmap

    def configure(item):
        pixmap = QPixmap(40, 40)
        pixmap.fill(Qt.GlobalColor.transparent)
        item.setPixmap(pixmap)
        item.setPos(5, 5)

    assert _is_blank(_rendered_selected(DesignPixmapItem, configure))


def test_design_items_are_still_instances_of_their_plain_qt_base_class(qt_app):
    """Every isinstance(item, QGraphicsRectItem)-style check throughout the
    app (project_io.py, properties_panel.py, commands.py, ...) must keep
    working unchanged for these subclasses."""
    assert isinstance(DesignTextItem("hi"), QGraphicsTextItem)
    assert isinstance(DesignRectItem(), QGraphicsRectItem)
    assert isinstance(DesignEllipseItem(), QGraphicsEllipseItem)
    assert isinstance(DesignPixmapItem(), QGraphicsPixmapItem)
