"""Pulling usable colours out of a cover image, so a J-card can be given a
background and an accent that actually belong to the album.

Pure functions over image bytes -- no Qt, no scene, so the layout code and
the tests can both use them without a QApplication. Pillow does the pixel
work (already a dependency, and its quantiser is C, unlike a per-pixel
Python loop over a 600x600 cover).

Colours are returned as "#rrggbb" strings because that is what this app
already stores in TextStyle.color and reads with QColor(...).
"""

from __future__ import annotations

import colorsys
import io
from dataclasses import dataclass

from PIL import Image

# The cover is shrunk before counting: a thumbnail carries the same colour
# distribution as the full image for this purpose and makes quantising it
# effectively free.
_SAMPLE_SIZE = 128
# How many colours to reduce the image to before counting. Too few and
# distinct areas merge into one muddy average; too many and the "most
# common" colour becomes a shade that only a handful of pixels have.
_PALETTE_SIZE = 12

# An accent has to be visibly different from the background it sits next to,
# or the spine just looks like a slightly wrong-coloured continuation of the
# back panel.
_MIN_ACCENT_DISTANCE = 0.25


@dataclass(frozen=True)
class Swatch:
    hex: str
    weight: float  # share of the sampled pixels, 0..1

    @property
    def rgb(self) -> tuple[int, int, int]:
        return (int(self.hex[1:3], 16), int(self.hex[3:5], 16), int(self.hex[5:7], 16))


def _to_hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def _hsv(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
    return colorsys.rgb_to_hsv(*(channel / 255 for channel in rgb))


def _distance(left: tuple[int, int, int], right: tuple[int, int, int]) -> float:
    """0..1 straight-line distance in RGB space. Crude next to a perceptual
    metric, but this only ever answers "are these two obviously different",
    which it is quite good enough for."""
    return sum((a - b) ** 2 for a, b in zip(left, right)) ** 0.5 / (255 * 3**0.5)


def _swatches_of(sample: "Image.Image", count: int) -> list[Swatch]:
    """The shared half of swatches()/region_colour(), taking an already-open
    RGB image so a crop does not have to be re-encoded just to be counted."""
    sample = sample.copy()
    sample.thumbnail((_SAMPLE_SIZE, _SAMPLE_SIZE))
    quantised = sample.quantize(colors=count, method=Image.Quantize.MEDIANCUT)
    palette = quantised.getpalette() or []
    counts = quantised.getcolors() or []

    total = sum(number for number, _ in counts) or 1
    found: list[Swatch] = []
    for number, index in sorted(counts, reverse=True):
        base = index * 3
        if base + 2 >= len(palette):
            continue
        rgb = (palette[base], palette[base + 1], palette[base + 2])
        found.append(Swatch(hex=_to_hex(rgb), weight=number / total))
    return found


def swatches(image_data: bytes, count: int = _PALETTE_SIZE) -> list[Swatch]:
    """The image's main colours, most common first.

    Returns [] for anything that isn't a readable image, so callers can fall
    back rather than having to guard every call with a try."""
    try:
        with Image.open(io.BytesIO(image_data)) as image:
            return _swatches_of(image.convert("RGB"), count)
    except (OSError, ValueError):
        return []


def dominant_colour(image_data: bytes, fallback: str = "#202020") -> str:
    """The colour the cover has most of -- the back panel's background."""
    found = swatches(image_data)
    return found[0].hex if found else fallback


def region_colour(image_data: bytes, top: float = 0.0, bottom: float = 1.0, fallback: str = "#202020") -> str:
    """The dominant colour of a horizontal band of the image, `top` to
    `bottom` as fractions of its height.

    The whole-image dominant colour is the wrong question when something has
    to be legible over one particular part of a cover: a sleeve that is dark
    at the top and pale at the bottom averages out to a mid-tone that
    describes neither end."""
    try:
        with Image.open(io.BytesIO(image_data)) as image:
            sample = image.convert("RGB")
            width, height = sample.size
            upper = max(0, min(height - 1, int(height * top)))
            lower = max(upper + 1, min(height, int(height * bottom)))
            found = _swatches_of(sample.crop((0, upper, width, lower)), _PALETTE_SIZE)
    except (OSError, ValueError):
        return fallback
    return found[0].hex if found else fallback


def accent_colour(image_data: bytes, against: str | None = None, fallback: str = "#c0392b") -> str:
    """A colour for the spine: from the cover, but not the same colour the
    back panel is already using.

    Scored on three things: how vivid it is, how much of the cover it
    covers, and -- decisively -- how far it is from the background it will
    sit beside. Vividness alone picked a muted brown out of a near-black
    cover that also contained a near-white; on a spine, the one you can
    actually see from across the room is the better accent. Anything too
    close to `against` is skipped outright."""
    found = swatches(image_data)
    if not found:
        return fallback
    avoid = Swatch(hex=against, weight=0).rgb if against else None

    def score(swatch: Swatch) -> float:
        _, saturation, value = _hsv(swatch.rgb)
        contrast = _distance(swatch.rgb, avoid) if avoid is not None else 0.0
        return saturation * value + swatch.weight * 0.3 + contrast * 0.4

    candidates = [s for s in found if avoid is None or _distance(s.rgb, avoid) >= _MIN_ACCENT_DISTANCE]
    if not candidates:
        candidates = found
    return max(candidates, key=score).hex


def relative_luminance(hex_colour: str) -> float:
    """WCAG relative luminance, 0 (black) to 1 (white)."""
    channels = []
    for raw in Swatch(hex=hex_colour, weight=0).rgb:
        value = raw / 255
        channels.append(value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4)
    red, green, blue = channels
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def tint_monochrome_png(data: bytes, colour: str) -> bytes:
    """Recolours a single-colour-plus-alpha image to `colour`, keeping its
    alpha channel exactly as it is.

    For a mark that is really a *mask* -- one opaque colour and a shape cut
    out of it by alpha, which is what assets/img/cd_digital_audio.png is
    (verified: exactly one opaque colour in it, pure black). Such a mark
    printed on a dark panel is invisible, so it has to be able to become
    the panel's own ink the way every piece of text on that panel already
    does.

    Deliberately **not** for an image with real internal colour: the
    MiniDisc logo beside it is black *and* white, and flattening that to
    one colour would erase the wordmark inside it. Callers pass a colour
    only for the marks they know are masks -- everything else keeps using
    scene.add_image() on the file itself.
    """
    image = Image.open(io.BytesIO(data)).convert("RGBA")
    alpha = image.getchannel("A")
    tinted = Image.new("RGBA", image.size, Swatch(hex=colour, weight=0).rgb + (255,))
    tinted.putalpha(alpha)
    out = io.BytesIO()
    tinted.save(out, format="PNG")
    return out.getvalue()


def readable_text_colour(background: str) -> str:
    """Black or white, whichever contrasts more with `background`.

    Deliberately only these two: an automatically derived mid-tone would
    look considered but read badly, and this text is printed small on a
    physical J-card where legibility beats subtlety."""
    return "#000000" if relative_luminance(background) > 0.35 else "#ffffff"
