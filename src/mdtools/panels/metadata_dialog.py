from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QAbstractItemDelegate,
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from mdtools import app_settings, audio_folder, embedded_cover, user_paths
from mdtools.gallery import downloaded_covers_dir, save_downloaded_cover
from mdtools.metadata_lookup import (
    AlbumCandidate,
    MetadataLookupError,
    fetch_artwork,
    fetch_tracks,
    find_cover,
    search_albums,
)
from mdtools.panels.cover_preview import CoverPreview
from mdtools.panels.mdrem_port import resolve_port
from mdtools.panels.mdrem_upload_dialog import MDRemUploadDialog
from mdtools.project import MEDIUM_MD, ProjectMetadata, Track, format_time, parse_time

# Artist sits between them: it belongs with the title it qualifies, and
# is empty on an ordinary album (see ProjectMetadata.is_compilation).
TITLE_COL, ARTIST_COL, TIME_COL = 0, 1, 2
COVER_SIZE = 100

_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*]')


def _sanitize_filename(text: str) -> str:
    return _INVALID_FILENAME_CHARS.sub("_", text).strip() or "cover"


class _TitleColumnDelegate(QStyledItemDelegate):
    """Enter, while typing a track title, commits it and moves straight to
    the next row's title cell, opening it for editing -- appending a fresh
    row past the last one -- so a whole track list can be typed with no
    mouse at all.

    This has to intercept the key event itself, on the editor, rather than
    reacting to `QTableWidget.closeEditor()` after the fact: Qt's own
    default handling closes an editor on Enter with `EndEditHint
    .SubmitModelCache` -- and, confirmed directly, that is the *exact
    same* hint a plain click on a different cell produces. There is no way
    to tell "the user pressed Enter" from "the user clicked elsewhere"
    once `closeEditor()` has already been called with that hint, so this
    has to happen earlier, in the delegate's own `eventFilter` on the
    editor widget -- which Qt calls before its default Enter/Tab/Escape
    handling ever runs. Returning True here consumes the key, so the base
    class's own SubmitModelCache path never fires for it."""

    def __init__(self, table: "_TrackTable", parent=None):
        super().__init__(parent)
        self._table = table

    def eventFilter(self, editor, event) -> bool:
        if event.type() == QEvent.Type.KeyPress and event.key() in (
            Qt.Key.Key_Return,
            Qt.Key.Key_Enter,
        ):
            self.commitData.emit(editor)
            self.closeEditor.emit(editor, QAbstractItemDelegate.EndEditHint.NoHint)
            self._table.advance_after_title_entry()
            return True
        return super().eventFilter(editor, event)


class _TrackTable(QTableWidget):
    """Plain QTableWidget, plus the Title column's own delegate above."""

    def __init__(self, parent=None):
        super().__init__(0, 3, parent)
        self.setItemDelegateForColumn(TITLE_COL, _TitleColumnDelegate(self, self))

    def advance_after_title_entry(self) -> None:
        row = self.currentRow()
        if row == self.rowCount() - 1:
            # Already the last row -- nothing to move to, so make one.
            row += 1
            self.insertRow(row)
            for col in (TITLE_COL, ARTIST_COL, TIME_COL):
                self.setItem(row, col, QTableWidgetItem(""))
        else:
            row += 1
        self.setCurrentCell(row, TITLE_COL)
        self.editItem(self.item(row, TITLE_COL))


class MetadataDialog(QDialog):
    def __init__(self, metadata: ProjectMetadata, parent=None, medium: str = MEDIUM_MD):
        """`medium` decides whether "Upload Tracklist" is offered at all.

        That button writes titles onto a MiniDisc over infrared; on a CD
        project there is no MiniDisc for it to write to, and the titles
        went onto the disc as CD-Text when it was burned. It stayed visible
        on CD projects at first -- reported directly."""
        super().__init__(parent)
        self.setWindowTitle(self.tr("Project Metadata"))
        self.resize(420, 480)
        self.result_metadata: ProjectMetadata | None = None

        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.album_edit = QLineEdit(metadata.album)
        form.addRow(self.tr("Album title"), self.album_edit)

        self.artist_edit = QLineEdit(metadata.artist)
        form.addRow(self.tr("Artist"), self.artist_edit)

        self.lookup_btn = QPushButton(self.tr("Lookup Track List..."))
        self.lookup_btn.setToolTip(
            self.tr(
                "Fetch the track list, release year and cover art from the iTunes Search API, using Album + "
                "Artist above. A fetched cover is saved for Tools > Insert Asset... to pick up."
            )
        )
        self.lookup_btn.clicked.connect(self._lookup_tracks)
        form.addRow(self.lookup_btn)

        # A second source for the same fields, reading a folder's own tags
        # directly -- no foobar2000 involved, so filling in the editor
        # does not need it running with the album already loaded first.
        self.folder_btn = QPushButton(self.tr("Import from Folder..."))
        self.folder_btn.setToolTip(
            self.tr(
                "Fills these fields from an album folder's own tags, then looks up its cover art."
            )
        )
        self.folder_btn.clicked.connect(self._load_from_folder)
        form.addRow(self.folder_btn)

        self.year_spin = QSpinBox()
        self.year_spin.setRange(0, 2100)
        self.year_spin.setSpecialValueText(self.tr("(unspecified)"))
        self.year_spin.setValue(metadata.year or 0)
        form.addRow(self.tr("Year of release"), self.year_spin)

        self.cover_label = CoverPreview(COVER_SIZE)
        self.cover_label.set_cover(metadata.cover_art)

        top_row = QHBoxLayout()
        top_row.addLayout(form, 1)
        top_row.addWidget(self.cover_label)
        layout.addLayout(top_row)

        layout.addWidget(QLabel(self.tr("Tracks:")))

        self.table = _TrackTable()
        self.table.setHorizontalHeaderLabels(
            [self.tr("Title"), self.tr("Artist (only on a compilation)"), self.tr("Time (mm:ss, optional)")]
        )
        self.table.horizontalHeader().setSectionResizeMode(TITLE_COL, QHeaderView.ResizeMode.Stretch)
        for track in metadata.tracks:
            self._append_row(track.title, format_time(track.time_seconds), track.artist)
        layout.addWidget(self.table)

        btn_row = QHBoxLayout()
        add_btn = QPushButton(self.tr("Add Track"))
        add_btn.clicked.connect(self._add_track)
        remove_btn = QPushButton(self.tr("Remove Selected"))
        remove_btn.clicked.connect(self._remove_selected)
        up_btn = QPushButton(self.tr("Move Up"))
        up_btn.clicked.connect(lambda: self._move_selected(-1))
        down_btn = QPushButton(self.tr("Move Down"))
        down_btn.clicked.connect(lambda: self._move_selected(1))
        for b in (add_btn, remove_btn, up_btn, down_btn):
            btn_row.addWidget(b)
        layout.addLayout(btn_row)

        # Only offered when the IR adapter is turned on in Window >
        # Settings... -- without hardware the button could do nothing but
        # explain itself, which is worse than not being there.
        self.upload_btn = QPushButton(self.tr("Upload Tracklist"))
        self.upload_btn.setToolTip(
            self.tr(
                "Writes the album title and every track name onto the MiniDisc itself, using the MDRem "
                "infrared adapter. Takes several minutes."
            )
        )
        self.upload_btn.clicked.connect(self._upload_tracklist)
        self.upload_btn.setVisible(app_settings.mdrem_enabled() and medium == MEDIUM_MD)
        layout.addWidget(self.upload_btn)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _lookup_tracks(self) -> None:
        artist = self.artist_edit.text().strip()
        album = self.album_edit.text().strip()
        if not artist:
            QMessageBox.information(self, self.tr("Lookup Track List"), self.tr("Fill in Artist first."))
            return

        # Album is optional -- some albums genuinely have no name, and
        # there's no reason to make the user wait on typing one in before
        # the artist alone can already narrow the search down.
        candidates = self._run_lookup(lambda: search_albums(artist, album))
        if candidates is None:
            return  # error already shown
        if not candidates:
            message = (
                self.tr('No album matching "{album}" by "{artist}" was found.').format(album=album, artist=artist)
                if album
                else self.tr('No album by "{artist}" was found.').format(artist=artist)
            )
            QMessageBox.warning(self, self.tr("Lookup Track List"), message)
            return

        chosen = candidates[0]
        if len(candidates) > 1:
            # Listed alphabetically -- asked for directly. search_albums()
            # returns them ranked by match score, which is the right order
            # for *picking* one automatically but a poor one for reading:
            # with a dozen pressings of the same album the eye has nothing
            # to scan by. The ranking is not thrown away, it just stops
            # deciding the display order -- the best match is still what
            # the list opens on, so pressing Enter picks exactly what it
            # picked before this changed.
            best = candidates[0]
            ordered = sorted(candidates, key=lambda c: self._candidate_label(c).casefold())
            labels = [self._candidate_label(c) for c in ordered]
            label, ok = QInputDialog.getItem(
                self,
                self.tr("Select Album"),
                self.tr("Multiple matches were found -- choose the correct one:"),
                labels,
                ordered.index(best),
                False,
            )
            if not ok:
                return
            chosen = ordered[labels.index(label)]

        result = self._run_lookup(lambda: fetch_tracks(chosen.collection_id, fallback_year=chosen.year))
        if result is None:
            return  # error already shown

        # The chosen candidate's own metadata is the authoritative name for
        # this release -- update the fields even if it differs from what the
        # user originally typed (different capitalization, "The" prefix,
        # a remaster suffix, etc.), so what's shown matches what was found.
        if chosen.collection_name:
            self.album_edit.setText(chosen.collection_name)
        if chosen.artist_name:
            self.artist_edit.setText(chosen.artist_name)

        if result.year is not None:
            self.year_spin.setValue(result.year)
        self.table.setRowCount(0)
        for track in result.tracks:
            self._append_row(track.title, format_time(track.time_seconds))

        if chosen.artwork_url:
            self._fetch_and_save_cover(chosen)

    def _load_from_folder(self) -> None:
        """Takes album, artist, year and the whole track list from an
        album folder's own tags -- no foobar2000 involved, replacing what
        used to be "Load from foobar2000" here (explicit user request).

        Useful on its own, not only after recording: these are the actual
        files, with their actual tags, in their actual order, and it is
        more trustworthy than a search for exactly that reason -- the
        same case "Load from foobar2000" made, just without needing
        foobar2000 running with the album already loaded first."""
        remembered = app_settings.music_folder()
        start = remembered if remembered and Path(remembered).is_dir() else user_paths.music_start_path()
        chosen = QFileDialog.getExistingDirectory(self, self.tr("Import from Folder"), start)
        if not chosen:
            return
        folder = Path(chosen)
        app_settings.set_music_folder(str(folder.parent if folder.parent != folder else folder))

        metadata = audio_folder.metadata_from_folder(folder)
        if not metadata.tracks:
            QMessageBox.information(
                self,
                self.tr("Import from Folder"),
                self.tr("No audio files were found in that folder."),
            )
            return

        self.album_edit.setText(metadata.album)
        self.artist_edit.setText(metadata.artist)
        self.year_spin.setValue(metadata.year or 0)
        self.table.setRowCount(0)
        for track in metadata.tracks:
            self._append_row(track.title, format_time(track.time_seconds), track.artist)

        paths = audio_folder.list_audio_files(folder)
        self._fetch_cover_for(metadata.album, metadata.artist, len(metadata.tracks), metadata.year, paths)

    def _fetch_cover_for(
        self, album: str, artist: str, track_count: int, year: int | None, paths: list[Path] = ()
    ) -> None:
        """Cover art (and a year, if the tags had none) for fields that were
        filled in from somewhere other than the iTunes picker. Silent on
        failure, like every other artwork fetch here -- the track list, which
        is what the user actually asked for, has already arrived.

        Clears whatever cover is currently showing *before* searching for
        the new one -- reported directly: importing a second folder that
        happens to have no findable cover left the first import's cover on
        screen, which then silently rode along into this album's own
        metadata. A folder import replaces the cover the same way it
        replaces the track list, empty-handed included.

        `paths` -- the folder's own audio files, when there's a folder to
        fall back to -- is what makes this the *last resort* the module
        docstring for embedded_cover.py describes: a search result is only
        a guess at this release, where the sleeve embedded in the files
        themselves is certainly the right one, just usually smaller/
        rougher, which is why it only runs once the search has already
        come up empty (including on a network failure, not only a genuine
        no-match)."""
        self.cover_label.set_cover(None)
        if not album and not artist:
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            data, chosen = find_cover(artist, album, track_count)
        except MetadataLookupError:
            data, chosen = None, None
        finally:
            QApplication.restoreOverrideCursor()

        if chosen is not None and year is None and chosen.year:
            self.year_spin.setValue(chosen.year)
        if data is None and paths:
            data = embedded_cover.cover_from_files(paths)
            chosen = None
        if data is None:
            return
        self.cover_label.set_cover(data)
        if chosen is not None:
            save_downloaded_cover(chosen.artist_name, chosen.collection_name, data)

    def _fetch_and_save_cover(self, candidate: AlbumCandidate) -> None:
        """Cover art is a bonus on top of the track/year lookup -- a
        failure here (missing artwork, network hiccup) is silently
        ignored rather than shown as a warning, since the primary lookup
        this button promises already succeeded.

        Saved in two places, for two different purposes: the per-user
        gallery cache (so it's immediately selectable from Tools > Insert
        Asset...), and the preview widget, which is what carries it into
        result_metadata on OK and so into the saved *project* -- which is
        why reopening this dialog later still shows it."""
        try:
            data = fetch_artwork(candidate.artwork_url)
        except MetadataLookupError:
            return

        filename = f"{_sanitize_filename(candidate.artist_name)} - {_sanitize_filename(candidate.collection_name)}.jpg"
        (downloaded_covers_dir() / filename).write_bytes(data)
        self.cover_label.set_cover(data)

    @property
    def _cover_art(self) -> bytes | None:
        """The cover the preview is holding. One owner, so a fetch, a
        locally chosen file and what OK returns cannot disagree."""
        return self.cover_label.data

    def _run_lookup(self, call):
        """Runs a blocking metadata_lookup call with a wait cursor and the
        button disabled meanwhile; on MetadataLookupError shows a warning
        and returns None (the caller treats None as "already handled")."""
        self.lookup_btn.setEnabled(False)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            return call()
        except MetadataLookupError as exc:
            QMessageBox.warning(self, self.tr("Lookup Track List"), str(exc))
            return None
        finally:
            QApplication.restoreOverrideCursor()
            self.lookup_btn.setEnabled(True)

    @staticmethod
    def _candidate_label(candidate: AlbumCandidate) -> str:
        year_text = str(candidate.year) if candidate.year else "?"
        return f"{candidate.artist_name} — {candidate.collection_name} ({year_text}, {candidate.track_count} tracks)"

    def _append_row(self, title: str, time_text: str, artist: str = "") -> int:
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, TITLE_COL, QTableWidgetItem(title))
        self.table.setItem(row, ARTIST_COL, QTableWidgetItem(artist))
        self.table.setItem(row, TIME_COL, QTableWidgetItem(time_text))
        return row

    def _add_track(self) -> None:
        row = self._append_row("", "", "")
        title_item = self.table.item(row, TITLE_COL)
        self.table.setCurrentItem(title_item)
        self.table.editItem(title_item)

    def _remove_selected(self) -> None:
        for row in sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True):
            self.table.removeRow(row)

    def _move_selected(self, direction: int) -> None:
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        if not rows:
            return
        row = rows[0]
        target = row + direction
        if target < 0 or target >= self.table.rowCount():
            return
        for col in (TITLE_COL, ARTIST_COL, TIME_COL):
            a = self.table.takeItem(row, col)
            b = self.table.takeItem(target, col)
            self.table.setItem(row, col, b)
            self.table.setItem(target, col, a)
        self.table.selectRow(target)

    def _current_metadata(self) -> ProjectMetadata:
        """Whatever the fields say right now, committed or not.

        Upload Tracklist needs this as much as OK does -- uploading what
        the project was saved with, rather than what is on screen after a
        lookup or a hand edit, would write stale titles onto a disc."""
        tracks: list[Track] = []
        for row in range(self.table.rowCount()):
            title_item = self.table.item(row, TITLE_COL)
            title = title_item.text().strip() if title_item else ""
            if not title:
                continue
            time_item = self.table.item(row, TIME_COL)
            time_text = time_item.text() if time_item else ""
            artist_item = self.table.item(row, ARTIST_COL)
            artist = artist_item.text().strip() if artist_item else ""
            tracks.append(Track(title=title, time_seconds=parse_time(time_text), artist=artist))

        return ProjectMetadata(
            album=self.album_edit.text().strip(),
            artist=self.artist_edit.text().strip(),
            year=self.year_spin.value() or None,
            tracks=tracks,
            cover_art=self.cover_label.data,
        )

    def _upload_tracklist(self) -> None:
        port = resolve_port(self)
        if port is None:
            return
        MDRemUploadDialog(self._current_metadata(), port, self).exec()

    def _on_accept(self) -> None:
        self.result_metadata = self._current_metadata()
        self.accept()
