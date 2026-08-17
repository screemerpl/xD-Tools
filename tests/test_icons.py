from mdtools.panels import icons

TOOL_PANEL_ICON_FNS = [
    icons.text_icon,
    icons.rectangle_icon,
    icons.image_icon,
    icons.gallery_icon,
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

ALL_ICON_FNS = TOOL_PANEL_ICON_FNS + ZOOM_TOOLBAR_ICON_FNS


def test_every_icon_renders_a_non_null_non_empty_pixmap(qt_app):
    for fn in ALL_ICON_FNS:
        icon = fn()
        assert not icon.isNull(), f"{fn.__name__} produced a null QIcon"
        pixmap = icon.pixmap(icons.SIZE, icons.SIZE)
        assert not pixmap.isNull()
        assert pixmap.width() > 0 and pixmap.height() > 0


def test_icons_are_visually_distinct_from_each_other(qt_app):
    images = [fn().pixmap(icons.SIZE, icons.SIZE).toImage() for fn in ALL_ICON_FNS]
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
    for fn in ALL_ICON_FNS:
        image = fn().pixmap(icons.SIZE, icons.SIZE).toImage()
        colors = {
            image.pixelColor(x, y).rgb()
            for y in range(image.height())
            for x in range(image.width())
            if image.pixelColor(x, y).alpha() > 10
        }
        assert len(colors) >= 2, f"{fn.__name__} rendered with only {len(colors)} distinct opaque color(s)"


def test_icons_dir_points_at_the_bundled_assets_folder(qt_app):
    icons_dir = icons.icons_dir()
    assert icons_dir.is_dir()
    for fn in ALL_ICON_FNS:
        name = fn.__name__.removesuffix("_icon")
        assert (icons_dir / f"{name}.svg").is_file()
