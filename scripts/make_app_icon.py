"""Draws the application icon: a quaver whose head is an "XD" face.

The name is a joke the user made and then kept -- "xD-Tools", where the x
stands in for C or M -- so the icon carries the same one: a musical note,
with the note head grinning the way XD does.

Writes `assets/img/xdtools.png` (for the window/taskbar icon, set at
runtime) and `assets/img/xdtools.ico` (baked into the .exe by PyInstaller's
`--icon`, which on Windows needs a real multi-resolution ICO rather than a
PNG). Pillow writes the ICO, exactly as `mdlogo.ico` was made.

Run it on the real platform plugin, not offscreen -- PySide6 ships no fonts
and offscreen finds no system ones, so the face would come out as empty
boxes (learned the hard way on the Digital Audio mark):

    .venv/Scripts/python.exe scripts/make_app_icon.py
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QImage, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QApplication

SIZE = 1024
INK = "#f2f4f8"  # the note itself, light: this sits on dark title bars
FACE = "#1b1e28"  # the grin, cut out of the head
ACCENT = "#5865f2"  # the app's own accent, from theme.py

ASSETS = Path(__file__).resolve().parents[1] / "assets" / "img"
PNG = ASSETS / "xdtools.png"
ICO = ASSETS / "xdtools.ico"
ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]


def _note(painter: QPainter) -> QRectF:
    """Stem and flag, returning the head's rect so the face can be drawn
    into it.

    The head takes most of the canvas and the stem is kept slim: at 16 or
    32 pixels the face is the only part that has to survive, and a
    correctly-proportioned quaver leaves it too little room to read as
    anything.
    """
    head = QRectF(SIZE * 0.06, SIZE * 0.40, SIZE * 0.66, SIZE * 0.54)

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(INK))
    painter.drawEllipse(head)

    stem = QRectF(head.right() - SIZE * 0.07, SIZE * 0.07, SIZE * 0.07, SIZE * 0.63)
    painter.drawRect(stem)

    # A single flag, drawn as a filled curve rather than a stroked line so
    # it keeps its weight when the icon is 16 pixels across.
    flag = QPainterPath()
    flag.moveTo(stem.right(), SIZE * 0.07)
    flag.cubicTo(
        QPointF(SIZE * 0.95, SIZE * 0.16),
        QPointF(SIZE * 0.92, SIZE * 0.32),
        QPointF(SIZE * 0.72, SIZE * 0.40),
    )
    flag.cubicTo(
        QPointF(SIZE * 0.86, SIZE * 0.28),
        QPointF(SIZE * 0.84, SIZE * 0.19),
        QPointF(stem.right(), SIZE * 0.19),
    )
    flag.closeSubpath()
    painter.setBrush(QColor(ACCENT))
    painter.drawPath(flag)
    return head


def _face(painter: QPainter, head: QRectF) -> None:
    """The XD: two screwed-shut eyes over a wide open grin.

    Drawn as shapes rather than as the letters "XD" -- at 16 pixels a glyph
    pair turns to mush, while a few thick strokes still read as a face.
    The first attempt had the eyes as full X shapes reaching down into the
    mouth, which read as a dead cartoon rather than a laughing one: they
    are smaller and higher now, and the mouth is a half-round grin rather
    than a hole.
    """
    pen = QPen(QColor(FACE))
    pen.setWidthF(head.height() * 0.085)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    eye_y = head.top() + head.height() * 0.33
    arm = head.width() * 0.075
    for centre_x in (head.left() + head.width() * 0.31, head.left() + head.width() * 0.63):
        painter.drawLine(
            QPointF(centre_x - arm, eye_y - arm), QPointF(centre_x + arm, eye_y + arm)
        )
        painter.drawLine(
            QPointF(centre_x - arm, eye_y + arm), QPointF(centre_x + arm, eye_y - arm)
        )

    # The grin: a flat top with a round bottom -- a "D" lying on its back,
    # which is the half of "XD" that has to be recognisable.
    mouth = QRectF(
        head.left() + head.width() * 0.26,
        head.top() + head.height() * 0.56,
        head.width() * 0.48,
        head.height() * 0.30,
    )
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(FACE))
    path = QPainterPath()
    path.moveTo(mouth.left(), mouth.top())
    path.lineTo(mouth.right(), mouth.top())
    path.arcTo(mouth, 0.0, -180.0)
    path.closeSubpath()
    painter.drawPath(path)


def render() -> QImage:
    image = QImage(SIZE, SIZE, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    _face(painter, _note(painter))
    painter.end()
    return image


def main() -> int:
    app = QApplication(sys.argv)  # noqa: F841 -- a QImage still needs one alive
    image = render()
    if not image.save(str(PNG), "PNG"):
        print(f"could not write {PNG}", file=sys.stderr)
        return 1

    buffer = io.BytesIO(PNG.read_bytes())
    with Image.open(buffer) as source:
        source.save(ICO, sizes=[(size, size) for size in ICO_SIZES])

    print(f"wrote {PNG} and {ICO}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
