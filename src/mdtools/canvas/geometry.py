"""Path construction helpers for template outlines."""

from __future__ import annotations

from PySide6.QtCore import QRectF
from PySide6.QtGui import QPainterPath


def left_rounded_rect(w: float, h: float, radius: float) -> QPainterPath:
    """A w x h rectangle with the top-left and bottom-left corners rounded
    (radius) and the top-right/bottom-right corners left square. Used for
    the MiniDisc slider label, which butts up against the cartridge's
    square-cornered slider opening on its right side.
    """
    if radius <= 0:
        path = QPainterPath()
        path.addRect(0, 0, w, h)
        return path
    r = radius
    path = QPainterPath()
    path.moveTo(r, 0)
    path.lineTo(w, 0)
    path.lineTo(w, h)
    path.lineTo(r, h)
    path.arcTo(QRectF(0, h - 2 * r, 2 * r, 2 * r), -90, -90)
    path.lineTo(0, r)
    path.arcTo(QRectF(0, 0, 2 * r, 2 * r), 180, -90)
    path.closeSubpath()
    return path


def chamfered_fillet_rect(w: float, h: float, chamfer: float, fillet: float) -> QPainterPath:
    """A w x h rectangle with a straight diagonal cut (chamfer) removing
    the top-left corner, and the other three corners rounded (fillet).
    """
    path = QPainterPath()
    r = fillet
    path.moveTo(chamfer, 0)
    path.lineTo(w - r, 0)
    path.arcTo(QRectF(w - 2 * r, 0, 2 * r, 2 * r), 90, -90)
    path.lineTo(w, h - r)
    path.arcTo(QRectF(w - 2 * r, h - 2 * r, 2 * r, 2 * r), 0, -90)
    path.lineTo(r, h)
    path.arcTo(QRectF(0, h - 2 * r, 2 * r, 2 * r), -90, -90)
    path.lineTo(0, chamfer)
    path.closeSubpath()  # straight diagonal back to (chamfer, 0) -- the chamfer cut
    return path
