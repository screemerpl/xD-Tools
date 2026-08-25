"""Background treatments a disc/shell label's cover art can be run through
before it goes onto the page.

Every disc-shaped or shell-shaped label in this app (MiniDisc's full-face
disc label, a CD-R's ring label, a cassette's two shell labels) prints the
album cover full-bleed behind the text -- and unlike a J-card or a CD
insert's front panel, where the cover *is* the point, here it is a
background something else has to stay legible over. `panels.
cover_filter_dialog.CoverFilterDialog` lets the user pick which treatment
before a label is generated, with a live preview built from the exact same
functions below -- so what is previewed and what is printed can never
diverge.

Pure Pillow, no Qt -- same reasoning as palette.py and grayscale.py: the
dialog's preview and the actual layout call this from two different
places, and neither should need a QApplication to do it.
"""

from __future__ import annotations

import io

from PIL import Image, ImageDraw, ImageFilter, ImageOps, ImageStat

FILTER_NONE = "none"
FILTER_BRIGHTEN = "brighten"
FILTER_BLUR = "blur"
FILTER_POSTERIZE = "posterize"
FILTER_HALFTONE = "halftone"
FILTER_PIXELATE = "pixelate"

# Display order -- the picker dialog lays its tiles out in exactly this
# sequence, "no filter" first since it's the one closest to "do nothing".
FILTER_IDS = (
    FILTER_NONE,
    FILTER_BRIGHTEN,
    FILTER_BLUR,
    FILTER_POSTERIZE,
    FILTER_HALFTONE,
    FILTER_PIXELATE,
)

# How strongly each filter acts, tuned by eye against a handful of real
# covers -- the same way cd_layout.LIGHTEN/LABEL_LIGHTEN were.
BRIGHTEN_AMOUNT = 0.55
BLUR_RADIUS_PX = 6.0
POSTERIZE_BITS = 3
PIXELATE_BLOCK_PX = 14
HALFTONE_CELL_PX = 10


def apply_cover_filter(image_data: bytes, filter_id: str) -> bytes:
    """`image_data` run through `filter_id`, as PNG bytes.

    FILTER_NONE returns the original bytes completely untouched -- there is
    nothing to re-encode, and doing so anyway would risk a lossy round trip
    for the one option that is supposed to mean "as is"."""
    if filter_id == FILTER_NONE:
        return image_data
    if filter_id == FILTER_BRIGHTEN:
        return _brighten(image_data)
    if filter_id == FILTER_BLUR:
        return _blur(image_data)
    if filter_id == FILTER_POSTERIZE:
        return _posterize(image_data)
    if filter_id == FILTER_HALFTONE:
        return _halftone(image_data)
    if filter_id == FILTER_PIXELATE:
        return _pixelate(image_data)
    raise ValueError(f"unknown cover filter: {filter_id!r}")


def _save(image: Image.Image) -> bytes:
    out = io.BytesIO()
    image.convert("RGB").save(out, format="PNG")
    return out.getvalue()


def _brighten(image_data: bytes, amount: float = BRIGHTEN_AMOUNT) -> bytes:
    """Blended `amount` of the way towards white -- the same operation
    cd_layout.lighten() already did for the CD label and the cassette shell
    label (both still call it directly for their own internal defaults;
    this is that same maths, exposed here so the picker dialog can offer it
    as one option among several instead of it being baked in)."""
    with Image.open(io.BytesIO(image_data)) as image:
        rgb = image.convert("RGB")
        white = Image.new("RGB", rgb.size, (255, 255, 255))
        return _save(Image.blend(rgb, white, max(0.0, min(1.0, amount))))


def _blur(image_data: bytes, radius: float = BLUR_RADIUS_PX) -> bytes:
    with Image.open(io.BytesIO(image_data)) as image:
        return _save(image.convert("RGB").filter(ImageFilter.GaussianBlur(radius)))


def _posterize(image_data: bytes, bits: int = POSTERIZE_BITS) -> bytes:
    with Image.open(io.BytesIO(image_data)) as image:
        return _save(ImageOps.posterize(image.convert("RGB"), bits))


def _pixelate(image_data: bytes, block: int = PIXELATE_BLOCK_PX) -> bytes:
    """Downscaled to one pixel per block, then scaled back up with
    nearest-neighbour resampling -- the standard mosaic effect, and cheap:
    no per-pixel Python loop, just two resizes."""
    with Image.open(io.BytesIO(image_data)) as image:
        rgb = image.convert("RGB")
        small_size = (max(1, rgb.width // block), max(1, rgb.height // block))
        small = rgb.resize(small_size, Image.Resampling.NEAREST)
        return _save(small.resize(rgb.size, Image.Resampling.NEAREST))


def _halftone(image_data: bytes, cell: int = HALFTONE_CELL_PX) -> bytes:
    """A classic newspaper-style dot screen: the cover reduced to
    grayscale, then one black dot per cell whose radius tracks how dark
    that cell is -- the darker the cell, the bigger the dot -- drawn onto a
    white canvas at the source's own resolution.

    Iterates cells (source size / cell, typically a few thousand for a
    600x600 cover), not pixels, so this stays fast without needing a
    C-optimized shortcut the way the alpha-bounds scans elsewhere in this
    codebase do."""
    with Image.open(io.BytesIO(image_data)) as image:
        gray = image.convert("L")
        canvas = Image.new("RGB", gray.size, (255, 255, 255))
        draw = ImageDraw.Draw(canvas)
        max_radius = cell * 0.5
        for top in range(0, gray.height, cell):
            for left in range(0, gray.width, cell):
                box = (left, top, min(left + cell, gray.width), min(top + cell, gray.height))
                patch = gray.crop(box)
                # ImageStat's mean, not a manual sum(getdata())/len(): same
                # number, computed from the image's own histogram rather
                # than materializing a Python list of every pixel in the
                # cell -- and getdata() is on its way out of Pillow.
                mean = ImageStat.Stat(patch).mean[0]
                # 0 (black) is the darkest a cell can be, 255 (white)
                # contributes no dot at all.
                darkness = 1.0 - (mean / 255)
                radius = max_radius * darkness
                if radius <= 0:
                    continue
                centre_x, centre_y = left + cell / 2, top + cell / 2
                draw.ellipse(
                    (centre_x - radius, centre_y - radius, centre_x + radius, centre_y + radius),
                    fill=(0, 0, 0),
                )
        return _save(canvas)
