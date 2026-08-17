from PySide6.QtGui import QColor, QImage, QPixmap
from PySide6.QtWidgets import QGraphicsPixmapItem

from mdtools.canvas.items import CONTENT_RECT_ROLE, opaque_content_rect
from mdtools.canvas.scene import DesignScene
from mdtools.templates.models import DiscTemplate


def _pixmap_with_opaque_patch(size: int, patch: tuple[int, int, int, int]) -> QPixmap:
    left, top, right, bottom = patch
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(QColor(0, 0, 0, 0))
    for y in range(top, bottom):
        for x in range(left, right):
            image.setPixelColor(x, y, QColor(255, 0, 0, 255))
    return QPixmap.fromImage(image)


def test_opaque_content_rect_tightens_to_the_non_transparent_patch(qt_app):
    item = QGraphicsPixmapItem(_pixmap_with_opaque_patch(100, (40, 40, 60, 60)))

    rect = opaque_content_rect(item)

    assert rect.left() == 40
    assert rect.top() == 40
    assert rect.width() == 20
    assert rect.height() == 20


def test_opaque_content_rect_matches_bounding_rect_for_a_fully_opaque_pixmap(qt_app):
    image = QImage(50, 30, QImage.Format.Format_ARGB32)
    image.fill(QColor("red"))
    item = QGraphicsPixmapItem(QPixmap.fromImage(image))

    assert opaque_content_rect(item) == item.boundingRect()


def test_opaque_content_rect_falls_back_to_bounding_rect_for_a_fully_transparent_pixmap(qt_app):
    image = QImage(50, 30, QImage.Format.Format_ARGB32)
    image.fill(QColor(0, 0, 0, 0))
    item = QGraphicsPixmapItem(QPixmap.fromImage(image))

    assert opaque_content_rect(item) == item.boundingRect()


def test_opaque_content_rect_is_cached_and_invalidated_on_pixmap_swap(qt_app):
    item = QGraphicsPixmapItem(_pixmap_with_opaque_patch(100, (40, 40, 60, 60)))
    first = opaque_content_rect(item)
    assert item.data(CONTENT_RECT_ROLE)[0] == item.pixmap().cacheKey()

    # same content queried again -- must return the cached value, not recompute
    assert opaque_content_rect(item) == first

    item.setPixmap(_pixmap_with_opaque_patch(100, (10, 10, 20, 20)))
    second = opaque_content_rect(item)
    assert second != first
    assert second.left() == 10 and second.top() == 10
    assert item.data(CONTENT_RECT_ROLE)[0] == item.pixmap().cacheKey()


def test_opaque_content_rect_is_a_plain_bounding_rect_for_non_pixmap_items(qt_app):
    scene = DesignScene(DiscTemplate(name="t", width_mm=37.0, height_mm=52.0))
    text_item = scene.add_text("hello")
    rect_item = scene.add_rectangle()

    assert opaque_content_rect(text_item) == text_item.boundingRect()
    assert opaque_content_rect(rect_item) == rect_item.boundingRect()


def test_opaque_content_rect_handles_a_null_pixmap(qt_app):
    item = QGraphicsPixmapItem()  # no pixmap set at all

    assert opaque_content_rect(item) == item.boundingRect()
