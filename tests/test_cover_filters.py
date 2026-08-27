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
    size = 480
    source = _checkerboard(size=(size, size), cell=1)  # noisy at pixel level
    out = cover_filters.apply_cover_filter(source, cover_filters.FILTER_PIXELATE)
    image = Image.open(io.BytesIO(out)).convert("RGB")
    block = size // cover_filters.PIXELATE_BLOCKS
    colours_in_first_block = {image.getpixel((x, y)) for x in range(block) for y in range(block)}
    assert len(colours_in_first_block) == 1


def test_pixelate_averages_a_block_rather_than_sampling_one_pixel_of_it():
    """A block spanning a 1px checkerboard averages to mid-grey. Picking
    a single pixel out of it instead (the original NEAREST downscale)
    lands on pure black or pure white, which is what made fine detail
    turn into noise rather than into a recognizable mosaic."""
    source = _checkerboard(size=(480, 480), cell=1)
    out = cover_filters.apply_cover_filter(source, cover_filters.FILTER_PIXELATE)
    red, green, blue = _pixel(out, (5, 5))
    assert 60 < red < 195, f"block colour {red} looks sampled, not averaged"
    assert red == green == blue


# -- halftone -----------------------------------------------------------------


def test_halftone_output_carries_no_colour_and_is_mostly_black_and_white():
    """Black dots on white, with grey only where a dot's antialiased edge
    falls (the supersample-then-downscale in _halftone) -- ImageDraw
    cannot antialias, and hard-edged ellipses at this dot size read as
    ragged rather than as a print screen. What must never come back is
    *colour*: a halftone is a one-ink effect."""
    source = _solid((60, 60, 90), (480, 480))
    out = cover_filters.apply_cover_filter(source, cover_filters.FILTER_HALFTONE)
    image = Image.open(io.BytesIO(out)).convert("RGB")
    sampled = [
        image.getpixel((x, y)) for x in range(0, image.width, 3) for y in range(0, image.height, 3)
    ]
    assert all(red == green == blue for red, green, blue in sampled), "a halftone must not keep colour"
    # Real ink and real paper, not an all-over grey wash: the dots have
    # to reach true black and the gaps true white. (What fraction lands
    # in between is just geometry -- a small dot is mostly perimeter --
    # so it is deliberately not asserted here.)
    tones = Image.open(io.BytesIO(out)).convert("L").histogram()
    assert tones[0] > 0, "no dot reaches black -- the screen has washed out to grey"
    assert tones[255] > 0, "no gap reaches white -- the screen has washed out to grey"


def test_halftone_dots_scale_with_the_cover_rather_than_staying_a_fixed_size():
    """The same guard as the pixelate/blur one below, for the dot screen:
    a fixed cell size in pixels put ~4x as many dots across a 1200px
    cover as across a 300px one."""
    counts = []
    for size in (300, 1200):
        out = cover_filters.apply_cover_filter(_solid((60, 60, 60), (size, size)), cover_filters.FILTER_HALFTONE)
        image = Image.open(io.BytesIO(out)).convert("L")
        # Dots across, counted as runs of dark pixels along a scanline.
        # The busiest scanline of many, not one fixed row: a single row
        # can fall in the gap between two rows of dots and find none,
        # which says nothing about the screen's density.
        best = 0
        for fraction in range(10, 90, 3):
            row = [image.getpixel((x, image.height * fraction // 100)) < 128 for x in range(image.width)]
            best = max(best, sum(1 for index, dark in enumerate(row) if dark and not row[index - 1]))
        counts.append(best)
    assert counts[0] > 0, "no dots found at all"
    assert counts[0] == pytest.approx(counts[1], rel=0.15), f"dot counts differ by source size: {counts}"


def test_halftone_dots_are_bigger_for_a_darker_source():
    def black_pixel_count(colour):
        out = cover_filters.apply_cover_filter(_solid(colour), cover_filters.FILTER_HALFTONE)
        image = Image.open(io.BytesIO(out)).convert("L")
        return sum(image.histogram()[:128])

    dark = black_pixel_count((20, 20, 20))
    light = black_pixel_count((220, 220, 220))
    assert dark > light


# -- strength must not depend on the source cover's resolution ----------------
#
# The defect these guard: every spatial constant used to be an absolute
# pixel size, so the same filter hit a small cover far harder than a big
# one. Covers arrive from iTunes/Deezer/MusicBrainz/embedded FLAC art/the
# user's own files at whatever size each provides, and pixelate on a small
# one was reported as leaving the cover "almost unrecognizable".


def _gradient(size: int) -> bytes:
    """Structure at several scales, so a filter has something real to
    destroy -- a flat colour survives everything."""
    image = Image.new("RGB", (size, size))
    pixels = image.load()
    for y in range(size):
        for x in range(size):
            stripe = 255 if int(x / (size / 32)) % 2 else 40
            pixels[x, y] = (int(255 * x / size), int(200 * y / size), stripe)
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


def _detail_kept(original: bytes, filtered: bytes) -> float:
    """How much of the picture still reads the same, 1.0 = identical.
    Both reduced to a common size first, so this compares the images
    rather than their resolutions."""
    def _reduced(data: bytes) -> list[int]:
        with Image.open(io.BytesIO(data)) as image:
            return list(image.convert("L").resize((128, 128), Image.Resampling.BOX).getdata())

    a, b = _reduced(original), _reduced(filtered)
    mean_a, mean_b = sum(a) / len(a), sum(b) / len(b)
    deltas_a = [v - mean_a for v in a]
    deltas_b = [v - mean_b for v in b]
    denominator = (sum(v * v for v in deltas_a) ** 0.5) * (sum(v * v for v in deltas_b) ** 0.5)
    return sum(x * y for x, y in zip(deltas_a, deltas_b)) / denominator if denominator else 0.0


@pytest.mark.parametrize(
    "filter_id",
    [cover_filters.FILTER_BLUR, cover_filters.FILTER_PIXELATE, cover_filters.FILTER_HALFTONE],
)
def test_a_filter_costs_a_small_cover_no_more_than_a_large_one(filter_id):
    kept = []
    for size in (300, 900):
        source = _gradient(size)
        kept.append(_detail_kept(source, cover_filters.apply_cover_filter(source, filter_id)))
    assert abs(kept[0] - kept[1]) < 0.15, f"{filter_id} is resolution-dependent: {kept}"


def test_pixelate_leaves_the_cover_recognizable():
    """Reported directly: it "pixels the image to almost unrecognizable".
    A mosaic has to still read as the cover it was made from -- it is a
    background a label's text prints over, not an abstraction of one."""
    source = _gradient(600)
    kept = _detail_kept(source, cover_filters.apply_cover_filter(source, cover_filters.FILTER_PIXELATE))
    assert kept > 0.9, f"only {kept:.2f} of the cover survives pixelating"
