"""Sorting a folder of albums downloaded through the Telegram bot chat
(panels/telegram_chat_dialog.py) into one subfolder per album.

Every file lands flat in the one configured download folder (see
telegram_chat_dialog.py's `_ChatWorker`) -- not a fresh, timestamped
subfolder per chat session; explicit user request, so downloads from
different sessions accumulate in the same place rather than scattering
across a new folder every time the dialog is reopened. A single chat
session can also download several albums in a row on its own. Either way,
"Record Downloaded Albums..." needs exactly one album's worth of tracks --
FolderRecordDialog/audio_folder.list_audio_files() already treat a folder
holding files directly in it as one album -- so a folder holding more than
one album's worth of files, from one session or several, needs splitting
up first.

**Two grouping signals, tried in order, decided with the user.** The
`ALBUM` tag read directly out of each file (embedded_cover.flac_tags(),
the same "read the file itself, no tag library" approach that module
already takes for cover art) is tried first -- reliable regardless of when
or how a file arrived, but only works for tagged FLACs. Anything left over
falls back to *arrival order*: files that arrived as one unbroken run of
file-messages, with no other kind of message in between, are treated as
one album -- covers non-FLAC files and untagged FLACs, at the cost of
being wrong if a bot interleaves a status message between two tracks of
the same album.

**Grouping keys strictly by ALBUM, never by artist+album -- reported
directly: a featured-artist credit on one track ("Skillet, Lacey Sturm")
split it into its own folder, apart from the rest of the same record
tagged plainly "Skillet".** An earlier version keyed each file's group by
its own `f"{artist} - {album}"`, so any per-track ARTIST variance --
exactly what a guest feature is -- produced two different keys for what is
still one album. The fix mirrors project.py's `ProjectMetadata.is_compilation()`/
`foobar.album_artist()`: the album's own identity comes from the ALBUM
tag alone, and the artist half of a folder's name is decided *after*
grouping, from every track's tag in that group, not from whichever track
happened to be read first. `read_album_tag()` also now prefers an
ALBUMARTIST tag over ARTIST when present, same "the album's own credited
performer, not whoever's on this one track" reasoning `foobar.album_artist()`
already uses -- but that alone isn't sufficient, since plenty of
real-world files simply have no ALBUMARTIST tag at all, only a per-track
ARTIST that varies on a collab -- so `_group_display_name()` still falls
back to a majority vote (`Counter.most_common()`) over whatever ARTIST
values a group's tracks actually carry, which is what makes a single
outlier credit lose to the rest of the album rather than fork it.

**`sort_folder()` is the standalone sibling of `sort_downloads()`, for
Source > "Sort Rip/Download Folder into Albums..." -- sorting
a folder that was never part of a live chat (an old session, or one picked
by hand).** There is no message arrival order to fall back on outside a
chat, so it groups by ALBUM tag only; anything untagged lands together in
one plain "Unsorted" folder instead of getting its own per-batch group.

**Sorting is incremental, not a one-shot pass over a fresh folder.** Since
downloads accumulate in one folder across every chat session (see
telegram_chat_dialog.py), the normal case after the first sort is "some
albums are already in subfolders, some newly-arrived tracks are still flat
in the root" -- so "only one album's worth of files is loose" is the
*common* state, not a reason to skip the move. `has_album_subfolders()` is
what tells those two situations apart; see `_create_folders_and_move()`.

No Qt in here, matching audio_folder.py/cdrip.py -- the panel imports
this, never the other way round.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from mdtools import audio_folder, cdrip, embedded_cover


def read_album_tag(path: Path) -> tuple[str, str]:
    """(artist, album), both "" for anything that is not a .flac or has no
    usable ALBUM tag. The extension check lives here, not in
    embedded_cover.flac_tags() -- that function reads a file's own magic
    bytes regardless of its name, same layering cover_from_file() already
    uses on top of flac_pictures().

    The artist half prefers an ALBUMARTIST tag over ARTIST when the file
    has one -- see the module docstring for why a per-track ARTIST alone
    isn't enough to build a group's folder name from."""
    if path.suffix.lower() != ".flac":
        return "", ""
    tags = embedded_cover.flac_tags(path)
    artist = tags.get("ALBUMARTIST", "").strip() or tags.get("ARTIST", "").strip()
    return artist, tags.get("ALBUM", "").strip()


def _group_display_name(album: str, artists: list[str]) -> str:
    """The folder name for one ALBUM-tag group -- the majority artist tag
    among that group's tracks (Counter.most_common(), ties broken by
    whichever value was seen first) wins, not whichever track happened to
    be read first. A collab-credited track is normally the *minority*
    value within its own album's group, so this is what keeps it from
    naming (or forking) the folder on its own."""
    if not artists:
        return album
    artist = Counter(artists).most_common(1)[0][0]
    return f"{artist} - {album}"


def batches_from_arrival_order(message_order: list[int], downloaded: dict[int, Path]) -> list[list[Path]]:
    """Splits `message_order` (every message id, in the order the dialog
    first saw it -- not touched by a later edit, see
    TelegramChatDialog._on_message_received) into runs of consecutive
    file-bearing messages. A message with no downloaded file (plain text,
    or a photo -- covers aren't part of this) ends whatever run is in
    progress; two files are "the same batch" only if nothing else arrived
    between them."""
    batches: list[list[Path]] = []
    current: list[Path] = []
    for message_id in message_order:
        path = downloaded.get(message_id)
        if path is not None:
            current.append(path)
        elif current:
            batches.append(current)
            current = []
    if current:
        batches.append(current)
    return batches


def has_album_subfolders(root: Path) -> bool:
    """Whether `root` already holds at least one sorted-into subfolder.

    This is what decides whether the "a single album needs no folder of its
    own" rule below still applies -- see _create_folders_and_move(). Also
    read by the chat dialog to decide whether there is anything worth
    recording, so it tolerates a folder that does not exist yet.

    The app's own scratch subfolders don't count (cdrip.RESERVED_SCRATCH_
    DIRNAMES: burning's work directory, and downloads' staging directory).
    Neither is an album, and either one being mistaken for one would flip
    the single-album rule for a folder that has never actually been
    sorted -- the same filter pick_album_folder() and the "is this folder
    empty?" checks already apply."""
    if not root.is_dir():
        return False
    return any(p.is_dir() and p.name not in cdrip.RESERVED_SCRATCH_DIRNAMES for p in root.iterdir())


def staging_dir(root: Path) -> Path:
    """Where a download is written while it is still arriving.

    A file is only worth looking at once it is complete: its tags cannot
    be read before then, and a half-written track sitting loose in the
    shared folder is something the recording picker would offer and a
    sort would file away as if it were finished. Created on demand, the
    same rule as every other folder here."""
    folder = root / cdrip.DOWNLOAD_STAGING_DIRNAME
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def album_folder_for(root: Path, path: Path) -> Path:
    """Which folder a finished download belongs in -- `root/Artist - Album`
    when the file says what album it is from, `root` itself when it does
    not.

    The same tags, the same majority-artist naming and the same
    sanitising a later sort would apply (read_album_tag/
    _group_display_name/cdrip.sanitize_filename), so a file placed on
    arrival and a file placed by "Sort Rip/Download Folder into
    Albums..." land in exactly the same folder rather than in two
    similarly-named ones.

    Only FLAC files carry an answer here today (read_album_tag reads FLAC
    tags alone) -- an MP3 or an Ogg goes to the root and waits for a sort,
    exactly as it did before."""
    artist, album = read_album_tag(path)
    if not album:
        return root
    return root / cdrip.sanitize_filename(_group_display_name(album, [artist] if artist else []))


def place_download(root: Path, path: Path) -> Path:
    """Moves a finished download out of staging into where it belongs,
    and says where that turned out to be.

    Never overwrites: a name already taken gains a " (2)" (or 3, or 4).
    Re-downloading a track therefore leaves two copies rather than
    replacing one, which is the right way round for this codebase --
    nothing here may destroy a file in the shared audio folder, and a
    duplicate is visible and removable by hand while a clobbered file is
    neither. In the ordinary retry path this never comes up anyway: a
    failed download's leftovers stay in staging, where the retry
    overwrites them, and only the finished file is ever placed.

    Returns `path` untouched if it has already gone (a retry that raced
    itself), rather than raising over work that is already done."""
    if not path.exists():
        return path
    destination = album_folder_for(root, path)
    destination.mkdir(parents=True, exist_ok=True)
    target = _free_name(destination / path.name)
    path.rename(target)
    return target


def _free_name(target: Path) -> Path:
    if not target.exists():
        return target
    for suffix in range(2, 1000):
        candidate = target.with_name(f"{target.stem} ({suffix}){target.suffix}")
        if not candidate.exists():
            return candidate
    return target.with_name(f"{target.stem} ({target.stat().st_mtime_ns}){target.suffix}")


def _create_folders_and_move(root: Path, groups: dict[str, list[Path]]) -> list[Path]:
    """The actual filesystem operation shared by sort_downloads() and
    sort_folder().

    **Moves nothing for a single group only when `root` holds no album
    subfolders yet.** One album sitting alone in the download folder has no
    reason to be nested under its own subfolder, and that is also what makes
    a repeat click a safe no-op. But once *anything* has been sorted, a
    single new group is the opposite case and the original unconditional
    `len(groups) <= 1` guard got it exactly backwards -- reported directly:
    two albums were sorted into folders, a third was downloaded, and sorting
    again reported "nothing to sort" because that third album was one group.
    Its files then stayed flat in the root while pick_album_folder() offered
    only the two existing subfolders, so the newest album was both unsorted
    *and* unrecordable -- invisible, with the UI claiming everything was
    fine.

    Idempotency does not depend on this guard anyway: both callers only ever
    look at files still sitting directly in `root`, so anything already moved
    into a subfolder is simply not seen a second time."""
    if len(groups) <= 1 and not has_album_subfolders(root):
        return []
    result: list[Path] = []
    for name, paths in groups.items():
        folder = root / name
        folder.mkdir(exist_ok=True)
        for path in paths:
            path.rename(folder / path.name)
        result.append(folder)
    return result


def loose_audio_files(root: Path) -> list[Path]:
    """Every *audio* file sitting directly in `root` -- i.e. a track not yet
    sorted into an album subfolder. `[]` for a folder that does not exist
    yet, which is the normal state before the first download rather than an
    error.

    **Deliberately the folder's own contents, never a caller-supplied list
    of "what this session downloaded".** `sort_downloads()` used to build
    this from `downloaded.values()` instead, which was correct only while
    each chat session had a folder to itself; once downloads started
    accumulating in one shared folder (see telegram_chat_dialog.py), files
    left loose by an *earlier* session became invisible to it -- so nothing
    was sorted and the recording picker then handed over the whole mixed
    root as if it were one album. Reading the directory is what makes both
    entry points agree about scope.

    **And equally deliberately audio only, filtered by the same
    `audio_folder.AUDIO_EXTENSIONS` the recording step itself uses.** Only a
    file that can actually end up on a disc is worth moving: a cover
    thumbnail a bot sent alongside the tracks, or anything else already
    living in what is a user-configurable folder, is never recorded (see
    `audio_folder.list_audio_files()`), so sorting has no business relocating
    it. Sweeping every file indiscriminately was caught by a test whose
    download folder also held an unrelated `.ini`, which promptly turned into
    a bogus second "album"."""
    if not root.is_dir():
        return []
    return sorted(
        p for p in root.iterdir() if p.is_file() and p.suffix.lower() in audio_folder.AUDIO_EXTENSIONS
    )


def _group_by_album_tag(flat_files: list[Path]) -> tuple[dict[str, list[Path]], set[Path]]:
    """The ALBUM-tag grouping both entry points share, as
    (folder name -> files, whichever files got grouped).

    Factored out rather than written twice: the two callers differing in
    what they looked at is exactly what produced the cross-session bug
    described in `loose_audio_files()`, so the parts that must not diverge now
    physically cannot."""
    by_album: dict[str, list[Path]] = {}
    artists_by_album: dict[str, list[str]] = {}
    grouped: set[Path] = set()

    for path in flat_files:
        artist, album = read_album_tag(path)
        if not album:
            continue
        by_album.setdefault(album, []).append(path)
        if artist:
            artists_by_album.setdefault(album, []).append(artist)
        grouped.add(path)

    groups = {
        cdrip.sanitize_filename(_group_display_name(album, artists_by_album.get(album, []))): paths
        for album, paths in by_album.items()
    }
    return groups, grouped


def sort_downloads(root: Path, downloaded: dict[int, Path], message_order: list[int]) -> list[Path]:
    """Groups every file directly in `root` into per-album subfolders,
    moving them there, and returns the resulting subfolder paths -- see
    the module docstring for the tag-then-arrival-batch grouping order (and
    for why grouping keys on ALBUM alone, never artist+album).

    `downloaded`/`message_order` are only the *arrival-order* signal for
    untagged files, never the list of files to consider -- see
    `loose_audio_files()`."""
    flat_files = loose_audio_files(root)
    if not flat_files:
        return []

    groups, grouped = _group_by_album_tag(flat_files)

    remaining_by_batch = [
        [path for path in batch if path not in grouped]
        for batch in batches_from_arrival_order(message_order, downloaded)
    ]
    batch_number = 0
    for batch in remaining_by_batch:
        if not batch:
            continue
        batch_number += 1
        groups.setdefault(f"Album {batch_number}", []).extend(batch)
        grouped.update(batch)

    # Untagged *and* with no arrival information -- e.g. an earlier session's
    # untagged leftovers, which this session knows nothing about. Same
    # "one Unsorted folder beats one folder per orphan file" rule
    # sort_folder() applies, rather than leaving them loose for the recording
    # picker to sweep up alongside a real album.
    leftover = [path for path in flat_files if path not in grouped]
    if leftover:
        groups.setdefault("Unsorted", []).extend(leftover)

    return _create_folders_and_move(root, groups)


def sort_folder(root: Path) -> list[Path]:
    """The standalone version -- every file directly in `root`, grouped by
    ALBUM tag alone (no chat, no arrival order to fall back on). Anything
    untagged is grouped together into one "Unsorted" folder rather than
    getting its own per-file group, so a folder of e.g. five untagged MP3s
    doesn't turn into five one-track "albums"."""
    flat_files = loose_audio_files(root)
    if not flat_files:
        return []

    groups, grouped = _group_by_album_tag(flat_files)

    untagged = [path for path in flat_files if path not in grouped]
    if untagged:
        groups.setdefault("Unsorted", []).extend(untagged)

    return _create_folders_and_move(root, groups)
