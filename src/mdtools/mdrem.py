"""Talking to MDRem -- an RP2040 board that emulates a Sony RM-D10P IR
remote, letting MDTools write a project's metadata straight onto the
MiniDisc it describes instead of only printing a label for it.

Deliberately a top-level module with no dependency on this app's widgets
(same reasoning as grayscale.py/app_settings.py): the panels import it,
never the other way round, and every pure function here -- transliteration,
disc-title formatting, building the command sequence -- is testable with no
hardware and no QApplication.

Transport is PySide6's own QtSerialPort rather than pyserial, so this adds
no dependency to pyproject.toml or to either build script. It is driven
synchronously (waitForReadyRead, not readyRead signals) because the only
caller is a worker thread with no event loop of its own -- a whole upload
blocks for minutes, so it can never run on the GUI thread anyway.

Things the deck imposes on us, all measured against a real MDS-JE480 (see
the MDRem firmware's own CLAUDE.md for the full findings):
- Titles are ASCII 0x20-0x7E only. The firmware silently skips anything
  else, so a Polish or Japanese title would arrive mangled -- hence
  transliterate() and its `dropped` report, which the UI shows before
  sending rather than after.
- The deck accepts roughly 3.5 keypresses per second and there is no
  feedback channel of any kind, so a full album takes minutes and nothing
  can confirm it worked except the user's own eyes.
- Nothing is written to the disc until it is ejected.
"""

from __future__ import annotations

import time
import unicodedata
from dataclasses import dataclass, field

from PySide6.QtCore import QCoreApplication
from PySide6.QtSerialPort import QSerialPort, QSerialPortInfo

from mdtools.project import ProjectMetadata

BAUD_RATE = 115200

# The RP2040's USB VID. Not a reliable identifier on its own -- the board's
# own manifest uses 2E8A:0003, which is both the bootloader's PID and a
# generic Waveshare one -- so it only ever prioritises which ports to probe
# first; PING/PONG is what actually identifies the device.
RP2040_VENDOR_ID = 0x2E8A

# Set from the firmware's platformio.ini as the USB product string. Windows
# exposes it as the parent device's bus-reported description, which is what
# QSerialPortInfo.description() usually surfaces.
PRODUCT_HINT = "RM-D10P Emulator"

# Short commands answer immediately; a title is a minutes-long operation on
# the deck's side and the firmware only replies once it has finished.
DEFAULT_TIMEOUT_MS = 4000
TITLE_TIMEOUT_MS = 180_000

# Detection probes every port on the machine, and a typical Windows box has
# several phantom Bluetooth serial ports that accept a connection and then
# say nothing. At the normal timeout that alone would take half a minute,
# so probing gets its own much shorter one -- the real device answers PING
# in milliseconds.
DETECT_TIMEOUT_MS = 700

# The firmware's key table stops at TRACK25.
MAX_TRACK = 25

# Timing constants measured on a real MDS-JE480, used only to estimate how
# long an upload will take so the progress dialog can say something useful
# up front. The deck accepts about 3.5 keypresses per second and gives no
# feedback at all, so this is genuinely all we can offer -- there is no
# progress signal to read, only elapsed time against an expectation.
_STEP_OVERHEAD_S = 6.0  # STOP/TRACK/PAUSE/NAME/ENTER plus the settle waits
_SECONDS_PER_CLEAR = 0.435
_SECONDS_PER_CHAR = 0.285

# The firmware's default number of delete presses before typing, which it
# overshoots on purpose because the old title's length can't be read back.
# Clearing is the single most expensive part of writing a title -- roughly
# 17 s of the ~25 s a track takes -- so skipping it on a disc whose titles
# are still empty very nearly halves a whole upload.
DEFAULT_CLEAR_COUNT = 40


class MDRemError(Exception):
    """Any failure talking to the device: port won't open, no reply in
    time, or the firmware answered ERR."""


@dataclass
class PortCandidate:
    name: str  # e.g. "COM3"
    description: str
    manufacturer: str
    is_likely: bool  # matches the RP2040 VID and/or the product string

    def label(self) -> str:
        parts = [self.name]
        if self.description:
            parts.append(self.description)
        return " - ".join(parts)


def list_ports() -> list[PortCandidate]:
    """Every serial port on the system, likely-looking ones first."""
    candidates: list[PortCandidate] = []
    for info in QSerialPortInfo.availablePorts():
        description = info.description() or ""
        likely = (info.hasVendorIdentifier() and info.vendorIdentifier() == RP2040_VENDOR_ID) or (
            PRODUCT_HINT.lower() in description.lower()
        )
        candidates.append(
            PortCandidate(
                name=info.portName(),
                description=description,
                manufacturer=info.manufacturer() or "",
                is_likely=likely,
            )
        )
    candidates.sort(key=lambda c: (not c.is_likely, c.name))
    return candidates


def detect_port(timeout_ms: int = DETECT_TIMEOUT_MS) -> str | None:
    """Finds the device by asking every port whether it answers PING.

    A handshake rather than a VID/PID match on purpose: the board reports
    2E8A:0003, which is indistinguishable from its own bootloader and from
    other Waveshare boards, so identity has to come from the protocol.
    Likely-looking ports are probed first purely to keep this quick."""
    for candidate in list_ports():
        try:
            with MDRemClient(candidate.name, timeout_ms=timeout_ms) as client:
                if client.ping():
                    return candidate.name
        except MDRemError:
            continue
    return None


class MDRemClient:
    """One open serial connection. Usable as a context manager."""

    def __init__(self, port_name: str, timeout_ms: int = DEFAULT_TIMEOUT_MS):
        self.port_name = port_name
        self.timeout_ms = timeout_ms
        # Constructed here rather than at module level -- see this project's
        # standing rule about never building Qt objects at import time.
        self._port = QSerialPort()
        self._port.setPortName(port_name)
        self._port.setBaudRate(BAUD_RATE)
        self._port.setDataBits(QSerialPort.DataBits.Data8)
        self._port.setParity(QSerialPort.Parity.NoParity)
        self._port.setStopBits(QSerialPort.StopBits.OneStop)
        self._port.setFlowControl(QSerialPort.FlowControl.NoFlowControl)

    def __enter__(self) -> MDRemClient:
        self.open()
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def open(self) -> None:
        if self._port.isOpen():
            return
        if not self._port.open(QSerialPort.OpenModeFlag.ReadWrite):
            raise MDRemError(f"{self.port_name}: {self._port.errorString()}")
        # The board reboots into its bootloader on a 1200-baud open, and a
        # freshly opened CDC port drops whatever the firmware said first.
        self._port.setDataTerminalReady(True)
        self._port.clear()

    def close(self) -> None:
        if self._port.isOpen():
            self._port.close()

    def ping(self) -> bool:
        try:
            self.command("PING")
            return True
        except MDRemError:
            return False

    def command(self, text: str, timeout_ms: int | None = None) -> list[str]:
        """Sends one line and collects the reply up to its terminator.

        Returns the informational lines (the firmware prefixes those with
        ';'), having consumed the final OK/PONG. Raises MDRemError on ERR
        or on a timeout."""
        if not self._port.isOpen():
            raise MDRemError("port is not open")

        timeout = self.timeout_ms if timeout_ms is None else timeout_ms
        self._port.clear()
        self._port.write((text + "\n").encode("ascii", errors="replace"))
        if not self._port.waitForBytesWritten(self.timeout_ms):
            raise MDRemError(f"timed out sending {text!r}")

        deadline = time.monotonic() + timeout / 1000.0
        info: list[str] = []
        while True:
            line = self._read_line(deadline, text)
            if line in ("OK", "PONG"):
                return info
            if line.startswith("ERR"):
                raise MDRemError(f"{text!r} -> {line}")
            info.append(line)

    def _read_line(self, deadline: float, sent: str) -> str:
        while not self._port.canReadLine():
            remaining_ms = int((deadline - time.monotonic()) * 1000)
            if remaining_ms <= 0 or not self._port.waitForReadyRead(remaining_ms):
                raise MDRemError(f"no reply to {sent!r}")
        return bytes(self._port.readLine()).decode("ascii", errors="replace").strip()


# --- text conversion -------------------------------------------------------

# Characters NFKD decomposition leaves alone because they aren't an
# accented form of a Latin letter at all -- "ł" is its own letter, not
# "l" plus a stroke -- plus the typographic punctuation metadata lookups
# routinely return, which has a plain ASCII equivalent worth keeping.
_EXPLICIT_MAP = {
    "ł": "l", "Ł": "L", "đ": "d", "Đ": "D", "ø": "o", "Ø": "O",
    "ß": "ss", "æ": "ae", "Æ": "AE", "œ": "oe", "Œ": "OE",
    "þ": "th", "Þ": "Th", "ð": "d", "Ð": "D",
    "‘": "'", "’": "'", "‚": ",",
    "“": '"', "”": '"', "„": '"',
    "–": "-", "—": "-", "…": "...",
    " ": " ", "×": "x", "·": "-",
}


@dataclass
class Transliteration:
    """`text` is what will actually be sent; `dropped` lists the distinct
    characters that had no ASCII equivalent and vanished entirely, so the
    UI can show them before anything is written to a disc."""

    text: str
    dropped: list[str] = field(default_factory=list)

    @property
    def is_lossy(self) -> bool:
        return bool(self.dropped)


def transliterate(text: str) -> Transliteration:
    """Best-effort ASCII 0x20-0x7E, which is all the deck accepts.

    Accented Latin letters lose their marks (ą -> a, é -> e) via NFKD
    decomposition; the handful of letters that decomposition doesn't touch
    are mapped explicitly. Anything left with no equivalent at all -- CJK,
    emoji -- is reported in `dropped` rather than silently discarded, since
    the firmware would drop it anyway and the user deserves to know before
    spending four minutes writing a mangled title."""
    out: list[str] = []
    dropped: list[str] = []
    for char in text:
        if " " <= char <= "~":
            out.append(char)
            continue
        replacement = _EXPLICIT_MAP.get(char)
        if replacement is None:
            decomposed = unicodedata.normalize("NFKD", char)
            replacement = "".join(c for c in decomposed if " " <= c <= "~")
        if replacement:
            out.append(replacement)
        elif char not in dropped and not char.isspace():
            dropped.append(char)
    return Transliteration(text="".join(out).strip(), dropped=dropped)


def disc_title(metadata: ProjectMetadata) -> str:
    """"Artist - Album (Year)", skipping whatever isn't filled in.

    Matches the format used when this was first done by hand against a real
    deck, and keeps the three metadata fields recoverable by eye from the
    single title line the format actually gives us."""
    head = " - ".join(part for part in (metadata.artist.strip(), metadata.album.strip()) if part)
    if metadata.year:
        return f"{head} ({metadata.year})".strip() if head else str(metadata.year)
    return head


# --- upload plan -----------------------------------------------------------


@dataclass
class UploadStep:
    label: str  # shown in the progress dialog
    command: str  # the line sent to the firmware
    text: str  # the title this step writes, already transliterated


@dataclass
class UploadPlan:
    """Pure description of what an upload would do -- built and inspected
    without a device attached, so the confirmation dialog and the tests can
    both use it (same "plan it, then let the caller execute it" split as
    DesignScene.plan_clip_layers/printing.build_copies_layout)."""

    steps: list[UploadStep] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)  # distinct, across every title
    skipped_tracks: list[str] = field(default_factory=list)  # beyond MAX_TRACK

    @property
    def is_empty(self) -> bool:
        return not self.steps


def estimated_step_seconds(step: UploadStep, clearing: bool = True) -> float:
    """Roughly how long one step takes. Approximate on purpose -- with no
    feedback channel, elapsed time against this estimate is the only thing
    a progress bar can possibly be driven by."""
    presses = max(DEFAULT_CLEAR_COUNT, len(step.text) + 8) if clearing else 0
    return _STEP_OVERHEAD_S + presses * _SECONDS_PER_CLEAR + len(step.text) * _SECONDS_PER_CHAR


def estimated_seconds(plan: UploadPlan, clearing: bool = True) -> float:
    return sum(estimated_step_seconds(step, clearing) for step in plan.steps)


def build_upload_plan(metadata: ProjectMetadata) -> UploadPlan:
    """Disc title first, then one step per track.

    Tracks past MAX_TRACK are reported rather than sent: the firmware's key
    table simply has no code for them, so there is no way to select those
    tracks on the deck at all."""
    plan = UploadPlan()

    def note_dropped(result: Transliteration) -> None:
        for char in result.dropped:
            if char not in plan.dropped:
                plan.dropped.append(char)

    title = transliterate(disc_title(metadata))
    note_dropped(title)
    if title.text:
        plan.steps.append(
            UploadStep(
                label=QCoreApplication.translate("MDRem", "Disc title"),
                command=f"TITLEDISC {title.text}",
                text=title.text,
            )
        )

    for index, track in enumerate(metadata.tracks, start=1):
        converted = transliterate(track.title)
        note_dropped(converted)
        if not converted.text:
            continue
        if index > MAX_TRACK:
            plan.skipped_tracks.append(track.title)
            continue
        plan.steps.append(
            UploadStep(
                label=QCoreApplication.translate("MDRem", "Track {n}").format(n=index),
                command=f"TITLETRACK {index} {converted.text}",
                text=converted.text,
            )
        )

    return plan
