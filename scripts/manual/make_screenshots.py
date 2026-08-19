"""Renders every screenshot the user manual uses, in all three languages.

Run it, don't hand-capture: the manual exists in English, Polish and
Japanese, so each figure is needed three times over, and a hand-taken set
drifts out of date the moment a label changes.

Two things it deliberately does NOT touch:

- The user's own settings. QStandardPaths test mode redirects
  AppConfigLocation to a throwaway folder, so enabling the adapter and
  pinning a port here can't leak into the real settings.ini, and no
  screenshot can expose a real recent-project path.
- The serial port and foobar2000. Every dialog that would open hardware or
  make an HTTP call gets a stand-in (see _FakeDeck/_FakeFoobar) -- the real
  ones may well be busy recording a disc while this runs.

Output: doc/img/<lang>/<name>.png, plus the two language-independent
diagrams at doc/img/.
"""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from PySide6.QtCore import QBuffer, QByteArray, QPointF, QRectF, QStandardPaths, Qt  # noqa: E402
from PySide6.QtGui import (  # noqa: E402
    QBrush,
    QColor,
    QFont,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QApplication  # noqa: E402

OUT_DIR = ROOT / "doc" / "img"

# The demo album every screenshot shows. Invented on purpose: a real cover
# would put someone else's artwork into a document meant to be shared, and
# a made-up one can be regenerated identically on any machine, offline.
DEMO_ALBUM = "Night Ferry"
DEMO_ARTIST = "Aurora Test Signal"
DEMO_YEAR = 2026
DEMO_TRACKS: list[tuple[str, int]] = [
    ("Harbour Lights", 252),
    ("Slow Tide", 228),
    ("Night Ferry", 321),
    ("Cold Deck", 243),
    ("Signal Drift", 375),
    ("Salt and Static", 217),
    ("Lantern", 284),
    ("Undertow", 302),
    ("Blue Hour", 239),
    ("Far Shore", 268),
    ("Morning Dock", 367),
]


# --- helpers ---------------------------------------------------------------


def settle(ms: int = 300) -> None:
    """Lets Qt finish laying out and painting before the grab.

    grab() on a window that has not yet had its layout and first paint run
    produces half-drawn panels, so this is not optional."""
    end = time.monotonic() + ms / 1000.0
    while time.monotonic() < end:
        QApplication.processEvents()
        time.sleep(0.01)


def save(widget, path: Path, settle_ms: int = 300, before_grab=None) -> None:
    """`before_grab` runs after the window is on screen and laid out.

    Anything that depends on the viewport's real size -- fitting the canvas
    to the window, above all -- has to happen there: called before show()
    it computes against a placeholder size and leaves the canvas at some
    arbitrary zoom, cropped."""
    path.parent.mkdir(parents=True, exist_ok=True)
    widget.show()
    settle(settle_ms)
    if before_grab is not None:
        before_grab()
        settle(250)
    widget.grab().save(str(path))
    close_quietly(widget)
    settle(60)
    print(f"  {path.relative_to(ROOT)}")


def close_quietly(widget) -> None:
    """Closes a widget without it stopping to ask anything.

    The demo project has nothing to lose, but MainWindow does not know that:
    the automatic layout leaves it dirty, so closing it puts up the
    unsaved-changes prompt and the whole run stops on a modal dialog with
    nobody to answer it."""
    if hasattr(widget, "_mark_saved"):
        widget._mark_saved()
    widget.close()


def demo_cover_bytes() -> bytes:
    """A synthetic album cover, so the layout screenshots have something
    real to lay out without borrowing anyone's artwork."""
    size = 900
    image = QImage(size, size, QImage.Format.Format_RGB32)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    gradient = QLinearGradient(0, 0, size, size)
    gradient.setColorAt(0.0, QColor("#0b2a3a"))
    gradient.setColorAt(0.55, QColor("#1c4f63"))
    gradient.setColorAt(1.0, QColor("#c2543f"))
    painter.fillRect(0, 0, size, size, QBrush(gradient))

    # A horizon and a low sun: enough shape that "cropped to the cut
    # outline" and "turned onto the J-card front" are visibly doing
    # something, which a flat gradient would not show.
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(255, 214, 170, 235))
    painter.drawEllipse(QPointF(size * 0.62, size * 0.44), size * 0.11, size * 0.11)

    water = QPainterPath()
    water.moveTo(0, size * 0.58)
    water.lineTo(size, size * 0.58)
    water.lineTo(size, size)
    water.lineTo(0, size)
    water.closeSubpath()
    painter.fillPath(water, QColor(8, 26, 38, 210))

    painter.setPen(QPen(QColor(255, 214, 170, 90), size * 0.006))
    for index in range(9):
        y = size * (0.62 + index * 0.042)
        spread = size * (0.04 + index * 0.028)
        painter.drawLine(QPointF(size * 0.62 - spread, y), QPointF(size * 0.62 + spread, y))

    title_font = QFont("Georgia")
    title_font.setPixelSize(int(size * 0.105))
    title_font.setBold(True)
    painter.setFont(title_font)
    painter.setPen(QColor("#f4f1ea"))
    painter.drawText(QRectF(size * 0.08, size * 0.72, size * 0.84, size * 0.13), Qt.AlignmentFlag.AlignLeft, DEMO_ALBUM)

    artist_font = QFont("Georgia")
    artist_font.setPixelSize(int(size * 0.045))
    artist_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, size * 0.006)
    painter.setFont(artist_font)
    painter.setPen(QColor(244, 241, 234, 200))
    painter.drawText(
        QRectF(size * 0.08, size * 0.855, size * 0.84, size * 0.08),
        Qt.AlignmentFlag.AlignLeft,
        DEMO_ARTIST.upper(),
    )
    painter.end()

    # Bound to a name, never inlined into the QBuffer call: a temporary
    # QByteArray here is freed while the buffer still points at it, which
    # takes the interpreter down rather than raising.
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QBuffer.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    buffer.close()
    return bytes(data.data())


# --- stand-ins for hardware and foobar2000 ---------------------------------


class _FakeDeck:
    """Everything MDRemClient offers, minus the serial port."""

    def __init__(self, port_name: str, timeout_ms: int = 0):
        self.port_name = port_name

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return None

    def open(self) -> None:
        pass

    def close(self) -> None:
        pass

    def ping(self) -> bool:
        return True

    def command(self, text: str, timeout_ms: int | None = None) -> list[str]:
        return []


def _fake_ports():
    from mdtools.mdrem import PortCandidate

    return [
        PortCandidate("COM7", "RM-D10P Emulator", "Waveshare", True),
        PortCandidate("COM3", "Standard Serial over Bluetooth link", "Microsoft", False),
    ]


def _install_cd_stand_ins() -> None:
    """A drive with the demo album in it, and a MusicBrainz that recognises
    it -- so the CD window can be photographed with a disc read, on a
    machine that has neither a drive nor a network."""
    from mdtools import cdrip, musicbrainz

    def drives():
        return [cdrip.CdDrive(device="D:", label="Audio CD", has_media=True)]

    def toc(device, run=None):
        tracks, start = [], 0
        for number, (_, seconds) in enumerate(DEMO_TRACKS, start=1):
            sectors = seconds * cdrip.SECTORS_PER_SECOND
            tracks.append(cdrip.TocTrack(number=number, first_lba=start, sectors=sectors))
            start += sectors
        return cdrip.DiscToc(tracks=tracks, leadout_lba=start)

    def lookup(disc_toc, opener=None):
        return [
            musicbrainz.DiscRelease(
                release_id="demo",
                title=DEMO_ALBUM,
                artist=DEMO_ARTIST,
                year=DEMO_YEAR,
                country="XE",
                track_titles=[title for title, _ in DEMO_TRACKS],
                track_artists=[""] * len(DEMO_TRACKS),
            )
        ]

    cdrip.list_drives = drives
    cdrip.read_toc = toc
    cdrip.missing_tools = lambda: []
    musicbrainz.lookup_disc = lookup


def _install_burner_stand_ins() -> None:
    """A burner and its tools, stood in for exactly as the deck and the CD
    drive already are -- otherwise every burn screenshot would show
    "Missing tools" and an empty drive list, which is a picture of a
    machine, not of the feature."""
    from mdtools import cdburn, decode

    cdburn.cdrecord_path = lambda: "cdrecord"
    cdburn.missing_tools = lambda: []
    cdburn.list_burners = lambda **_kwargs: [
        cdburn.Burner(device="1,0,0", description="HL-DT-ST DVDRAM GP20N 1.02")
    ]
    # A hi-res album is what a download normally is, and the verdict column
    # saying so is worth showing.
    decode.can_convert = lambda: True


def _install_cover_stand_in() -> None:
    """Stops the recording dialogs reaching iTunes, and gives them the demo
    sleeve instead.

    Two reasons, and the first is not cosmetic: this script is meant to
    regenerate the same figures on any machine, offline (see DEMO_ALBUM), and
    those dialogs now look a cover up as soon as they open. The second is
    that the demo album is invented, so a real search correctly finds
    nothing -- every figure would show an empty preview while the text
    beside it describes the artwork.

    Patched per importing module rather than on cover_preview itself: each
    one did `from ... import fetch_into`, so its own name is what gets
    called."""
    from mdtools.panels import cd_rip_dialog, folder_record_dialog, record_dialog

    def fake_fetch(preview, artist, album, track_count=None):
        preview.set_cover(demo_cover_bytes())
        return None

    for module in (record_dialog, cd_rip_dialog, folder_record_dialog):
        module.fetch_into = fake_fetch


def _demo_playlist_items():
    from mdtools import foobar

    return [
        foobar.PlaylistItem(
            track_number=str(index),
            title=title,
            album_artist=DEMO_ARTIST,
            album=DEMO_ALBUM,
            date=str(DEMO_YEAR),
            length_seconds=length,
        )
        for index, (title, length) in enumerate(DEMO_TRACKS, start=1)
    ]


def _install_folder_stand_in() -> None:
    """Makes choosing a folder land straight in the loaded state.

    Picking a folder now hands it to foobar2000 on a worker thread, which
    this script has no real foobar for -- and a figure does not want a
    thread in it anyway. Replacing the load with the result it would have
    produced gives the dialog exactly the state a reader sees, including
    the Record button being enabled."""
    from mdtools.panels.folder_record_dialog import FolderRecordDialog

    FolderRecordDialog._load = lambda self: self._on_loaded(_demo_playlist_items())


def _make_fake_foobar():
    from mdtools import foobar

    items = _demo_playlist_items()

    class _FakeFoobar:
        def __init__(self, base_url: str = "", timeout: float = 0.0):
            pass

        def current_playlist(self):
            return foobar.Playlist(id="p1", title=f"{DEMO_ARTIST} - {DEMO_ALBUM}", item_count=len(items), is_current=True)

        def playlist_items(self, playlist_id: str, offset: int = 0, count: int = 0):
            return items

    return _FakeFoobar


# --- diagrams --------------------------------------------------------------


def _diagram_canvas(width: int, height: int) -> tuple[QImage, QPainter]:
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor("#ffffff"))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    return image, painter


def _box(painter: QPainter, rect: QRectF, title: str, subtitle: str = "", fill: str = "#eef3f7") -> None:
    painter.setPen(QPen(QColor("#33556b"), 2))
    painter.setBrush(QColor(fill))
    painter.drawRoundedRect(rect, 10, 10)
    painter.setPen(QColor("#12303f"))

    font = QFont("Segoe UI")
    font.setPixelSize(19)
    font.setBold(True)
    painter.setFont(font)
    title_rect = QRectF(rect.x(), rect.y() + (10 if subtitle else 0), rect.width(), rect.height() - (18 if subtitle else 0))
    painter.drawText(title_rect, Qt.AlignmentFlag.AlignCenter, title)

    if subtitle:
        font.setPixelSize(15)
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(QColor("#4a6a7c"))
        painter.drawText(
            QRectF(rect.x(), rect.bottom() - 34, rect.width(), 28), Qt.AlignmentFlag.AlignCenter, subtitle
        )


def _arrow(painter: QPainter, points: list[QPointF], colour: str = "#33556b", dashed: bool = False) -> None:
    """A polyline with a head on the last segment. Routing the S/PDIF link
    around the boxes rather than straight through them needs more than one
    segment, hence a point list."""
    pen = QPen(QColor(colour), 2.5)
    if dashed:
        pen.setStyle(Qt.PenStyle.DashLine)
    painter.setPen(pen)
    for start, end in zip(points, points[1:]):
        painter.drawLine(start, end)

    tail, tip = points[-2], points[-1]
    length = max(1.0, ((tip.x() - tail.x()) ** 2 + (tip.y() - tail.y()) ** 2) ** 0.5)
    ux, uy = (tip.x() - tail.x()) / length, (tip.y() - tail.y()) / length
    head = QPainterPath()
    head.moveTo(tip)
    head.lineTo(tip.x() - 14 * ux + 7 * uy, tip.y() - 14 * uy - 7 * ux)
    head.lineTo(tip.x() - 14 * ux - 7 * uy, tip.y() - 14 * uy + 7 * ux)
    head.closeSubpath()
    painter.fillPath(head, QColor(colour))


def _wire_label(painter: QPainter, centre: QPointF, text: str, colour: str) -> None:
    """Centred on a point, on an opaque patch. Sizing the box to the text
    rather than to the gap between two boxes is what stops a long label
    from being clipped -- which is exactly what the first version did."""
    font = QFont("Segoe UI")
    font.setPixelSize(16)
    painter.setFont(font)

    width = painter.fontMetrics().horizontalAdvance(text) + 14
    rect = QRectF(centre.x() - width / 2, centre.y() - 13, width, 26)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#ffffff"))
    painter.drawRect(rect)
    painter.setPen(QColor(colour))
    painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)


def draw_signal_chain(path: Path, strings: dict) -> None:
    """Which cable carries what. The single most common setup mistake is
    expecting the USB link to carry audio, or the optical one to carry
    commands -- this exists to make that split obvious."""
    image, painter = _diagram_canvas(1020, 420)

    pc = QRectF(30, 40, 230, 115)
    adapter = QRectF(400, 40, 230, 115)
    deck = QRectF(770, 40, 220, 115)

    _box(painter, pc, strings["pc"], strings["pc_sub"])
    _box(painter, adapter, strings["adapter"], strings["adapter_sub"], fill="#f7f0e8")
    _box(painter, deck, strings["deck"], strings["deck_sub"], fill="#eaf1ea")

    usb = "#33556b"
    ir = "#a8442a"
    spdif = "#2f6b4f"

    _arrow(painter, [QPointF(pc.right() + 6, 97), QPointF(adapter.left() - 8, 97)], usb)
    _wire_label(painter, QPointF((pc.right() + adapter.left()) / 2, 62), strings["usb"], usb)

    _arrow(painter, [QPointF(adapter.right() + 6, 97), QPointF(deck.left() - 8, 97)], ir)
    _wire_label(painter, QPointF((adapter.right() + deck.left()) / 2, 62), strings["ir"], ir)

    # Routed under everything: the audio path bypasses the adapter entirely,
    # and a straight line would suggest it passes through it.
    _arrow(
        painter,
        [
            QPointF(pc.center().x(), pc.bottom() + 6),
            QPointF(pc.center().x(), 320),
            QPointF(deck.center().x(), 320),
            QPointF(deck.center().x(), deck.bottom() + 10),
        ],
        spdif,
        dashed=True,
    )
    _wire_label(painter, QPointF((pc.center().x() + deck.center().x()) / 2, 320), strings["spdif"], spdif)

    painter.end()
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(str(path))
    print(f"  {path.relative_to(ROOT)}")


def draw_ir_circuit(path: Path) -> None:
    """The adapter's output stage. Component values only -- no prose -- so
    one drawing serves all three languages."""
    image, painter = _diagram_canvas(760, 470)

    ink = QColor("#12303f")
    wire = QPen(ink, 2.4)

    font = QFont("Consolas")
    font.setPixelSize(17)
    painter.setFont(font)

    def label(text: str, x: float, y: float) -> None:
        painter.setPen(ink)
        painter.drawText(QRectF(x, y, 260, 24), Qt.AlignmentFlag.AlignLeft, text)

    rail = 470.0  # x of the LED/collector branch
    painter.setPen(wire)

    # +5 V down through the current-setting resistor.
    painter.drawLine(rail, 40, rail, 80)
    painter.drawLine(rail - 16, 40, rail + 16, 40)
    label("+5 V (VBUS)", rail + 26, 28)

    painter.drawRect(QRectF(rail - 20, 80, 40, 66))
    label("Rd 47 R", rail + 34, 100)
    painter.drawLine(rail, 146, rail, 178)

    # LED: anode triangle pointing at the cathode bar, current flowing down.
    led = QPainterPath()
    led.moveTo(rail - 24, 178)
    led.lineTo(rail + 24, 178)
    led.lineTo(rail, 218)
    led.closeSubpath()
    painter.fillPath(led, ink)
    painter.setPen(wire)
    painter.drawLine(rail - 24, 218, rail + 24, 218)
    label("IR LED", rail + 62, 186)

    # Emission arrows, kept clear of the text to their right.
    painter.setPen(QPen(QColor("#a8442a"), 2))
    for offset in (0, 14):
        painter.drawLine(rail + 30 + offset, 206, rail + 46 + offset, 188)
        painter.drawLine(rail + 46 + offset, 188, rail + 41 + offset, 190)
        painter.drawLine(rail + 46 + offset, 188, rail + 44 + offset, 195)
    painter.setPen(wire)

    painter.drawLine(rail, 218, rail, 268)

    # NPN: vertical base bar, collector and emitter angling off it.
    bar_x = rail - 42
    painter.drawLine(bar_x, 258, bar_x, 322)
    painter.drawLine(bar_x, 272, rail, 268)  # collector
    painter.drawLine(bar_x, 308, rail, 312)  # emitter

    # The emitter arrow is what makes this an NPN rather than a PNP.
    arrow = QPainterPath()
    arrow.moveTo(rail - 4, 311)
    arrow.lineTo(rail - 22, 300)
    arrow.lineTo(rail - 19, 311)
    arrow.closeSubpath()
    painter.fillPath(arrow, ink)

    label("S9014", rail + 30, 276)
    label("C", rail - 20, 232)
    label("E", rail - 20, 322)
    label("B", bar_x - 24, 268)

    # Base drive: GPIO through the base resistor onto the bar.
    painter.drawLine(bar_x, 290, bar_x - 60, 290)
    painter.drawRect(QRectF(bar_x - 130, 268, 70, 44))
    label("Rb 470 R", bar_x - 142, 232)
    painter.drawLine(bar_x - 130, 290, 90, 290)
    label("GPIO12", 20, 278)

    # Emitter to ground.
    painter.drawLine(rail, 312, rail, 380)
    for half_width, y in ((26, 380), (17, 391), (8, 402)):
        painter.drawLine(rail - half_width, y, rail + half_width, y)
    label("GND", rail + 40, 372)

    painter.end()
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(str(path))
    print(f"  {path.relative_to(ROOT)}")


SIGNAL_CHAIN_STRINGS = {
    "en": {
        "pc": "PC - MDTools",
        "pc_sub": "foobar2000 + Beefweb",
        "adapter": "MDRem adapter",
        "adapter_sub": "RP2040, virtual COM port",
        "deck": "MiniDisc deck",
        "deck_sub": "MDS-JE480",
        "usb": "USB (commands)",
        "ir": "infrared (keys)",
        "spdif": "S/PDIF (audio)",
    },
    "pl": {
        "pc": "Komputer - MDTools",
        "pc_sub": "foobar2000 + Beefweb",
        "adapter": "Przystawka MDRem",
        "adapter_sub": "RP2040, wirtualny port COM",
        "deck": "Magnetofon MD",
        "deck_sub": "MDS-JE480",
        "usb": "USB (komendy)",
        "ir": "podczerwien (klawisze)",
        "spdif": "S/PDIF (dzwiek)",
    },
    "ja": {
        "pc": "PC - MDTools",
        "pc_sub": "foobar2000 + Beefweb",
        "adapter": "MDRem アダプター",
        "adapter_sub": "RP2040 / 仮想COMポート",
        "deck": "MDデッキ",
        "deck_sub": "MDS-JE480",
        "usb": "USB (コマンド)",
        "ir": "赤外線 (キー)",
        "spdif": "S/PDIF (音声)",
    },
}


# --- the screenshots themselves --------------------------------------------


def _demo_album_folder() -> Path:
    """A throwaway folder of empty files for the Record Folder screenshot.

    Empty is enough: that dialog only ever lists filenames and asks foobar
    (stood in for here) what the tags say, so it never opens one. Under the
    temp folder rather than anywhere the reader might have real music."""
    folder = Path(tempfile.gettempdir()) / "MDTools Manual" / f"{DEMO_ARTIST} - {DEMO_ALBUM} ({DEMO_YEAR})"
    folder.mkdir(parents=True, exist_ok=True)
    for index, (title, _length) in enumerate(DEMO_TRACKS, start=1):
        (folder / f"{index:02d} {title}.flac").write_bytes(b"")
    return folder


def demo_metadata():
    from mdtools.project import ProjectMetadata, Track

    return ProjectMetadata(
        album=DEMO_ALBUM,
        artist=DEMO_ARTIST,
        year=DEMO_YEAR,
        tracks=[Track(title=title, time_seconds=length) for title, length in DEMO_TRACKS],
        cover_art=demo_cover_bytes(),
    )


def capture_language(app, code: str) -> None:
    from mdtools import app_settings, i18n, mdrem
    from mdtools.app_window import MainWindow
    from mdtools.panels.about_dialog import AboutDialog
    from mdtools.panels.cd_rip_dialog import CdRipDialog
    from mdtools.panels.erase_dialog import EraseDiscDialog
    from mdtools.panels.folder_record_dialog import FolderRecordDialog
    from mdtools.panels.metadata_dialog import MetadataDialog
    from mdtools.panels.mdrem_upload_dialog import MDRemUploadDialog
    from mdtools.panels.new_design_dialog import NewDesignDialog
    from mdtools.panels.print_dialog import PrintDialog
    from mdtools.panels.record_dialog import RecordDialog
    from mdtools.panels.remote_dialog import RemoteDialog
    from mdtools.panels.settings_dialog import SettingsDialog
    from mdtools.panels.startup_dialog import StartupDialog
    from mdtools.project import PAGE_COVER, PAGE_DISC
    from mdtools.templates.template_dialog import TemplateManagerDialog

    print(f"[{code}]")
    i18n.set_language(code)
    i18n.install_translator(app, code)

    app_settings.set_mdrem_enabled(True)
    app_settings.set_mdrem_port("COM7")

    out = OUT_DIR / code
    metadata = demo_metadata()

    draw_signal_chain(out / "signal-chain.png", SIGNAL_CHAIN_STRINGS[code])

    # -- startup and new project
    recent = [
        str(Path.home() / "Documents" / "MiniDisc" / f"{DEMO_ALBUM}.mdproj"),
        str(Path.home() / "Documents" / "MiniDisc" / "Popular Monster.mdproj"),
    ]
    save(StartupDialog(recent), out / "startup.png")
    save(NewDesignDialog(), out / "new-project.png")

    # -- the main window, with both pages laid out from the demo album
    window = MainWindow(show_startup_dialog=False)
    window.show()
    settle(400)
    window.project.metadata = metadata
    window._auto_layout_project(metadata)
    settle(500)
    save(window, out / "main-disc.png", settle_ms=500, before_grab=window.view.fit_to_window)

    def show_jcard() -> None:
        window.page_combo.setCurrentIndex(window.page_combo.findData(PAGE_COVER))
        settle(200)
        # A selected text layer, so the Properties panel shows its fields
        # rather than the empty state every other screenshot catches.
        scene = window.project.pages[PAGE_COVER]
        texts = [item for item in scene.print_items() if hasattr(item, "toPlainText")]
        if texts:
            window._select_item(texts[-1])
        window.view.fit_to_window()

    save(window, out / "main-jcard.png", settle_ms=400, before_grab=show_jcard)

    # -- dialogs reached from the main window
    save(MetadataDialog(metadata), out / "metadata.png")
    save(SettingsDialog(), out / "settings.png")
    save(TemplateManagerDialog(), out / "templates.png")

    window.show()
    settle(200)
    save(PrintDialog(window.project), out / "print.png", settle_ms=600)
    close_quietly(window)

    save(AboutDialog(), out / "about.png")

    # -- a CD project: the ring label, the folded insert, and the burn
    _capture_cd(out, code, metadata)

    # -- everything MDRem, with the hardware and foobar2000 stood in for
    save(RemoteDialog("COM7"), out / "remote.png")
    save(MDRemUploadDialog(metadata, "COM7"), out / "upload.png", settle_ms=400)
    save(RecordDialog("COM7", "http://localhost:8880"), out / "record.png", settle_ms=400)

    # -- reading a CD, with the drive and MusicBrainz stood in for
    rip = CdRipDialog("http://localhost:8880")
    rip.show()
    settle(200)
    rip._read_disc()
    save(rip, out / "cd-rip.png", settle_ms=400)
    close_quietly(rip)

    # -- recording a folder of files, with a throwaway album on disk
    folder = FolderRecordDialog("http://localhost:8880")
    folder.show()
    settle(200)
    folder.set_folder(_demo_album_folder())  # which loads it, see the stand-in
    save(folder, out / "folder-record.png", settle_ms=400)
    close_quietly(folder)

    save(EraseDiscDialog("COM7"), out / "erase.png")

    _capture_telegram(out, code)


# --- the experimental Telegram feature ------------------------------------
#
# **Nothing here contacts Telegram**, which is the same rule the rest of this
# script follows for the serial port, foobar2000 and the cover lookup -- but
# it needs no stand-in object to achieve it. Both dialogs are inert until an
# explicit action starts their worker (TelegramChatDialog.start_connecting(),
# and TelegramLoginDialog only on "Send code"), so plain construction opens no
# socket at all. The chat transcript is then filled by handing synthetic
# ChatMessages straight to the dialog's own signal handlers -- the real
# rendering code, driven with fake data, rather than a mock of the rendering.

_TELEGRAM_CHAT: dict[str, list[str]] = {
    #        bot greeting, the reply we show as sent, the file it answers with
    "en": ["Send me an artist and album and I will look it up.", "Aurora Test Signal - Night Ferry"],
    "pl": ["Podaj wykonawcę i album, a poszukam.", "Aurora Test Signal - Night Ferry"],
    "ja": ["アーティストとアルバム名を送ってください。", "Aurora Test Signal - Night Ferry"],
}

# One row, two columns -- ChatMessage.buttons is a label *grid*, not a flat
# list, since a position in it is what identifies a button to click.
_TELEGRAM_BUTTONS = [["FLAC (312 MB)", "MP3 320 (98 MB)"]]


# Windows captured here are kept alive for the life of the process. A
# MainWindow collected while its scenes still have selectionChanged
# connected prints "Internal C++ object (DesignScene) already deleted" at
# interpreter shutdown -- harmless, since every file is written by then,
# but it reads like a failed run.
_KEEP_ALIVE: list = []


def _capture_cd(out: Path, code: str, metadata) -> None:
    """The CD half: a project on the CD templates with both pages laid out,
    and the burn dialog over a folder of files.

    The album is written to disk as real (empty) FLACs, because the burn
    dialog reads its track lengths from the files themselves -- a list of
    names alone would show a disc of zero-length tracks, which is a picture
    of nothing.
    """
    import tempfile

    from mdtools.app_window import CD_INSERT_TEMPLATE, CD_LABEL_TEMPLATE, MainWindow
    from mdtools.panels.burn_dialog import BurnDialog
    from mdtools.panels.print_dialog import PrintDialog
    from mdtools.project import MEDIUM_CD, PAGE_COVER, PAGE_DISC
    from mdtools.templates import registry

    templates = registry.load_templates()
    window = MainWindow(show_startup_dialog=False)
    window.project.medium = MEDIUM_CD
    window.apply_template(PAGE_DISC, next(t for t in templates["disc"] if t.name == CD_LABEL_TEMPLATE))
    window.apply_template(PAGE_COVER, next(t for t in templates["cover"] if t.name == CD_INSERT_TEMPLATE))
    window.project.metadata = metadata
    window.show()
    settle(300)
    window._auto_layout_project(metadata)
    settle(400)
    save(window, out / "cd-label.png", settle_ms=500, before_grab=window.view.fit_to_window)

    def show_insert() -> None:
        window.page_combo.setCurrentIndex(window.page_combo.findData(PAGE_COVER))
        settle(200)
        window.view.fit_to_window()

    save(window, out / "cd-insert.png", settle_ms=400, before_grab=show_insert)

    def separate_sheets(dialog) -> None:
        dialog.orientation_combo.setCurrentIndex(1)
        dialog.separate_sheets_check.setChecked(True)

    printing = PrintDialog(window.project)
    separate_sheets(printing)
    save(printing, out / "cd-print.png", settle_ms=600)
    close_quietly(printing)
    close_quietly(window)
    _KEEP_ALIVE.append(window)

    # The dialog reads each track's length from the file itself, so the
    # album is stood in for the same way the deck and the CD drive are:
    # decode.analyze answers with the demo album's real running times.
    # Writing eight real WAVs would mean 300MB of silence, and putting them
    # anywhere near the repo would be worse than that.
    from mdtools import decode

    lengths = {}
    sources = []
    scratch = Path(tempfile.gettempdir()) / "xdtools-manual-burn"
    for index, track in enumerate(metadata.tracks[:8], start=1):
        path = scratch / f"{index:02d}.flac"
        lengths[str(path)] = track.time_seconds or 210
        sources.append((path, track.title, track.artist or metadata.artist))

    def stand_in(target):
        seconds = lengths.get(str(target), 210)
        return decode.AudioProperties(
            sample_rate=44100, bits_per_sample=16, channels=2, frames=seconds * 44100
        )

    real_analyze = decode.analyze
    decode.analyze = stand_in
    try:
        burn = BurnDialog(
            sources,
            album=metadata.album,
            artist=metadata.artist,
            year=metadata.year,
            cover_art=metadata.cover_art,
        )
        save(burn, out / "burn.png", settle_ms=400)
        close_quietly(burn)
    finally:
        decode.analyze = real_analyze


def _capture_telegram(out: Path, code: str) -> None:
    from mdtools import app_settings, telegram_bot
    from mdtools.panels.experimental_settings_dialog import ExperimentalSettingsDialog
    from mdtools.panels.telegram_chat_dialog import TelegramChatDialog
    from mdtools.panels.telegram_login_dialog import TelegramLoginDialog

    # A folder of its own rather than the real system temp: the button-state
    # checks below read it, so controlling exactly what is in it keeps the
    # figures deterministic. Two real (empty) .flac files, because Sort and
    # Record enable themselves from what is actually on disk -- without them
    # the figure would show three greyed-out buttons the manual points at.
    download_folder = Path(tempfile.mkdtemp(prefix="mdtools-manual-telegram-"))
    for track in ("01 Harbour Lights.flac", "02 Slow Tide.flac"):
        (download_folder / track).write_bytes(b"")
    app_settings.set_experimental_features_enabled(True)
    app_settings.set_telegram_bot_username("@my_music_bot")
    app_settings.set_telegram_download_folder(str(download_folder))

    save(ExperimentalSettingsDialog(), out / "experimental-settings.png")
    save(TelegramLoginDialog("0", "0"), out / "telegram-login.png")

    greeting, reply = _TELEGRAM_CHAT[code]
    chat = TelegramChatDialog("0", "0", "@my_music_bot", download_folder, None)
    chat.show()
    settle(200)
    # What _on_ready() would normally set once connected.
    chat._bot_name = "@my_music_bot"
    chat._session_folder = str(download_folder)
    chat.status_label.setText(chat.tr("Connected to {name}.").format(name="@my_music_bot"))
    chat.message_edit.setEnabled(True)
    chat.send_btn.setEnabled(True)
    chat.open_folder_btn.setEnabled(True)
    for button in chat.quick_command_buttons:
        button.setEnabled(True)

    chat._on_message_received(telegram_bot.ChatMessage(id=1, outgoing=False, text=greeting))
    chat._on_message_received(telegram_bot.ChatMessage(id=2, outgoing=True, text=reply))
    chat._on_message_received(
        telegram_bot.ChatMessage(id=3, outgoing=False, text="Night Ferry", buttons=_TELEGRAM_BUTTONS)
    )
    for index, (name, size) in enumerate(
        [("01 Harbour Lights.flac", 31_400_000), ("02 Slow Tide.flac", 28_900_000)], start=10
    ):
        chat._on_message_received(
            telegram_bot.ChatMessage(id=index, outgoing=False, text="", file_name=name, file_size=size)
        )
    # One row mid-download, one already finished -- the two states the queue
    # spends nearly all its time in.
    chat._on_download_started(10)
    chat._on_download_progress(10, 19_800_000, 31_400_000)
    chat._on_download_started(11)
    chat._on_download_finished(11, str(download_folder / "02 Slow Tide.flac"))
    # _on_download_started(10) above left that one "in flight", which
    # deliberately disables Sort/Record -- clear it so the figure shows their
    # normal, usable state rather than a transient one.
    chat._active_downloads.clear()
    chat._update_sort_button()
    chat._update_continue_button()

    save(chat, out / "telegram-chat.png", settle_ms=400)
    close_quietly(chat)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("MDTools")
    # Everything this script writes through QSettings/QStandardPaths lands
    # in a throwaway folder instead of the user's real configuration.
    QStandardPaths.setTestModeEnabled(True)

    from mdtools import foobar, mdrem, theme
    from mdtools.templates import registry

    # Matches main.py exactly -- otherwise these screenshots would keep
    # showing Qt's old default light theme while the real app has looked
    # like this (Fusion + a dark palette) since it was added.
    theme.apply_theme(app)

    registry.sync_builtin_templates()

    mdrem.MDRemClient = _FakeDeck
    mdrem.list_ports = _fake_ports
    foobar.FoobarClient = _make_fake_foobar()
    _install_cd_stand_ins()
    _install_burner_stand_ins()
    _install_cover_stand_in()
    _install_folder_stand_in()

    draw_ir_circuit(OUT_DIR / "ir-circuit.png")
    for code in ("en", "pl", "ja"):
        capture_language(app, code)

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
