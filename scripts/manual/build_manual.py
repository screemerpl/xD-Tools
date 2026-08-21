"""Builds the user manual as a PDF, one per language.

Rendering is Qt's own: the content is described as blocks (see
content_*.py), turned into the rich-text subset QTextDocument understands,
and painted onto a QPdfWriter. That keeps the manual buildable with
nothing installed beyond what xD-Tools already needs -- no LaTeX, no
wkhtmltopdf, no reportlab.

Pagination is done by hand rather than through QTextDocument.print_(),
which cannot draw anything outside the text flow: the page footers and the
running page numbers are the whole reason for the extra work. The table of
contents needs page numbers that don't exist until after layout, so the
document is laid out repeatedly until the numbers stop moving -- usually
twice, three times if a late entry crosses a page boundary.

    python scripts/manual/build_manual.py            # all languages
    python scripts/manual/build_manual.py pl         # just one

Screenshots come from scripts/manual/make_screenshots.py -- run that first
if doc/img is empty or stale.
"""

from __future__ import annotations

import sys
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtCore import QMarginsF, QRectF, QSizeF, QUrl, Qt  # noqa: E402
from PySide6.QtGui import (  # noqa: E402
    QColor,
    QFont,
    QImage,
    QPageLayout,
    QPageSize,
    QPainter,
    QPalette,
    QPdfWriter,
    QTextDocument,
)
from PySide6.QtWidgets import QApplication  # noqa: E402

IMG_DIR = ROOT / "doc" / "img"
OUT_DIR = ROOT / "doc"

RESOLUTION = 300  # dpi the PDF is painted at
PAGE_MARGINS_MM = (20.0, 18.0, 18.0, 20.0)  # left, top, right, bottom
FOOTER_HEIGHT_MM = 10.0
FIGURE_WIDTH_MM = 150.0  # screenshots are wide; anything more crowds the margins
NARROW_FIGURE_WIDTH_MM = 105.0  # for the tall, narrow dialogs

# Screenshots that are portrait-shaped: at the full figure width they would
# run off the bottom of a page.
NARROW_FIGURES = {"remote", "upload", "record", "metadata", "startup", "settings", "about", "new-project"}

ACCENT = "#1c4f63"
# Body text's own colour. Never left to the palette -- see make_document.
BODY_INK = "#1a1a1a"
RULE = "#c8d4db"

# Type sizes, in points. Converted to pixels via pt() before they reach the
# document -- see make_document() for why nothing here can stay in points.
BODY_PT = 10.5
H1_PT = 19.0
H2_PT = 13.5
TITLE_PT = 34.0
SUBTITLE_PT = 15.0
CAPTION_PT = 9.0
PAD_PT = 4.0


def mm(value: float) -> float:
    return value * RESOLUTION / 25.4


def pt(value: float) -> int:
    """Points to device pixels at the resolution the PDF is painted at."""
    return int(round(value * RESOLUTION / 72.0))


# --- content -> HTML -------------------------------------------------------


class _Builder:
    """Turns the block list into HTML, collecting headings as it goes.

    Headings get a matching entry in `self.headings` so the table of
    contents is generated from the same source as the body -- a
    hand-written contents list is one edit away from lying."""

    def __init__(self):
        self.parts: list[str] = []
        self.headings: list[tuple[int, str]] = []  # (level, text)
        self.images: dict[str, QImage] = {}
        self._figure_number = 0

    def add(self, html: str) -> None:
        self.parts.append(html)

    def heading(self, level: int, text: str, chapter: int | None = None) -> None:
        self.headings.append((level, text))
        label = f"{chapter}. {escape(text)}" if chapter is not None else escape(text)
        if level == 1:
            self.add(
                f'<h1 style="color:{ACCENT}; font-size:{pt(H1_PT)}px; page-break-before:always;">{label}</h1>'
                f'<hr style="height:{pt(1.5)}px; background-color:{ACCENT};" />'
            )
        else:
            self.add(f'<h2 style="color:{ACCENT}; font-size:{pt(H2_PT)}px;">{label}</h2>')

    def paragraph(self, text: str) -> None:
        self.add(f"<p>{_inline(text)}</p>")

    def bullets(self, items: list[str], ordered: bool = False) -> None:
        tag = "ol" if ordered else "ul"
        rows = "".join(f"<li>{_inline(item)}</li>" for item in items)
        self.add(f"<{tag}>{rows}</{tag}>")

    def table(self, head: list[str], rows: list[list[str]]) -> None:
        pad = pt(PAD_PT)
        header = "".join(
            f'<th bgcolor="#e8eef2" style="padding:{pad}px;"><b>{_inline(cell)}</b></th>' for cell in head
        )
        body = "".join(
            "<tr>" + "".join(f'<td style="padding:{pad}px;">{_inline(cell)}</td>' for cell in row) + "</tr>"
            for row in rows
        )
        self.add(
            f'<table width="100%" cellspacing="0" cellpadding="{pad}" border="1" '
            f'style="border-color:{RULE};"><tr>{header}</tr>{body}</table><p></p>'
        )

    def callout(self, kind: str, text: str) -> None:
        colours = {"note": ("#eef3f7", ACCENT), "warn": ("#fbeeea", "#a8442a"), "tip": ("#eef5ee", "#2f6b4f")}
        background, border = colours.get(kind, colours["note"])
        pad = pt(PAD_PT * 1.6)
        self.add(
            f'<table width="100%" cellspacing="0" cellpadding="{pad}" border="1" style="border-color:{border};">'
            f'<tr><td bgcolor="{background}" style="padding:{pad}px;">{_inline(text)}</td></tr></table><p></p>'
        )

    def figure(self, lang: str, key: str, caption: str) -> None:
        """A screenshot plus a numbered caption. A missing file is skipped
        with a warning rather than failing the build -- the manual is still
        readable without one figure, and stopping here would mean the whole
        PDF disappears because a screenshot run was forgotten."""
        path = IMG_DIR / lang / f"{key}.png"
        if not path.exists():
            path = IMG_DIR / f"{key}.png"
        if not path.exists():
            print(f"  ! missing figure: {key}")
            return
        image = QImage(str(path))
        if image.isNull():
            print(f"  ! unreadable figure: {key}")
            return

        self._figure_number += 1
        name = f"fig{self._figure_number}"
        self.images[name] = image

        width_mm = NARROW_FIGURE_WIDTH_MM if key in NARROW_FIGURES else FIGURE_WIDTH_MM
        width = mm(width_mm)
        height = width * image.height() / image.width()
        self.add(
            f'<p align="center"><img src="{name}" width="{int(width)}" height="{int(height)}" /></p>'
            f'<p align="center" style="color:#5a707c; font-size:{pt(CAPTION_PT)}px;">'
            f"<i>{self._figure_number}. {_inline(caption)}</i></p>"
        )


# Order matters: ** is consumed before a lone * is looked at, or bold would
# be read as an italic wrapping an empty string.
_INLINE_MARKS = (("**", "b"), ("`", "code"), ("*", "i"))


def _inline(text: str) -> str:
    """Escapes the text, then re-enables the inline marks the content files
    use: **bold**, *italic* and `literal`."""
    out = escape(text)
    for mark, tag in _INLINE_MARKS:
        pieces = out.split(mark)
        if len(pieces) < 3:
            continue
        rebuilt = []
        for index, piece in enumerate(pieces):
            if index % 2 == 1:
                style = ' style="background-color:#eef1f3;"' if tag == "code" else ""
                rebuilt.append(f"<{tag}{style}>{piece}</{tag}>")
            else:
                rebuilt.append(piece)
        out = "".join(rebuilt)
    return out.replace("\n", "<br />")


def render_blocks(builder: _Builder, blocks: list, lang: str) -> None:
    for block in blocks:
        kind, value = next(iter(block.items()))
        if kind == "h2":
            builder.heading(2, value)
        elif kind == "p":
            builder.paragraph(value)
        elif kind == "ul":
            builder.bullets(value)
        elif kind == "ol":
            builder.bullets(value, ordered=True)
        elif kind == "table":
            builder.table(value["head"], value["rows"])
        elif kind in ("note", "warn", "tip"):
            builder.callout(kind, value)
        elif kind == "fig":
            builder.figure(lang, value[0], value[1])
        else:
            raise ValueError(f"unknown block: {kind}")


# --- document assembly -----------------------------------------------------


def build_html(content, lang: str, toc_pages: dict[str, int] | None) -> tuple[str, dict[str, QImage], list[str]]:
    """Returns the whole document's HTML, its images, and the heading texts
    the table of contents needs page numbers for.

    `toc_pages` is None on the measuring pass, when the numbers are not
    known yet -- placeholders of the same width keep that pass's layout as
    close as possible to the final one."""
    builder = _Builder()

    # Title page. The page break belongs to the *next* heading (every h1
    # carries page-break-before), so nothing is needed at the end here.
    # The application's own icon, not the MiniDisc logo: this manual has
    # covered CD-R as well since 0.2.0, and a MiniDisc on the cover said
    # otherwise. Falls back to the old logo if the icon has not been
    # generated (scripts/make_app_icon.py writes it).
    logo = ROOT / "assets" / "img" / "xdtools.png"
    if not logo.exists():
        logo = ROOT / "assets" / "img" / "mdlogo.png"
    if logo.exists():
        image = QImage(str(logo))
        if not image.isNull():
            builder.images["logo"] = image
            width = mm(34)
            height = width * image.height() / image.width()
            builder.add(
                f'<p align="center" style="margin-top:{pt(90)}px;">'
                f'<img src="logo" width="{int(width)}" height="{int(height)}" /></p>'
            )
    builder.add(
        f'<p align="center" style="color:{ACCENT}; font-size:{pt(TITLE_PT)}px;">'
        f"<b>{escape(content.TITLE)}</b></p>"
        f'<p align="center" style="font-size:{pt(SUBTITLE_PT)}px;">{escape(content.SUBTITLE)}</p>'
        f'<p align="center" style="color:#5a707c;">{escape(content.TITLE_NOTE)}</p>'
        f'<p align="center" style="color:#5a707c; margin-top:{pt(60)}px;">{escape(content.VERSION_LINE)}<br />'
        f"{escape(content.AUTHOR_LINE)}<br />{escape(content.DATE_LINE)}</p>"
    )

    # Contents.
    builder.add(
        f'<h1 style="color:{ACCENT}; font-size:{pt(H1_PT)}px; page-break-before:always;">'
        f"{escape(content.TOC_TITLE)}</h1>"
        f'<hr style="height:{pt(1.5)}px; background-color:{ACCENT};" />'
    )
    pad = pt(PAD_PT * 0.8)
    toc_rows = []
    for index, chapter in enumerate(content.BOOK, start=1):
        title = f"{index}. {chapter['title']}"
        page = "--" if toc_pages is None else str(toc_pages.get(chapter["title"], "--"))
        toc_rows.append(
            f'<tr><td style="padding:{pad}px;">{escape(title)}</td>'
            f'<td align="right" style="padding:{pad}px;">{page}</td></tr>'
        )
    builder.add(f'<table width="100%" cellspacing="0" cellpadding="{pad}">{"".join(toc_rows)}</table>')

    for index, chapter in enumerate(content.BOOK, start=1):
        builder.heading(1, chapter["title"], chapter=index)
        render_blocks(builder, chapter["blocks"], lang)

    html = (
        '<html><body style="line-height:135%;">' + "".join(builder.parts) + "</body></html>"
    )
    return html, builder.images, [chapter["title"] for chapter in content.BOOK]


def make_document(html: str, images: dict[str, QImage], body_size: QSizeF, lang: str) -> QTextDocument:
    doc = QTextDocument()
    font = QFont()
    # Family fallback rather than one name: the Japanese edition needs a
    # font with kana and kanji, and the Latin ones look wrong in it.
    if lang == "ja":
        font.setFamilies(["Yu Gothic UI", "Meiryo", "MS PGothic", "Segoe UI"])
    else:
        font.setFamilies(["Segoe UI", "Calibri", "Arial"])
    # Pixels, not points. A standalone QTextDocument resolves point sizes
    # against the *screen's* DPI, while it is being painted onto a 300 dpi
    # page -- which came out at roughly a third of the intended size.
    font.setPixelSize(pt(BODY_PT))
    doc.setDefaultFont(font)
    # **Body text needs an explicit colour or it does not print at all.**
    # Everything this file styles inline -- headings, captions, the title
    # block -- carries its own `color:` and was always fine. Everything else
    # (paragraphs, list items, table cells, the text inside a note/warn/tip
    # box) comes out of setHtml() with BrushStyle.NoBrush: no colour of its
    # own, to be resolved against a palette when it is painted. That palette
    # is not one this code controls, and on a dark-mode desktop its Text role
    # is white -- so the manual painted white text onto a white page and
    # every paragraph vanished, headings and rules still present.
    #
    # Found by rebuilding the unchanged manual on a different machine: the
    # PDFs in doc/ were produced on Windows 10 in light mode, and the same
    # source on Windows 11 in dark mode lost all of its body copy.
    #
    # Measured, rather than reasoned about, because two plausible fixes do
    # nothing at all. Rendering a one-paragraph document to a real PDF and
    # reading the darkest ink back: no fix and setting the QPainter's pen
    # both leave the body blank (only the heading's own #1c4f63 inks);
    # a default style sheet and a mergeCharFormat sweep both ink it. The
    # style sheet is the one used here because an inline `color:` still
    # beats it, so the accent colours above survive -- a sweep would flatten
    # them to this grey.
    doc.setDefaultStyleSheet("p,li,td,th,ul,ol,div,body{color:%s;}" % BODY_INK)
    doc.setDocumentMargin(0)
    for name, image in images.items():
        doc.addResource(QTextDocument.ResourceType.ImageResource, QUrl(name), image)
    doc.setPageSize(body_size)
    doc.setHtml(html)
    return doc


def measure_chapter_pages(doc: QTextDocument, titles: list[str], body_height: float) -> dict[str, int]:
    """Which page each chapter heading landed on.

    Read from the laid-out document rather than guessed: a heading's y
    position divided by the page height is the page it is on, and that is
    the only way to know before the numbers are printed."""
    pages: dict[str, int] = {}
    layout = doc.documentLayout()
    block = doc.begin()
    while block.isValid():
        if block.blockFormat().headingLevel() == 1:
            text = block.text().strip()
            # Headings are numbered in the body ("3. The main window"), the
            # contents list is keyed on the bare title.
            bare = text.split(". ", 1)[1] if ". " in text else text
            if bare in titles and bare not in pages:
                top = layout.blockBoundingRect(block).top()
                pages[bare] = int(top // body_height) + 1
        block = block.next()
    return pages


def paint(doc: QTextDocument, path: Path, content, body_size: QSizeF, footer_height: float) -> int:
    writer = QPdfWriter(str(path))
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    writer.setPageMargins(QMarginsF(*PAGE_MARGINS_MM), QPageLayout.Unit.Millimeter)
    writer.setResolution(RESOLUTION)
    writer.setTitle(f"{content.TITLE} - {content.SUBTITLE}")
    writer.setCreator("xD-Tools")

    painter = QPainter(writer)
    # A QPdfWriter whose output file cannot be opened -- on Windows, most
    # often because a PDF viewer still has the previous build of it open --
    # fails here *silently*: QPainter simply comes back inactive, every
    # drawing call after it is a no-op, and this function used to go on to
    # report a page count for a file it had not written. That cost a long
    # detour once: a stale PL manual, left over from a build before a fix,
    # looked exactly like the fix not working. Say so instead.
    if not painter.isActive():
        raise RuntimeError(
            f"could not open {path} for writing -- close it if a PDF viewer still has it open"
        )
    body_height = body_size.height()
    page_count = doc.pageCount()

    footer_font = QFont(doc.defaultFont())
    footer_font.setPointSizeF(8.0)

    for page in range(page_count):
        if page:
            writer.newPage()
        painter.save()
        painter.translate(0, -page * body_height)
        painter.setClipRect(0, page * body_height, body_size.width(), body_height)
        doc.drawContents(painter, QRectF(0, page * body_height, body_size.width(), body_height))
        painter.restore()

        # No furniture on the title page -- a page number under a title is
        # noise, and the numbering still counts it so the contents match.
        if page:
            painter.save()
            painter.setFont(footer_font)
            painter.setPen(QColor(RULE))
            rule_y = body_height + footer_height * 0.35
            painter.drawLine(0, int(rule_y), int(body_size.width()), int(rule_y))
            painter.setPen(QColor("#5a707c"))
            text_rect = QRectF(0, rule_y + mm(1.5), body_size.width(), footer_height)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft, content.FOOTER_LEFT)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignRight, str(page + 1))
            painter.restore()

    painter.end()
    return page_count


def build(lang: str) -> None:
    module = __import__(f"content_{lang}")
    print(f"[{lang}] {module.TITLE}")

    page_size = QPageSize(QPageSize.PageSizeId.A4)
    full = page_size.sizePixels(RESOLUTION)
    left, top, right, bottom = (mm(v) for v in PAGE_MARGINS_MM)
    footer_height = mm(FOOTER_HEIGHT_MM)
    body_size = QSizeF(full.width() - left - right, full.height() - top - bottom - footer_height)

    # Lay out, read the page numbers, put them in the contents, lay out
    # again -- repeated until adding the numbers stops moving anything.
    toc_pages: dict[str, int] | None = None
    doc = None
    for attempt in range(4):
        html, images, titles = build_html(module, lang, toc_pages)
        doc = make_document(html, images, body_size, lang)
        measured = measure_chapter_pages(doc, titles, body_size.height())
        if measured == toc_pages:
            break
        toc_pages = measured
    else:
        print("  ! contents page numbers did not settle; using the last measurement")

    out = OUT_DIR / f"xD-Tools-Manual-{lang.upper()}.pdf"
    pages = paint(doc, out, module, body_size, footer_height)
    print(f"  {out.relative_to(ROOT)} -- {pages} pages")


def _force_light_palette(app: QApplication) -> None:
    """Build against a light palette whatever the host machine's theme is.

    Not the fix for the invisible-body-text bug -- make_document's default
    style sheet is, and it is the one that was measured to work. This is
    here for everything else that reads the palette on the way to a page
    meant for white paper (table rules, selection colours, any widget Qt
    constructs internally while laying rich text out), so that the same
    source builds the same document on a light-mode and a dark-mode
    desktop. Cheap, and it removes a whole class of "works on my machine".
    """
    palette = app.palette()
    palette.setColor(QPalette.ColorRole.Text, QColor(BODY_INK))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(BODY_INK))
    palette.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.Window, QColor("#ffffff"))
    app.setPalette(palette)


def main(argv: list[str]) -> int:
    # A QApplication, not QGuiApplication: QTextDocument's HTML layout
    # pulls in widget-level font resolution on Windows.
    app = QApplication(argv[:1])
    app.setApplicationName("MDTools")
    _force_light_palette(app)
    languages = argv[1:] or ["en", "pl", "ja"]
    for lang in languages:
        build(lang)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
