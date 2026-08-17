"""Recording > "Record Folder to MiniDisc..." -- an album that is already
on disk as files.

The third way into the same recording flow, and structurally the simplest.
Where CdRipDialog has to *make* the audio first, this one only has to point
foobar2000 at files that already exist:

  1. pick a folder; list the audio files in it, in filename order
  2. empty foobar's playlist and put them in it
  3. read the playlist back -- that is where every title, artist and length
     comes from, because foobar has just read the tags for us
  4. fill in what the tags did not say (year, cover art) from iTunes
  5. hand off to RecordDialog, unchanged and unaware where the files came
     from

Step 3 is worth being precise about: nothing here parses a tag. There is no
tag library in this project, and foobar is a better one than anything that
could be bolted on for this. What a file has no tag for falls back to its
filename (foobar.PlaylistItem.display_title).

Step 4 is the one place this differs from the CD flow, and the difference
is in what is missing. A CD is identified from its TOC, which is exact; a
folder is identified by what somebody typed into its tags years ago, so the
lookup here is enrichment only -- year and cover art -- and never replaces a
title. What is about to be played is what will be on the disc; a search
result is a guess about it.

The load runs on a worker thread. foobar accepts a command line in about a
second and then reads the files asynchronously, so the wait is normally
short -- but both halves have a 30 second timeout, and a minute of frozen
window is not something to leave to chance. Same shape as CdRipDialog's
_RipWorker, minus everything to do with a disc.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mdtools import app_settings, audio_folder, foobar, mixtape_cover, user_paths
from mdtools.panels.cover_preview import CoverPreview, fetch_into
from mdtools.project import ProjectMetadata

# The same 80 minutes RecordDialog and CdRipDialog warn about, checked here
# too because here it is still free to act on: a folder can be trimmed, or
# the deck set to LP2, before anything has been recorded.
DISC_SP_SECONDS = 80 * 60

# A folder holding this many tracks is not an album. Not refused -- the list
# is right there to look at, and somebody may genuinely be recording a
# hundred-track collection onto an LP4 disc -- but worth saying out loud,
# since picking a whole library's root folder produces exactly this.
UNLIKELY_TRACK_COUNT = 60


def _mmss(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


class _LoadWorker(QThread):
    """Replaces foobar's playlist with these files and reads it back."""

    failed = Signal(str)
    loaded = Signal(list)  # list[foobar.PlaylistItem]

    def __init__(self, client: foobar.FoobarClient, exe: str, paths: list[Path], parent=None):
        super().__init__(parent)
        self._client = client
        self._exe = exe
        self._paths = paths

    def run(self) -> None:
        try:
            playlist = foobar.replace_current_playlist(self._client, self._exe, self._paths)
            items = self._client.playlist_items(playlist.id)
        except foobar.FoobarError as exc:
            self.failed.emit(str(exc))
            return
        self.loaded.emit(items)


class FolderRecordDialog(QDialog):
    def __init__(self, base_url: str = foobar.DEFAULT_BASE_URL, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Record Folder to MiniDisc"))
        self.resize(600, 560)
        self._client = foobar.FoobarClient(base_url)
        self._paths: list[Path] = []
        self._items: list[foobar.PlaylistItem] = []
        self._worker: _LoadWorker | None = None
        self._folder: Path | None = None
        # What the folder name suggested, so a field still holding it can be
        # told apart from one the user typed into -- see _resolve().
        self._guessed: tuple[str, str, int | None] = ("", "", None)
        # Read by MainWindow after exec() and handed to RecordDialog. Unlike
        # the CD flow -- which writes its titles into the files it created,
        # so the playlist alone carries them -- these are somebody else's
        # files and nothing here rewrites them, so an edit made in this
        # dialog reaches the disc only by being passed forward.
        self.result_metadata: ProjectMetadata | None = None

        layout = QVBoxLayout(self)
        layout.addWidget(self._build_folder_row())

        form = QFormLayout()
        self.artist_edit = QLineEdit()
        self.album_edit = QLineEdit()
        self.year_spin = QSpinBox()
        self.year_spin.setRange(0, 2999)
        self.year_spin.setSpecialValueText(" ")
        form.addRow(self.tr("Artist"), self.artist_edit)
        form.addRow(self.tr("Album"), self.album_edit)
        form.addRow(self.tr("Year"), self.year_spin)

        self.cover_label = CoverPreview()

        header = QHBoxLayout()
        header.addLayout(form, 1)
        header.addWidget(self.cover_label)
        layout.addLayout(header)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([self.tr("#"), self.tr("Title"), self.tr("Artist"), self.tr("Length")])
        self.tree.setRootIsDecorated(False)
        layout.addWidget(self.tree)

        hint = QLabel(
            self.tr(
                "The tracks are recorded in the order shown, which comes from the filenames. Titles come "
                "from the files' own tags; a file with no title tag is recorded under its filename."
            )
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.warning_label = QLabel()
        self.warning_label.setWordWrap(True)
        self.warning_label.setVisible(False)
        layout.addWidget(self.warning_label)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)  # indeterminate: foobar reports no progress
        self.progress.setTextVisible(False)
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        self.status_label = QLabel(self.tr("Choose the folder holding the album."))
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.buttons = QDialogButtonBox()
        self.start_btn = QPushButton(self.tr("Load Folder"))
        self.start_btn.setEnabled(False)
        self.start_btn.clicked.connect(self._start)
        self.buttons.addButton(self.start_btn, QDialogButtonBox.ButtonRole.AcceptRole)
        self.close_btn = QPushButton(self.tr("Cancel"))
        self.close_btn.clicked.connect(self.reject)
        self.buttons.addButton(self.close_btn, QDialogButtonBox.ButtonRole.RejectRole)
        layout.addWidget(self.buttons)

    # --- choosing the folder ---------------------------------------------

    def _build_folder_row(self) -> QWidget:
        widget = QWidget()
        row = QHBoxLayout(widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(QLabel(self.tr("Folder")))
        self.folder_edit = QLineEdit()
        self.folder_edit.setReadOnly(True)
        row.addWidget(self.folder_edit, 1)
        self.browse_btn = QPushButton(self.tr("Browse..."))
        self.browse_btn.clicked.connect(self._browse)
        row.addWidget(self.browse_btn)
        return widget

    def _browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, self.tr("Choose Album Folder"), self._start_directory()
        )
        if folder:
            self.set_folder(Path(folder))

    def _start_directory(self) -> str:
        """Back where the last album came from, if there was one -- somebody
        recording a second album is overwhelmingly likely to be picking a
        sibling of the first."""
        remembered = app_settings.music_folder()
        if remembered and Path(remembered).is_dir():
            return remembered
        return user_paths.music_start_path()

    def set_folder(self, folder: Path) -> None:
        """Lists what is in the folder. Nothing is sent to foobar yet -- the
        user's current playlist is not replaced until they commit to it."""
        self._folder = folder
        self.folder_edit.setText(str(folder))
        self._paths = audio_folder.list_audio_files(folder)
        self._items = []
        self._show_filenames()
        app_settings.set_music_folder(str(folder.parent if folder.parent != folder else folder))

        if not self._paths:
            self.status_label.setText(
                self.tr("No audio files in that folder. Choose the one the tracks are actually in.")
            )
            self.start_btn.setEnabled(False)
            self.warning_label.setVisible(False)
            return

        artist, album, year = audio_folder.guess_from_folder_name(folder.name)
        self._guessed = (artist, album, year)
        self.artist_edit.setText(artist)
        self.album_edit.setText(album)
        self.year_spin.setValue(year or 0)
        self.start_btn.setEnabled(True)
        self.status_label.setText(
            self.tr(
                "{count} audio files. Loading them into foobar2000 will replace its current playlist."
            ).format(count=len(self._paths))
        )
        self._warn_about_count()

    def _show_filenames(self) -> None:
        """What is known before foobar has seen the files: their names, in
        the order they will be played. Replaced by the real tags as soon as
        the playlist has been loaded."""
        self.tree.clear()
        for index, path in enumerate(self._paths, start=1):
            QTreeWidgetItem(self.tree, [str(index), path.stem, "", ""])
        self.tree.resizeColumnToContents(0)

    def _warn_about_count(self) -> None:
        if len(self._paths) <= UNLIKELY_TRACK_COUNT:
            self.warning_label.setVisible(False)
            return
        self.warning_label.setText(
            self.tr(
                "That is {count} tracks -- far more than a MiniDisc holds. Check that this is one album's "
                "folder and not a whole library."
            ).format(count=len(self._paths))
        )
        self.warning_label.setVisible(True)

    # --- loading ----------------------------------------------------------

    def _start(self) -> None:
        """Loads the folder, or -- once it is loaded -- hands it over.

        Two presses rather than one, so what was found is on screen before
        the recording window opens: the album it turned out to be, the
        artwork it will be labelled with, and the titles foobar read out of
        the files. There is nothing to check in a dialog that closes the
        instant you press its only button."""
        if self._items:
            self.result_metadata = self._final_metadata()
            self.accept()
            return
        if not self._paths:
            return
        exe = self._resolve_foobar_exe()
        if exe is None:
            return
        if not self._foobar_reachable():
            return

        self._set_running(True)
        self.progress.setVisible(True)
        self.status_label.setText(self.tr("Loading the tracks into foobar2000..."))

        self._worker = _LoadWorker(self._client, exe, self._paths, self)
        self._worker.failed.connect(self._on_failed)
        self._worker.loaded.connect(self._on_loaded)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()

    def _resolve_foobar_exe(self) -> str | None:
        """The same check the CD flow makes, for the same reason: Beefweb
        cannot be given a file outside foobar's own configured music
        directories (it answers 403), so the files go in through foobar's
        command line and its location has to be known."""
        exe = app_settings.foobar_exe() or (foobar.find_foobar_exe() or "")
        if exe and Path(exe).is_file():
            if not app_settings.foobar_exe():
                app_settings.set_foobar_exe(exe)
            return exe
        QMessageBox.warning(
            self,
            self.tr("Record Folder to MiniDisc"),
            self.tr(
                "foobar2000 could not be found. The tracks are loaded into it through its own program file, "
                "so its location has to be set in Window > Settings..."
            ),
        )
        return None

    def _foobar_reachable(self) -> bool:
        try:
            self._client.current_playlist()
        except foobar.FoobarError as exc:
            QMessageBox.warning(
                self,
                self.tr("Record Folder to MiniDisc"),
                self.tr(
                    "Could not reach foobar2000: {error}\n\nIt must be running with the Beefweb Remote "
                    "Control component (foo_beefweb) enabled."
                ).format(error=exc),
            )
            return False
        return True

    def _set_running(self, running: bool) -> None:
        for widget in (
            self.start_btn,
            self.browse_btn,
            self.tree,
            self.artist_edit,
            self.album_edit,
            self.year_spin,
        ):
            widget.setEnabled(not running)

    def _on_failed(self, message: str) -> None:
        self.status_label.setText(self.tr("Could not load the tracks: {error}").format(error=message))

    def _on_loaded(self, items: list) -> None:
        self._items = items
        if not items:
            self.status_label.setText(
                self.tr("foobar2000 accepted no tracks from that folder -- none of them could be played.")
            )
            return
        self._show_playlist(items)
        self.result_metadata = self._capture_metadata(items)
        self.cover_label.set_cover(self.result_metadata.cover_art)
        self.start_btn.setText(self.tr("Record"))
        self.status_label.setText(
            self.tr("Loaded into foobar2000. Check the album below, then record.")
        )

    def _on_worker_finished(self) -> None:
        self._worker = None
        self._set_running(False)
        self.progress.setVisible(False)

    def _show_playlist(self, items: list) -> None:
        """What foobar made of the files -- the real titles and lengths,
        which is also what the disc will be titled from."""
        self.tree.clear()
        for index, item in enumerate(items, start=1):
            QTreeWidgetItem(
                self.tree,
                [str(index), item.display_title(), item.artist, _mmss(item.length_seconds)],
            )
        self.tree.resizeColumnToContents(0)
        self.tree.resizeColumnToContents(3)
        self._warn_about_length(foobar.total_seconds(items))

    def _warn_about_length(self, total: int) -> None:
        if total <= DISC_SP_SECONDS:
            return
        self.warning_label.setText(
            self.tr(
                "This runs {total}, longer than the {limit} an MD holds in SP mode. Set the deck to LP2 "
                "first, or the recording will be cut short."
            ).format(total=_mmss(total), limit=_mmss(DISC_SP_SECONDS))
        )
        self.warning_label.setVisible(True)

    # --- metadata ----------------------------------------------------------

    def _capture_metadata(self, items: list) -> ProjectMetadata:
        """The playlist as project metadata, reconciled with the album
        fields.

        Three sources, in strict order of authority: what the user typed
        beats what the files are tagged with, which beats what the folder
        name looked like. The middle rung is the one that is easy to get
        wrong -- the fields are *prefilled* from the folder name before
        foobar has read a single tag, so treating whatever is in them as
        the user's word would let a folder called "Album" quietly rename a
        properly tagged record."""
        metadata = foobar.metadata_from_playlist(items)
        guessed_artist, guessed_album, guessed_year = self._guessed
        metadata.artist = self._resolve(self.artist_edit.text().strip(), guessed_artist, metadata.artist)
        metadata.album = self._resolve(self.album_edit.text().strip(), guessed_album, metadata.album)
        metadata.year = self._resolve(self.year_spin.value() or None, guessed_year, metadata.year)
        self._show_resolved(metadata)

        # A compilation has no sleeve to look up: a search for "Various
        # Artists" returns some unrelated record's artwork, which would then
        # be printed on this disc as though it belonged to it. One is drawn
        # from the track list instead -- same branch as record_dialog's.
        if metadata.is_compilation():
            metadata.cover_art = mixtape_cover.render_cover(metadata)
            return metadata
        if metadata.artist or metadata.album:
            self._fetch_cover(metadata)
        return metadata

    @staticmethod
    def _resolve(typed, guessed, tagged):
        """One field: an edit, else the tag, else the folder-name guess.

        "An edit" means the field no longer holds what was put in it. There
        is no other signal available -- a QLineEdit cannot say who wrote
        what is in it -- and clearing a field is deliberately not treated as
        an edit meaning "nothing", since falling back to the tags is what
        somebody emptying a wrong guess actually wants."""
        if typed and typed != guessed:
            return typed
        return tagged or guessed

    def _show_resolved(self, metadata: ProjectMetadata) -> None:
        """Puts the answer back in the fields, so what the dialog shows is
        what it is about to hand over."""
        self.artist_edit.setText(metadata.artist)
        self.album_edit.setText(metadata.album)
        self.year_spin.setValue(metadata.year or 0)

    def _fetch_cover(self, metadata: ProjectMetadata) -> None:
        """Enrichment only: a year the tags did not have, and a cover.

        Never a title. What foobar is about to play is what will be on the
        disc, in that order; an iTunes result is whatever the search
        matched."""
        self.status_label.setText(self.tr("Looking up cover art..."))
        chosen = fetch_into(self.cover_label, metadata.artist, metadata.album, len(metadata.tracks))
        if chosen is not None and metadata.year is None:
            metadata.year = chosen.year
        metadata.cover_art = self.cover_label.data

    def _final_metadata(self) -> ProjectMetadata:
        """What the second press hands over: the captured album with
        whatever the user changed on screen since, artwork included -- the
        preview is clickable, and a cover chosen there has to survive."""
        captured = self.result_metadata or ProjectMetadata()
        return replace(
            captured,
            artist=self.artist_edit.text().strip() or captured.artist,
            album=self.album_edit.text().strip() or captured.album,
            year=self.year_spin.value() or captured.year,
            cover_art=self.cover_label.data,
        )

    # --- shutdown ----------------------------------------------------------

    def reject(self) -> None:
        """A load in flight is left to finish rather than cancelled.

        There is nothing to interrupt that would help: the work is inside
        foobar2000, the playlist has already been cleared, and stopping
        halfway would leave it holding part of an album with no indication
        why. It is seconds, not the minutes a rip takes."""
        if self._worker is not None and self._worker.isRunning():
            self.status_label.setText(self.tr("Waiting for foobar2000 to finish..."))
            return
        super().reject()

    def closeEvent(self, event) -> None:
        if self._worker is not None and self._worker.isRunning():
            event.ignore()
            return
        super().closeEvent(event)
