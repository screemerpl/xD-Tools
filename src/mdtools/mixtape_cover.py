"""Drawing a cover for a compilation, which by definition has none.

Every automatic layout in this app is built around the album's artwork --
`auto_layout` scales it across the disc label, `jcard_layout` puts it on the
front panel, `palette` takes the card's whole colour scheme out of it. A
mixtape has no artwork to take any of that from, and looking one up would be
worse than having none: a search for "Various Artists" returns some other
record's sleeve, presented as though it were this disc's.

So one is drawn, from the only material a mixtape actually has -- its track
titles -- and handed back as ordinary image bytes. That is the whole point of
doing it this way: nothing downstream needs to know. `metadata.cover_art`
gets a real PNG, and the disc label, the J-card, the palette extraction and
the saved `.mdproj` all carry on exactly as they do for a fetched sleeve.

Two constraints shape how it looks, both physical rather than aesthetic:

- **It has to survive grayscale.** These pages get printed, often through
  Export Print PNG (Grayscale). Two colours chosen to contrast by hue can
  come out as the same grey, so the accent here is forced apart from the
  background by *luminance*, not just hue.
- **It has to survive being small.** A disc label is 37x52mm. Type that
  looks refined on screen disappears at that size, so the track list is
  fitted by measurement and the wordmark is deliberately heavy.
"""

from __future__ import annotations

import colorsys
import hashlib

from PySide6.QtCore import QBuffer, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter

from mdtools.palette import readable_text_colour, relative_luminance
from mdtools.project import ProjectMetadata, format_time

# Covers this app already handles are 600px square (iTunes' largest plain
# size). Twice that, since unlike a fetched sleeve this one costs nothing to
# make larger and ends up stretched across a full-face disc label.
DEFAULT_SIZE = 1200

# Fractions of the image edge, so every measurement scales with `size`.
_MARGIN = 0.075
_WORDMARK_HEIGHT = 0.17
_RULE_THICKNESS = 0.012

# The accent has to differ from the background by at least this much WCAG
# relative luminance, or the two print as the same grey.
_MIN_LUMINANCE_GAP = 0.22

# Past this many tracks a single column has to be set too small to read at
# 37mm, so the list splits -- the same reasoning (and roughly the same
# threshold) as jcard_layout's own two-column switch.
_TWO_COLUMN_THRESHOLD = 9

_MAX_TRACK_POINT_SIZE = 40
_MIN_TRACK_POINT_SIZE = 5

# Qt wants an alignment alongside a wrap flag; measuring with the wrap flag
# alone gives heights that do not match what then gets drawn.
_LINE_FLAGS = int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
_WRAP_FLAGS = _LINE_FLAGS | int(Qt.TextFlag.TextWordWrap)


def _seed(metadata: ProjectMetadata) -> int:
    """A stable number for this particular set of tracks.

    Hashed rather than random so the same mixtape always comes out the same
    colour -- regenerating a cover after editing one title should not
    reshuffle the whole design -- and so two different mixes reliably look
    different. Python's own hash() is salted per process and would give a
    different cover on every run."""
    material = "\n".join(f"{track.artist}\x1f{track.title}" for track in metadata.tracks)
    material += f"\x1e{metadata.album}\x1f{metadata.artist}"
    return int.from_bytes(hashlib.sha1(material.encode("utf-8")).digest()[:4], "big")


def _hex(rgb: tuple[float, float, float]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*(max(0, min(255, round(channel * 255))) for channel in rgb))


def scheme(metadata: ProjectMetadata) -> tuple[str, str, str]:
    """(background, accent, text) for this mixtape, as "#rrggbb".

    The background hue comes from the seed, kept dark and only moderately
    saturated so white type sits on it cleanly.

    The accent is a near neighbour on the colour wheel rather than its
    opposite. A complement at full saturation was the first attempt and
    looked garish -- hot pink on bottle green -- where an analogous hue
    lifted well clear in brightness reads as deliberate. It also prints
    better, which is the part that is not a matter of taste: the two are
    then separated by *luminance*, so they stay distinct once Export Print
    PNG (Grayscale) throws the hue away, whereas a complement can convert
    to the same grey as its own background."""
    seed = _seed(metadata)
    hue = (seed % 360) / 360.0
    background = _hex(colorsys.hsv_to_rgb(hue, 0.45, 0.30))

    accent_hue = (hue + 0.08) % 1.0
    background_luminance = relative_luminance(background)
    # Brighten first, then desaturate towards a pale tint. Brightness alone
    # is not enough and the loop must not simply run out: blue carries very
    # little luminance (0.0722 of it, against green's 0.7152), so a fully
    # bright blue accent is still darker than a mid grey and can sit only
    # 0.14 away from its own background -- caught by
    # test_background_and_accent_stay_apart_in_grayscale, which sweeps every
    # hue rather than trusting one sample. Washing the colour out always
    # raises luminance, whatever the hue, so the ladder ends somewhere that
    # works for all of them.
    for saturation, value in ((0.55, 0.90), (0.55, 1.0), (0.42, 1.0), (0.28, 1.0), (0.16, 1.0)):
        candidate = _hex(colorsys.hsv_to_rgb(accent_hue, saturation, value))
        if abs(relative_luminance(candidate) - background_luminance) >= _MIN_LUMINANCE_GAP:
            return background, candidate, readable_text_colour(background)
    # Unreachable against the dark backgrounds this function produces, but
    # the invariant is worth more than the hue: a near-white tint is always
    # far enough away.
    return background, "#f5f5f5", readable_text_colour(background)


def _fitted_font(painter: QPainter, lines: list[str], rect: QRect, bold: bool = False) -> QFont:
    """The largest point size at which `lines` fit inside `rect`.

    Measured rather than calculated, for the same reason jcard_layout._fit_text
    is: how tall wrapped text ends up depends on where Qt breaks the lines,
    which is not worth re-deriving."""
    font = QFont(painter.font())
    font.setBold(bold)
    text = "\n".join(lines)
    for point_size in range(_MAX_TRACK_POINT_SIZE, _MIN_TRACK_POINT_SIZE - 1, -1):
        font.setPointSize(point_size)
        bounds = QFontMetrics(font).boundingRect(rect, int(Qt.TextFlag.TextWordWrap), text)
        if bounds.height() <= rect.height() and bounds.width() <= rect.width():
            return font
    font.setPointSize(_MIN_TRACK_POINT_SIZE)
    return font


def _entries(metadata: ProjectMetadata) -> list[tuple[str, str]]:
    """(number, "Artist - Title") per track.

    Kept as two parts rather than one string so the number can be set in
    its own column and the rest given a hanging indent -- see
    `_draw_entries`. Deliberately not project.numbered_track_lines(): that
    one is for text layers the user goes on to edit and includes running
    times, which here are already summarised in the footer and cost the
    titles room they need more."""
    entries = []
    for index, track in enumerate(metadata.tracks, start=1):
        rest = f"{track.artist.strip()} - {track.title}" if track.artist.strip() else track.title
        entries.append((f"{index:02d}", rest))
    return entries


def _entries_height(font: QFont, entries: list[tuple[str, str]], width: int, indent: int) -> int:
    metrics = QFontMetrics(font)
    leading = max(1, metrics.height() // 5)
    total = 0
    for _, rest in entries:
        bounds = metrics.boundingRect(
            QRect(0, 0, max(1, width - indent), 1 << 20), _WRAP_FLAGS, rest
        )
        total += max(bounds.height(), metrics.height()) + leading
    return total


def _fitted_entry_font(painter: QPainter, entries: list[tuple[str, str]], rect: QRect) -> QFont:
    """The largest size at which every track fits, hanging indents and all.

    Measured with the same routine that draws them, rather than with a
    single wrapped block: a block measured as one lump does not know about
    the number column, so it would report a height the drawn result then
    overshoots."""
    font = QFont(painter.font())
    for point_size in range(_MAX_TRACK_POINT_SIZE, _MIN_TRACK_POINT_SIZE - 1, -1):
        font.setPointSize(point_size)
        if _entries_height(font, entries, rect.width(), _indent_for(font)) <= rect.height():
            return font
    font.setPointSize(_MIN_TRACK_POINT_SIZE)
    return font


def _indent_for(font: QFont) -> int:
    """How far the titles are inset past their track numbers -- the width of
    a two-digit number plus a gap, measured in the font actually in use."""
    return QFontMetrics(font).horizontalAdvance("00") * 2


def _draw_entries(
    painter: QPainter,
    entries: list[tuple[str, str]],
    rect: QRect,
    font: QFont,
    block_height: int | None = None,
) -> None:
    """Numbers in a column, titles wrapped beside them with a hanging
    indent, the block centred in the space it was given.

    The hanging indent is the point. Wrapping the whole "01  Artist -
    Title" string as one paragraph puts continuation lines hard against the
    left margin, where they line up with the track numbers and read as
    further tracks -- "Heaven" on its own line looked like track 03. The
    centring follows jcard_layout's own reasoning: the size search is
    capped, so a short list lands well inside its allowance, and centring
    spreads that slack instead of leaving one dead band underneath.

    `block_height` overrides what that centring is computed from. Two
    columns each centred on their own contents start at different heights
    -- visibly so, since one half almost always wraps more than the other
    -- so the caller passes the taller column's height for both, and they
    line up along their first row."""
    painter.setFont(font)
    metrics = QFontMetrics(font)
    indent = _indent_for(font)
    leading = max(1, metrics.height() // 5)

    used = block_height if block_height is not None else _entries_height(font, entries, rect.width(), indent)
    y = rect.top() + max(0, (rect.height() - used) // 2)
    for number, rest in entries:
        text_rect = QRect(rect.left() + indent, y, max(1, rect.width() - indent), 1 << 20)
        bounds = metrics.boundingRect(text_rect, _WRAP_FLAGS, rest)
        height = max(bounds.height(), metrics.height())
        painter.drawText(QRect(rect.left(), y, indent, metrics.height()), _LINE_FLAGS, number)
        painter.drawText(QRect(text_rect.left(), y, text_rect.width(), height), _WRAP_FLAGS, rest)
        y += height + leading


def _total_time(metadata: ProjectMetadata) -> int | None:
    times = [track.time_seconds for track in metadata.tracks if track.time_seconds]
    return sum(times) if times else None


def render_cover(metadata: ProjectMetadata, size: int = DEFAULT_SIZE) -> bytes:
    """The mixtape's cover, as PNG bytes ready for `metadata.cover_art`."""
    background, accent, text_colour = scheme(metadata)

    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor(background))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    try:
        _paint(painter, metadata, size, accent, text_colour)
    finally:
        painter.end()

    # QBuffer() with no argument, deliberately: QBuffer(QByteArray()) keeps
    # only a *pointer* to that array, and a Python temporary passed in that
    # way is collected out from under it -- a hard segfault, not an
    # exception. The no-argument form owns its buffer. Same family of
    # lifetime trap as QWidget.setGraphicsEffect() and QTranslator.
    buffer = QBuffer()
    buffer.open(QBuffer.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(buffer.data())


def _paint(painter: QPainter, metadata: ProjectMetadata, size: int, accent: str, text_colour: str) -> None:
    margin = int(size * _MARGIN)
    inner = size - 2 * margin

    # --- the wordmark, which is the album's own name --------------------
    wordmark = (metadata.album or "Mixtape").upper()
    word_rect = QRect(margin, margin, inner, int(size * _WORDMARK_HEIGHT))
    font = _fitted_font(painter, [wordmark], word_rect, bold=True)
    painter.setFont(font)
    painter.setPen(QColor(text_colour))
    painter.drawText(QRectF(word_rect), int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), wordmark)

    # --- the accent rule, the one place the second colour appears -------
    rule_y = word_rect.bottom() + int(size * 0.02)
    rule_height = max(2, int(size * _RULE_THICKNESS))
    painter.fillRect(QRect(margin, rule_y, inner, rule_height), QColor(accent))

    # --- who it is by ---------------------------------------------------
    credit_rect = QRect(margin, rule_y + rule_height + int(size * 0.015), inner, int(size * 0.06))
    credit_font = _fitted_font(painter, [metadata.artist or ""], credit_rect)
    painter.setFont(credit_font)
    painter.setPen(QColor(accent))
    painter.drawText(
        QRectF(credit_rect),
        int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
        (metadata.artist or "").upper(),
    )

    # --- the footer, laid out before the list so the list knows its room -
    footer_height = int(size * 0.05)
    footer_top = size - margin - footer_height
    total = _total_time(metadata)
    footer = f"{len(metadata.tracks)} tracks"
    if total:
        footer += f"   /   {format_time(total)}"
    if metadata.year:
        footer += f"   /   {metadata.year}"
    footer_rect = QRect(margin, footer_top, inner, footer_height)
    painter.setFont(_fitted_font(painter, [footer], footer_rect))
    painter.setPen(QColor(text_colour))
    painter.drawText(QRectF(footer_rect), int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), footer)

    # --- the track list, which is the actual subject of the cover -------
    entries = _entries(metadata)
    if not entries:
        return
    list_top = credit_rect.bottom() + int(size * 0.035)
    list_rect = QRect(margin, list_top, inner, footer_top - list_top - int(size * 0.02))
    painter.setPen(QColor(text_colour))

    if len(entries) <= _TWO_COLUMN_THRESHOLD:
        _draw_entries(painter, entries, list_rect, _fitted_entry_font(painter, entries, list_rect))
        return
    # Split down the middle, first half on the left, continuing on the
    # right -- the same reading order project.track_list_two_columns uses.
    gutter = int(size * 0.03)
    column_width = (list_rect.width() - gutter) // 2
    midpoint = (len(entries) + 1) // 2
    left = QRect(list_rect.left(), list_rect.top(), column_width, list_rect.height())
    right = QRect(list_rect.left() + column_width + gutter, list_rect.top(), column_width, list_rect.height())
    # One font for both columns, sized to whichever half needs the smaller,
    # so the two sides cannot end up set at visibly different sizes.
    font = min(
        (
            _fitted_entry_font(painter, entries[:midpoint], left),
            _fitted_entry_font(painter, entries[midpoint:], right),
        ),
        key=lambda candidate: candidate.pointSize(),
    )
    indent = _indent_for(font)
    tallest = max(
        _entries_height(font, entries[:midpoint], left.width(), indent),
        _entries_height(font, entries[midpoint:], right.width(), indent),
    )
    _draw_entries(painter, entries[:midpoint], left, font, tallest)
    _draw_entries(painter, entries[midpoint:], right, font, tallest)
