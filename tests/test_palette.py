"""Pulling background and accent colours out of a cover image.

Everything here is pure -- no scene, no QApplication -- so the J-card layout
can be reasoned about separately from the colours it happens to be given.
"""

import io

from PIL import Image

from mdtools import palette


def _image(*bands: tuple[str, int]) -> bytes:
    """A 100x100 PNG built from horizontal bands: (hex colour, height)."""
    image = Image.new("RGB", (100, sum(height for _, height in bands)))
    y = 0
    for colour, height in bands:
        rgb = tuple(int(colour[i : i + 2], 16) for i in (1, 3, 5))
        image.paste(rgb, (0, y, 100, y + height))
        y += height
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


# --- swatches --------------------------------------------------------------


def test_a_solid_image_yields_that_one_colour():
    found = palette.swatches(_image(("#3366cc", 100)))
    assert found
    assert found[0].hex == "#3366cc"
    assert found[0].weight > 0.95


def test_swatches_come_back_most_common_first():
    found = palette.swatches(_image(("#101010", 80), ("#ee2222", 20)))
    assert found[0].hex.startswith("#1")
    assert found[0].weight > found[-1].weight


def test_unreadable_data_yields_nothing_rather_than_raising():
    """Callers fall back on an empty list; making them guard every call
    with a try would be worse."""
    assert palette.swatches(b"not an image") == []


# --- chosen colours --------------------------------------------------------


def test_the_background_is_the_colour_there_is_most_of():
    background = palette.dominant_colour(_image(("#0b2f1a", 85), ("#eeeada", 15)))
    red, green, blue = palette.Swatch(background, 0).rgb
    assert green > red and green > blue, "the large dark green area should win"


def test_the_accent_avoids_the_background_it_sits_next_to():
    """A spine in nearly the background's colour reads as a mistake rather
    than a band."""
    data = _image(("#0b2f1a", 85), ("#eeeada", 15))
    background = palette.dominant_colour(data)
    accent = palette.accent_colour(data, against=background)

    assert accent != background
    assert palette._distance(palette.Swatch(accent, 0).rgb, palette.Swatch(background, 0).rgb) > 0.25


def test_a_light_accent_wins_over_a_muted_one_on_a_dark_cover():
    """Scoring on vividness alone picked a muted brown out of a near-black
    cover that also held a near-white -- on a spine, the visible one is the
    better accent."""
    data = _image(("#000000", 90), ("#75675a", 5), ("#f2efea", 5))
    accent = palette.accent_colour(data, against="#000000")

    assert palette.relative_luminance(accent) > 0.5


def test_both_choices_fall_back_rather_than_failing_on_junk():
    assert palette.dominant_colour(b"junk", fallback="#123456") == "#123456"
    assert palette.accent_colour(b"junk", fallback="#654321") == "#654321"


# --- text colour -----------------------------------------------------------


def test_text_is_white_on_dark_and_black_on_light():
    assert palette.readable_text_colour("#000000") == "#ffffff"
    assert palette.readable_text_colour("#0b2f1a") == "#ffffff"
    assert palette.readable_text_colour("#ffffff") == "#000000"
    assert palette.readable_text_colour("#eeeada") == "#000000"


def test_luminance_orders_colours_the_way_eyes_do():
    assert palette.relative_luminance("#000000") == 0.0
    assert palette.relative_luminance("#ffffff") == 1.0
    # Green looks far brighter than blue at the same channel value.
    assert palette.relative_luminance("#00ff00") > palette.relative_luminance("#0000ff")
