"""Unit conversion helpers shared across the app.

The canvas works internally in millimeters. On-screen, the QGraphicsScene
uses a display scale in dots-per-inch (mdtools.app_settings.screen_dpi(),
user-configurable via Window > Settings..., 96 by default -- a CSS-style
convention, not necessarily the display's real physical DPI) so shapes
look correct at 100% zoom; export to PNG uses a separate, user-chosen DPI
(see io/png_export.py). Both mm_to_px()/px_to_mm() below read the
*current* screen_dpi() setting on every call rather than a fixed
constant, so changing it in Settings takes effect immediately.
"""

from __future__ import annotations

from mdtools.app_settings import screen_dpi

MM_PER_INCH = 25.4


def mm_to_px(mm: float) -> float:
    return mm * screen_dpi() / MM_PER_INCH


def px_to_mm(px: float) -> float:
    return px * MM_PER_INCH / screen_dpi()
