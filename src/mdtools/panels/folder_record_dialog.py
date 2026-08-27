"""Recording > "Record Folder to MiniDisc..." -- an album that is already
on disk as files.

The third way into the same recording flow, and structurally the simplest.
Where CdRipDialog has to *make* the audio first, this one only has to point
at files that already exist:

  1. pick a folder; list the audio files in it, in filename order
  2. read each file's own tags (title, artist, length) directly
  3. fill in what the tags did not say (year, cover art) from iTunes
  4. hand the files' paths, in this order, off to RecordDialog -- unchanged
     and unaware where they came from

Step 2 used to go through foobar2000's own playlist -- putting the files
into it and reading its columns back, because there was no tag library in
this project and foobar already read tags perfectly well. That reasoning
stopped applying once `tracks.py` existed (see its own module docstring):
`tracks.playlist_items_from_paths()` reads a file's tags directly with
`mutagen`, the same way `audio_folder.metadata_from_folder()` already does
for the "Import from Folder..." button. Reading a folder's worth of local
files this way is fast enough that it no longer needs a worker thread or
a progress bar -- there is no external process to wait on any more.

Step 3 is the one place this differs from the CD flow, and the difference
is in what is missing. A CD is identified from its TOC, which is exact; a
folder is identified by what somebody typed into its tags years ago, so the
lookup here is enrichment only -- year and cover art -- and never replaces a
title. What is in the files is what will be on the disc; a search result is
a guess about it.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mdtools import app_settings, audio_folder, embedded_cover, mixtape_cover, tracks, user_paths
from mdtools.panels.cover_preview import CoverPreview, fetch_into
from mdtools.panels.progress_format import mmss as _mmss
from mdtools.project import MEDIUM_MD, medium_name, ProjectMetadata

# The same 80 minutes RecordDialog and CdRipDialog warn about, checked here
# too because here it is still free to act on: a folder can be trimmed, or
# the deck set to LP2, before anything has been recorded.
DISC_SP_SECONDS = 80 * 60

# A folder holding this many tracks is not an album. Not refused -- the list
# is right there to look at, and somebody may genuinely be recording a
# hundred-track collection onto an LP4 disc -- but worth saying out loud,
# since picking a whole library's root folder produces exactly this.
UNLIKELY_TRACK_COUNT = 60


class FolderRecordDialog(QDialog):
    def __init__(self, parent=None, medium: str = MEDIUM_MD):
        """`medium` is wording only -- see CdRipDialog's own note."""
        super().__init__(parent)
        self._medium = medium
        self._target = medium_name(medium)
        self.setWindowTitle(self._window_title())
        self.resize(600, 560)
        self._paths: list[Path] = []
        self._items: list[tracks.PlaylistItem] = []
        self._folder: Path | None = None
        # What the folder name suggested, so a field still holding it can be
        # told apart from one the user typed into -- see _resolve().
        self._guessed: tuple[str, str, int | None] = ("", "", None)
        # Read by MainWindow after exec() and handed to RecordDialog. Unlike
        # the CD flow -- which writes its titles into the files it created,
        # so their tags alone carry them -- these are somebody else's files
        # and nothing here rewrites them, so an edit made in this dialog
        # reaches the disc only by being passed forward.
        self.result_metadata: ProjectMetadata | None = None
        self.result_paths: list[Path] = []

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

        self.status_label = QLabel(self.tr("Choose the folder holding the album."))
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.buttons = QDialogButtonBox()
        # One button, and it is the one that matters. Choosing a folder is
        # already the decision; making the user then press "Load Folder" was
        # asking them to confirm something they had just done.
        self.record_btn = QPushButton(self.tr("Record"))
        self.record_btn.setEnabled(False)
        self.record_btn.clicked.connect(self._on_record)
        self.buttons.addButton(self.record_btn, QDialogButtonBox.ButtonRole.AcceptRole)
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
        """Lists what is in the folder and reads their tags.

        Reading happens here rather than behind a second button: picking a
        folder in this dialog *is* the decision, and asking the user to then
        confirm it was asking them to press a button for something they had
        already done."""
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
            self.record_btn.setEnabled(False)
            self.warning_label.setVisible(False)
            return

        artist, album, year = audio_folder.guess_from_folder_name(folder.name)
        self._guessed = (artist, album, year)
        self.artist_edit.setText(artist)
        self.album_edit.setText(album)
        self.year_spin.setValue(year or 0)
        self._warn_about_count()
        self._load()

    def _show_filenames(self) -> None:
        """What is known before the tags have been read: the files' own
        names, in the order they will be played. Replaced by the real tags
        as soon as they have been read."""
        self.tree.clear()
        for index, path in enumerate(self._paths, start=1):
            QTreeWidgetItem(self.tree, [str(index), path.stem, "", ""])
        self.tree.resizeColumnToContents(0)

    def _window_title(self) -> str:
        return self.tr("Record Folder to {medium}").format(medium=self._target)

    def _warn_about_count(self) -> None:
        if len(self._paths) <= UNLIKELY_TRACK_COUNT:
            self.warning_label.setVisible(False)
            return
        self.warning_label.setText(
            self.tr(
                "That is {count} tracks -- far more than a {medium} holds. Check that this is one album's "
                "folder and not a whole library."
            ).format(count=len(self._paths), medium=self._target)
        )
        self.warning_label.setVisible(True)

    # --- reading the tags ---------------------------------------------------

    def _on_record(self) -> None:
        """Hands the loaded album over to the recording window."""
        if not self._items:
            return
        self.result_metadata = self._final_metadata()
        self.result_paths = list(self._paths)
        self.accept()

    def _load(self) -> None:
        """Reads every file's tags directly -- no external player involved,
        and fast enough (plain local file reads through mutagen) to run
        right here rather than on a worker thread."""
        if not self._paths:
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            items = tracks.playlist_items_from_paths(self._paths)
        finally:
            QApplication.restoreOverrideCursor()
        self._on_loaded(items)

    def _on_loaded(self, items: list) -> None:
        self._items = items
        self._show_playlist(items)
        self.result_metadata = self._capture_metadata(items)
        self.cover_label.set_cover(self.result_metadata.cover_art)
        self.record_btn.setEnabled(True)
        self.status_label.setText(self.tr("Check the album below, then record."))

    def _show_playlist(self, items: list) -> None:
        """The real titles and lengths, read from the files -- which is also
        what the disc will be titled from."""
        self.tree.clear()
        for index, item in enumerate(items, start=1):
            QTreeWidgetItem(
                self.tree,
                [str(index), item.display_title(), item.artist, _mmss(item.length_seconds)],
            )
        self.tree.resizeColumnToContents(0)
        self.tree.resizeColumnToContents(3)
        self._warn_about_length(tracks.total_seconds(items))

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
        """The album as project metadata, reconciled with the album fields.

        Three sources, in strict order of authority: what the user typed
        beats what the files are tagged with, which beats what the folder
        name looked like. The middle rung is the one that is easy to get
        wrong -- the fields are *prefilled* from the folder name before a
        single tag has been read, so treating whatever is in them as the
        user's word would let a folder called "Album" quietly rename a
        properly tagged record."""
        metadata = tracks.metadata_from_playlist(items)
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

        Never a title. What is in the files is what will be on the disc, in
        that order; an iTunes result is whatever the search matched."""
        self.status_label.setText(self.tr("Looking up cover art..."))
        chosen = fetch_into(self.cover_label, metadata.artist, metadata.album, len(metadata.tracks))
        if chosen is not None and metadata.year is None:
            metadata.year = chosen.year
        if not self.cover_label.data:
            # Last resort: the sleeve the files themselves carry. Certainly
            # the right one for this release, where a search result is only
            # a guess -- but usually a smaller, rougher image, which is why
            # it comes second rather than first. See embedded_cover.
            self.cover_label.set_cover(embedded_cover.cover_from_files(self._paths))
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
