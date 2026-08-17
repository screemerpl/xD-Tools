"""Export a DesignScene's artwork to a raster PNG at a chosen print DPI.

The output is clipped to the template's cut outline (chamfered/filleted
rect for a disc, rect for a cover) -- anything outside that shape, and any
of the corners cut away by the chamfer/fillets, is left transparent rather
than printed.
"""

from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QImage, QPainter, QTransform

from mdtools import app_settings
from mdtools.grayscale import apply_grayscale


def render_scene_to_image(scene, dpi: float | None = None) -> QImage:
    """Renders `scene`'s print layers to a transparent QImage at `dpi`,
    clipped to the template's cut outline -- the exact same rendering path
    export_png() uses below. Shared so anything else that needs a flattened
    rendering of the scene (Tools > Bake Layers) can never visually diverge
    from what Export Print PNG actually produces.

    `dpi=None` (the default) resolves to app_settings.default_export_dpi()
    at call time, not at import/def time -- so a change made in Window >
    Settings... takes effect on the very next call, not just for new
    processes started after the change."""
    if dpi is None:
        dpi = app_settings.default_export_dpi()
    rect: QRectF = scene.sceneRect()
    scale = dpi / app_settings.screen_dpi()
    width_px = math.ceil(rect.width() * scale)
    height_px = math.ceil(rect.height() * scale)

    # Premultiplied, not plain ARGB32: Qt's raster paint engine composites
    # internally in premultiplied space regardless, so painting onto a
    # plain (non-premultiplied) QImage forces an extra unpremultiply/
    # repremultiply round trip on every antialiased edge pixel -- most
    # visible exactly where it matters most here, the partially-transparent
    # edge pixels of antialiased text glyphs against a fully transparent
    # background. QImage.save() converts back to a plain-alpha PNG on write
    # regardless of which format was used while painting, so this only
    # affects rendering precision, not the saved file's pixel format.
    image = QImage(width_px, height_px, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)

    # maps scene coordinates to this image's device pixels: same scale/
    # offset scene.render(..., target, source) below would use internally.
    to_device = QTransform(scale, 0, 0, scale, -rect.left() * scale, -rect.top() * scale)
    clip_path = to_device.map(scene.template_clip_path())

    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    try:
        painter.setClipPath(clip_path)
        # deselected_for_export must be entered *before* hidden_for_export:
        # Qt auto-deselects an item the moment it's hidden, so capturing the
        # "real" selection has to happen before anything gets hidden --
        # otherwise there's nothing left to restore afterward.
        with scene.deselected_for_export(), scene.hidden_for_export(show_print=True, show_cut=False, show_fold=False):
            scene.render(painter, QRectF(0, 0, width_px, height_px), rect)
    finally:
        painter.end()

    return image


def export_png(
    scene,
    path: str | Path,
    dpi: float | None = None,
    grayscale: bool = False,
    brightness: int = 0,
    contrast: int = 0,
) -> None:
    """`dpi=None` resolves to app_settings.default_export_dpi() -- see
    render_scene_to_image() above. `brightness`/`contrast` (-100..100,
    0 = unchanged) are only applied when `grayscale` is True -- see
    mdtools.grayscale.apply_grayscale, the same function
    GrayscaleExportDialog's live preview and the canvas's own
    grayscale-preview toolbar sliders call, so what gets previewed and
    what actually gets saved here can never visually diverge."""
    if dpi is None:
        dpi = app_settings.default_export_dpi()
    image = render_scene_to_image(scene, dpi)

    if grayscale:
        image = apply_grayscale(image, brightness, contrast)

    dots_per_meter = round(dpi / 0.0254)
    image.setDotsPerMeterX(dots_per_meter)
    image.setDotsPerMeterY(dots_per_meter)
    image.save(str(path), "PNG")
