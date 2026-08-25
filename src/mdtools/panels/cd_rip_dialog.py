"""Recording > "Record CD to MiniDisc..." -- the step that turns a compact
disc into something the existing recording flow can play.

The sequence:

  1. pick a drive and read the disc's table of contents
  2. identify it (MusicBrainz, by the TOC itself -- a CD carries no text)
  3. extract every track to a tagged FLAC in the rip folder
  4. hand its file paths, in disc order, off to RecordDialog -- which is
     unchanged and unaware a CD was ever involved

Step 4 is the point of steps 1-3. Everything that makes recording work --
arming the deck, the lead-in, a track mark at every boundary, titling
afterwards -- already exists and is driven by whichever files RecordDialog
is handed. So this feature's job is not to record anything; it is to
produce the right files in the right order, and hand their paths over.
Same hand-off shape as RecordDialog's own to MDRemUploadDialog.

This used to empty foobar2000's playlist and load the ripped files into it
instead of handing paths over directly -- see RecordDialog's own module
docstring for why that step (and the exe/Beefweb-reachability checks that
came with it) is gone now that RecordDialog decodes and plays files
itself, through AudioPlayer.

Why rip at all, rather than play the CD directly during the recording: the
disc would then be read in real time, with nothing to fall back on. A
drive that stumbles on a scratch at minute 31 would put that stumble
on the MiniDisc, and MiniDisc recording is not something you can retry a
few seconds of. Ripping first moves every read error to a point where it
costs nothing but a re-read -- which is exactly what cdparanoia spends its
effort on.

The rip itself runs on a worker thread, like the MDRem upload and unlike
everything else here: a full album is minutes of solid work. The TOC read
and the MusicBrainz lookup stay blocking, matching metadata_lookup.py --
they are single, occasional, user-initiated clicks measured in seconds, and
a thread each would buy nothing but machinery.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
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

from mdtools import app_settings, cdrip, mixtape_cover, musicbrainz
from mdtools.panels.cover_preview import CoverPreview, fetch_into
from mdtools.panels.hideable_dialog import hide_for_background
from mdtools.panels.progress_format import mmss as _mmss
from mdtools.project import MEDIUM_MD, medium_name, ProjectMetadata, Track, apply_compilation_naming

# An MD holds 80 minutes in SP -- the same limit RecordDialog warns about,
# checked here as well because here it is still free to act on: the disc in
# the drive can be swapped, or the deck set to LP2, before ten minutes have
# been spent ripping it.
DISC_SP_SECONDS = 80 * 60

_PROGRESS_SCALE = 1000

# Within one track, extraction is the long part and encoding the short one.
# Not measured precisely -- it only decides how the bar moves inside a
# track, never what actually happens.
_RIP_SHARE = 0.9

# Emitting a signal for every line cdparanoia prints would be thousands per
# track for movement far below one pixel.
_PROGRESS_EPSILON = 0.002


def _same_name(left: str, right: str) -> bool:
    return left.strip().casefold() == right.strip().casefold()


class _RipWorker(QThread):
    """Extracts and encodes every track of the disc, in order."""

    track_started = Signal(int)
    progress = Signal(float)
    track_progress = Signal(float)  # this track's own fraction, 0.0-1.0
    stage = Signal(str)
    failed = Signal(str)
    cancelled = Signal()
    succeeded = Signal()

    def __init__(self, device: str, plan: cdrip.RipPlan, parent=None):
        super().__init__(parent)
        self._device = device
        self._plan = plan
        self._cancelled = False
        self._total_sectors = max(1, sum(task.sectors for task in plan.tasks))
        self._done_sectors = 0
        self._last_emitted = -1.0

    def cancel(self) -> None:
        """Takes effect immediately, unlike the MDRem upload's -- killing a
        read leaves nothing half-written anywhere that matters, and the
        partial WAV is deleted on the way out."""
        self._cancelled = True

    def run(self) -> None:
        try:
            for index, task in enumerate(self._plan.tasks):
                if self._cancelled:
                    self.cancelled.emit()
                    return
                self.track_started.emit(index)
                cdrip.rip_track(
                    self._device,
                    task,
                    on_progress=lambda fraction, t=task: self._on_track_progress(t, fraction * _RIP_SHARE),
                    should_cancel=lambda: self._cancelled,
                )
                self.stage.emit("encode")
                cdrip.encode_track(task)
                self._done_sectors += task.sectors
                self._emit_progress(self._done_sectors / self._total_sectors)
            if self._cancelled:
                self.cancelled.emit()
                return
        except cdrip.CdRipCancelled:
            self.cancelled.emit()
            return
        except cdrip.CdRipError as exc:
            self.failed.emit(str(exc))
            return
        self.succeeded.emit()

    def _on_track_progress(self, task: cdrip.RipTask, within_track: float) -> None:
        self._emit_progress((self._done_sectors + within_track * task.sectors) / self._total_sectors)
        # within_track only ever reaches _RIP_SHARE (extraction's own share
        # of the track) -- rescaled back to a genuine 0.0-1.0 fraction of
        # this one track, encoding's own short remainder included for free
        # since it snaps to 1.0 the moment the *next* track_started fires.
        self.track_progress.emit(min(1.0, within_track / _RIP_SHARE))

    def _emit_progress(self, fraction: float) -> None:
        fraction = min(1.0, max(0.0, fraction))
        if fraction - self._last_emitted < _PROGRESS_EPSILON and fraction < 1.0:
            return
        self._last_emitted = fraction
        self.progress.emit(fraction)


class CdRipDialog(QDialog):
    # Mirrored by MainWindow's own bottom-of-window progress bar (#27) --
    # see app_window.py's _drive_recording_bar()/_release_recording_bar().
    running_changed = Signal(bool)
    overall_progress_changed = Signal(float, str)
    track_progress_changed = Signal(float, str)
    visibility_changed = Signal(bool)
    # Asked for by the progress bar's "Show recording window" button --
    # see panels/hideable_dialog.py, which is what actually re-shows this.
    show_requested = Signal()

    def __init__(self, parent=None, medium: str = MEDIUM_MD):
        """`medium` is only ever wording: the rip itself is the same work
        whichever machine the tracks are recorded onto afterwards, but a
        window headed "Record CD to MiniDisc" in front of a cassette
        project is telling the user something untrue about what they are
        about to do."""
        super().__init__(parent)
        self._medium = medium
        self._target = medium_name(medium)
        self.setWindowTitle(self._window_title())
        self.resize(560, 560)
        self._toc: cdrip.DiscToc | None = None
        self._releases: list[musicbrainz.DiscRelease] = []
        self._worker: _RipWorker | None = None
        self._closing = False
        # Set by the Hide button, read by exec_hideable() -- see
        # panels/hideable_dialog.py for why a hide has to be told apart
        # from a cancel at all.
        self.hidden_for_background = False
        # Several discs ripped as one album: which one is in the drive, the
        # folder they all share (fixed by the first, since a later disc may
        # well be identified under a different name), and what the discs
        # already done contributed.
        self._disc = 1
        self._album_folder: Path | None = None
        self._done_tracks: list[Track] = []
        self._done_paths: list[Path] = []
        self._current_paths: list[Path] = []
        self._advance_when_finished = False
        # Read by MainWindow after exec(): where the tracks were written, so
        # a message can name it.
        self.result_folder: Path | None = None
        # The ripped files, in disc order -- handed straight to RecordDialog.
        self.result_paths: list[Path] = []
        # And what the disc turned out to be. The titles in it are the same
        # ones the files are tagged with -- they were written as tags during
        # encoding, so there is no second source of truth to disagree with.
        # What it adds is the artwork, which a FLAC file's tags do not carry
        # here and which the user may have corrected by clicking the preview.
        self.result_metadata: ProjectMetadata | None = None

        layout = QVBoxLayout(self)

        layout.addWidget(self._build_drive_row())

        form = QFormLayout()
        self.artist_edit = QLineEdit()
        self.album_edit = QLineEdit()
        self.year_spin = QSpinBox()
        self.year_spin.setRange(0, 2999)
        self.year_spin.setSpecialValueText(" ")
        self.release_combo = QComboBox()
        self.release_combo.currentIndexChanged.connect(self._on_release_chosen)
        form.addRow(self.tr("Artist"), self.artist_edit)
        form.addRow(self.tr("Album"), self.album_edit)
        form.addRow(self.tr("Year"), self.year_spin)
        form.addRow(self.tr("Release"), self.release_combo)
        self._form = form
        form.setRowVisible(self.release_combo, False)

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
                "Titles and artists can be edited here -- they are written into the ripped files, and are "
                "what ends up on the {medium}. Fill the artist column in when the disc is a compilation: "
                "xD-Tools then names it accordingly and draws it a cover of its own."
            ).format(medium=self._target)
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.multi_check = QCheckBox(self.tr("Rip several discs as one album"))
        self.multi_check.setToolTip(
            self.tr(
                "For a set that came as more than one CD. Each disc is read, identified and ripped on its "
                "own, and you are asked for the next -- they end up in one folder, tagged with the disc "
                "they came from, as a single album."
            )
        )
        layout.addWidget(self.multi_check)

        self.warning_label = QLabel()
        self.warning_label.setWordWrap(True)
        self.warning_label.setVisible(False)
        layout.addWidget(self.warning_label)

        self.progress = QProgressBar()
        self.progress.setRange(0, _PROGRESS_SCALE)
        self.progress.setTextVisible(False)
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.buttons = QDialogButtonBox()
        self.start_btn = QPushButton(self.tr("Rip and Record"))
        self.start_btn.setEnabled(False)
        self.start_btn.clicked.connect(self._start)
        self.buttons.addButton(self.start_btn, QDialogButtonBox.ButtonRole.AcceptRole)
        self.hide_btn = QPushButton(self.tr("Hide"))
        self.hide_btn.setToolTip(
            self.tr("Hide this window and keep ripping in the background -- use \"Show recording "
                    "window\" in the bar at the bottom of the main window to bring it back.")
        )
        self.hide_btn.clicked.connect(self._on_hide_clicked)
        self.buttons.addButton(self.hide_btn, QDialogButtonBox.ButtonRole.ActionRole)
        self.close_btn = QPushButton(self.tr("Cancel"))
        self.close_btn.clicked.connect(self.reject)
        self.buttons.addButton(self.close_btn, QDialogButtonBox.ButtonRole.RejectRole)
        layout.addWidget(self.buttons)

        self._refresh_drives()  # which also runs the bundled-tool check

    # --- construction helpers -------------------------------------------

    def _build_drive_row(self) -> QWidget:
        widget = QWidget()
        row = QHBoxLayout(widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(QLabel(self.tr("Drive")))
        self.drive_combo = QComboBox()
        row.addWidget(self.drive_combo, 1)
        self.refresh_btn = QPushButton(self.tr("Refresh"))
        self.refresh_btn.clicked.connect(self._refresh_drives)
        row.addWidget(self.refresh_btn)
        self.read_btn = QPushButton(self.tr("Read Disc"))
        self.read_btn.clicked.connect(self._read_disc)
        row.addWidget(self.read_btn)
        return widget

    def _refresh_drives(self) -> None:
        """Lists drives whether or not they hold a disc -- the usual order
        of events is to open this, see the drive, and only then put the CD
        in."""
        self.drive_combo.clear()
        drives = cdrip.list_drives()
        for drive in drives:
            self.drive_combo.addItem(drive.display(), drive.device)
        if not drives:
            self.status_label.setText(self.tr("No CD drive was found. Connect one and press Refresh."))
            self.read_btn.setEnabled(False)
            return
        self.read_btn.setEnabled(True)
        index = self.drive_combo.findData(app_settings.cd_drive())
        if index >= 0:
            self.drive_combo.setCurrentIndex(index)
        self.status_label.setText(self.tr("Insert an audio CD and press Read Disc."))
        # Re-checked here, not only in __init__: this method enables the
        # button, so pressing Refresh would otherwise undo the tool check.
        self._check_tools()

    def _check_tools(self) -> None:
        missing = cdrip.missing_tools()
        if not missing:
            return
        self.read_btn.setEnabled(False)
        self.status_label.setText(
            self.tr(
                "These bundled tools are missing, so a CD cannot be read: {tools}. Reinstall xD-Tools, or put "
                "them on your PATH."
            ).format(tools=", ".join(missing))
        )

    # --- reading the disc ------------------------------------------------

    def selected_device(self) -> str:
        return str(self.drive_combo.currentData() or "")

    def _read_disc(self) -> None:
        device = self.selected_device()
        if not device:
            return
        self.read_btn.setEnabled(False)
        self.status_label.setText(self.tr("Reading the disc..."))
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            toc = cdrip.read_toc(device)
        except cdrip.CdRipError as exc:
            self.status_label.setText(self.tr("Could not read the disc: {error}").format(error=exc))
            self._toc = None
            self.start_btn.setEnabled(False)
            return
        finally:
            QApplication.restoreOverrideCursor()
            self.read_btn.setEnabled(True)

        self._toc = toc
        app_settings.set_cd_drive(device)
        self._show_toc(toc)
        self._lookup_metadata(toc)
        self.start_btn.setEnabled(True)

    def _show_toc(self, toc: cdrip.DiscToc) -> None:
        self.tree.clear()
        for track in toc.tracks:
            item = QTreeWidgetItem(
                self.tree,
                [
                    str(track.number),
                    self.tr("Track {number}").format(number=track.number),
                    "",
                    _mmss(track.seconds),
                ],
            )
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        self.tree.resizeColumnToContents(0)
        self.tree.resizeColumnToContents(3)
        self._warn_about_length(toc.total_seconds)

    def _window_title(self) -> str:
        return self.tr("Record CD to {medium}").format(medium=self._target)

    def _warn_about_length(self, total: float) -> None:
        # A MiniDisc's 80-minute SP limit, and nothing else's: a cassette is
        # measured against the tape that is actually in the deck, which
        # TapeRecordDialog asks for and warns about itself.
        if self._medium != MEDIUM_MD or total <= DISC_SP_SECONDS:
            self.warning_label.setVisible(False)
            return
        self.warning_label.setText(
            self.tr(
                "This disc runs {total}, longer than the {limit} an MD holds in SP mode. Set the deck to LP2 "
                "first, or the recording will be cut short."
            ).format(total=_mmss(total), limit=_mmss(DISC_SP_SECONDS))
        )
        self.warning_label.setVisible(True)

    def _lookup_metadata(self, toc: cdrip.DiscToc) -> None:
        """Fills in what the disc itself cannot say.

        A miss is not a failure: the track rows are already there with
        placeholder titles the user can type over, which is exactly what
        anyone with a home-burned or obscure disc will have to do
        regardless."""
        self.status_label.setText(self.tr("Looking the disc up on MusicBrainz..."))
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self._releases = musicbrainz.lookup_disc(toc)
        except musicbrainz.MusicBrainzError as exc:
            self._releases = []
            self.status_label.setText(
                self.tr("The disc could not be looked up ({error}) -- type the titles in yourself.").format(error=exc)
            )
            return
        finally:
            QApplication.restoreOverrideCursor()

        if not self._releases:
            self.status_label.setText(
                self.tr("This disc is not in MusicBrainz -- type the album, artist and titles in yourself.")
            )
            self._form.setRowVisible(self.release_combo, False)
            return

        self.release_combo.blockSignals(True)
        self.release_combo.clear()
        for release in self._releases:
            self.release_combo.addItem(release.label())
        self.release_combo.setCurrentIndex(0)
        self.release_combo.blockSignals(False)
        # One candidate needs no picker; several are genuinely ambiguous
        # (pressings, reissues, a tribute album with the same track lengths),
        # the same reason MetadataDialog shows a list rather than guessing.
        self._form.setRowVisible(self.release_combo, len(self._releases) > 1)
        self._apply_release(self._releases[0])
        self.status_label.setText(
            self.tr("Identified as {name}. Check the titles, then rip.").format(name=self._releases[0].label())
        )

    def _on_release_chosen(self, index: int) -> None:
        if 0 <= index < len(self._releases):
            self._apply_release(self._releases[index])

    def _apply_release(self, release: musicbrainz.DiscRelease) -> None:
        self.artist_edit.setText(release.artist)
        self.album_edit.setText(release.title)
        self.year_spin.setValue(release.year or 0)
        # Looked up here rather than after the recording, and re-looked-up
        # when a different pressing is picked: this is the moment the album
        # is decided, and the artwork is what the label is built around. It
        # also gives the user something to disagree with -- the preview is
        # clickable -- while there is still time to fix it.
        fetch_into(self.cover_label, release.artist, release.title, len(release.track_titles))
        for index in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(index)
            if index < len(release.track_titles):
                item.setText(1, release.track_titles[index])
            # Left blank on an ordinary album rather than repeating the
            # album's own artist on all twelve rows: a per-track artist is
            # only information when it differs from it.
            if index < len(release.track_artists):
                performer = release.track_artists[index]
                item.setText(2, "" if _same_name(performer, release.artist) else performer)

    # --- ripping ----------------------------------------------------------

    def track_titles(self) -> list[str]:
        return [self.tree.topLevelItem(i).text(1) for i in range(self.tree.topLevelItemCount())]

    def track_artists(self) -> list[str]:
        return [self.tree.topLevelItem(i).text(2) for i in range(self.tree.topLevelItemCount())]

    def build_plan(self) -> cdrip.RipPlan:
        assert self._toc is not None
        root = Path(app_settings.cd_rip_folder())
        # Every disc of a set goes into the folder the first one made: a
        # later disc is often identified under its own title ("... [Disc
        # 2]"), and a folder per disc would be two albums rather than one.
        folder = self._album_folder or root / cdrip.rip_folder_name(
            self.artist_edit.text(), self.album_edit.text()
        )
        year = self.year_spin.value() or None
        return cdrip.build_rip_plan(
            self._toc,
            folder,
            self.track_titles(),
            artist=self.artist_edit.text(),
            album=self.album_edit.text(),
            year=year,
            track_artists=self.track_artists(),
            disc_number=self._disc if self.multi_check.isChecked() else None,
        )

    def build_metadata(self) -> ProjectMetadata:
        """The disc as project metadata, from the fields and the tree.

        Handed to RecordDialog so it opens on the album this is, artwork
        included. The titles in it are the same ones the ripped files are
        tagged with, so it is not a second source of truth competing with
        them -- it is their own contents plus a cover, which a tag does not
        carry."""
        tracks = list(self._done_tracks)
        for index, track in enumerate(self._toc.tracks if self._toc else []):
            row = self.tree.topLevelItem(index)
            tracks.append(
                Track(
                    title=row.text(1).strip() if row is not None else "",
                    time_seconds=int(track.seconds) or None,
                    artist=row.text(2).strip() if row is not None else "",
                )
            )
        metadata = apply_compilation_naming(
            ProjectMetadata(
                album=self.album_edit.text().strip(),
                artist=self.artist_edit.text().strip(),
                year=self.year_spin.value() or None,
                tracks=tracks,
                cover_art=self.cover_label.data,
            )
        )
        if metadata.is_compilation() and not metadata.cover_art:
            # Nothing to look up for a Various Artists disc -- see
            # cover_preview.fetch_into. One is drawn from the track list.
            metadata.cover_art = mixtape_cover.render_cover(metadata)
        return metadata

    def _start(self) -> None:
        if self._toc is None:
            return

        plan = self.build_plan()
        self.result_metadata = self.build_metadata()
        # Nothing here ever deletes a previous rip -- explicit instruction:
        # this folder is shared with permanently-organized albums (Telegram
        # downloads, "Sort Audio Folder into Albums..."), and a folder of
        # nothing but .flac files looks exactly like a stale rip whether it
        # is one or not (see cdrip.py's own history for the real incident
        # this cost). Ripped files simply accumulate; nothing here cleans
        # up after itself.
        try:
            cdrip.ensure_folder(plan.folder)
        except cdrip.CdRipError as exc:
            QMessageBox.warning(
                self,
                self._window_title(),
                self.tr(
                    "The rip folder could not be created: {error}\n\nChoose a different one in "
                    "Window > Settings..."
                ).format(error=exc),
            )
            return
        self.result_folder = plan.folder
        self._album_folder = plan.folder

        self._set_running(True)
        self._succeeded = False
        self._plan = plan
        self.progress.setValue(0)
        self.progress.setVisible(True)
        self.status_label.setText(self.tr("Starting..."))

        # Everything ripped so far, so the final result holds the whole
        # album rather than only the disc that finished last.
        self._current_paths = self._done_paths + list(plan.flac_paths)

        self._worker = _RipWorker(self.selected_device(), plan, self)
        self._worker.track_started.connect(self._on_track_started)
        self._worker.progress.connect(self._on_progress)
        self._worker.track_progress.connect(self._on_track_progress)
        self._worker.stage.connect(self._on_stage)
        self._worker.failed.connect(self._on_failed)
        self._worker.cancelled.connect(self._on_cancelled)
        self._worker.succeeded.connect(self._on_succeeded)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()

    def _set_running(self, running: bool) -> None:
        self.running_changed.emit(running)
        for widget in (
            self.start_btn,
            self.read_btn,
            self.refresh_btn,
            self.drive_combo,
            self.tree,
            self.artist_edit,
            self.album_edit,
            self.year_spin,
            self.release_combo,
            self.multi_check,
        ):
            widget.setEnabled(not running)
        self.close_btn.setText(self.tr("Stop") if running else self.tr("Cancel"))

    def _on_track_started(self, index: int) -> None:
        self._current_index = index
        task = self._plan.tasks[index]
        self.status_label.setText(
            self.tr("Ripping {index} of {count}: {title}").format(
                index=index + 1, count=len(self._plan.tasks), title=task.title
            )
        )

    def _on_stage(self, stage: str) -> None:
        if stage == "encode":
            self.status_label.setText(
                self.tr("Encoding {index} of {count}...").format(
                    index=getattr(self, "_current_index", 0) + 1, count=len(self._plan.tasks)
                )
            )

    def _on_progress(self, fraction: float) -> None:
        self.progress.setValue(int(_PROGRESS_SCALE * fraction))
        self.overall_progress_changed.emit(fraction, self.status_label.text())

    def _on_track_progress(self, fraction: float) -> None:
        task = self._plan.tasks[self._current_index]
        self.track_progress_changed.emit(fraction, task.title)

    def _on_failed(self, message: str) -> None:
        self.progress.setVisible(False)
        self.status_label.setText(self.tr("Ripping failed: {error}").format(error=message))

    def _on_cancelled(self) -> None:
        self.progress.setVisible(False)
        self.status_label.setText(self.tr("Stopped. Nothing was recorded."))

    def _on_succeeded(self) -> None:
        self.progress.setValue(_PROGRESS_SCALE)
        if self.multi_check.isChecked():
            # Asked about from _on_worker_finished rather than here: this
            # thread is still running, and starting the next disc now would
            # have its worker cleared away the moment this one finishes.
            self._advance_when_finished = True
            self.status_label.setText(
                self.tr("Disc {number} is ripped.").format(number=self._disc)
            )
            return
        self.status_label.setText(self.tr("The disc is ripped."))
        self._succeeded = True

    def _on_worker_finished(self) -> None:
        """The single place a run ends, whatever ended it -- the same shape
        MDRemUploadDialog uses, and for the same reason: it lets Stop return
        immediately instead of blocking the GUI thread on wait()."""
        self._worker = None
        self._set_running(False)
        if self._advance_when_finished:
            self._advance_when_finished = False
            self._keep_finished_disc()
            if self._ask_for_next_disc():
                self._read_next_disc()
                return
            self._succeeded = True
        if getattr(self, "_succeeded", False):
            self.result_paths = list(self._current_paths)
            # Accepting is the hand-off: MainWindow opens RecordDialog next.
            self.accept()
            return
        if self._closing:
            super().reject()

    def _keep_finished_disc(self) -> None:
        """Folds the disc just ripped into what the album is, so the next
        one is added to it rather than replacing it."""
        self._done_tracks = list(self.build_metadata().tracks)
        self._done_paths += list(self._plan.flac_paths)

    def _ask_for_next_disc(self) -> bool:
        return (
            QMessageBox.question(
                self,
                self._window_title(),
                self.tr(
                    "Disc {number} is ripped.\n\nPut the next disc of the set in the drive and close the "
                    "tray, then continue -- or stop here and record what has been ripped so far."
                ).format(number=self._disc),
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Ok,
            )
            == QMessageBox.StandardButton.Ok
        )

    def _read_next_disc(self) -> None:
        """Reads and identifies the next disc of the set.

        The album, artist and year are put back afterwards: MusicBrainz
        routinely names the second disc of a set as its own release, and
        this is one album being ripped, not two. The *titles* are disc 2's
        own -- those are the ones being asked for."""
        self._disc += 1
        album, artist, year = (
            self.album_edit.text(),
            self.artist_edit.text(),
            self.year_spin.value(),
        )
        self._read_disc()
        self.album_edit.setText(album)
        self.artist_edit.setText(artist)
        self.year_spin.setValue(year)
        self.status_label.setText(
            self.tr("Disc {number} of the set. Check its titles, then rip it.").format(number=self._disc)
        )

    # --- shutdown ---------------------------------------------------------

    def request_stop(self) -> None:
        """What MainWindow's own Stop button calls."""
        self.reject()

    def request_show(self) -> None:
        """What the progress bar's "Show recording window" button calls."""
        self.show_requested.emit()

    def _on_hide_clicked(self) -> None:
        hide_for_background(self)

    def reject(self) -> None:
        worker = self._worker
        if worker is not None and worker.isRunning():
            self._closing = True
            worker.cancel()
            self.status_label.setText(self.tr("Stopping..."))
            self.close_btn.setEnabled(False)
            return
        super().reject()

    def closeEvent(self, event) -> None:
        if self._worker is not None and self._worker.isRunning():
            self.reject()
            event.ignore()
            return
        super().closeEvent(event)
