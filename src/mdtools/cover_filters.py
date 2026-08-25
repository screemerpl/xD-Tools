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

from PIL import Image, ImageDraw, ImageFilter, ImageOps

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

# How strongly each filter acts.
#
# **Everything spatial here is a count across the image, never a pixel
# size.** Absolute pixel constants (a 14px mosaic block, a 6px blur
# radius, a 10px dot cell) make a filter's real strength depend entirely
# on how big the source cover happens to be: the same block size that
# gives a 900px cover a fine mosaic reduces a 300px one to a handful of
# giant squares. Covers reach this app from iTunes, Deezer, MusicBrainz,
# a FLAC file's embedded art and the user's own picture folder, at
# whatever size each of those hands over -- so a fixed pixel size meant
# nobody could tune these once and have them stay tuned. Pixelate was
# reported as "almost unrecognizable"; it was the small-cover end of
# exactly this. Counting divisions of the image instead makes each filter
# look the same at any source resolution, which is also what the picker
# dialog's own thumbnails have always implicitly promised.
#
# The counts below are then deliberately gentler than the pixel sizes
# they replace (~80 blocks across, where a 600px cover used to get ~43),
# because these are backgrounds a label's text prints over: the cover
# still has to read as itself.
BRIGHTEN_AMOUNT = 0.55
# Divisions of the image's shorter side. Higher = finer = gentler.
BLUR_DIVISIONS = 200
POSTERIZE_BITS = 4
PIXELATE_BLOCKS = 80
# Bounded by the smallest cover worth supporting (~300px) over the
# smallest cell a dot can actually be drawn in (_HALFTONE_MIN_CELL_PX):
# ask for more cells than that and a small cover clamps to the minimum
# and stops matching a large one, which is the very thing these counts
# exist to prevent. Measured at 75: an identical 75-dot screen from a
# 300px cover through a 1200px one.
HALFTONE_CELLS = 75


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


def _divide(image: Image.Image, divisions: int, *, minimum: int = 1) -> int:
    """`image`'s shorter side split into `divisions` parts, as a whole
    number of pixels of at least `minimum`.

    The shorter side, not the longer or the average: it is the one that
    decides how much detail there is to lose, and using it means a wide
    or tall cover gets the same treatment a square one does rather than a
    coarser one along its narrow axis."""
    return max(minimum, round(min(image.width, image.height) / divisions))


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


def _blur(image_data: bytes, divisions: int = BLUR_DIVISIONS) -> bytes:
    with Image.open(io.BytesIO(image_data)) as image:
        rgb = image.convert("RGB")
        radius = min(rgb.width, rgb.height) / divisions
        return _save(rgb.filter(ImageFilter.GaussianBlur(radius)))


def _posterize(image_data: bytes, bits: int = POSTERIZE_BITS) -> bytes:
    with Image.open(io.BytesIO(image_data)) as image:
        return _save(ImageOps.posterize(image.convert("RGB"), bits))


def _pixelate(image_data: bytes, blocks: int = PIXELATE_BLOCKS) -> bytes:
    """Downscaled to one pixel per block, then scaled back up with
    nearest-neighbour resampling -- the standard mosaic effect, and cheap:
    no per-pixel Python loop, just two resizes.

    The downscale averages each block (BOX), rather than picking one
    arbitrary pixel out of it (NEAREST, which is what this did first).
    Both give the same blocky result, but sampling a single pixel throws
    away everything else in the block, so fine detail turned into
    essentially random block colours and the cover stopped reading as
    itself far sooner than the block size alone would explain. Averaging
    is what a mosaic actually is. The upscale stays NEAREST -- that is
    what keeps the block edges hard instead of smearing them."""
    with Image.open(io.BytesIO(image_data)) as image:
        rgb = image.convert("RGB")
        block = _divide(rgb, blocks)
        small_size = (max(1, rgb.width // block), max(1, rgb.height // block))
        small = rgb.resize(small_size, Image.Resampling.BOX)
        return _save(small.resize(rgb.size, Image.Resampling.NEAREST))


# The dot grid is drawn at this multiple of the source's own size and
# then scaled back down, so the dots come out antialiased -- ImageDraw
# has no antialiasing of its own, and at this dot size hard-edged
# ellipses read as ragged rather than as a print screen. 2 rather than 3
# measured as indistinguishable in the result while costing ~40% less
# time, which matters because the picker dialog renders every filter.
_HALFTONE_SUPERSAMPLE = 2

# A dot needs real pixels to be a dot: below about this, the ellipse plus
# its antialiased edge is all edge, and the screen degenerates into flat
# grey rather than a pattern of dots.
_HALFTONE_MIN_CELL_PX = 4


def _halftone(image_data: bytes, cells: int = HALFTONE_CELLS) -> bytes:
    """A classic newspaper-style dot screen: the cover reduced to
    grayscale, then one black dot per cell whose radius tracks how dark
    that cell is -- the darker the cell, the bigger the dot -- drawn onto a
    white canvas at the source's own resolution.

    Each cell's mean brightness comes from a single downscale to the cell
    grid (BOX resampling averages exactly the pixels of one cell), not
    from cropping each cell and measuring it in a Python loop. Same
    numbers, but computed in one C-level pass instead of several thousand
    interpreted ones -- which is what makes a finer, gentler screen
    affordable at all: the picker dialog renders all six filters live, so
    a per-cell loop got noticeably slower exactly as the dots got smaller
    and there were more of them."""
    with Image.open(io.BytesIO(image_data)) as image:
        gray = image.convert("L")
        cell = _divide(gray, cells, minimum=_HALFTONE_MIN_CELL_PX)
        across = max(1, round(gray.width / cell))
        down = max(1, round(gray.height / cell))
        means = gray.resize((across, down), Image.Resampling.BOX)
        pixels = means.load()

        # Derived from the grid actually used rather than from `cell`, so
        # the dots stay centred in their cells even when the image's size
        # is not an exact multiple of the cell size.
        cell_w = gray.width / across
        cell_h = gray.height / down
        max_radius = min(cell_w, cell_h) * 0.5

        scale = _HALFTONE_SUPERSAMPLE
        canvas = Image.new("RGB", (gray.width * scale, gray.height * scale), (255, 255, 255))
        draw = ImageDraw.Draw(canvas)
        for row in range(down):
            for column in range(across):
                # 0 (black) is the darkest a cell can be, 255 (white)
                # contributes no dot at all.
                darkness = 1.0 - (pixels[column, row] / 255)
                radius = max_radius * darkness * scale
                if radius <= 0:
                    continue
                centre_x = (column + 0.5) * cell_w * scale
                centre_y = (row + 0.5) * cell_h * scale
                draw.ellipse(
                    (centre_x - radius, centre_y - radius, centre_x + radius, centre_y + radius),
                    fill=(0, 0, 0),
                )
        return _save(canvas.resize(gray.size, Image.Resampling.LANCZOS))
