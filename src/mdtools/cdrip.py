"""Reading an audio CD: which drives exist, what is on the disc, and
extracting it to tagged FLAC files that foobar2000 can then play into the
deck.

The actual work is done by two bundled command line programs rather than
by talking to the drive ourselves -- see `bin/win64/ATTRIBUTION.md`:

- **cd-paranoia** (libcdio's maintained port of Xiph's cdparanoia), which
  is what makes this worth doing at all. Windows will happily hand you a
  CD track as a 44-byte `.cda` stub and nothing else; reading the actual
  audio means raw CDDA sector reads, and doing those *correctly* means
  jitter correction and re-reads on scratches. That is the entire subject
  cdparanoia exists for, and reimplementing it over `IOCTL_CDROM_RAW_READ`
  would be a worse version of it.
- **flac**, to encode what came off the disc.

Both are located through `tools_dir()`, which mirrors `gallery.gallery_dir()`
/ `icons.icons_dir()` exactly: `bin/<platform>` beside the source checkout in
dev mode, or inside a PyInstaller bundle's `sys._MEIPASS` in a frozen build.
Nothing is bundled for Linux -- there `find_tool()` falls through to PATH,
where a distro's own `cdparanoia`/`flac` packages live.

No Qt anywhere in here, matching mdrem.py and foobar.py: the panels import
this, never the other way round, and everything except the two functions
that actually spawn a process is testable without a drive.

The split is the same "build a plan, let the caller execute it" one used by
`DesignScene.plan_clip_layers()` / `printing.build_copies_layout()` /
`mdrem.build_upload_plan()`: `build_rip_plan()` is pure, so what will be
written where -- and under what titles -- can be shown to the user, and
tested, without a disc anywhere near it.
"""

from __future__ import annotations

import base64
import ctypes
import hashlib
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

# A CDDA sector is 1/75th of a second of 16-bit stereo 44.1kHz audio.
SECTOR_BYTES = 2352
SECTORS_PER_SECOND = 75

# LBA 0 is MSF 00:02:00 -- the 150-sector lead-in gap. Disc identifiers are
# specified in MSF-based frame offsets, so every LBA has to be shifted by
# this before it goes into one.
PREGAP_SECTORS = 150

# Nothing here is quick, and a drive that is spinning up, retrying a
# scratch, or simply absent must not wedge the app forever.
TOC_TIMEOUT_S = 60.0
ENCODE_TIMEOUT_S = 300.0

# How often a running rip is checked on. Also the worst case delay before
# Stop takes effect, which is what keeps this well under a second.
RIP_POLL_S = 0.2

# Enough of cdparanoia's log to hold its actual complaint, without reading a
# whole album's worth of per-sector chatter back into memory to find it.
_LOG_TAIL_CHARS = 4000

# Windows only: keep every child process from flashing up its own console
# window. A frozen GUI build has no console of its own, so without this a
# 12-track rip would pop 24 black windows in the user's face.
# Public because cdburn.py drives its own child processes and needs the
# same "don't flash a console window" flag -- one definition, not two.
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


class CdRipError(Exception):
    """No drive, no disc, a tool that is missing or failed, or output that
    does not match what the TOC promised."""


class CdRipCancelled(Exception):
    """Raised out of a rip the user stopped. Deliberately not a CdRipError:
    nothing went wrong, so nothing should be reported as having done."""


# --- bundled tools ----------------------------------------------------


def tools_dir() -> Path:
    """Where the bundled command line tools live: inside a frozen build's
    bundled data (sys._MEIPASS), or `bin/<platform>` at the repo root in dev
    mode -- the same dev-vs-frozen resolution gallery.gallery_dir() and
    icons.icons_dir() use for their own out-of-package asset folders."""
    frozen_base = getattr(sys, "_MEIPASS", None)
    if frozen_base is not None:
        base = Path(frozen_base)
    else:
        # this file: src/mdtools/cdrip.py -> repo root is two levels above src/
        base = Path(__file__).resolve().parents[2]
    return base / "bin" / ("win64" if sys.platform == "win32" else "linux")


def find_tool(*names: str) -> str | None:
    """The bundled copy of a tool if there is one, otherwise whatever PATH
    offers.

    Bundled first, so a Windows install needs nothing installed alongside
    it and every user is running the same known version; PATH second, so
    Linux -- where nothing is bundled, since distros package both tools
    themselves -- works with no special casing anywhere else."""
    directory = tools_dir()
    for name in names:
        for candidate in (name, f"{name}.exe"):
            path = directory / candidate
            if path.is_file():
                return str(path)
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    return None


def cdparanoia_path() -> str | None:
    """libcdio's port calls itself cd-paranoia; Xiph's original, still what
    most distros package, calls itself cdparanoia."""
    return find_tool("cd-paranoia", "cdparanoia")


def flac_path() -> str | None:
    return find_tool("flac")


def missing_tools() -> list[str]:
    """Which of the two are unavailable, for a preflight message that names
    them rather than failing halfway through a rip."""
    missing = []
    if cdparanoia_path() is None:
        missing.append("cd-paranoia")
    if flac_path() is None:
        missing.append("flac")
    return missing


# --- drives -----------------------------------------------------------


@dataclass
class CdDrive:
    device: str  # "D:" on Windows, "/dev/sr0" on Linux
    label: str  # the disc's volume label, empty when unknown/absent
    has_media: bool

    def display(self) -> str:
        if self.label:
            return f"{self.device} ({self.label})"
        return self.device


_DRIVE_CDROM = 5


def list_drives() -> list[CdDrive]:
    """Every optical drive, whether or not a disc is in it.

    Listing empty drives matters: the user picks the drive and *then* puts
    the disc in, so a list that only showed loaded drives would be empty
    exactly when it is first looked at."""
    if sys.platform == "win32":
        return _list_drives_windows()
    return _list_drives_posix()


def _list_drives_windows() -> list[CdDrive]:
    kernel32 = ctypes.windll.kernel32
    # Without this, querying an empty drive can raise the shell's own
    # "There is no disk in the drive" modal, which we would have no way to
    # dismiss and the user no way to understand.
    old_mode = kernel32.SetErrorMode(0x0001 | 0x0002)  # SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX
    try:
        drives = []
        mask = kernel32.GetLogicalDrives()
        for index in range(26):
            if not mask & (1 << index):
                continue
            letter = chr(ord("A") + index)
            root = f"{letter}:\\"
            if kernel32.GetDriveTypeW(root) != _DRIVE_CDROM:
                continue
            label = ctypes.create_unicode_buffer(261)
            ok = kernel32.GetVolumeInformationW(root, label, 261, None, None, None, None, 0)
            # An audio CD has no filesystem, but Windows' CDFS driver still
            # answers this for one, reporting the label "Audio CD" --
            # observed on a real disc, not assumed. So this is a usable
            # "something is in the drive" signal, though never the
            # authoritative one: whether the disc is *readable* is answered
            # by reading its TOC, and nothing here should pre-empt that.
            drives.append(CdDrive(device=f"{letter}:", label=label.value if ok else "", has_media=bool(ok)))
        return drives
    finally:
        kernel32.SetErrorMode(old_mode)


def _list_drives_posix() -> list[CdDrive]:
    found = []
    for pattern in ("sr*", "scd*"):
        found.extend(sorted(Path("/dev").glob(pattern)))
    cdrom = Path("/dev/cdrom")
    if cdrom.exists() and cdrom not in found:
        found.insert(0, cdrom)
    return [CdDrive(device=str(p), label="", has_media=True) for p in found]


def device_candidates(device: str) -> list[str]:
    """Spellings of a drive to try, in order.

    libcdio's Windows driver is documented as taking a plain "D:", but the
    same drive is also reachable as the raw device path, and which one a
    particular build/driver combination accepts is not something to find
    out for the first time in front of a user with a disc in their hand."""
    device = device.rstrip("\\")
    if sys.platform != "win32":
        return [device]
    letter = device.rstrip(":")[:1]
    if not letter:
        return [device]
    return [f"{letter}:", rf"\\.\{letter}:"]


# --- the table of contents --------------------------------------------


@dataclass
class TocTrack:
    number: int
    first_lba: int
    sectors: int

    @property
    def seconds(self) -> float:
        return self.sectors / SECTORS_PER_SECOND


@dataclass
class DiscToc:
    tracks: list[TocTrack] = field(default_factory=list)
    leadout_lba: int = 0

    @property
    def total_seconds(self) -> float:
        return sum(track.sectors for track in self.tracks) / SECTORS_PER_SECOND

    def frame_offsets(self) -> list[int]:
        """Track start offsets as MSF frames, which is what every disc
        identifier is specified in terms of -- LBA plus the 150-sector
        lead-in."""
        return [track.first_lba + PREGAP_SECTORS for track in self.tracks]

    def leadout_offset(self) -> int:
        return self.leadout_lba + PREGAP_SECTORS

    def musicbrainz_disc_id(self) -> str:
        """The disc's MusicBrainz identifier.

        SHA-1 over a fixed-width text rendering of the TOC -- first and last
        track numbers as two uppercase hex digits, then exactly 100 eight
        digit hex slots holding the lead-out offset followed by every track
        offset, zero-filled to the end -- base64'd with the three characters
        that are unsafe in a URL swapped out.

        The 100 fixed slots are not padding for its own sake: they are what
        makes two pressings of the same disc hash identically regardless of
        how many tracks they have, so this must not be "simplified" down to
        just the tracks that exist. Verified against the live service: the
        TOC of Nirvana's Nevermind hashes to I5l9cCSFccLKFEKS.7wqSZAorPU-,
        which musicbrainz.org resolves to that release."""
        if not self.tracks:
            raise CdRipError("cannot identify a disc with no tracks")
        slots = [0] * 99
        for index, offset in enumerate(self.frame_offsets()[:99]):
            slots[index] = offset
        parts = [
            f"{self.tracks[0].number:02X}",
            f"{self.tracks[-1].number:02X}",
            f"{self.leadout_offset():08X}",
        ]
        parts += [f"{offset:08X}" for offset in slots]
        digest = hashlib.sha1("".join(parts).encode("ascii")).digest()
        return base64.b64encode(digest).decode("ascii").translate(str.maketrans("+/=", "._-"))

    def musicbrainz_toc_param(self) -> str:
        """The same TOC in the "first+last+leadout+offsets" form MusicBrainz
        accepts for a *fuzzy* lookup.

        Worth having alongside the exact disc id because the two answer
        different questions: the disc id matches this pressing and nothing
        else, while the TOC search also returns releases whose own disc ids
        nobody has ever submitted, which is most of them."""
        if not self.tracks:
            raise CdRipError("cannot identify a disc with no tracks")
        values = [self.tracks[0].number, self.tracks[-1].number, self.leadout_offset()]
        values += self.frame_offsets()
        return "+".join(str(value) for value in values)


# cdparanoia -Q prints one row per audio track:
#     1.    18855 [04:11.30]        0 [00:00.00]    no   no  2
# i.e. number, length in sectors, length as MSF, start LBA, start as MSF.
_TOC_ROW = re.compile(r"^\s*(\d+)\.\s+(\d+)\s*\[[\d:.]+\]\s+(\d+)\s*\[", re.MULTILINE)


def parse_toc(text: str) -> DiscToc:
    """The track table out of `cd-paranoia -Q` output.

    Deliberately tolerant about everything around the rows -- the banner,
    the drive autosense chatter and the TOTAL line all vary between builds
    and drives, and none of them carry information the rows do not."""
    tracks = [
        TocTrack(number=int(number), first_lba=int(start), sectors=int(length))
        for number, length, start in _TOC_ROW.findall(text)
    ]
    if not tracks:
        raise CdRipError("no audio tracks in the drive's table of contents")
    last = tracks[-1]
    return DiscToc(tracks=tracks, leadout_lba=last.first_lba + last.sectors)


def read_toc(device: str, run=subprocess.run) -> DiscToc:
    """Asks the drive what is on the disc.

    Every spelling of the device is tried before giving up (see
    `device_candidates`), and the *last* failure's own output is what gets
    reported -- cdparanoia's message ("Unable find or access a CD-ROM drive
    with an audio CD in it") says more about what went wrong than anything
    that could be written here.

    Two things about cdparanoia's behaviour that this depends on, both
    confirmed by running the bundled binary rather than read anywhere:
    it writes all of this to **stderr**, success included (stdout is
    reserved for ripped audio), and `-Q` exits **0 even when it found no
    drive at all**. So neither the exit code nor stdout can be used to
    decide whether it worked -- having parsed a track table out of the
    output is the only evidence there is. A rip proper does exit non-zero
    on failure; that is checked in rip_track."""
    tool = cdparanoia_path()
    if tool is None:
        raise CdRipError("cd-paranoia was not found")

    last_output = ""
    for candidate in device_candidates(device):
        try:
            completed = run(
                [tool, "-d", candidate, "-Q"],
                capture_output=True,
                text=True,
                errors="replace",
                timeout=TOC_TIMEOUT_S,
                creationflags=NO_WINDOW,
            )
        except subprocess.TimeoutExpired as exc:
            raise CdRipError(f"the drive did not answer within {TOC_TIMEOUT_S:.0f}s") from exc
        except OSError as exc:
            raise CdRipError(f"could not run cd-paranoia: {exc}") from exc
        last_output = f"{completed.stdout or ''}\n{completed.stderr or ''}"
        try:
            return parse_toc(last_output)
        except CdRipError:
            continue
    raise CdRipError(_first_useful_line(last_output) or "no audio CD in the drive")


def _first_useful_line(text: str) -> str:
    """cdparanoia's real complaint, out of its banner. The copyright block
    is four lines long and would otherwise be all the user ever saw."""
    skip = ("cdparanoia", "(C)", "Report bugs", "Copyright")
    for line in reversed([line.strip() for line in text.splitlines() if line.strip()]):
        if not line.startswith(skip):
            return line
    return ""


# --- what to rip, where -----------------------------------------------


@dataclass
class RipTask:
    number: int
    title: str
    sectors: int
    wav_path: Path
    flac_path: Path
    tags: dict[str, str] = field(default_factory=dict)

    @property
    def expected_wav_bytes(self) -> int:
        """What the TOC says this track must weigh, as a plain WAV: 44 bytes
        of header plus one 2352-byte sector per 1/75th of a second."""
        return 44 + self.sectors * SECTOR_BYTES


@dataclass
class RipPlan:
    folder: Path
    tasks: list[RipTask] = field(default_factory=list)

    @property
    def flac_paths(self) -> list[Path]:
        return [task.flac_path for task in self.tasks]


def sanitize_filename(text: str) -> str:
    """Same job as gallery._sanitize_filename, kept separate because this
    one also has to survive a trailing dot or space -- Windows silently
    drops those from a directory name, which would make the folder we
    create and the folder we then write into two different places."""
    cleaned = _INVALID_FILENAME_CHARS.sub("_", text).strip(" .")
    return cleaned or "Unknown"


def ensure_folder(path: Path) -> Path:
    """Creates a folder and every parent it needs, or says why it could not.

    The rip folder is a setting, and a setting is a path somebody typed --
    it routinely names a directory that does not exist yet, which is not an
    error, it is the normal state before the first rip. Every caller that is
    about to *use* it therefore creates it, rather than any of them assuming
    somebody else already did. Same "created on demand, at the moment it is
    needed" rule as user_paths.projects_dir().

    What is left is the case a folder genuinely cannot be made -- a drive
    that is not there, a path with no write permission. That is worth a
    sentence naming the folder, not an unhandled OSError."""
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise CdRipError(f"could not create the folder {path}: {exc}") from exc
    return path


def rip_folder_name(artist: str, album: str) -> str:
    artist = sanitize_filename(artist) if artist.strip() else "Unknown Artist"
    album = sanitize_filename(album) if album.strip() else "Unknown Album"
    return f"{artist} - {album}"


def build_rip_plan(
    toc: DiscToc,
    folder: Path,
    titles: list[str] | None = None,
    *,
    artist: str = "",
    album: str = "",
    year: int | None = None,
    track_artists: list[str] | None = None,
) -> RipPlan:
    """What will be written where, and under what tags -- computed without
    touching the disc or the filesystem, so the dialog can show it and the
    tests can check it.

    Filenames are zero-padded with the track number in front for a reason
    that is not cosmetic: the files are handed to foobar2000 as a batch, and
    a padded numeric prefix means CD order survives even if anything along
    the way decides to sort them.

    `track_artists` is what makes a compilation survive the trip. Tagging
    every track with the release's own artist would write "Various Artists"
    twelve times and throw away the only information that says who actually
    plays on each one -- which is what the J-card and the generated cover
    are then built from."""
    tasks = []
    for index, track in enumerate(toc.tracks):
        title = ""
        if titles is not None and index < len(titles):
            title = titles[index].strip()
        if not title:
            title = f"Track {track.number:02d}"
        performer = ""
        if track_artists is not None and index < len(track_artists):
            performer = track_artists[index].strip()
        stem = f"{track.number:02d} - {sanitize_filename(title)}"
        tags = {
            "TITLE": title,
            "TRACKNUMBER": str(track.number),
            "TRACKTOTAL": str(len(toc.tracks)),
        }
        if album.strip():
            tags["ALBUM"] = album.strip()
        # Both, deliberately, and not necessarily the same: foobar's
        # %album artist% is what the record flow reads for the disc title
        # (see foobar.album_artist), while %artist% is per-track and is what
        # tells a compilation apart from an album.
        if artist.strip():
            tags["ALBUMARTIST"] = artist.strip()
        if performer or artist.strip():
            tags["ARTIST"] = performer or artist.strip()
        if year is not None:
            tags["DATE"] = str(year)
        tasks.append(
            RipTask(
                number=track.number,
                title=title,
                sectors=track.sectors,
                wav_path=folder / f"{stem}.wav",
                flac_path=folder / f"{stem}.flac",
                tags=tags,
            )
        )
    return RipPlan(folder=folder, tasks=tasks)


# --- doing it ---------------------------------------------------------


def rip_command(tool: str, device: str, number: int, wav_path: Path) -> list[str]:
    """-e puts progress on stderr in the machine-readable form cdparanoia
    documents "for wrapper scripts", which is exactly what this is."""
    return [tool, "-d", device, "-e", "-w", str(number), str(wav_path)]


def encode_command(tool: str, task: RipTask) -> list[str]:
    """-f overwrites a leftover from an interrupted run rather than
    stopping to ask; -s keeps the encoder from competing with our own
    progress reporting."""
    command = [tool, "-f", "-s"]
    command += [f"--tag={name}={value}" for name, value in task.tags.items()]
    command += ["-o", str(task.flac_path), str(task.wav_path)]
    return command


def rip_track(
    device: str,
    task: RipTask,
    *,
    on_progress=None,
    should_cancel=None,
    popen=subprocess.Popen,
    sleep=time.sleep,
) -> None:
    """Extracts one track to WAV, reporting 0.0-1.0 progress as it goes.

    Progress is how large the output file has grown against what the TOC
    says it will be, rather than anything parsed out of cdparanoia's own
    progress output. Two reasons: its `@ n` position field means different
    things in different builds, while a file's size on disk cannot be
    misread -- and the same measurement gives the check at the end for
    free, since a track that came up short is a failed rip however cleanly
    the process exited.

    **stderr goes to a file, not a pipe, and the loop polls the clock
    rather than reading lines.** Reading the pipe line by line was the
    obvious shape and has two failure modes this avoids: it assumes
    cdparanoia terminates its progress output with newlines (it redraws a
    bar, and only `-e` mode promises lines at all), and it makes cancelling
    depend on a line arriving -- so a quiet stretch would leave Stop doing
    nothing until the track finished. Not reading the pipe at all is not an
    option either: a full pipe buffer would block the child. A file has no
    buffer to fill.

    Cancelling therefore takes effect within a poll interval, unlike
    cancelling an MDRem upload (which has to wait out the current title or
    the deck is left in name-edit mode). Nothing is left in a state by
    stopping a read halfway, so the partial WAV is simply deleted."""
    tool = cdparanoia_path()
    if tool is None:
        raise CdRipError("cd-paranoia was not found")
    task.wav_path.parent.mkdir(parents=True, exist_ok=True)
    log_path = task.wav_path.with_suffix(".log")

    cancelled = False
    tail = ""
    with open(log_path, "w+", encoding="utf-8", errors="replace") as log:
        process = popen(
            rip_command(tool, device, task.number, task.wav_path),
            stdout=subprocess.DEVNULL,
            stderr=log,
            creationflags=NO_WINDOW,
        )
        while process.poll() is None:
            if should_cancel is not None and should_cancel():
                process.kill()
                process.wait()
                cancelled = True
                break
            if on_progress is not None:
                on_progress(_wav_fraction(task))
            sleep(RIP_POLL_S)
        if not cancelled:
            log.seek(0)
            tail = log.read()[-_LOG_TAIL_CHARS:]

    # Both deletions have to wait until the log file above is closed --
    # Windows refuses to unlink a file that is still open.
    if cancelled:
        task.wav_path.unlink(missing_ok=True)
        log_path.unlink(missing_ok=True)
        raise CdRipCancelled()

    if process.returncode != 0:
        # The log is deliberately left behind on failure: it holds
        # cdparanoia's per-sector account of what went wrong.
        raise CdRipError(_first_useful_line(tail) or f"cd-paranoia failed on track {task.number}")

    actual = task.wav_path.stat().st_size if task.wav_path.exists() else 0
    if actual < task.expected_wav_bytes:
        raise CdRipError(
            f"track {task.number} came up short: {actual} bytes of an expected {task.expected_wav_bytes}"
        )
    log_path.unlink(missing_ok=True)
    if on_progress is not None:
        on_progress(1.0)


def _wav_fraction(task: RipTask) -> float:
    try:
        size = task.wav_path.stat().st_size
    except OSError:
        return 0.0
    return min(1.0, size / max(1, task.expected_wav_bytes))


def encode_track(task: RipTask, *, run=subprocess.run, keep_wav: bool = False) -> None:
    """WAV to FLAC, then the WAV goes -- it is twice the size of what
    replaces it and has served its purpose."""
    tool = flac_path()
    if tool is None:
        raise CdRipError("flac was not found")
    try:
        completed = run(
            encode_command(tool, task),
            capture_output=True,
            text=True,
            errors="replace",
            timeout=ENCODE_TIMEOUT_S,
            creationflags=NO_WINDOW,
        )
    except subprocess.TimeoutExpired as exc:
        raise CdRipError(f"encoding track {task.number} timed out") from exc
    except OSError as exc:
        raise CdRipError(f"could not run flac: {exc}") from exc
    if completed.returncode != 0:
        raise CdRipError(_first_useful_line(completed.stderr or "") or f"flac failed on track {task.number}")
    if not keep_wav:
        task.wav_path.unlink(missing_ok=True)


# --- housekeeping -----------------------------------------------------

_RIP_SUFFIXES = {".flac", ".wav", ".log"}


def clean_stale_rip_folders(root: Path, keep: Path | None = None) -> list[Path]:
    """Removes previous rips, leaving the one about to be used alone.

    Old rips are cleared at the *start* of a new one rather than at the end
    of the last, because the files stay in foobar2000's playlist for as long
    as the user might want to play them again -- deleting them the moment a
    recording finished would pull them out from under it.

    Only folders holding nothing but rip output are touched. The rip folder
    is configurable, so it can be pointed at somewhere that also holds
    something else, and a recursive delete has no business guessing."""
    removed = []
    if not root.is_dir():
        return removed
    for child in sorted(root.iterdir()):
        if not child.is_dir() or (keep is not None and child == keep):
            continue
        if any(item.is_dir() or item.suffix.lower() not in _RIP_SUFFIXES for item in child.iterdir()):
            continue
        shutil.rmtree(child, ignore_errors=True)
        removed.append(child)
    return removed
