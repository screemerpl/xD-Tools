from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
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
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from mdtools import app_settings, foobar
from mdtools.gallery import downloaded_covers_dir, save_downloaded_cover
from mdtools.metadata_lookup import (
    AlbumCandidate,
    MetadataLookupError,
    fetch_artwork,
    fetch_tracks,
    find_cover,
    search_albums,
)
from mdtools.panels.mdrem_port import resolve_port
from mdtools.panels.mdrem_upload_dialog import MDRemUploadDialog
from mdtools.project import ProjectMetadata, Track, format_time, parse_time

TITLE_COL, TIME_COL = 0, 1
COVER_SIZE = 100

_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*]')


def _sanitize_filename(text: str) -> str:
    return _INVALID_FILENAME_CHARS.sub("_", text).strip() or "cover"


class _CoverLabel(QLabel):
    """The cover preview, clickable.

    Both automatic sources here guess: iTunes returns whatever release its
    search matched, which for a reissue, a compilation or a band with a
    common name is regularly the wrong artwork. Being able to point at a
    file is the only way out of that, so the picture itself is the button
    -- clicking what you want to change is where anyone looks first."""

    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mouseReleaseEvent(self, event) -> None:
        # Released inside, not merely pressed: a press that wandered off the
        # label before letting go is how anyone cancels a misclick.
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class MetadataDialog(QDialog):
    def __init__(self, metadata: ProjectMetadata, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Project Metadata"))
        self.resize(420, 480)
        self.result_metadata: ProjectMetadata | None = None
        # Carries over into result_metadata on OK -- seeded from whatever
        # was already saved with the project, so reopening this dialog
        # later still shows a cover fetched in an earlier session.
        self._cover_art: bytes | None = metadata.cover_art

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

        # A second source for the same fields. Deliberately not gated behind
        # the MDRem setting: reading a playlist needs foobar2000, not the
        # infrared adapter.
        self.foobar_btn = QPushButton(self.tr("Load from foobar2000"))
        self.foobar_btn.setToolTip(
            self.tr(
                "Fills these fields from whatever is loaded in foobar2000's current playlist, then looks up "
                "its cover art. Needs the Beefweb Remote Control component (foo_beefweb)."
            )
        )
        self.foobar_btn.clicked.connect(self._load_from_foobar)
        form.addRow(self.foobar_btn)

        self.year_spin = QSpinBox()
        self.year_spin.setRange(0, 2100)
        self.year_spin.setSpecialValueText(self.tr("(unspecified)"))
        self.year_spin.setValue(metadata.year or 0)
        form.addRow(self.tr("Year of release"), self.year_spin)

        self.cover_label = _CoverLabel()
        self.cover_label.setFixedSize(COVER_SIZE, COVER_SIZE)
        self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover_label.setFrameShape(QFrame.Shape.Box)
        self.cover_label.setScaledContents(False)
        self.cover_label.setToolTip(
            self.tr("Click to choose the cover art yourself -- use this when the fetched one is wrong.")
        )
        self.cover_label.clicked.connect(self._choose_cover_file)
        self._show_no_cover()
        if self._cover_art:
            self._show_cover_bytes(self._cover_art)

        top_row = QHBoxLayout()
        top_row.addLayout(form, 1)
        top_row.addWidget(self.cover_label)
        layout.addLayout(top_row)

        layout.addWidget(QLabel(self.tr("Tracks:")))

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels([self.tr("Title"), self.tr("Time (mm:ss, optional)")])
        self.table.horizontalHeader().setSectionResizeMode(TITLE_COL, QHeaderView.ResizeMode.Stretch)
        for track in metadata.tracks:
            self._append_row(track.title, format_time(track.time_seconds))
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
        self.upload_btn.setVisible(app_settings.mdrem_enabled())
        layout.addWidget(self.upload_btn)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _lookup_tracks(self) -> None:
        artist = self.artist_edit.text().strip()
        album = self.album_edit.text().strip()
        if not artist or not album:
            QMessageBox.information(
                self, self.tr("Lookup Track List"), self.tr("Fill in Album title and Artist first.")
            )
            return

        candidates = self._run_lookup(lambda: search_albums(artist, album))
        if candidates is None:
            return  # error already shown
        if not candidates:
            QMessageBox.warning(
                self,
                self.tr("Lookup Track List"),
                self.tr('No album matching "{album}" by "{artist}" was found.').format(album=album, artist=artist),
            )
            return

        chosen = candidates[0]
        if len(candidates) > 1:
            labels = [self._candidate_label(c) for c in candidates]
            label, ok = QInputDialog.getItem(
                self,
                self.tr("Select Album"),
                self.tr("Multiple matches were found -- choose the correct one:"),
                labels,
                0,
                False,
            )
            if not ok:
                return
            chosen = candidates[labels.index(label)]

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

    def _load_from_foobar(self) -> None:
        """Takes album, artist, year and the whole track list from
        foobar2000's current playlist.

        Useful on its own, not only after recording: what is queued up to
        play is usually exactly what the label is being made for, and it is
        more trustworthy than a search -- these are the actual files, with
        their actual tags, in their actual order."""
        client = foobar.FoobarClient(app_settings.foobar_url())
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            playlist = client.current_playlist()
            items = client.playlist_items(playlist.id) if playlist is not None else []
        except foobar.FoobarError as exc:
            QMessageBox.warning(self, self.tr("Load from foobar2000"), str(exc))
            return
        finally:
            QApplication.restoreOverrideCursor()

        if not items:
            QMessageBox.information(
                self,
                self.tr("Load from foobar2000"),
                self.tr("foobar2000's current playlist is empty."),
            )
            return

        metadata = foobar.metadata_from_playlist(items)
        self.album_edit.setText(metadata.album)
        self.artist_edit.setText(metadata.artist)
        self.year_spin.setValue(metadata.year or 0)
        self.table.setRowCount(0)
        for track in metadata.tracks:
            self._append_row(track.title, format_time(track.time_seconds))

        self._fetch_cover_for(metadata.album, metadata.artist, len(metadata.tracks), metadata.year)

    def _fetch_cover_for(self, album: str, artist: str, track_count: int, year: int | None) -> None:
        """Cover art (and a year, if the tags had none) for fields that were
        filled in from somewhere other than the iTunes picker. Silent on
        failure, like every other artwork fetch here -- the track list, which
        is what the user actually asked for, has already arrived."""
        if not album and not artist:
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            data, chosen = find_cover(artist, album, track_count)
        except MetadataLookupError:
            return
        finally:
            QApplication.restoreOverrideCursor()

        if chosen is not None and year is None and chosen.year:
            self.year_spin.setValue(chosen.year)
        if data is None or chosen is None:
            return
        self._cover_art = data
        self._show_cover_bytes(data)
        save_downloaded_cover(chosen.artist_name, chosen.collection_name, data)

    def _fetch_and_save_cover(self, candidate: AlbumCandidate) -> None:
        """Cover art is a bonus on top of the track/year lookup -- a
        failure here (missing artwork, network hiccup) is silently
        ignored rather than shown as a warning, since the primary lookup
        this button promises already succeeded.

        Saved in two places, for two different purposes: the per-user
        gallery cache (so it's immediately selectable from Tools > Insert
        Asset...), and self._cover_art (so it's carried into
        result_metadata on OK and saved with the *project*, restoring the
        preview here next time this dialog is reopened)."""
        try:
            data = fetch_artwork(candidate.artwork_url)
        except MetadataLookupError:
            return

        filename = f"{_sanitize_filename(candidate.artist_name)} - {_sanitize_filename(candidate.collection_name)}.jpg"
        (downloaded_covers_dir() / filename).write_bytes(data)
        self._cover_art = data
        self._show_cover_bytes(data)

    def _choose_cover_file(self) -> None:
        """Replaces the cover with a local image file.

        Deliberately overrides whatever a lookup found, without asking: the
        user clicked the picture they can see is wrong."""
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("Choose Cover Art"), "", self.tr("Images (*.png *.jpg *.jpeg *.bmp *.webp)")
        )
        if not path:
            return
        try:
            data = Path(path).read_bytes()
        except OSError as exc:
            QMessageBox.warning(self, self.tr("Choose Cover Art"), self.tr("Could not read the file:\n{error}").format(error=exc))
            return
        # Checked here rather than trusted from the extension: the bytes are
        # what gets saved into the project and later handed to the layout
        # code, which has no way to report back that they were never an image.
        if not self._show_cover_bytes(data):
            QMessageBox.warning(
                self, self.tr("Choose Cover Art"), self.tr("That file could not be read as an image.")
            )
            return
        self._cover_art = data

    def _show_no_cover(self) -> None:
        self.cover_label.setPixmap(QPixmap())
        self.cover_label.setText(self.tr("No cover\n\n(click to\nchoose one)"))

    def _show_cover_bytes(self, data: bytes) -> bool:
        pixmap = QPixmap()
        if not pixmap.loadFromData(data):
            return False
        self.cover_label.setText("")
        self.cover_label.setPixmap(
            pixmap.scaled(
                COVER_SIZE, COVER_SIZE, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
        )
        return True

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

    def _append_row(self, title: str, time_text: str) -> int:
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, TITLE_COL, QTableWidgetItem(title))
        self.table.setItem(row, TIME_COL, QTableWidgetItem(time_text))
        return row

    def _add_track(self) -> None:
        row = self._append_row("", "")
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
        for col in (TITLE_COL, TIME_COL):
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
            tracks.append(Track(title=title, time_seconds=parse_time(time_text)))

        return ProjectMetadata(
            album=self.album_edit.text().strip(),
            artist=self.artist_edit.text().strip(),
            year=self.year_spin.value() or None,
            tracks=tracks,
            cover_art=self._cover_art,
        )

    def _upload_tracklist(self) -> None:
        port = resolve_port(self)
        if port is None:
            return
        MDRemUploadDialog(self._current_metadata(), port, self).exec()

    def _on_accept(self) -> None:
        self.result_metadata = self._current_metadata()
        self.accept()
