"""The asset gallery: ready-made images the user can insert as an image
layer without having to browse for a file. Two sources feed the same
gallery:

- `gallery_dir()` -- the bundled read-only folder (currently just the
  xD-Tools logo), at `assets/img` alongside the source checkout --
  deliberately NOT embedded/encoded into Python source -- so adding a new
  bundled image later is just dropping a file in that folder. Locating it
  at runtime differs between dev mode (running from the source checkout)
  and a PyInstaller-frozen build (see scripts/build_windows.ps1 /
  build_linux.sh, which --add-data the whole directory into the bundle).
- `downloaded_covers_dir()` -- a per-user, writable cache (unlike the
  bundled folder, which is read-only, especially in a frozen build) where
  album covers fetched via the Metadata dialog's "Lookup Track List..."
  are saved, so a fetched cover shows up here immediately without any
  extra "add to gallery" step.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from PySide6.QtCore import QStandardPaths

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp"}


def gallery_dir() -> Path:
    """Where the bundled gallery images live: next to a frozen build's
    bundled data (sys._MEIPASS), or assets/img at the repo root in dev
    mode."""
    frozen_base = getattr(sys, "_MEIPASS", None)
    if frozen_base is not None:
        base = Path(frozen_base)
    else:
        # this file: src/mdtools/gallery.py -> repo root is two levels above src/
        base = Path(__file__).resolve().parents[2]
    return base / "assets" / "img"


def downloaded_covers_dir() -> Path:
    """Where album covers fetched via metadata lookup are cached -- the
    same per-user AppConfigLocation directory templates.json lives in
    (see templates/registry.py), under a "covers" subfolder."""
    config_dir = Path(QStandardPaths.writableLocation(QStandardPaths.AppConfigLocation))
    covers_dir = config_dir / "covers"
    covers_dir.mkdir(parents=True, exist_ok=True)
    return covers_dir


_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*]')


def _sanitize_filename(text: str) -> str:
    return _INVALID_FILENAME_CHARS.sub("_", text).strip() or "cover"


def save_downloaded_cover(artist: str, album: str, data: bytes) -> Path | None:
    """Caches a fetched cover where list_gallery_images() will find it, so
    Tools > Insert Asset... can pick it up with no extra step.

    The filename is deterministic, so re-fetching the same album overwrites
    rather than accumulating near-duplicates. Returns None if it could not
    be written -- a cached copy is a convenience, never worth failing a
    lookup over."""
    path = downloaded_covers_dir() / f"{_sanitize_filename(artist)} - {_sanitize_filename(album)}.jpg"
    try:
        path.write_bytes(data)
    except OSError:
        return None
    return path


def list_gallery_images() -> list[Path]:
    """All gallery images from both sources above, sorted by filename. A
    missing/empty bundled folder (e.g. a dev checkout that deleted
    assets/, or a build that forgot to bundle it) isn't an error -- an
    empty gallery is a legitimate, handle-able state for the picker
    dialog."""
    images = []
    for directory in (gallery_dir(), downloaded_covers_dir()):
        if directory.is_dir():
            images.extend(p for p in directory.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS)
    return sorted(images, key=lambda p: p.name.lower())
