"""Export a DesignScene's cut outline to SVG for Cricut Design Space.

Only the template's cut outline (red stroke, no fill) is exported --
nothing else. Fold/score lines are an on-canvas design aid only and are
deliberately excluded: they aren't cut, so they don't belong in the cut
file. Your actual artwork (text/images) is exported separately as a PNG
for printing -- see png_export.py.
"""

from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import QRectF, QSize
from PySide6.QtGui import QPainter
from PySide6.QtSvg import QSvgGenerator

from mdtools import app_settings


def export_svg(scene, path: str | Path) -> None:
    rect: QRectF = scene.sceneRect()
    width_px = math.ceil(rect.width())
    height_px = math.ceil(rect.height())

    generator = QSvgGenerator()
    generator.setFileName(str(path))
    generator.setSize(QSize(width_px, height_px))
    generator.setViewBox(QRectF(0, 0, width_px, height_px))
    # rect (scene units) was built from mm via mm_to_px(), which divides by
    # the *current* screen_dpi() -- this must use that same value, or the
    # physical width/height Qt writes into the SVG would be wrong.
    generator.setResolution(int(app_settings.screen_dpi()))
    generator.setTitle(Path(path).stem)

    painter = QPainter(generator)
    try:
        # deselected_for_export must be entered *before* hidden_for_export:
        # Qt auto-deselects an item the moment it's hidden, so capturing the
        # "real" selection has to happen before anything gets hidden --
        # otherwise there's nothing left to restore afterward.
        with scene.deselected_for_export(), scene.hidden_for_export(show_print=False, show_cut=True, show_fold=False):
            scene.render(painter, QRectF(0, 0, width_px, height_px), rect)
    finally:
        painter.end()
