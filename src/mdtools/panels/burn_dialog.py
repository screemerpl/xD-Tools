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

from mdtools import (
    app_settings,
    audio_folder,
    cdburn,
    cdrip,
    decode,
    embedded_cover,
    mixtape_cover,
    multidisc,
)
from mdtools.panels.cover_preview import CoverPreview, fetch_into
from mdtools.panels.hideable_dialog import hide_for_background, surface
from mdtools.panels.preview_player import PreviewPlayerBar
from mdtools.project import ProjectMetadata, Track

# The track table's columns. Named because a Disc column was put in front
# of the other four, so every read of a row moved along by one.
COL_DISC, COL_TITLE, COL_ARTIST, COL_LENGTH, COL_STATUS = range(5)

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
    # Mirrored by MainWindow's own bottom-of-window progress bar (#27) --
    # see app_window.py's _drive_recording_bar()/_release_recording_bar().
    # No track_progress_changed: cdrecord writes the whole disc as one
    # continuous DAO stream with no natural per-track breakdown to surface.
    running_changed = Signal(bool)
    overall_progress_changed = Signal(float, str)
    visibility_changed = Signal(bool)
    # Asked for by the progress bar's "Show recording window" button --
    # see panels/hideable_dialog.py, which is what actually re-shows this.
    show_requested = Signal()


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

        # The album's own order, taken from the files rather than from
        # however they were handed over. A two-disc set downloaded into one
        # folder arrives interleaved -- both discs number their tracks from
        # one -- and a disc break worked out from *that* falls on nearly
        # every track: a 34-track album was offered as 26 discs before this
        # was here. The recording dialog sorts its playlist for the same
        # reason and by the same rule.
        given = [(Path(path), title, track_artist) for path, title, track_artist in sources]
        order = audio_folder.disc_and_track_order([path for path, _t, _a in given])
        self._sources = [given[index] for index in order]
        self._worker: _BurnWorker | None = None
        self._burning = False
        # The last fraction _on_progress reported -- re-emitted from
        # _on_stage too, since a decode->burn transition changes the status
        # text without necessarily coming with a fresh progress tick.
        self._last_fraction = 0.0
        # Set by the Hide button, read by exec_hideable() -- see
        # panels/hideable_dialog.py for why a hide has to be told apart
        # from a cancel at all.
        self.hidden_for_background = False
        # One plan per disc, and which of them is on the drive now. A list
        # of one for an ordinary album, so the single-disc path is the same
        # code rather than a special case.
        self._plans: list[cdburn.BurnPlan] = []
        self._disc = 0
        self._advance_when_finished = False
        # None means "wherever the files or the arithmetic put them"; a list
        # means the user has placed the breaks by hand.
        self._manual_breaks: list[int] | None = None
        self.result_metadata: ProjectMetadata | None = None

        layout = QVBoxLayout(self)
        layout.addWidget(self._build_album_row(album, artist, year, cover_art))
        layout.addWidget(self._build_table_row())
        self.preview_bar = PreviewPlayerBar()
        self.preview_bar.prev_requested.connect(lambda: self._step_preview(-1))
        self.preview_bar.next_requested.connect(lambda: self._step_preview(1))
        # Locked for as long as real work is in progress -- connected to
        # this dialog's own running_changed rather than toggled by hand at
        # each start/finish/fail site, so it cannot drift out of step with
        # them. See PreviewPlayerBar.set_locked().
        self.running_changed.connect(self.preview_bar.set_locked)
        layout.addWidget(self.preview_bar)
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
        self.hide_button = QPushButton(self.tr("Hide"))
        self.hide_button.setToolTip(
            self.tr("Hide this window and keep burning in the background -- use \"Show recording "
                    "window\" in the bar at the bottom of the main window to bring it back.")
        )
        self.hide_button.clicked.connect(self._on_hide_clicked)
        buttons.addWidget(self.hide_button)
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
        self.table = QTableWidget(len(self._sources), 5)
        self.table.setHorizontalHeaderLabels(
            [self.tr("Disc"), self.tr("Title"), self.tr("Artist"), self.tr("Length"), self.tr("Status")]
        )
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(COL_TITLE, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(COL_ARTIST, QHeaderView.ResizeMode.Stretch)
        # Nothing to say until there is more than one disc, exactly as in
        # the recording dialog's own table.
        self.table.setColumnHidden(COL_DISC, True)

        for row, (path, title, artist) in enumerate(self._sources):
            self.table.setItem(row, COL_TITLE, QTableWidgetItem(title or path.stem))
            self.table.setItem(row, COL_ARTIST, QTableWidgetItem(artist))
            for column in (COL_DISC, COL_LENGTH, COL_STATUS):
                item = QTableWidgetItem("")
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, column, item)
        return self.table

    def _build_table_row(self) -> QWidget:
        """The table, plus the same four buttons the recording dialog has.

        Reordering and placing the disc breaks by hand are the same job
        whichever machine the album ends up on, so they are the same
        controls in the same place -- reported directly, as the burn dialog
        having none of them."""
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.addWidget(self._build_tracks_table(), 1)

        self.up_button = QPushButton(self.tr("Move Up"))
        self.up_button.clicked.connect(lambda: self._move_selected(-1))
        self.down_button = QPushButton(self.tr("Move Down"))
        self.down_button.clicked.connect(lambda: self._move_selected(1))
        for button in (self.up_button, self.down_button):
            button.setToolTip(self.tr("Changes the order the tracks are written to the disc in."))
        self.split_button = QPushButton(self.tr("Start Disc Here"))
        self.split_button.clicked.connect(self._toggle_split)
        self.split_button.setToolTip(
            self.tr(
                "Makes the selected track the first one on a new disc, instead of wherever the split was "
                "worked out to go."
            )
        )
        self.auto_split_button = QPushButton(self.tr("Split Automatically"))
        self.auto_split_button.clicked.connect(self._auto_split)
        self.auto_split_button.setToolTip(
            self.tr("Throws away the splits placed by hand and works them out again.")
        )

        side = QVBoxLayout()
        side.addWidget(self.up_button)
        side.addWidget(self.down_button)
        side.addSpacing(12)
        side.addWidget(self.split_button)
        side.addWidget(self.auto_split_button)
        side.addStretch(1)
        row_layout.addLayout(side)

        self.table.currentCellChanged.connect(lambda *_: self._refresh_split_button())
        self.table.currentCellChanged.connect(lambda *_: self._refresh_preview())
        return row

    # -- the order, and where the discs end --------------------------------

    def _selected_row(self) -> int:
        return self.table.currentRow()

    def _refresh_preview(self) -> None:
        row = self._selected_row()
        path = self._sources[row][0] if 0 <= row < len(self._sources) else None
        self.preview_bar.set_current(path, has_prev=row > 0, has_next=0 <= row < len(self._sources) - 1)

    def _step_preview(self, delta: int) -> None:
        row = self._selected_row() + delta
        if 0 <= row < self.table.rowCount():
            self.table.setCurrentCell(row, 0)

    def _current_breaks(self) -> list[int]:
        if self._manual_breaks is not None:
            return list(self._manual_breaks)
        starts = []
        index = 0
        for plan in self._plans[1:]:
            index += len(self._plans[self._plans.index(plan) - 1].tracks)
            starts.append(index)
        return starts

    def _refresh_split_button(self) -> None:
        row = self._selected_row()
        breaks = set(self._current_breaks())
        self.split_button.setEnabled(
            self.multi_check.isChecked() and row > 0 and not self._burning
        )
        self.auto_split_button.setEnabled(
            self.multi_check.isChecked() and self._manual_breaks is not None and not self._burning
        )
        self.split_button.setText(
            self.tr("Do Not Start Disc Here") if row in breaks else self.tr("Start Disc Here")
        )

    def _toggle_split(self) -> None:
        """Adds a disc break at the selected track, or takes one away.

        Starts from the breaks already on screen rather than from none, so
        moving a boundary on a three-disc album does not throw the other one
        away -- the same rule, and the same button text, as the recording
        dialog."""
        row = self._selected_row()
        if row <= 0:
            return
        breaks = set(self._current_breaks())
        breaks.discard(row) if row in breaks else breaks.add(row)
        self._manual_breaks = sorted(breaks)
        self._rebuild_plan()

    def _auto_split(self) -> None:
        self._manual_breaks = None
        self._rebuild_plan()

    def _move_selected(self, delta: int) -> None:
        """Moves the selected track one place up or down.

        Unlike the recording dialog, nothing outside this window has to be
        told: a burn hands the files to cdrecord itself, so the order in
        this table *is* the order on the disc."""
        row = self._selected_row()
        target = row + delta
        if row < 0 or not 0 <= target < len(self._sources):
            return
        self._sources[row], self._sources[target] = self._sources[target], self._sources[row]
        for column in (COL_TITLE, COL_ARTIST):
            here = self.table.item(row, column)
            there = self.table.item(target, column)
            here_text = here.text() if here else ""
            there_text = there.text() if there else ""
            if here:
                here.setText(there_text)
            if there:
                there.setText(here_text)
        self.table.setCurrentCell(target, COL_TITLE)
        self._rebuild_plan()

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

        self.multi_check = QCheckBox(self.tr("Burn across several discs"))
        self.multi_check.setToolTip(
            self.tr(
                "For an album longer than one disc. Each disc is written and ejected on its own, and you "
                "are asked to put the next blank one in."
            )
        )
        self.multi_check.toggled.connect(lambda _checked: self._rebuild_plan())
        form.addRow("", self.multi_check)

        self.disc_minutes_spin = QSpinBox()
        self.disc_minutes_spin.setRange(multidisc.MIN_DISC_MINUTES, 99)
        self.disc_minutes_spin.setValue(
            int(cdburn.DEFAULT_CAPACITY_SECTORS / cdburn.SECTORS_PER_SECOND / 60)
        )
        self.disc_minutes_spin.setSuffix(self.tr(" min"))
        self.disc_minutes_spin.setToolTip(
            self.tr("What one blank holds: 80 minutes on an ordinary CD-R, 74 on an older one.")
        )
        self.disc_minutes_spin.valueChanged.connect(lambda _value: self._rebuild_plan())
        form.addRow(self.tr("One disc holds"), self.disc_minutes_spin)
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
            title_item = self.table.item(row, COL_TITLE)
            artist_item = self.table.item(row, COL_ARTIST)
            title = title_item.text().strip() if title_item else ""
            artist = artist_item.text().strip() if artist_item else ""
            sources.append((path, title or path.stem, artist))
        return sources

    def capacity_sectors(self) -> int:
        return int(self.disc_minutes_spin.value() * 60 * cdburn.SECTORS_PER_SECOND)

    def build_plan(self) -> cdburn.BurnPlan:
        """The whole album as one disc -- what a single-disc burn writes,
        and the measuring stick the split below is worked out from."""
        return cdburn.build_burn_plan(
            self.track_sources(),
            album=self.album_edit.text().strip(),
            artist=self.artist_edit.text().strip(),
            capacity_sectors=self.capacity_sectors(),
        )

    def build_disc_plans(self) -> list[cdburn.BurnPlan]:
        """One plan per disc -- a list of one for an ordinary album.

        The files are measured once and those durations reused for every
        per-disc plan (`analyze` is memoised across the lot), so splitting
        costs no extra reads.

        Where the split falls comes from the files themselves when they say
        so: a two-disc rip carries DISCNUMBER, and honouring it beats
        balancing by running time, which would put the break wherever the
        arithmetic preferred. Only when they say nothing is the time-based
        split used.
        """
        sources = self.track_sources()
        measured: dict[Path, object] = {}

        def analyze(path):
            path = Path(path)
            if path not in measured:
                measured[path] = decode.analyze(path)
            return measured[path]

        capacity = self.capacity_sectors()
        album = self.album_edit.text().strip()
        artist = self.artist_edit.text().strip()
        whole = cdburn.build_burn_plan(
            sources, album=album, artist=artist, capacity_sectors=capacity, analyze=analyze
        )
        if not self.multi_check.isChecked():
            return [whole]

        tracks = [
            Track(title=track.title, time_seconds=track.seconds, artist=track.artist)
            for track in whole.tracks
        ]
        declared = self._manual_breaks
        if declared is None:
            declared = audio_folder.disc_breaks([path for path, _title, _artist in sources])
        # The lead-in is part of what a disc holds, so the music has that
        # much less room -- the same arithmetic BurnPlan.total_sectors does.
        usable = (capacity - cdburn.LEAD_IN_SECTORS) / cdburn.SECTORS_PER_SECOND
        split = (
            multidisc.plan_from_breaks(tracks, declared, usable)
            if declared
            else multidisc.split_discs(tracks, usable)
        )
        if split.count <= 1:
            return [whole]

        return [
            cdburn.build_burn_plan(
                sources[disc.first_index : disc.last_index + 1],
                album=f"{album} [{disc.number}/{split.count}]".strip(),
                artist=artist,
                capacity_sectors=capacity,
                analyze=analyze,
            )
            for disc in split.discs
        ]

    def _rebuild_plan(self) -> None:
        self._plans = self.build_disc_plans()
        # Kept: "the plan" has always meant the disc about to be written,
        # and for an ordinary album nothing about this has changed.
        self.plan = self._plans[0]
        self._show_plans(self._plans)
        self._refresh_split_button()

    def _show_plans(self, plans: list[cdburn.BurnPlan]) -> None:
        several = len(plans) > 1
        self.table.setColumnHidden(COL_DISC, not several)
        row = 0
        for index, plan in enumerate(plans, start=1):
            for number, track in enumerate(plan.tracks, start=1):
                if row >= self.table.rowCount():
                    break
                self.table.item(row, COL_DISC).setText(str(index) if several else "")
                self.table.item(row, COL_LENGTH).setText(
                    _mmss(track.seconds) if track.properties else "-"
                )
                self.table.item(row, COL_STATUS).setText(self._status_for(plan, number))
                row += 1

        lines = []
        for index, plan in enumerate(plans, start=1):
            # Phrased to avoid a bare "{count} tracks": Polish alone has
            # three plural forms, and a label is not worth a plural rule.
            line = self.tr("Tracks: {count} -- {length} of an available {capacity}").format(
                count=len(plan.tracks),
                length=_mmss(plan.total_seconds),
                capacity=_mmss(plan.capacity_sectors / cdburn.SECTORS_PER_SECOND),
            )
            if several:
                line = self.tr("Disc {number}: {summary}").format(number=index, summary=line)
            lines.append(line)
            for problem in plan.problems_for(0):
                lines.append(self._describe(problem))

        dropped: list[str] = []
        for plan in plans:
            for character in self._cd_text_losses(plan):
                if character not in dropped:
                    dropped.append(character)
        if dropped:
            lines.append(
                self.tr(
                    "CD-Text cannot carry these characters and they will be left out: {characters}"
                ).format(characters=" ".join(dropped))
            )

        self.summary_label.setText(chr(10).join(lines))
        self.burn_button.setEnabled(
            all(plan.can_burn for plan in plans) and not cdburn.missing_tools()
        )

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
        # Every disc's tracks, end to end: the label describes the album,
        # which is all of it, exactly as the multi-disc recording flow hands
        # back the whole record rather than one disc of it.
        measured = [track for plan in self._plans for track in plan.tracks]
        if not measured:
            measured = self.build_plan().tracks
        return ProjectMetadata(
            album=self.album_edit.text().strip(),
            artist=self.artist_edit.text().strip(),
            year=int(year_text) if year_text.isdigit() else None,
            tracks=[
                Track(
                    title=title,
                    time_seconds=int(measured[index].seconds) if index < len(measured) else None,
                    artist=artist,
                )
                for index, (_path, title, artist) in enumerate(sources)
            ],
            cover_art=self.cover_preview.data,  # a property, not a call
        )

    def _start(self) -> None:
        self._rebuild_plan()
        if not all(plan.can_burn for plan in self._plans):
            return
        if not self.selected_device():
            QMessageBox.warning(
                self,
                self.tr("Burn Audio CD"),
                self.tr("No burner was found. Check that the drive is connected and press Refresh."),
            )
            return

        simulate = self.simulate_check.isChecked()
        if simulate:
            question = self.tr(
                "Run through the whole burn with the laser off? Nothing will be written to the disc."
            )
        elif len(self._plans) > 1:
            question = self.tr(
                "Write this album to {discs} discs, one after another?\n\nEach is written and ejected on "
                "its own and you will be asked for the next blank. A CD-R cannot be rewritten: once this "
                "starts, a disc is either finished or wasted."
            ).format(discs=len(self._plans))
        else:
            question = self.tr(
                "Write {count} tracks to the disc in the drive?\n\nA CD-R cannot be rewritten: once this "
                "starts, the disc is either finished or wasted."
            ).format(count=len(self.plan.tracks))
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

        self.preview_bar.stop()
        self._disc = 0
        self._burn_current_disc()

    def _burn_current_disc(self) -> None:
        """Starts one disc. Called once for an ordinary album, and once per
        disc for a long one."""
        plan = self._plans[self._disc]
        several = len(self._plans) > 1
        # A folder per disc: track numbering restarts on each, so one shared
        # folder would leave a longer previous disc's scratch WAVs sitting
        # beside a shorter one's.
        work_dir = Path(app_settings.cd_rip_folder()) / cdrip.BURN_SCRATCH_DIRNAME
        if several:
            work_dir = work_dir / f"disc{self._disc + 1}"
        try:
            cdrip.ensure_folder(work_dir)
        except cdrip.CdRipError as exc:
            QMessageBox.critical(self, self.tr("Burn Audio CD"), str(exc))
            return

        self._set_running(True)
        if several:
            self.stage_label.setText(
                self.tr("Disc {number} of {count}...").format(
                    number=self._disc + 1, count=len(self._plans)
                )
            )
        self._worker = _BurnWorker(
            plan,
            self.selected_device(),
            work_dir,
            speed=self.speed_spin.value(),
            simulate=self.simulate_check.isChecked(),
            # Every disc but the last has to come out for the next one to go
            # in, so the checkbox only governs the final one.
            eject=self.eject_check.isChecked() or self._disc + 1 < len(self._plans),
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
        self.running_changed.emit(running)
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
            self.multi_check,
            self.disc_minutes_spin,
            self.up_button,
            self.down_button,
            self.split_button,
            self.auto_split_button,
            self.burn_button,
        ):
            widget.setEnabled(not running)
        if not running:
            self._refresh_split_button()

    def _on_stage(self, stage: str) -> None:
        text = self.tr("Preparing audio...") if stage == "decode" else self.tr("Writing the disc...")
        self.stage_label.setText(text)
        self.overall_progress_changed.emit(self._last_fraction, text)

    def _on_progress(self, fraction: float) -> None:
        self._last_fraction = fraction
        self.progress_bar.setValue(int(fraction * 1000))
        self.overall_progress_changed.emit(fraction, self.stage_label.text())

    def _on_failed(self, message: str) -> None:
        surface(self)
        QMessageBox.critical(self, self.tr("Burn Audio CD"), message)

    def _on_cancelled(self) -> None:
        self.stage_label.setText(self.tr("Stopped."))

    def _on_succeeded(self) -> None:
        surface(self)
        self.result_metadata = self.metadata()
        if self._disc + 1 < len(self._plans):
            # Asked for from _on_worker_finished, not here: this thread is
            # still running, and starting the next disc now would have its
            # own worker cleared away the moment this one finishes.
            self._advance_when_finished = True
            return
        if self.simulate_check.isChecked():
            QMessageBox.information(
                self,
                self.tr("Burn Audio CD"),
                self.tr("The test run finished without an error. Nothing was written to the disc."),
            )
        elif len(self._plans) > 1:
            QMessageBox.information(
                self,
                self.tr("Burn Audio CD"),
                self.tr("All {count} discs are written.").format(count=len(self._plans)),
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
        if not self._advance_when_finished:
            return
        self._advance_when_finished = False
        if not self._ask_for_next_disc():
            self.stage_label.setText(
                self.tr("Stopped after disc {number}. The discs already written are finished.").format(
                    number=self._disc + 1
                )
            )
            return
        self._disc += 1
        self.progress_bar.setValue(0)
        self._burn_current_disc()

    def _ask_for_next_disc(self) -> bool:
        surface(self)
        return (
            QMessageBox.question(
                self,
                self.tr("Burn Audio CD"),
                self.tr(
                    "Disc {done} of {count} is written and ejected.\n\nPut the next blank disc in the "
                    "drive and close the tray, then continue with disc {next}."
                ).format(done=self._disc + 1, count=len(self._plans), next=self._disc + 2),
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Ok,
            )
            == QMessageBox.StandardButton.Ok
        )

    def reject(self) -> None:
        """Stopping mid-burn is a decision with a physical cost, so it is
        put to the user in those words.

        Never waits on the worker here -- that is what froze the MDRem
        upload dialog once already; _on_worker_finished is the single place
        anything is torn down."""
        self.preview_bar.stop()
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

    def request_stop(self) -> None:
        """What MainWindow's own Stop button calls -- reuses the same
        "Stop now?" confirmation reject() already asks, rather than a
        second, silent way to abandon a disc mid-write."""
        self.reject()

    def request_show(self) -> None:
        """What the progress bar's "Show recording window" button calls."""
        self.show_requested.emit()

    def _on_hide_clicked(self) -> None:
        hide_for_background(self)
