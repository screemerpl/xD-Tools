"""Where file dialogs should start.

Every browse/save dialog in this app used to pass an empty starting
directory, which leaves Qt to fall back on the process's working
directory -- wherever the app happened to be launched from, and for a
frozen build that is the install folder. Projects landed next to the
executable and exports scattered wherever the last dialog had wandered to.

The rule here is the one the operating system already sets: documents go in
Documents, pictures come from Pictures. Only the project folder gets a name
of its own, because a project is several files' worth of one thing and
"MiniDiscProjects" is a folder a user can recognise a year later.

Deliberately derived rather than configurable. The CD rip folder is a
setting because it holds hundreds of megabytes of disposable audio and
somebody may need that off their system drive; these are just sensible
starting points for a file picker, and a preference for each one would be
more machinery than the problem deserves.

QStandardPaths, not a hand-built "%USERPROFILE%/Documents": the real folder
is localised (Dokumenty, ドキュメント) and can be redirected to OneDrive or
another drive entirely, and only the OS knows where it actually is.

No Qt widgets here -- app_window and the panels import this, never the
other way round, matching app_settings.py.
"""

from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import QStandardPaths

# Not translated, on purpose: a folder name is part of the filesystem, and
# switching the interface language should not strand a user's projects in a
# directory under a name they no longer recognise.
PROJECTS_FOLDER_NAME = "MiniDiscProjects"


def _standard(location: QStandardPaths.StandardLocation, fallback: str) -> Path:
    """QStandardPaths returns "" when a location is not configured at all,
    which would put a dialog back at the working directory -- the very thing
    this module exists to stop."""
    found = QStandardPaths.writableLocation(location)
    return Path(found) if found else Path.home() / fallback


def documents_dir() -> Path:
    return _standard(QStandardPaths.StandardLocation.DocumentsLocation, "Documents")


def pictures_dir() -> Path:
    return _standard(QStandardPaths.StandardLocation.PicturesLocation, "Pictures")


def projects_dir() -> Path:
    """Documents/MiniDiscProjects, created if it is not there yet.

    Created on demand rather than at startup: a folder that appears in
    somebody's Documents before they have saved anything is clutter, and
    this is called exactly when a dialog is about to open in it. A dialog
    pointed at a directory that does not exist falls back to somewhere
    arbitrary, which is why it is created here rather than left to the
    first save."""
    folder = documents_dir() / PROJECTS_FOLDER_NAME
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError:
        # A read-only or redirected Documents is not worth failing a file
        # dialog over -- Documents itself is still a better answer than the
        # working directory.
        return documents_dir()
    return folder


_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

PROJECT_SUFFIX = ".mdproj"


def sanitize_filename(text: str) -> str:
    """Its own copy rather than cdrip's, which is identical: cdrip.py is
    documented as importing no Qt at all, and this module imports QtCore for
    QStandardPaths. Trading a nine-line duplicate for that property is the
    cheaper side of the deal."""
    cleaned = _INVALID_FILENAME_CHARS.sub("_", text).strip(" .")
    return cleaned


def project_start_path(current_path: str | None, suggested_name: str = "") -> str:
    """Where a project open/save dialog should start.

    An already-saved project reopens where it lives -- moving a project's
    folder should not keep sending its owner back to the default one.

    `suggested_name` fills in the filename for a project being saved for the
    first time. Callers pass `mdrem.disc_title(metadata)`, so the file is
    proposed under the same "Artist - Album (Year)" the deck itself gets
    told -- one function, so the two can never drift into disagreeing about
    what this disc is called.

    Note it is *not* passed through mdrem.transliterate(). That strips a
    title down to ASCII because the deck can display nothing else; a
    filesystem has no such limit, and mangling "Zażółć" into "Zazolc" on
    disk to match a hardware restriction would be carrying the deck's
    problem somewhere it does not apply."""
    if current_path:
        return current_path
    folder = projects_dir()
    name = sanitize_filename(suggested_name)
    return str(folder / f"{name}{PROJECT_SUFFIX}") if name else str(folder)


def export_start_path(current_path: str | None, filename: str = "") -> str:
    """Where an export dialog should start: beside the project it came from
    if that project has been saved, otherwise the projects folder.

    Next to the project rather than in a downloads or desktop folder,
    because an export belongs to one design -- the SVG that cuts it and the
    PNG that prints it are the same job as the .mdproj, and keeping them
    together is what makes the set findable when it is time to cut."""
    base = Path(current_path).parent if current_path else projects_dir()
    return str(base / filename) if filename else str(base)


def image_start_path() -> str:
    return str(pictures_dir())
