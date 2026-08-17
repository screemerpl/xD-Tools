"""Tools panel and zoom toolbar icons -- colorful, standard emoji glyphs (Twemoji,
https://github.com/twitter/twemoji, CC-BY 4.0 -- see Help > About and
assets/icons/ATTRIBUTION.md) bundled as SVG files at assets/icons/,
rendered into pixmaps at load time.

Bundled the same way the asset gallery's images are (assets/img,
gallery.py) -- outside the mdtools package, not embedded/encoded into
Python source, so adding/swapping an icon later is just replacing a file.
icons_dir() mirrors gallery.gallery_dir()'s dev-vs-frozen-build path
resolution exactly.

Rendered via QSvgRenderer directly into a QPixmap, not QIcon(path)
(which depends on Qt's separate "iconengines" plugin actually being
bundled in a frozen build -- not guaranteed by PyInstaller's default
PySide6 hook the way the QtSvg module itself is, since this app already
demonstrably relies on QtSvg working in a frozen build via
io/svg_export.py's QSvgGenerator).

Each function must be called after a QApplication exists (they construct
QPixmap/QPainter), same rule as everywhere else in this codebase -- never
at module import time.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

SIZE = 28


def icons_dir() -> Path:
    """Where the bundled icon SVGs live: next to a frozen build's bundled
    data (sys._MEIPASS), or assets/icons at the repo root in dev mode --
    exactly mirrors gallery.gallery_dir()."""
    frozen_base = getattr(sys, "_MEIPASS", None)
    if frozen_base is not None:
        base = Path(frozen_base)
    else:
        # this file: src/mdtools/panels/icons.py -> repo root is three levels up
        base = Path(__file__).resolve().parents[3]
    return base / "assets" / "icons"


def _load_svg_icon(name: str) -> QIcon:
    pixmap = QPixmap(SIZE, SIZE)
    pixmap.fill(Qt.GlobalColor.transparent)
    renderer = QSvgRenderer(str(icons_dir() / f"{name}.svg"))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter)
    painter.end()
    return QIcon(pixmap)


def text_icon() -> QIcon:
    """Input latin letters, for Add Text."""
    return _load_svg_icon("text")


def rectangle_icon() -> QIcon:
    """A colored square, for Add Rectangle."""
    return _load_svg_icon("rectangle")


def image_icon() -> QIcon:
    """A framed picture, for Add Image... (loading an arbitrary file from
    disk)."""
    return _load_svg_icon("image")


def gallery_icon() -> QIcon:
    """Card index dividers, for Insert Asset... (distinct from the plain
    single-photo Add Image icon -- this one's about picking from a
    curated set, not browsing an arbitrary file)."""
    return _load_svg_icon("gallery")


def metadata_icon() -> QIcon:
    """A musical note, for Insert from Metadata (track titles/album
    info)."""
    return _load_svg_icon("metadata")


def crop_icon() -> QIcon:
    """Scissors, for Clip Layers."""
    return _load_svg_icon("crop")


def bake_icon() -> QIcon:
    """A clamp, for Bake Layers (flatten every layer into a single
    image) -- a compression/consolidation metaphor."""
    return _load_svg_icon("bake")


def save_icon() -> QIcon:
    """A floppy disk, for Save as Template...."""
    return _load_svg_icon("save")


def autolayout_icon() -> QIcon:
    """A magic wand, for building a disc label from the metadata."""
    return _load_svg_icon("autolayout")


def zoom_out_icon() -> QIcon:
    """A heavy minus sign, for the zoom toolbar's Zoom Out."""
    return _load_svg_icon("zoom_out")


def zoom_in_icon() -> QIcon:
    """A heavy plus sign, for the zoom toolbar's Zoom In."""
    return _load_svg_icon("zoom_in")


def zoom_reset_icon() -> QIcon:
    """"100 points" (a red "100" sticker), for the zoom toolbar's 100%
    (reset to actual size)."""
    return _load_svg_icon("zoom_reset")


def zoom_fit_icon() -> QIcon:
    """A triangular ruler, for the zoom toolbar's Fit (to window)."""
    return _load_svg_icon("zoom_fit")


def grayscale_icon() -> QIcon:
    """A half-light-half-dark moon, for the zoom toolbar's Grayscale
    preview toggle."""
    return _load_svg_icon("grayscale")
