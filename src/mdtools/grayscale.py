"""Shared grayscale + brightness/contrast pixel math.

Used by both the live canvas grayscale preview
(canvas/view.py's _TrueGrayscaleEffect) and the real Export Print PNG
(Grayscale) pipeline (io/png_export.py) -- kept in its own module, rather
than under either canvas/ or io/ specifically, so neither package has to
import the other just to share this. Since both call through the exact
same function, a preview (the live toolbar sliders, or the pre-export
dialog) can never end up looking different from what actually gets saved.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter

BRIGHTNESS_RANGE = (-100, 100)
CONTRAST_RANGE = (-100, 100)


def brightness_contrast_lut(brightness: int, contrast: int) -> bytes:
    """256-entry byte lookup table mapping an original grayscale intensity
    (0-255) to its brightness/contrast-adjusted value -- contrast first
    (a multiplicative scale pivoting around mid-gray, 128), then
    brightness (a plain multiplicative scale), each clamped to
    +/-100 so a stray out-of-range value can't invert or overflow the
    mapping. 0 for both means "unchanged" (identity lookup table).

    Built once per adjustment change (a handful of Python iterations),
    then applied to a whole image buffer in a single bytes.translate()
    call in apply_grayscale() below -- a fast, single C op, not a
    per-pixel Python loop -- so this stays cheap enough for a
    continuously-repainted live preview, not just a one-shot export."""
    brightness = max(BRIGHTNESS_RANGE[0], min(BRIGHTNESS_RANGE[1], brightness))
    contrast = max(CONTRAST_RANGE[0], min(CONTRAST_RANGE[1], contrast))
    contrast_factor = (100 + contrast) / 100.0
    brightness_factor = (100 + brightness) / 100.0
    lut = bytearray(256)
    for value in range(256):
        adjusted = (value - 128) * contrast_factor + 128
        adjusted *= brightness_factor
        lut[value] = max(0, min(255, round(adjusted)))
    return bytes(lut)


def apply_grayscale(image: QImage, brightness: int = 0, contrast: int = 0) -> QImage:
    """Desaturates `image` to grayscale and applies a brightness/contrast
    adjustment, preserving `image`'s own alpha channel throughout.

    Uses QImage.convertToFormat(Format_Grayscale8) for the desaturation
    step -- Qt's own native, accurate luma conversion (a single fast C++
    call). NOT QGraphicsColorizeEffect: confirmed empirically that even at
    full strength with a neutral gray color, it washes the image toward
    white rather than doing an honest conversion (black comes out as
    RGB(128, 128, 128), not black) -- it's meant for a sepia/tinted-photo
    look, not a true grayscale preview.

    Format_Grayscale8 has no alpha channel of its own, so alpha is
    composited back in via CompositionMode_DestinationIn against the
    original `image` rather than lost."""
    gray = image.convertToFormat(QImage.Format.Format_Grayscale8)

    if brightness or contrast:
        lut = brightness_contrast_lut(brightness, contrast)
        adjusted_bytes = bytes(gray.constBits()).translate(lut)
        # QImage(data, ...) borrows the buffer it's given rather than
        # copying it -- .copy() immediately detaches the image into its
        # own separately-owned buffer, so it doesn't end up referencing
        # `adjusted_bytes` after this local variable goes out of scope.
        gray = QImage(
            adjusted_bytes, gray.width(), gray.height(), gray.bytesPerLine(), QImage.Format.Format_Grayscale8
        ).copy()

    gray_opaque = gray.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    result = QImage(image.size(), QImage.Format.Format_ARGB32_Premultiplied)
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    painter.drawImage(0, 0, gray_opaque)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
    painter.drawImage(0, 0, image)
    painter.end()
    return result
