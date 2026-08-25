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
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from mdtools import theme

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


def _render_svg(painter: QPainter, name: str, rect) -> None:
    QSvgRenderer(str(icons_dir() / f"{name}.svg")).render(painter, rect)


def _load_svg_icon(name: str) -> QIcon:
    pixmap = QPixmap(SIZE, SIZE)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    _render_svg(painter, name, pixmap.rect())
    painter.end()
    return QIcon(pixmap)


def _load_svg_icon_tinted(name: str, color: str) -> QIcon:
    """Recolours a single-fill Twemoji glyph to `color` at render time,
    the source SVG file itself left completely untouched -- same
    "composed at render time, not by hand-editing the bundled file"
    convention _load_svg_icon_with_badge already follows, for the same
    ATTRIBUTION.md "no modifications were made to the source SVGs" reason.

    Only meant for the handful of icons that are already a single solid
    fill (zoom_in/zoom_out's Twemoji "heavy plus/minus sign" glyphs,
    `#31373D`) -- recoloring a genuinely multi-colour icon this way would
    just paint over its own detail with one flat colour.

    `QPainter.CompositionMode.CompositionMode_SourceIn` keeps whatever
    alpha the SVG render already produced (the glyph's own shape,
    antialiased edges included) and replaces only the RGB channels, which
    is what lets a solid rectangle filled with `color` become "the glyph,
    recoloured" rather than "a solid rectangle"."""
    pixmap = QPixmap(SIZE, SIZE)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    _render_svg(painter, name, pixmap.rect())
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(pixmap.rect(), QColor(color))
    painter.end()
    return QIcon(pixmap)


def _load_svg_icon_with_badge(name: str, badge: str) -> QIcon:
    """`badge` rendered small, in the bottom-right corner, over `name` --
    composed here at render time out of two already-bundled SVGs rather
    than a third file, so ATTRIBUTION.md's "no modifications were made to
    the source SVGs" holds for this too: neither source file is touched,
    only the pixmap they are painted into."""
    from PySide6.QtCore import QRect

    pixmap = QPixmap(SIZE, SIZE)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    _render_svg(painter, name, pixmap.rect())
    badge_size = round(SIZE * 0.62)
    badge_rect = QRect(SIZE - badge_size, SIZE - badge_size, badge_size, badge_size)
    _render_svg(painter, badge, badge_rect)
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


def edit_metadata_icon() -> QIcon:
    """A memo (pencil on a pad), for opening the album metadata editor --
    deliberately not the musical note below, which is about inserting the
    metadata onto the page rather than editing it."""
    return _load_svg_icon("edit_metadata")


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
    """A heavy minus sign, for the zoom toolbar's Zoom Out.

    Tinted to theme._TEXT rather than left at the bundled SVG's own
    near-black fill (#31373D) -- reported directly as too dark to see
    once theme.py's own toolbar background became Discord's similarly
    dark #2f3136 (see theme.py's own 2026-08-25 recolour note): the two
    are close enough in value that the glyph nearly disappeared into its
    own background. Every other bundled icon is multi-colour and stayed
    legible through that same recolour; these two are the only
    single-fill ones."""
    return _load_svg_icon_tinted("zoom_out", theme._TEXT)


def zoom_in_icon() -> QIcon:
    """A heavy plus sign, for the zoom toolbar's Zoom In -- tinted, see
    zoom_out_icon()."""
    return _load_svg_icon_tinted("zoom_in", theme._TEXT)


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


def regenerate_icon() -> QIcon:
    """The recycling symbol, for the page toolbar's Regenerate."""
    return _load_svg_icon("regenerate")


def regenerate_font_icon() -> QIcon:
    """The recycling symbol with a small "input Latin letters" badge in
    the corner -- Regenerate with Font..., composed from two already-
    bundled icons (see _load_svg_icon_with_badge) rather than a third
    downloaded file, since no single Twemoji glyph means "regenerate, but
    with a chosen font"."""
    return _load_svg_icon_with_badge("regenerate", "text")
