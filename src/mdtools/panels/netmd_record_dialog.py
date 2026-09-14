"""Recording > "Record to MiniDisc..." over NetMD -- the whole album,
sent to the deck as files over its own USB cable.

Structurally this is closer to `BurnDialog` than to the MDRem
`RecordDialog` it stands beside: nothing here plays in real time, so there
is no arming, no lead-in, no infrared track marks and no adapter port at
all. Each track is decoded to a Red Book WAV (`netmd.prepare_track_wavs()`,
the same conversion `cdburn.py` uses for a CD-R) and handed to netmdcli's
own `send` one file at a time -- SP as plain PCM, LP2/LP4 through
netmdcli's on-the-fly ATRAC3 encoder -- which is what makes a NetMD
recording, in any mode, a USB-only affair (see `netmd.py`'s own header for
why SP no longer needs a Toslink cable the way it does under MDRem).
Because `send` takes a track's title in the same command as its audio,
there is no second, separate titling pass here the way MDRem's flow
needs one -- a track lands on the disc already named.

The track table, cover art, disc splitting and reordering are the same UI
`RecordDialog`/`BurnDialog` already offer, read from the same
`tracks.PlaylistItem` list `RecordDialog` uses (not `BurnDialog`'s plain
triples) -- app_window.py hands this dialog the same `paths`/`metadata` it
already resolved for MDRem, so the two are interchangeable at the call
site with no extra shape of data to build.

**Several discs** are handled exactly as BurnDialog's own: one
`netmd.RecordPlan` per disc, each disc prepared and sent in turn, an
erase-free "Put the next blank disc in and continue" prompt in between.
Unlike MDRem's own multi-disc flow, nothing here needs a confirm-then-wait
between the last track and the titles -- the title already went out with
the track that carries it."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
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
)

from mdtools import app_settings, cdrip, embedded_cover, mixtape_cover, multidisc, netmd, tracks
from mdtools.panels.cover_preview import CoverPreview, fetch_into
from mdtools.panels.hideable_dialog import close_hides_while_busy, surface
from mdtools.panels.preview_player import PreviewPlayerBar
from mdtools.panels.progress_format import mmss as _mmss
from mdtools.project import ProjectMetadata, Track

# Decoding is a small fraction of a recording in wall-clock terms compared
# to the USB transfer itself, but it happens before anything irreversible,
# so it still gets a visible share of the bar rather than none -- the same
# split BurnDialog's own decode/burn stages use.
_PREPARE_SHARE = 0.2
_PROGRESS_EPSILON = 0.002

COL_DISC, COL_NUMBER, COL_TITLE, COL_ARTIST, COL_LENGTH = range(5)


class _NetMdRecordWorker(QThread):
    """Decodes one disc's tracks and sends them, in order, over USB.

    On its own thread for the same reason `_BurnWorker` is: a send can
    take a while (see `netmd.SEND_TIMEOUT_S`'s own note on why that is not
    tightly bounded), and nothing about moving a file to a deck should
    happen on the thread painting the window."""

    stage = Signal(str)  # "prepare" | "send"
    progress = Signal(float)
    track_started = Signal(int, int, str)  # index, total, title
    failed = Signal(str)
    cancelled = Signal()
    succeeded = Signal()

    def __init__(self, plan: netmd.RecordPlan, work_dir: Path, *, parent=None):
        super().__init__(parent)
        self._plan = plan
        self._work_dir = work_dir
        self._cancelled = False
        self._last_emitted = -1.0

    def cancel(self) -> None:
        """Takes effect between decoded tracks, or between sends. Once a
        send is actually under way it runs to completion or to its own
        timeout -- netmdcli is not told to stop mid-transfer."""
        self._cancelled = True

    def run(self) -> None:
        try:
            self.stage.emit("prepare")
            names = netmd.prepare_track_wavs(
                self._plan,
                self._work_dir,
                on_progress=lambda fraction: self._emit(fraction * _PREPARE_SHARE),
                should_cancel=lambda: self._cancelled,
            )

            if self._cancelled:
                raise netmd.NetMdCancelled()

            self.stage.emit("send")

            def on_progress(index: int, total: int, description: str) -> None:
                self.track_started.emit(index, total, description)
                self._emit(_PREPARE_SHARE + (index - 1) / total * (1.0 - _PREPARE_SHARE))

            netmd.send_tracks(self._plan, self._work_dir, names, on_progress=on_progress)
        except netmd.NetMdCancelled:
            self.cancelled.emit()
            return
        except netmd.NetMdError as exc:
            self.failed.emit(str(exc))
            return
        self._emit(1.0)
        self.succeeded.emit()

    def _emit(self, fraction: float) -> None:
        fraction = min(1.0, max(0.0, fraction))
        if fraction - self._last_emitted < _PROGRESS_EPSILON and fraction < 1.0:
            return
        self._last_emitted = fraction
        self.progress.emit(fraction)


class NetMdRecordDialog(QDialog):
    # Mirrored by MainWindow's own bottom-of-window progress bar (#27) --
    # see app_window.py's _drive_recording_bar()/_release_recording_bar().
    running_changed = Signal(bool)
    overall_progress_changed = Signal(float, str)
    track_progress_changed = Signal(float, str)
    visibility_changed = Signal(bool)
    show_requested = Signal()

    def __init__(
        self,
        paths: list[Path | str],
        parent=None,
        metadata: ProjectMetadata | None = None,
    ):
        """Same shape as `RecordDialog.__init__` (see its own docstring for
        `paths`/`metadata`) -- no `port`, since nothing here resolves an
        MDRem adapter at all."""
        super().__init__(parent)
        self.setWindowTitle(self.tr("Record to MiniDisc (NetMD)"))
        self.resize(560, 560)
        self._items: list[tracks.PlaylistItem] = tracks.playlist_items_from_paths(paths) if paths else []
        self._recording = False
        self._closing = False
        self._plan: multidisc.MultiDiscPlan | None = None
        self._disc = 0
        self._manual_breaks: list[int] | None = None
        self.result_metadata: ProjectMetadata | None = None
        self._given_metadata = metadata
        self._worker: _NetMdRecordWorker | None = None
        self._advance_when_finished = False
        self._last_fraction = 0.0
        self.hidden_for_background = False

        layout = QVBoxLayout(self)

        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

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
        self.tree.setHeaderLabels(
            [self.tr("Disc"), self.tr("#"), self.tr("Title"), self.tr("Artist"), self.tr("Length")]
        )
        self.tree.setRootIsDecorated(False)
        self.tree.setColumnHidden(COL_DISC, True)
        self.tree.currentItemChanged.connect(lambda *_: self._refresh_split_button())
        self.tree.currentItemChanged.connect(lambda *_: self._refresh_preview())

        self.up_btn = QPushButton(self.tr("Move Up"))
        self.up_btn.clicked.connect(lambda: self._move_selected(-1))
        self.down_btn = QPushButton(self.tr("Move Down"))
        self.down_btn.clicked.connect(lambda: self._move_selected(1))
        for button in (self.up_btn, self.down_btn):
            button.setToolTip(self.tr("Changes the order the album is recorded in."))
        self.split_btn = QPushButton(self.tr("Start Disc Here"))
        self.split_btn.clicked.connect(self._toggle_split)
        self.auto_split_btn = QPushButton(self.tr("Split Automatically"))
        self.auto_split_btn.clicked.connect(self._auto_split)
        self.auto_split_btn.setToolTip(
            self.tr("Throws away the splits placed by hand and works them out again from the running times.")
        )

        side = QVBoxLayout()
        side.addWidget(self.up_btn)
        side.addWidget(self.down_btn)
        side.addSpacing(12)
        side.addWidget(self.split_btn)
        side.addWidget(self.auto_split_btn)
        side.addStretch(1)

        table_row = QHBoxLayout()
        table_row.addWidget(self.tree, 1)
        table_row.addLayout(side)
        layout.addLayout(table_row)

        self.preview_bar = PreviewPlayerBar()
        self.preview_bar.prev_requested.connect(lambda: self._step_preview(-1))
        self.preview_bar.next_requested.connect(lambda: self._step_preview(1))
        self.running_changed.connect(self.preview_bar.set_locked)
        layout.addWidget(self.preview_bar)

        hint = QLabel(
            self.tr(
                "Everything above and in the Title column can be edited, and is what gets written onto the "
                "disc. Fill the Artist column in only on a compilation, where each track has its own."
            )
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.multi_check = QCheckBox(self.tr("Record across several discs"))
        self.multi_check.setToolTip(
            self.tr(
                "For an album longer than one disc. Each disc is prepared, sent and ejected on its own, "
                "and you are asked to load the next one."
            )
        )
        self.multi_check.toggled.connect(self._on_multi_toggled)
        self.disc_minutes_spin = QSpinBox()
        self.disc_minutes_spin.setRange(multidisc.MIN_DISC_MINUTES, multidisc.MAX_DISC_MINUTES)
        self.disc_minutes_spin.setValue(netmd.mode(app_settings.netmd_recording_mode()).minutes)
        self.disc_minutes_spin.setSuffix(self.tr(" min"))
        self.disc_minutes_spin.setToolTip(
            self.tr(
                "What one disc holds in the recording mode chosen in Settings. Fixed, not guessed -- "
                "unlike MDRem, NetMD is told which mode it is in rather than having to ask the deck to "
                "show it, so this is not something to second-guess here. Change it in Settings instead."
            )
        )
        # Read-only: the real send plan's own capacity check
        # (build_record_plan()) is always measured against the *actual*
        # mode in Settings, never against this spin box -- letting the two
        # disagree would let the split shown here promise something the
        # send itself then refuses.
        self.disc_minutes_spin.setEnabled(False)
        self.disc_minutes_label = QLabel(self.tr("One disc holds"))

        multi_row = QHBoxLayout()
        multi_row.addWidget(self.multi_check)
        multi_row.addStretch(1)
        multi_row.addWidget(self.disc_minutes_label)
        multi_row.addWidget(self.disc_minutes_spin)
        layout.addLayout(multi_row)

        self.split_label = QLabel()
        self.split_label.setWordWrap(True)
        self.split_label.setVisible(False)
        layout.addWidget(self.split_label)

        self.warning_label = QLabel()
        self.warning_label.setWordWrap(True)
        self.warning_label.setVisible(False)
        layout.addWidget(self.warning_label)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setTextVisible(False)
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.status_label.setVisible(False)
        layout.addWidget(self.status_label)

        self.buttons = QDialogButtonBox()
        self.erase_btn = QPushButton(self.tr("Erase MiniDisc..."))
        self.erase_btn.clicked.connect(self._erase_disc)
        self.buttons.addButton(self.erase_btn, QDialogButtonBox.ButtonRole.ActionRole)
        self.start_btn = QPushButton(self.tr("Start Recording"))
        self.start_btn.clicked.connect(self._start)
        self.buttons.addButton(self.start_btn, QDialogButtonBox.ButtonRole.AcceptRole)
        self.close_btn = QPushButton(self.tr("Cancel"))
        self.close_btn.clicked.connect(self.reject)
        self.buttons.addButton(self.close_btn, QDialogButtonBox.ButtonRole.RejectRole)
        layout.addWidget(self.buttons)

        self._load_items()
        self._check_tools()
        self._refresh_split_button()

    # --- preflight ----------------------------------------------------

    def _check_tools(self) -> None:
        missing = netmd.missing_tools()
        if missing:
            self.summary_label.setText(
                self.summary_label.text()
                + "\n"
                + self.tr("Missing tools: {tools}. Recording is unavailable until they are installed.").format(
                    tools=", ".join(missing)
                )
            )
            self.start_btn.setEnabled(False)

    def _load_items(self) -> None:
        if not self._items:
            self.summary_label.setText(self.tr("There are no tracks to record."))
            self.start_btn.setEnabled(False)
            return

        # Same reordering-by-the-files'-own-order fix RecordDialog applies
        # -- a double album dropped in as one folder arrives interleaved,
        # since both discs number their tracks from one.
        ordered = tracks.sort_by_disc_and_track(self._items)
        if [item.path for item in ordered] != [item.path for item in self._items]:
            positions = {id(item): index for index, item in enumerate(self._items)}
            permutation = [positions[id(item)] for item in ordered]
            given = self._given_metadata
            if given is not None and len(given.tracks) == len(permutation):

                self._given_metadata = replace(given, tracks=[given.tracks[index] for index in permutation])
            self._items = ordered
        self._manual_breaks = tracks.disc_breaks(self._items) or None

        self._seed = self._given_metadata or tracks.metadata_from_playlist(self._items)
        self._fill_fields(self._seed)

        total = tracks.total_seconds(self._items)
        self.summary_label.setText(
            self.tr(
                "{count} tracks, {total} total.\n"
                "They will be sent to the deck over USB in this order, each already carrying its own title."
            ).format(count=len(self._items), total=_mmss(total))
        )
        if self._manual_breaks:
            self.summary_label.setText(
                self.summary_label.text()
                + "\n"
                + self.tr(
                    "The files say this is a {count}-disc album, so the disc splits below are already placed "
                    "where they say."
                ).format(count=len(self._manual_breaks) + 1)
            )
        self._ensure_cover()
        if self._manual_breaks:
            self.multi_check.setChecked(True)
        self._recompute_plan()

    def _fill_fields(self, metadata: ProjectMetadata) -> None:
        self.artist_edit.setText(metadata.artist)
        self.album_edit.setText(metadata.album)
        self.year_spin.setValue(metadata.year or 0)
        self.cover_label.set_cover(metadata.cover_art)
        self.tree.clear()
        for index, item in enumerate(self._items):
            title = metadata.tracks[index].title if index < len(metadata.tracks) else item.display_title()
            artist = metadata.tracks[index].artist if index < len(metadata.tracks) else item.artist
            row = QTreeWidgetItem(
                self.tree, ["", item.track_number, title, artist, _mmss(item.length_seconds)]
            )
            row.setFlags(row.flags() | Qt.ItemFlag.ItemIsEditable)
        self.tree.resizeColumnToContents(COL_DISC)
        self.tree.resizeColumnToContents(COL_NUMBER)
        self.tree.resizeColumnToContents(COL_LENGTH)

    def _set_fields_editable(self, editable: bool) -> None:
        for widget in (
            self.artist_edit,
            self.album_edit,
            self.year_spin,
            self.tree,
            self.cover_label,
            self.up_btn,
            self.down_btn,
            self.split_btn,
            self.auto_split_btn,
            self.multi_check,
        ):
            widget.setEnabled(editable)
        if editable:
            self._refresh_split_button()

    def _ensure_cover(self) -> None:
        if self.cover_label.data:
            return
        if self._seed.is_compilation():
            self.cover_label.set_cover(mixtape_cover.render_cover(self._seed))
            return
        chosen = fetch_into(
            self.cover_label, self.artist_edit.text(), self.album_edit.text(), len(self._items)
        )
        if chosen is not None and not self.year_spin.value() and chosen.year:
            self.year_spin.setValue(chosen.year)
        if not self.cover_label.data:
            self.cover_label.set_cover(embedded_cover.cover_from_files(i.path for i in self._items if i.path))

    # --- the split ----------------------------------------------------

    def _plan_tracks(self) -> list[Track]:
        return [
            Track(title=item.display_title(), time_seconds=item.length_seconds or 0)
            for item in self._items
        ]

    def _multi(self) -> bool:
        return bool(self.multi_check.isChecked() and self._plan is not None and self._plan.count > 1)

    def _recompute_plan(self) -> None:
        if not self._items:
            return
        capacity = self.disc_minutes_spin.value() * 60
        plan_tracks = self._plan_tracks()
        if not self.multi_check.isChecked():
            self._plan = multidisc.plan_from_breaks(plan_tracks, [], capacity)
        elif self._manual_breaks is None:
            self._plan = multidisc.split_discs(plan_tracks, capacity)
        else:
            self._plan = multidisc.plan_from_breaks(plan_tracks, self._manual_breaks, capacity)
        self._refresh_disc_column()
        self._refresh_split_label()
        self._refresh_warning()
        self._refresh_split_button()

    def _refresh_disc_column(self) -> None:
        multi = self._multi()
        self.tree.setColumnHidden(COL_DISC, not multi)
        for index in range(self.tree.topLevelItemCount()):
            row = self.tree.topLevelItem(index)
            disc = self._plan.disc_for_index(index) if (multi and self._plan) else None
            row.setText(COL_DISC, str(disc.number) if disc else "")
        if multi:
            self.tree.resizeColumnToContents(COL_DISC)

    def _refresh_split_label(self) -> None:
        if not self._multi() or self._plan is None:
            self.split_label.setVisible(False)
            return
        parts = [
            self.tr("Disc {number}: tracks {first}-{last}, {time}").format(
                number=disc.number,
                first=disc.first_index + 1,
                last=disc.last_index + 1,
                time=_mmss(disc.total_seconds),
            )
            for disc in self._plan.discs
        ]
        text = "  ·  ".join(parts)
        if self._plan.untimed:
            text += "\n" + self.tr(
                "These tracks carry no running times, so nothing here knows how full a disc is -- place the "
                "splits yourself."
            )
        elif not self._plan.fits:
            text += "\n" + self.tr(
                "That is {over} more than one disc holds. Split it again, or choose a longer mode in "
                "Settings and say so above."
            ).format(over=_mmss(self._plan.overflow_seconds))
        self.split_label.setText(text)
        self.split_label.setVisible(True)

    def _refresh_warning(self) -> None:
        if self._plan is None or self._multi() or self._plan.fits:
            self.warning_label.setVisible(False)
            return
        self.warning_label.setText(
            self.tr(
                'This is longer than the {limit} the chosen mode holds. Turn on "Record across several '
                'discs" below, or choose a longer mode in Settings.'
            ).format(limit=_mmss(self.disc_minutes_spin.value() * 60))
        )
        self.warning_label.setVisible(True)

    def _refresh_split_button(self) -> None:
        row = self._selected_row()
        breaks = set(self._current_breaks())
        enabled = self.multi_check.isChecked() and row > 0 and not self._recording
        self.split_btn.setEnabled(enabled)
        self.auto_split_btn.setEnabled(
            self.multi_check.isChecked() and self._manual_breaks is not None and not self._recording
        )
        self.split_btn.setText(
            self.tr("Do Not Start Disc Here") if row in breaks else self.tr("Start Disc Here")
        )

    def _current_breaks(self) -> list[int]:
        if self._manual_breaks is not None:
            return list(self._manual_breaks)
        return self._plan.breaks if self._plan is not None else []

    def _selected_row(self) -> int:
        item = self.tree.currentItem()
        return self.tree.indexOfTopLevelItem(item) if item is not None else -1

    def _refresh_preview(self) -> None:
        row = self._selected_row()
        path = Path(self._items[row].path) if 0 <= row < len(self._items) and self._items[row].path else None
        self.preview_bar.set_current(path, has_prev=row > 0, has_next=0 <= row < len(self._items) - 1)

    def _step_preview(self, delta: int) -> None:
        row = self._selected_row() + delta
        if 0 <= row < self.tree.topLevelItemCount():
            self.tree.setCurrentItem(self.tree.topLevelItem(row))

    def _on_multi_toggled(self, _checked: bool) -> None:
        self._recompute_plan()

    def _toggle_split(self) -> None:
        row = self._selected_row()
        if row <= 0:
            return
        breaks = set(self._current_breaks())
        breaks.discard(row) if row in breaks else breaks.add(row)
        self._manual_breaks = sorted(breaks)
        self._recompute_plan()

    def _auto_split(self) -> None:
        self._manual_breaks = None
        self._recompute_plan()

    def _move_selected(self, delta: int) -> None:
        row = self._selected_row()
        target = row + delta
        if row < 0 or not 0 <= target < len(self._items):
            return
        self._items[row], self._items[target] = self._items[target], self._items[row]
        if len(self._seed.tracks) == len(self._items):

            seed_tracks = list(self._seed.tracks)
            seed_tracks[row], seed_tracks[target] = seed_tracks[target], seed_tracks[row]
            self._seed = replace(self._seed, tracks=seed_tracks)
        moved = self.tree.takeTopLevelItem(row)
        self.tree.insertTopLevelItem(target, moved)
        self.tree.setCurrentItem(moved)
        self._recompute_plan()

    # --- the plan -------------------------------------------------------

    def _disc_bounds(self) -> tuple[int, int]:
        disc = self._current_disc()
        if disc is None or not self._multi():
            return 0, len(self._items) - 1
        return disc.first_index, disc.last_index

    def _current_disc(self) -> multidisc.DiscPlan | None:
        if self._plan is None or not 0 <= self._disc < self._plan.count:
            return None
        return self._plan.discs[self._disc]

    def _disc_sources(self) -> list[tuple[Path, str]]:
        """(path, title) for the disc about to be sent, titles taken from
        the table -- what is on screen when Start is pressed is what gets
        written, the same rule every recording dialog here follows."""
        first, last = self._disc_bounds()
        sources = []
        for index in range(first, last + 1):
            row = self.tree.topLevelItem(index)
            title = row.text(COL_TITLE).strip() if row else self._items[index].display_title()
            sources.append((Path(self._items[index].path), title))
        return sources

    def _disc_album_title(self) -> str:
        album = self.album_edit.text().strip()
        total = self._plan.count if self._plan is not None else 1
        if self._multi() and total > 1:
            album = f"{album} [{self._disc + 1}/{total}]".strip()
        return album

    def _build_plan(self) -> netmd.RecordPlan:
        return netmd.build_record_plan(
            self._disc_sources(),
            disc_title=self._disc_album_title(),
            mode_key=app_settings.netmd_recording_mode(),
        )

    # --- recording --------------------------------------------------------

    def _start(self) -> None:
        if not self._items:
            return
        if not self._confirm_overwrite():
            return
        self.preview_bar.stop()
        self._disc = 0
        self.start_btn.setEnabled(False)
        self.erase_btn.setEnabled(False)
        self._set_fields_editable(False)
        self.close_btn.setText(self.tr("Stop"))
        self.progress.setVisible(True)
        self.status_label.setVisible(True)
        self._record_current_disc()

    def _confirm_overwrite(self) -> bool:
        if self._multi() and self._plan is not None:
            text = self.tr(
                "This album takes {count} discs. Each one is prepared, sent and ejected on its own, and "
                "you will be asked to load the next.\n\nRecording replaces whatever is on a disc, and "
                "nothing about it can be undone. Make sure the first disc is loaded and its write-protect "
                "tab is open, then continue."
            ).format(count=self._plan.count)
        else:
            text = self.tr(
                "Recording replaces whatever is on the disc, and nothing about it can be undone.\n\n"
                "Make sure the right disc is loaded and its write-protect tab is open, then continue."
            )
        answer = QMessageBox.warning(
            self,
            self.windowTitle(),
            text,
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        return answer == QMessageBox.StandardButton.Ok

    def _record_current_disc(self) -> None:
        plan = self._build_plan()
        if not plan.can_record:
            self._fail(self._describe_problems(plan))
            return
        if plan.changed and not self._confirm_title_losses(plan):
            self._fail(self.tr("Cancelled."))
            return
        work_dir = Path(app_settings.cd_rip_folder()) / cdrip.NETMD_SCRATCH_DIRNAME
        if self._multi():
            work_dir = work_dir / f"disc{self._disc + 1}"

        self._recording = True
        self.running_changed.emit(True)
        self.progress.setValue(0)
        self.status_label.setText(
            self.tr("Preparing disc {number}...").format(number=self._disc + 1)
            if self._multi()
            else self.tr("Preparing the recording...")
        )
        self._worker = _NetMdRecordWorker(plan, work_dir, parent=self)
        self._worker.stage.connect(self._on_stage)
        self._worker.progress.connect(self._on_progress)
        self._worker.track_started.connect(self._on_track_started)
        self._worker.failed.connect(self._on_failed)
        self._worker.cancelled.connect(self._on_cancelled)
        self._worker.succeeded.connect(self._on_succeeded)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()

    def _confirm_title_losses(self, plan: netmd.RecordPlan) -> bool:
        """A title going onto a NetMD disc is sent in the same command as
        its audio, with no second, separate titling pass to catch a
        dropped character the way MDRemUploadDialog's own preview does --
        so this is said before the (irreversible) send starts, the same
        promise CD-Text and MDRem titling both make."""
        lines = [self.tr("{before} -> {after}").format(before=before, after=after) for before, after in plan.changed]
        answer = QMessageBox.warning(
            self,
            self.windowTitle(),
            self.tr(
                "These titles cannot be written to the disc as typed and will be shortened to plain ASCII:\n\n{list}\n\nContinue?"
            ).format(list="\n".join(lines)),
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        return answer == QMessageBox.StandardButton.Ok

    def _describe_problems(self, plan: netmd.RecordPlan) -> str:
        lines = [self._describe(problem) for problem in plan.problems]
        return "\n".join(lines) or self.tr("Nothing can be recorded.")

    def _describe(self, problem: netmd.RecordProblem) -> str:
        if problem.code == netmd.UNREADABLE:
            return self.tr("Track {number} could not be read: {detail}").format(
                number=problem.track_number, detail=problem.detail
            )
        if problem.code == netmd.TOO_MANY_TRACKS:
            return self.tr("A MiniDisc holds at most 99 tracks, and this is {count}.").format(
                count=problem.detail
            )
        if problem.code == netmd.TOO_LONG_FOR_DISC:
            return self.tr("This is {over} longer than the chosen mode holds.").format(over=problem.detail)
        if problem.code == netmd.NO_TRACKS:
            return self.tr("There are no tracks to record.")
        return problem.code

    def _on_stage(self, stage: str) -> None:
        if stage == "prepare":
            text = self.tr("Preparing audio...")
        else:
            text = self.tr("Sending to the deck over USB...")
        self.status_label.setText(text)
        self.overall_progress_changed.emit(self._last_fraction, text)

    def _on_progress(self, fraction: float) -> None:
        self._last_fraction = fraction
        self.progress.setValue(int(fraction * 1000))
        self.overall_progress_changed.emit(fraction, self.status_label.text())

    def _on_track_started(self, index: int, total: int, title: str) -> None:
        text = self.tr("Sending track {index} of {total}: {title}").format(
            index=index, total=total, title=title
        )
        self.status_label.setText(text)
        self.track_progress_changed.emit(0.0, text)

    def _on_failed(self, message: str) -> None:
        surface(self)
        self._fail(message)

    def _on_cancelled(self) -> None:
        self.status_label.setText(self.tr("Stopped."))

    def _on_succeeded(self) -> None:
        self._capture_metadata()
        if self._disc + 1 < (self._plan.count if self._plan else 1):
            self._advance_when_finished = True
            return
        self.status_label.setText(
            self.tr("All {count} discs are recorded and titled.").format(count=self._plan.count)
            if self._multi()
            else self.tr("Recording finished. The disc is titled.")
        )
        self.accept()

    def _on_worker_finished(self) -> None:
        self._worker = None
        self._recording = False
        self.running_changed.emit(False)
        self.progress.setValue(1000)
        if self._closing:
            self._closing = False
            super().reject()
            return
        if not self._advance_when_finished:
            self.close_btn.setText(self.tr("Close"))
            self.start_btn.setEnabled(True)
            self.erase_btn.setEnabled(True)
            self._set_fields_editable(True)
            return
        self._advance_when_finished = False
        if not self._ask_for_next_disc():
            self.status_label.setText(
                self.tr("Stopped after disc {number}. The discs already sent are finished.").format(
                    number=self._disc + 1
                )
            )
            self.close_btn.setText(self.tr("Close"))
            self.start_btn.setEnabled(True)
            self.erase_btn.setEnabled(True)
            self._set_fields_editable(True)
            return
        self._disc += 1
        self.progress.setValue(0)
        self._record_current_disc()

    def _ask_for_next_disc(self) -> bool:
        surface(self)
        answer = QMessageBox.question(
            self,
            self.windowTitle(),
            self.tr(
                "Disc {done} of {count} is written and titled.\n\nPut a blank disc in the deck and close "
                "the tray, then continue to record disc {next}."
            ).format(done=self._disc + 1, count=self._plan.count if self._plan else 1, next=self._disc + 2),
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Ok,
        )
        return answer == QMessageBox.StandardButton.Ok

    def _capture_metadata(self) -> None:

        metadata = replace(
            self._seed,
            artist=self.artist_edit.text().strip(),
            album=self.album_edit.text().strip(),
            year=self.year_spin.value() or None,
            cover_art=self.cover_label.data,
            tracks=self._tracks_from_tree(),
        )
        self.result_metadata = metadata

    def _tracks_from_tree(self) -> list[Track]:
        result = []
        for index, item in enumerate(self._items):
            row = self.tree.topLevelItem(index)
            seed = self._seed.tracks[index] if index < len(self._seed.tracks) else None
            title = (
                row.text(COL_TITLE).strip()
                if row is not None
                else (seed.title if seed else item.display_title())
            )
            artist = (
                row.text(COL_ARTIST).strip() if row is not None else (seed.artist if seed else item.artist)
            )
            result.append(Track(title=title, time_seconds=item.length_seconds or None, artist=artist))
        return result

    def _erase_disc(self) -> None:
        answer = QMessageBox.warning(
            self,
            self.tr("Erase MiniDisc"),
            self.tr("This clears whatever disc is currently in the deck, and cannot be undone. Continue?"),
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Ok:
            return
        try:
            netmd.erase_disc()
        except netmd.NetMdError as exc:
            QMessageBox.critical(self, self.tr("Erase MiniDisc"), str(exc))

    def _fail(self, message: str) -> None:
        self.status_label.setVisible(True)
        self.status_label.setText(message)
        self.close_btn.setText(self.tr("Close"))
        self.start_btn.setEnabled(True)
        self.erase_btn.setEnabled(True)
        self._set_fields_editable(True)
        self._recording = False
        self.running_changed.emit(False)

    # --- window plumbing --------------------------------------------------

    def request_stop(self) -> None:
        self.reject()

    def is_busy(self) -> bool:
        return self._recording

    def closeEvent(self, event) -> None:
        if close_hides_while_busy(self, event):
            return
        super().closeEvent(event)

    def request_show(self) -> None:
        self.show_requested.emit()

    def reject(self) -> None:
        """Stopping mid-recording has to wait for the worker to notice --
        never wait() on the GUI thread for it (the same rule BurnDialog's
        own reject() follows); _on_worker_finished() is the single place
        anything is torn down."""
        self.preview_bar.stop()
        worker = self._worker
        if worker is None:
            super().reject()
            return
        answer = QMessageBox.question(
            self,
            self.windowTitle(),
            self.tr("Stop now? A track already being sent will finish or fail on its own; nothing after it goes out."),
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Ok:
            return
        self._closing = True
        worker.cancel()
        self.status_label.setText(self.tr("Stopping..."))
