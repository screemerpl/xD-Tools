"""Recording > "Burn Audio CD..." -- the disc, before it is written.

Structurally this is `RecordDialog`'s sibling: the same editable
album/artist/year, the same clickable cover, the same editable Title and
Artist columns, and the same rule that what is on screen when the button is
pressed is what gets written. The difference is what it is writing to. A
MiniDisc recording plays an album in real time and titles it afterwards
over infrared; a CD-R is decoded first and then written in one pass, with
the titles going on as CD-Text in the same pass.

Two things are shaped by the disc being one-shot:

**Everything that can be known is shown before the button.** The plan lists
every track that is not Red Book, every track too short for the standard,
and whether the album fits -- next to the tracks they are about, all at
once. A CD-R cannot be edited afterwards the way a MiniDisc's TOC can, so
"find out on playback" is not an acceptable place to learn any of this.

**Stopping mid-burn is offered, but not quietly.** Cancelling during the
decode stage costs nothing (a scratch folder). Cancelling while the laser
is writing leaves a disc that is neither blank nor finished and cannot be
rewritten, so that one asks first -- the same reasoning behind the erase
dialog asking what the deck's display says rather than assuming.

"Simulate" is a real cdrecord dry run (-dummy): the whole sequence with the
laser off. It is the only way to rehearse a burn without spending a disc, so
it is offered directly rather than buried.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mdtools import app_settings, cdburn, cdrip, embedded_cover, mixtape_cover
from mdtools.panels.cover_preview import CoverPreview, fetch_into
from mdtools.project import ProjectMetadata, Track

# Decoding is a small fraction of a burn in wall-clock terms, but it is the
# part that happens before anything irreversible, so it gets a visible share
# of the bar rather than none.
_DECODE_SHARE = 0.15
_PROGRESS_EPSILON = 0.002


def _mmss(seconds: float) -> str:
    total = int(round(seconds))
    return f"{total // 60}:{total % 60:02d}"


class _BurnWorker(QThread):
    """Decodes the album, writes its CD-Text, and hands both to cdrecord.

    On its own thread for the same reason the rip worker is: cdrecord holds
    the drive for minutes at a time, and nothing about that should be
    happening on the thread painting the window.
    """

    stage = Signal(str)  # "decode" | "burn"
    progress = Signal(float)
    failed = Signal(str)
    cancelled = Signal()
    succeeded = Signal()

    def __init__(
        self,
        plan: cdburn.BurnPlan,
        device: str,
        work_dir: Path,
        *,
        speed: int,
        simulate: bool,
        eject: bool,
        parent=None,
    ):
        super().__init__(parent)
        self._plan = plan
        self._device = device
        self._work_dir = work_dir
        self._speed = speed
        self._simulate = simulate
        self._eject = eject
        self._cancelled = False
        self._last_emitted = -1.0

    def cancel(self) -> None:
        """Takes effect between decoded tracks, or within a poll interval
        once cdrecord is running. What that *means* differs sharply between
        those two stages -- see the dialog, which is where the user is
        warned."""
        self._cancelled = True

    def run(self) -> None:
        try:
            self.stage.emit("decode")
            names = cdburn.prepare_wavs(
                self._plan,
                self._work_dir,
                on_progress=lambda fraction: self._emit(fraction * _DECODE_SHARE),
                should_cancel=lambda: self._cancelled,
            )
            # The CD-Text, one file per track, beside the audio it belongs
            # to -- which is how cdrecord finds it.
            cdburn.write_inf_files(self._plan, self._work_dir)

            self.stage.emit("burn")
            cdburn.burn(
                self._device,
                self._work_dir,
                names,
                speed=self._speed,
                simulate=self._simulate,
                eject=self._eject,
                megabytes=cdburn.track_megabytes(self._plan),
                on_progress=lambda fraction: self._emit(
                    _DECODE_SHARE + fraction * (1.0 - _DECODE_SHARE)
                ),
                should_cancel=lambda: self._cancelled,
            )
        except cdburn.BurnCancelled:
            self.cancelled.emit()
            return
        except cdburn.BurnError as exc:
            self.failed.emit(str(exc))
            return
        self.succeeded.emit()

    def _emit(self, fraction: float) -> None:
        fraction = min(1.0, max(0.0, fraction))
        if fraction - self._last_emitted < _PROGRESS_EPSILON and fraction < 1.0:
            return
        self._last_emitted = fraction
        self.progress.emit(fraction)


class BurnDialog(QDialog):
    """`sources` is (path, title, artist) per track, in disc order.

    Whoever assembled that list -- a folder, a foobar2000 playlist -- is not
    this dialog's business, exactly as `RecordDialog` does not know whether
    its playlist came from a CD, a folder or the user.
    """

    def __init__(
        self,
        sources,
        *,
        album: str = "",
        artist: str = "",
        year: int | None = None,
        cover_art: bytes | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Burn Audio CD"))
        self.resize(760, 640)

        self._sources = [(Path(path), title, track_artist) for path, title, track_artist in sources]
        self._worker: _BurnWorker | None = None
        self._burning = False
        self.result_metadata: ProjectMetadata | None = None

        layout = QVBoxLayout(self)
        layout.addWidget(self._build_album_row(album, artist, year, cover_art))
        layout.addWidget(self._build_tracks_table())
        layout.addWidget(self._build_disc_box())

        # Two labels, not one: a missing cdrecord must not hide what the plan
        # says about the album -- fixing a hi-res track and installing a
        # tool are separate jobs, and the user may well do them in either
        # order.
        self.tools_label = QLabel()
        self.tools_label.setWordWrap(True)
        self.tools_label.setVisible(False)
        layout.addWidget(self.tools_label)

        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        self.stage_label = QLabel()
        layout.addWidget(self.stage_label)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1000)
        layout.addWidget(self.progress_bar)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.burn_button = QPushButton(self.tr("Burn"))
        self.burn_button.setDefault(True)
        self.burn_button.clicked.connect(self._start)
        buttons.addWidget(self.burn_button)
        self.close_button = QPushButton(self.tr("Close"))
        self.close_button.clicked.connect(self.reject)
        buttons.addWidget(self.close_button)
        layout.addLayout(buttons)

        self._refresh_drives()
        self._check_tools()
        self._rebuild_plan()
        self._ensure_cover()

    # -- construction ----------------------------------------------------

    def _build_album_row(self, album: str, artist: str, year: int | None, cover_art: bytes | None) -> QWidget:
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)

        form = QFormLayout()
        self.artist_edit = QLineEdit(artist)
        form.addRow(self.tr("Artist"), self.artist_edit)
        self.album_edit = QLineEdit(album)
        form.addRow(self.tr("Album"), self.album_edit)
        self.year_edit = QLineEdit("" if year is None else str(year))
        form.addRow(self.tr("Year"), self.year_edit)
        row_layout.addLayout(form, 1)

        # Clickable, like everywhere else a cover appears: every automatic
        # source guesses, and this one is going onto a printed label.
        self.cover_preview = CoverPreview()
        self.cover_preview.set_cover(cover_art)
        row_layout.addWidget(self.cover_preview)
        return row

    def _build_tracks_table(self) -> QWidget:
        self.table = QTableWidget(len(self._sources), 4)
        self.table.setHorizontalHeaderLabels(
            [self.tr("Title"), self.tr("Artist"), self.tr("Length"), self.tr("Status")]
        )
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

        for row, (path, title, artist) in enumerate(self._sources):
            self.table.setItem(row, 0, QTableWidgetItem(title or path.stem))
            self.table.setItem(row, 1, QTableWidgetItem(artist))
            for column in (2, 3):
                item = QTableWidgetItem("")
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, column, item)
        return self.table

    def _build_disc_box(self) -> QWidget:
        box = QGroupBox(self.tr("Disc"))
        form = QFormLayout(box)

        drive_row = QWidget()
        drive_layout = QHBoxLayout(drive_row)
        drive_layout.setContentsMargins(0, 0, 0, 0)
        self.drive_combo = QComboBox()
        drive_layout.addWidget(self.drive_combo, 1)
        self.refresh_button = QPushButton(self.tr("Refresh"))
        self.refresh_button.clicked.connect(self._refresh_drives)
        drive_layout.addWidget(self.refresh_button)
        form.addRow(self.tr("Burner"), drive_row)

        self.speed_spin = QSpinBox()
        self.speed_spin.setRange(1, 48)
        self.speed_spin.setValue(cdburn.DEFAULT_SPEED)
        form.addRow(self.tr("Speed"), self.speed_spin)

        self.simulate_check = QCheckBox(self.tr("Simulate only (test run, nothing is written)"))
        form.addRow("", self.simulate_check)

        self.eject_check = QCheckBox(self.tr("Eject when finished"))
        self.eject_check.setChecked(True)
        form.addRow("", self.eject_check)
        return box

    def _ensure_cover(self) -> None:
        """Finds the artwork now, while the album's name can still be
        corrected.

        The same order RecordDialog uses, and for the same reasons: a search
        first, because iTunes returns a clean 600x600 that a printed label
        wants, then whatever the files themselves carry, which is certainly
        the right record but often a small scan. A compilation is never
        searched for -- "Various Artists" returns some unrelated sleeve --
        and gets one drawn from its own track list instead.

        This was missing entirely at first: the burn flow went straight from
        a folder to the dialog, so the cover box sat empty even for files
        that had one, and the album reached the label with no artwork.
        """
        if self.cover_preview.data:
            return
        metadata = self.metadata()
        if metadata.is_compilation():
            self.cover_preview.set_cover(mixtape_cover.render_cover(metadata))
            return

        chosen = fetch_into(
            self.cover_preview, self.artist_edit.text(), self.album_edit.text(), len(self._sources)
        )
        if chosen is not None and not self.year_edit.text().strip() and chosen.year:
            self.year_edit.setText(str(chosen.year))
        if not self.cover_preview.data:
            self.cover_preview.set_cover(embedded_cover.cover_from_files(path for path, _t, _a in self._sources))

    # -- drives and tools -------------------------------------------------

    def _refresh_drives(self) -> None:
        self.drive_combo.clear()
        try:
            burners = cdburn.list_burners()
        except cdburn.BurnError:
            burners = []
        for burner in burners:
            self.drive_combo.addItem(burner.display(), burner.device)
        if not burners:
            self.drive_combo.addItem(self.tr("(no burner found)"), "")

    def _check_tools(self) -> None:
        missing = cdburn.missing_tools()
        self.tools_label.setVisible(bool(missing))
        if missing:
            self.tools_label.setText(
                self.tr("Missing tools: {tools}. Burning is unavailable until they are installed.").format(
                    tools=", ".join(missing)
                )
            )

    def selected_device(self) -> str:
        return self.drive_combo.currentData() or ""

    # -- the plan ---------------------------------------------------------

    def track_sources(self):
        """The tracks as they are on screen right now.

        Read from the widgets rather than from what was passed in, for the
        same reason RecordDialog._capture_metadata reads its own: an album
        name corrected here has to be the one that gets written, not the one
        that happened to be guessed.
        """
        sources = []
        for row, (path, _title, _artist) in enumerate(self._sources):
            title = self.table.item(row, 0).text().strip() if self.table.item(row, 0) else ""
            artist = self.table.item(row, 1).text().strip() if self.table.item(row, 1) else ""
            sources.append((path, title or path.stem, artist))
        return sources

    def build_plan(self) -> cdburn.BurnPlan:
        return cdburn.build_burn_plan(
            self.track_sources(),
            album=self.album_edit.text().strip(),
            artist=self.artist_edit.text().strip(),
        )

    def _rebuild_plan(self) -> None:
        self.plan = self.build_plan()
        self._show_plan(self.plan)

    def _show_plan(self, plan: cdburn.BurnPlan) -> None:
        for row, track in enumerate(plan.tracks):
            if row >= self.table.rowCount():
                break
            self.table.item(row, 2).setText(_mmss(track.seconds) if track.properties else "-")
            self.table.item(row, 3).setText(self._status_for(plan, row + 1))

        lines = [
            # Phrased to avoid a bare "{count} tracks": Polish alone has
            # three plural forms, and a label is not worth a plural rule.
            self.tr("Tracks: {count} -- {length} of an available {capacity}").format(
                count=len(plan.tracks),
                length=_mmss(plan.total_seconds),
                capacity=_mmss(plan.capacity_sectors / cdburn.SECTORS_PER_SECOND),
            )
        ]
        for problem in plan.problems_for(0):
            lines.append(self._describe(problem))

        dropped = self._cd_text_losses(plan)
        if dropped:
            lines.append(
                self.tr("CD-Text cannot carry these characters and they will be left out: {characters}").format(
                    characters=" ".join(dropped)
                )
            )

        self.summary_label.setText("\n".join(lines))
        self.burn_button.setEnabled(plan.can_burn and not cdburn.missing_tools())

    def _status_for(self, plan: cdburn.BurnPlan, track_number: int) -> str:
        entries = plan.problems_for(track_number) + plan.notes_for(track_number)
        if not entries:
            return self.tr("OK")
        return "; ".join(self._describe(entry) for entry in entries)

    def _describe(self, problem: cdburn.Problem) -> str:
        """Turns a plan's problem code into a sentence.

        The codes live in cdburn.py precisely so this translation happens
        here, where there is a tr() to do it with."""
        if problem.code == cdburn.NOT_RED_BOOK:
            return self.tr("{format} -- a CD needs 44100 Hz / 16-bit / stereo").format(format=problem.detail)
        if problem.code == cdburn.RESAMPLED:
            return self.tr("{format} -- will be converted to 44100 Hz / 16-bit").format(format=problem.detail)
        if problem.code == cdburn.TOO_SHORT:
            return self.tr("shorter than the 4 seconds a CD track must be ({length})").format(
                length=problem.detail
            )
        if problem.code == cdburn.UNREADABLE:
            return self.tr("could not be read")
        if problem.code == cdburn.TOO_MANY_TRACKS:
            return self.tr("A CD holds at most 99 tracks, and this is {count}.").format(count=problem.detail)
        if problem.code == cdburn.TOO_LONG_FOR_DISC:
            return self.tr("This is {over} longer than the disc holds.").format(over=problem.detail)
        if problem.code == cdburn.NO_TRACKS:
            return self.tr("There are no tracks to burn.")
        return problem.code

    def _cd_text_losses(self, plan: cdburn.BurnPlan) -> list[str]:
        """Every character CD-Text will drop, gathered once.

        Shown before the burn rather than after, the same promise the MDRem
        upload dialog makes about a MiniDisc title -- it is the same
        transliterator underneath."""
        dropped: list[str] = []
        for value in [plan.album, plan.artist] + [track.title for track in plan.tracks]:
            for character in cdburn.cd_text(value).dropped:
                if character not in dropped:
                    dropped.append(character)
        return dropped

    # -- burning ----------------------------------------------------------

    def metadata(self) -> ProjectMetadata:
        """What was burned, in the project's own terms -- so a label can be
        designed for the disc that was just written."""
        year_text = self.year_edit.text().strip()
        sources = self.track_sources()
        plan = self.plan if getattr(self, "plan", None) else self.build_plan()
        return ProjectMetadata(
            album=self.album_edit.text().strip(),
            artist=self.artist_edit.text().strip(),
            year=int(year_text) if year_text.isdigit() else None,
            tracks=[
                Track(
                    title=title,
                    time_seconds=int(plan.tracks[index].seconds) if index < len(plan.tracks) else None,
                    artist=artist,
                )
                for index, (_path, title, artist) in enumerate(sources)
            ],
            cover_art=self.cover_preview.data,  # a property, not a call
        )

    def _start(self) -> None:
        self._rebuild_plan()
        if not self.plan.can_burn:
            return
        device = self.selected_device()
        if not device:
            QMessageBox.warning(
                self,
                self.tr("Burn Audio CD"),
                self.tr("No burner was found. Check that the drive is connected and press Refresh."),
            )
            return

        simulate = self.simulate_check.isChecked()
        question = (
            self.tr("Run through the whole burn with the laser off? Nothing will be written to the disc.")
            if simulate
            else self.tr(
                "Write {count} tracks to the disc in the drive?\n\nA CD-R cannot be rewritten: once this "
                "starts, the disc is either finished or wasted."
            ).format(count=len(self.plan.tracks))
        )
        if (
            QMessageBox.question(
                self,
                self.tr("Burn Audio CD"),
                question,
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            != QMessageBox.StandardButton.Ok
        ):
            return

        work_dir = Path(app_settings.cd_rip_folder()) / "burn"
        try:
            cdrip.ensure_folder(work_dir)
        except cdrip.CdRipError as exc:
            QMessageBox.critical(self, self.tr("Burn Audio CD"), str(exc))
            return

        self._set_running(True)
        self._worker = _BurnWorker(
            self.plan,
            device,
            work_dir,
            speed=self.speed_spin.value(),
            simulate=simulate,
            eject=self.eject_check.isChecked(),
            parent=self,
        )
        self._worker.stage.connect(self._on_stage)
        self._worker.progress.connect(self._on_progress)
        self._worker.failed.connect(self._on_failed)
        self._worker.cancelled.connect(self._on_cancelled)
        self._worker.succeeded.connect(self._on_succeeded)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()

    def _set_running(self, running: bool) -> None:
        """Freezes everything that decides what goes on the disc.

        What is on screen when Burn is pressed is what gets written -- and
        unlike a MiniDisc, it cannot be corrected afterwards."""
        self._burning = running
        for widget in (
            self.table,
            self.album_edit,
            self.artist_edit,
            self.year_edit,
            self.cover_preview,
            self.drive_combo,
            self.refresh_button,
            self.speed_spin,
            self.simulate_check,
            self.eject_check,
            self.burn_button,
        ):
            widget.setEnabled(not running)

    def _on_stage(self, stage: str) -> None:
        self.stage_label.setText(
            self.tr("Preparing audio...") if stage == "decode" else self.tr("Writing the disc...")
        )

    def _on_progress(self, fraction: float) -> None:
        self.progress_bar.setValue(int(fraction * 1000))

    def _on_failed(self, message: str) -> None:
        QMessageBox.critical(self, self.tr("Burn Audio CD"), message)

    def _on_cancelled(self) -> None:
        self.stage_label.setText(self.tr("Stopped."))

    def _on_succeeded(self) -> None:
        self.result_metadata = self.metadata()
        if self.simulate_check.isChecked():
            QMessageBox.information(
                self,
                self.tr("Burn Audio CD"),
                self.tr("The test run finished without an error. Nothing was written to the disc."),
            )
        else:
            QMessageBox.information(
                self,
                self.tr("Burn Audio CD"),
                self.tr("The disc is written."),
            )
        self.accept()

    def _on_worker_finished(self) -> None:
        self._worker = None
        self._set_running(False)

    def reject(self) -> None:
        """Stopping mid-burn is a decision with a physical cost, so it is
        put to the user in those words.

        Never waits on the worker here -- that is what froze the MDRem
        upload dialog once already; _on_worker_finished is the single place
        anything is torn down."""
        worker = self._worker
        if worker is None:
            super().reject()
            return

        answer = QMessageBox.question(
            self,
            self.tr("Burn Audio CD"),
            self.tr(
                "Stop now? If the disc is already being written it will be left unfinished, and a CD-R "
                "cannot be reused."
            ),
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Ok:
            return
        worker.cancel()
        self.stage_label.setText(self.tr("Stopping..."))

    def closeEvent(self, event) -> None:
        """The window's X goes through the same question as Close, so the
        dialog can never be torn down while cdrecord still holds the drive."""
        if self._worker is not None:
            event.ignore()
            self.reject()
            return
        super().closeEvent(event)
