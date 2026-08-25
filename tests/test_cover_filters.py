"""The six pure Pillow filters a disc/shell label's background can be run
through, and nothing about Qt or the picker dialog -- see
test_cover_filter_dialog.py for that.
"""

from __future__ import annotations

import io

import pytest
from PIL import Image

from mdtools import cover_filters


def _solid(colour=(20, 40, 90), size=(120, 120)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, colour).save(out, format="PNG")
    return out.getvalue()


def _checkerboard(size=(120, 120), cell=10) -> bytes:
    image = Image.new("RGB", size, (255, 255, 255))
    for y in range(0, size[1], cell):
        for x in range(0, size[0], cell):
            if ((x // cell) + (y // cell)) % 2 == 0:
                for py in range(y, min(y + cell, size[1])):
                    for px in range(x, min(x + cell, size[0])):
                        image.putpixel((px, py), (0, 0, 0))
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


def _pixel(data: bytes, xy=(5, 5)):
    return Image.open(io.BytesIO(data)).convert("RGB").getpixel(xy)


# -- dispatch -----------------------------------------------------------------


def test_every_filter_id_produces_a_decodable_png_of_the_same_size():
    source = _solid()
    original_size = Image.open(io.BytesIO(source)).size
    for filter_id in cover_filters.FILTER_IDS:
        out = cover_filters.apply_cover_filter(source, filter_id)
        assert Image.open(io.BytesIO(out)).size == original_size


def test_an_unknown_filter_id_raises():
    with pytest.raises(ValueError):
        cover_filters.apply_cover_filter(_solid(), "sepia")


def test_no_filter_returns_the_exact_same_bytes():
    source = _solid()
    assert cover_filters.apply_cover_filter(source, cover_filters.FILTER_NONE) is source


# -- brighten -------------------------------------------------------------


def test_brighten_moves_every_pixel_towards_white():
    source = _solid((10, 20, 40))
    out = cover_filters.apply_cover_filter(source, cover_filters.FILTER_BRIGHTEN)
    r, g, b = _pixel(out)
    assert r > 10 and g > 20 and b > 40


# -- blur -------------------------------------------------------------------


def test_blur_smooths_a_sharp_edge():
    """A checkerboard has hard black/white boundaries; blurring one must
    introduce in-between grey pixels that were not there before."""
    source = _checkerboard()
    before = {Image.open(io.BytesIO(source)).convert("RGB").getpixel((x, x)) for x in range(0, 120, 3)}
    out = cover_filters.apply_cover_filter(source, cover_filters.FILTER_BLUR)
    after = {Image.open(io.BytesIO(out)).convert("RGB").getpixel((x, x)) for x in range(0, 120, 3)}
    assert before != after
    assert any(0 < channel < 255 for pixel in after for channel in pixel)


# -- posterize ----------------------------------------------------------------


def test_posterize_reduces_the_number_of_distinct_tones():
    source = io.BytesIO()
    gradient = Image.new("L", (256, 1))
    gradient.putdata(list(range(256)))
    gradient.convert("RGB").save(source, format="PNG")
    out = cover_filters.apply_cover_filter(source.getvalue(), cover_filters.FILTER_POSTERIZE)
    image = Image.open(io.BytesIO(out)).convert("RGB")
    distinct = {image.getpixel((x, 0)) for x in range(256)}
    assert len(distinct) < 256


# -- pixelate -----------------------------------------------------------------


def test_pixelate_makes_each_block_a_flat_colour():
    source = _checkerboard(size=(140, 140), cell=1)  # noisy at pixel level
    out = cover_filters.apply_cover_filter(source, cover_filters.FILTER_PIXELATE)
    image = Image.open(io.BytesIO(out)).convert("RGB")
    block = cover_filters.PIXELATE_BLOCK_PX
    colours_in_first_block = {image.getpixel((x, y)) for x in range(block) for y in range(block)}
    assert len(colours_in_first_block) == 1


# -- halftone -----------------------------------------------------------------


def test_halftone_output_is_only_black_and_white():
    source = _solid((60, 60, 60))
    out = cover_filters.apply_cover_filter(source, cover_filters.FILTER_HALFTONE)
    image = Image.open(io.BytesIO(out)).convert("RGB")
    colours = {image.getpixel((x, y)) for x in range(0, image.width, 3) for y in range(0, image.height, 3)}
    assert colours <= {(0, 0, 0), (255, 255, 255)}


def test_halftone_dots_are_bigger_for_a_darker_source():
    def black_pixel_count(colour):
        out = cover_filters.apply_cover_filter(_solid(colour), cover_filters.FILTER_HALFTONE)
        image = Image.open(io.BytesIO(out)).convert("L")
        return sum(image.histogram()[:128])

    dark = black_pixel_count((20, 20, 20))
    light = black_pixel_count((220, 220, 220))
    assert dark > light
