from PySide6.QtGui import QColor

from mdtools import theme
from mdtools.panels import icons

TOOL_PANEL_ICON_FNS = [
    icons.text_icon,
    icons.rectangle_icon,
    icons.image_icon,
    icons.gallery_icon,
    icons.edit_metadata_icon,
    icons.metadata_icon,
    icons.crop_icon,
    icons.bake_icon,
    icons.save_icon,
    icons.autolayout_icon,
]

ZOOM_TOOLBAR_ICON_FNS = [
    icons.zoom_out_icon,
    icons.zoom_in_icon,
    icons.zoom_reset_icon,
    icons.zoom_fit_icon,
    icons.grayscale_icon,
]

PAGE_TOOLBAR_ICON_FNS = [icons.regenerate_icon]

ALL_ICON_FNS = TOOL_PANEL_ICON_FNS + ZOOM_TOOLBAR_ICON_FNS + PAGE_TOOLBAR_ICON_FNS

# Composed from two already-bundled files at render time (see
# icons._load_svg_icon_with_badge) rather than mapping to one file of its
# own -- covered by the rendering/distinctness/color tests below, but kept
# out of ALL_ICON_FNS since test_icons_dir_points_at_the_bundled_assets_folder
# assumes a 1:1 name-to-file mapping that this icon doesn't have.
COMPOSITE_ICON_FNS = [icons.regenerate_font_icon]


def test_every_icon_renders_a_non_null_non_empty_pixmap(qt_app):
    for fn in ALL_ICON_FNS + COMPOSITE_ICON_FNS:
        icon = fn()
        assert not icon.isNull(), f"{fn.__name__} produced a null QIcon"
        pixmap = icon.pixmap(icons.SIZE, icons.SIZE)
        assert not pixmap.isNull()
        assert pixmap.width() > 0 and pixmap.height() > 0


def test_icons_are_visually_distinct_from_each_other(qt_app):
    fns = ALL_ICON_FNS + COMPOSITE_ICON_FNS
    images = [fn().pixmap(icons.SIZE, icons.SIZE).toImage() for fn in fns]
    for i, image_a in enumerate(images):
        for image_b in images[i + 1 :]:
            assert image_a != image_b


def test_icons_are_colorful_not_a_single_flat_tint(qt_app):
    """Regression guard for the switch away from self-drawn, single-color
    QPainter glyphs (which -- since drawn with one QPen/QBrush color --
    always render as exactly one distinct hue, antialiasing included,
    once alpha is ignored) to bundled colorful SVG icons (Twemoji). Most
    icons use several distinct hues; the "large blue square" icon is a
    legitimate exception (a solid colored square plus a slightly
    different anti-aliased rounded-corner shade == 2), so the threshold
    here is ">= 2", not "> 2"."""
    for fn in ALL_ICON_FNS + COMPOSITE_ICON_FNS:
        image = fn().pixmap(icons.SIZE, icons.SIZE).toImage()
        colors = {
            image.pixelColor(x, y).rgb()
            for y in range(image.height())
            for x in range(image.width())
            if image.pixelColor(x, y).alpha() > 10
        }
        assert len(colors) >= 2, f"{fn.__name__} rendered with only {len(colors)} distinct opaque color(s)"


def test_zoom_in_out_icons_contrast_with_the_toolbar_background(qt_app):
    """Reported directly: the bundled Twemoji "heavy plus/minus sign"
    glyphs are a single near-black fill (#31373D), which used to be
    legible against the old theme's mid-grey toolbar but nearly
    disappeared once theme.py's own background became Discord's
    similarly dark #2f3136 -- zoom_in_icon()/zoom_out_icon() now tint
    that glyph to theme._TEXT instead of the bundled file's own colour.
    This checks the actual, current gap in lightness rather than pinning
    an exact colour, so a later shade tweak within the theme doesn't
    break it -- only a regression back to a near-invisible icon should."""
    background = QColor(theme._WINDOW)
    for fn in (icons.zoom_in_icon, icons.zoom_out_icon):
        image = fn().pixmap(icons.SIZE, icons.SIZE).toImage()
        center = image.pixelColor(icons.SIZE // 2, icons.SIZE // 2)
        assert center.alpha() > 200, f"{fn.__name__}'s own glyph should be opaque at its centre"
        gap = abs(center.lightness() - background.lightness())
        assert gap > 60, f"{fn.__name__} is only {gap} lightness points from the toolbar background"


def test_icons_dir_points_at_the_bundled_assets_folder(qt_app):
    icons_dir = icons.icons_dir()
    assert icons_dir.is_dir()
    for fn in ALL_ICON_FNS:
        name = fn.__name__.removesuffix("_icon")
        assert (icons_dir / f"{name}.svg").is_file()
