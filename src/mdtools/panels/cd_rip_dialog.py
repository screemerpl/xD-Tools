"""Recording > "Record CD to MiniDisc..." -- the step that turns a compact
disc into something the existing recording flow can play.

The sequence:

  1. pick a drive and read the disc's table of contents
  2. identify it (MusicBrainz, by the TOC itself -- a CD carries no text)
  3. extract every track to a tagged FLAC in the rip folder
  4. empty foobar2000's playlist and put those files in it, in disc order
  5. hand off to RecordDialog, which is unchanged and unaware a CD was
     ever involved

Step 5 is the point of steps 1-4. Everything that makes recording work --
arming the deck, the lead-in, a track mark at every boundary, titling
afterwards -- already exists and is driven by whatever foobar2000 happens to
have in its playlist. So this feature's job is not to record anything; it is
to make the playlist say the right thing, and then get out of the way. Same
hand-off shape as RecordDialog's own to MDRemUploadDialog.

Why rip at all, rather than let foobar play the CD directly: the disc would
then be read in real time, during the recording, with nothing to fall back
on. A drive that stumbles on a scratch at minute 31 would put that stumble
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

from mdtools import app_settings, cdrip, foobar, mixtape_cover, musicbrainz
from mdtools.panels.cover_preview import CoverPreview, fetch_into
from mdtools.project import ProjectMetadata, Track, apply_compilation_naming

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


def _mmss(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


def _same_name(left: str, right: str) -> bool:
    return left.strip().casefold() == right.strip().casefold()


class _RipWorker(QThread):
    """Extracts, encodes, and finally loads the result into foobar2000.

    The playlist load is in here rather than back on the GUI thread because
    of what it has to wait for: foobar accepts a command line immediately
    but adds the files asynchronously, so somebody has to poll until the
    count settles (foobar.wait_for_item_count), and that somebody must not
    be the thread painting the window."""

    track_started = Signal(int)
    progress = Signal(float)
    stage = Signal(str)
    failed = Signal(str)
    cancelled = Signal()
    succeeded = Signal()

    def __init__(self, device: str, plan: cdrip.RipPlan, client: foobar.FoobarClient, exe: str, parent=None):
        super().__init__(parent)
        self._device = device
        self._plan = plan
        self._client = client
        self._exe = exe
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
            self.stage.emit("playlist")
            foobar.replace_current_playlist(self._client, self._exe, self._plan.flac_paths)
        except cdrip.CdRipCancelled:
            self.cancelled.emit()
            return
        except (cdrip.CdRipError, foobar.FoobarError) as exc:
            self.failed.emit(str(exc))
            return
        self.succeeded.emit()

    def _on_track_progress(self, task: cdrip.RipTask, within_track: float) -> None:
        self._emit_progress((self._done_sectors + within_track * task.sectors) / self._total_sectors)

    def _emit_progress(self, fraction: float) -> None:
        fraction = min(1.0, max(0.0, fraction))
        if fraction - self._last_emitted < _PROGRESS_EPSILON and fraction < 1.0:
            return
        self._last_emitted = fraction
        self.progress.emit(fraction)


class CdRipDialog(QDialog):
    def __init__(self, base_url: str = foobar.DEFAULT_BASE_URL, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Record CD to MiniDisc"))
        self.resize(560, 560)
        self._client = foobar.FoobarClient(base_url)
        self._toc: cdrip.DiscToc | None = None
        self._releases: list[musicbrainz.DiscRelease] = []
        self._worker: _RipWorker | None = None
        self._closing = False
        # Read by MainWindow after exec(): where the tracks were written, so
        # a message can name it.
        self.result_folder: Path | None = None
        # And what the disc turned out to be. The titles in it are the same
        # ones the playlist carries -- they were written into the files as
        # tags, so there is no second source of truth to disagree with. What
        # it adds is the artwork, which a FLAC file's tags do not carry here
        # and which the user may have corrected by clicking the preview.
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
                "what ends up on the MiniDisc. Fill the artist column in when the disc is a compilation: "
                "MDTools then names it accordingly and draws it a cover of its own."
            )
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

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
                "These bundled tools are missing, so a CD cannot be read: {tools}. Reinstall MDTools, or put "
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

    def _warn_about_length(self, total: float) -> None:
        if total <= DISC_SP_SECONDS:
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
        folder = root / cdrip.rip_folder_name(self.artist_edit.text(), self.album_edit.text())
        year = self.year_spin.value() or None
        return cdrip.build_rip_plan(
            self._toc,
            folder,
            self.track_titles(),
            artist=self.artist_edit.text(),
            album=self.album_edit.text(),
            year=year,
            track_artists=self.track_artists(),
        )

    def build_metadata(self) -> ProjectMetadata:
        """The disc as project metadata, from the fields and the tree.

        Handed to RecordDialog so it opens on the album this is, artwork
        included. The titles in it are the same ones the ripped files are
        tagged with, so it is not a second source of truth competing with
        the playlist -- it is the playlist's own contents plus a cover,
        which a tag cannot carry to foobar and back."""
        tracks = []
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
        exe = self._resolve_foobar_exe()
        if exe is None:
            return
        if not self._foobar_reachable():
            return

        plan = self.build_plan()
        self.result_metadata = self.build_metadata()
        # Previous rips go now, not at the end of this one: the files stay
        # in foobar's playlist for as long as the user might replay them.
        cdrip.clean_stale_rip_folders(plan.folder.parent, keep=plan.folder)
        try:
            cdrip.ensure_folder(plan.folder)
        except cdrip.CdRipError as exc:
            QMessageBox.warning(
                self,
                self.tr("Record CD to MiniDisc"),
                self.tr(
                    "The rip folder could not be created: {error}\n\nChoose a different one in "
                    "Window > Settings..."
                ).format(error=exc),
            )
            return
        self.result_folder = plan.folder

        self._set_running(True)
        self._succeeded = False
        self._plan = plan
        self.progress.setValue(0)
        self.progress.setVisible(True)
        self.status_label.setText(self.tr("Starting..."))

        self._worker = _RipWorker(self.selected_device(), plan, self._client, exe, self)
        self._worker.track_started.connect(self._on_track_started)
        self._worker.progress.connect(self._on_progress)
        self._worker.stage.connect(self._on_stage)
        self._worker.failed.connect(self._on_failed)
        self._worker.cancelled.connect(self._on_cancelled)
        self._worker.succeeded.connect(self._on_succeeded)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()

    def _resolve_foobar_exe(self) -> str | None:
        """Checked before the rip, not after: finding out that the files
        cannot be handed over is worth minutes if it happens first and
        nothing if it happens last."""
        exe = app_settings.foobar_exe() or (foobar.find_foobar_exe() or "")
        if exe and Path(exe).is_file():
            if not app_settings.foobar_exe():
                app_settings.set_foobar_exe(exe)
            return exe
        QMessageBox.warning(
            self,
            self.tr("Record CD to MiniDisc"),
            self.tr(
                "foobar2000 could not be found. The ripped tracks are loaded into it through its own program "
                "file, so its location has to be set in Window > Settings..."
            ),
        )
        return None

    def _foobar_reachable(self) -> bool:
        try:
            self._client.current_playlist()
        except foobar.FoobarError as exc:
            QMessageBox.warning(
                self,
                self.tr("Record CD to MiniDisc"),
                self.tr(
                    "Could not reach foobar2000: {error}\n\nIt must be running with the Beefweb Remote Control "
                    "component (foo_beefweb) enabled."
                ).format(error=exc),
            )
            return False
        return True

    def _set_running(self, running: bool) -> None:
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
        elif stage == "playlist":
            self.status_label.setText(self.tr("Loading the tracks into foobar2000..."))

    def _on_progress(self, fraction: float) -> None:
        self.progress.setValue(int(_PROGRESS_SCALE * fraction))

    def _on_failed(self, message: str) -> None:
        self.progress.setVisible(False)
        self.status_label.setText(self.tr("Ripping failed: {error}").format(error=message))

    def _on_cancelled(self) -> None:
        self.progress.setVisible(False)
        self.status_label.setText(self.tr("Stopped. Nothing was recorded."))

    def _on_succeeded(self) -> None:
        self.progress.setValue(_PROGRESS_SCALE)
        self.status_label.setText(self.tr("The disc is ripped and loaded into foobar2000."))
        self._succeeded = True

    def _on_worker_finished(self) -> None:
        """The single place a run ends, whatever ended it -- the same shape
        MDRemUploadDialog uses, and for the same reason: it lets Stop return
        immediately instead of blocking the GUI thread on wait()."""
        self._worker = None
        self._set_running(False)
        if getattr(self, "_succeeded", False):
            # Accepting is the hand-off: MainWindow opens RecordDialog next.
            self.accept()
            return
        if self._closing:
            super().reject()

    # --- shutdown ---------------------------------------------------------

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
