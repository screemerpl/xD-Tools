"""Renders assets/img/cd_digital_audio.png from the SVG beside it.

The mark is the "Compact Disc Digital Audio" logo, taken from Wikimedia
Commons (`CDDAlogo.svg`) rather than drawn here -- an earlier attempt to
draw it from memory produced something that plainly was not the logo. See
`assets/img/ATTRIBUTION.md` for provenance and the trademark note.

**Why a PNG at all**, when the SVG is right there: `gallery.py` lists only
raster files, and `DesignScene.add_image()` goes through `QPixmap(path)`,
which needs Qt's SVG *image format plugin* -- a different thing from the
QtSvg module, and not guaranteed to be in a PyInstaller build (the same
reasoning `panels/icons.py` gives for rendering its own icons through
`QSvgRenderer` instead of `QIcon(path)`). So the SVG is the source, kept
in the repo, and this turns it into the asset the app actually uses.

Run it on the real platform plugin (offscreen is fine here -- there is no
text to lay out, unlike the version that drew the mark itself):

    .venv/Scripts/python.exe scripts/make_cd_logo.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication

# Wide enough that the mark stays crisp when printed: it lands about 8mm
# across on a disc label, which at the 900dpi this project bakes at is
# roughly 280 pixels, so this has headroom in hand.
WIDTH = 1200

ASSETS = Path(__file__).resolve().parents[1] / "assets" / "img"
SOURCE = ASSETS / "cd_digital_audio.svg"
OUT = ASSETS / "cd_digital_audio.png"


def render() -> QImage:
    renderer = QSvgRenderer(str(SOURCE))
    if not renderer.isValid():
        raise SystemExit(f"{SOURCE} is not a readable SVG")

    size = renderer.defaultSize()
    height = max(1, round(WIDTH * size.height() / size.width()))
    image = QImage(WIDTH, height, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    renderer.render(painter)
    painter.end()
    return image


def main() -> int:
    app = QApplication(sys.argv)  # noqa: F841 -- a QImage still needs one alive
    image = render()
    if not image.save(str(OUT), "PNG"):
        print(f"could not write {OUT}", file=sys.stderr)
        return 1
    print(f"wrote {OUT} ({image.width()}x{image.height()})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
