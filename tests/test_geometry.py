from PySide6.QtCore import QPointF

from mdtools.canvas.geometry import chamfered_fillet_rect, left_rounded_rect


def test_chamfer_removes_top_left_corner():
    path = chamfered_fillet_rect(w=100, h=100, chamfer=10, fillet=5)
    assert not path.contains(QPointF(1, 1))  # inside the chamfered-off corner
    assert path.contains(QPointF(50, 50))  # well inside the shape


def test_fillet_rounds_other_corners():
    path = chamfered_fillet_rect(w=100, h=100, chamfer=10, fillet=5)
    assert not path.contains(QPointF(99, 1))  # top-right fillet corner
    assert not path.contains(QPointF(99, 99))  # bottom-right fillet corner
    assert not path.contains(QPointF(1, 99))  # bottom-left fillet corner


def test_bounding_rect_matches_full_rectangle():
    path = chamfered_fillet_rect(w=37, h=52, chamfer=3, fillet=1)
    rect = path.boundingRect()
    assert rect.width() == 37
    assert rect.height() == 52


def test_left_rounded_rect_rounds_only_the_left_corners():
    path = left_rounded_rect(w=100, h=60, radius=10)
    assert not path.contains(QPointF(1, 1))  # top-left rounded corner
    assert not path.contains(QPointF(1, 59))  # bottom-left rounded corner
    assert path.contains(QPointF(99, 1))  # top-right stays square
    assert path.contains(QPointF(99, 59))  # bottom-right stays square
    assert path.contains(QPointF(50, 30))  # well inside the shape


def test_left_rounded_rect_bounding_rect_matches_full_rectangle():
    path = left_rounded_rect(w=27.5, h=17.5, radius=2.5)
    rect = path.boundingRect()
    assert rect.width() == 27.5
    assert rect.height() == 17.5


def test_left_rounded_rect_with_zero_radius_is_a_plain_rectangle():
    path = left_rounded_rect(w=100, h=60, radius=0)
    assert path.contains(QPointF(1, 1))
    assert path.contains(QPointF(1, 59))
    assert path.contains(QPointF(99, 1))
    assert path.contains(QPointF(99, 59))
