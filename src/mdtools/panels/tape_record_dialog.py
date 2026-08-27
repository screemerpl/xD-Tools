"""Recording > "Record to Cassette..." -- records an album onto a compact
cassette, one side at a time.

Everything else this app records to is driven: a MiniDisc deck takes its
keys over infrared, a CD-R burner takes a command line. **A tape deck here
is driven by the user**, and that is the whole shape of this dialog. There
is no adapter, no key table and no way to know what the machine is doing --
so xD-Tools does the one half it can (play the right tracks, in the right
order, at the right moment) and *says* the other half out loud, one
instruction at a time, waiting for the user to say it is done.

The sequence per side:

  1. the user presses RECORD on the deck and clicks the button, which is
     the only confirmation there is that the deck is actually rolling
  2. ten seconds of nothing, so the music misses the leader (see tape.py --
     leader tape is not magnetic, and anything recorded onto it is gone)
  3. xD-Tools' own AudioPlayer (audio_engine.py) plays that side's tracks --
     only that side's, sliced up front, so playback simply ends where the
     side does, with no need to arm anything to stop early
  4. the user stops the deck and turns the tape over

Where the break falls is `tape.split_sides()`, the same function the shell
labels are laid out from -- a label that says side B starts at track seven
and a recording that turns over after track six would each be defensible
alone and wrong together.

The audio path is the deck's analogue inputs, and nothing here depends on
that: xD-Tools plays the album itself and fires an event when a side ends,
so how the sound gets from the sound card to the tape is entirely outside
this loop. The deck's own input selector and recording level are the
user's to set, which the manual says and this does not try to enforce.

This used to drive foobar2000 over Beefweb the way RecordDialog once did,
polling its now-playing index to decide when a side ended -- see that
module's own docstring for the full reasoning behind the swap to
AudioPlayer. No worker thread either way: every step here is either
instantaneous or a QTimer tick, and the genuinely real-time part (playback
itself) runs on AudioPlayer's own audio callback thread, reached safely
through `panels/playback_bridge.py`.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtWidgets import (
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
)

from mdtools import app_settings, audio_engine, embedded_cover, mixtape_cover, tape, tracks
from mdtools.panels.cover_preview import CoverPreview, fetch_into
from mdtools.panels.decode_worker import DecodeWorker
from mdtools.panels.hideable_dialog import close_hides_while_busy, surface
from mdtools.panels.playback_bridge import PlaybackBridge
from mdtools.panels.preview_player import PreviewPlayerBar
from mdtools.panels.progress_format import mmss as _mmss
from mdtools.project import ProjectMetadata, Track

POLL_MS = 250
COUNTDOWN_MS = 1000


class TapeRecordDialog(QDialog):
    # Mirrored by MainWindow's own bottom-of-window progress bar (#27) --
    # see app_window.py's _drive_recording_bar()/_release_recording_bar().
    # running_changed goes False between sides (the user has to flip the
    # tape and press Start again -- nothing is happening in the background
    # the way RecordDialog's automatic disc-to-disc titling is).
    running_changed = Signal(bool)
    overall_progress_changed = Signal(float, str)
    track_progress_changed = Signal(float, str)
    visibility_changed = Signal(bool)
    # Asked for by the progress bar's "Show recording window" button --
    # see panels/hideable_dialog.py, which is what actually re-shows this.
    show_requested = Signal()

    def __init__(
        self,
        paths: list[Path | str],
        parent=None,
        metadata: ProjectMetadata | None = None,
        total_minutes: float = tape.DEFAULT_LENGTH.total_minutes,
    ):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Record to Cassette"))
        self.resize(560, 620)
        self._items: list[tracks.PlaylistItem] = tracks.playlist_items_from_paths(paths) if paths else []
        self._given_metadata = metadata
        self._seed = ProjectMetadata()
        self._plan: tape.TapePlan | None = None

        self._side = 0  # which side is being recorded, 0 = A
        self._recording = False
        self._current_local_index = 0
        self._remaining = 0  # seconds of leader silence still to go
        self._player: audio_engine.AudioPlayer | None = None
        self._pending_buffers: list | None = None
        # The decode running ahead of a side, whether a Stop is waiting for
        # it to notice, and the window between Start and the countdown --
        # see _on_start_clicked()/reject(). "Preparing" counts as busy: the
        # worker must not be left running with nobody holding it.
        self._decoder: DecodeWorker | None = None
        self._closing = False
        self._preparing = False
        # Set by the Hide button, read by exec_hideable() -- see
        # panels/hideable_dialog.py for why a hide has to be told apart
        # from a cancel at all.
        self.hidden_for_background = False
        self._bridge = PlaybackBridge(self)
        self._bridge.track_boundary.connect(self._on_track_boundary)
        self._bridge.finished.connect(self._on_side_finished)

        # Read by MainWindow after exec(): what was recorded, as project
        # metadata. None means nothing was, so nothing should be adopted.
        self.result_metadata: ProjectMetadata | None = None
        # And which tape it went onto, so the labels split where the
        # recording did.
        self.total_minutes = total_minutes

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
        self.length_combo = QComboBox()
        for length in tape.CASSETTE_LENGTHS:
            self.length_combo.addItem(
                self.tr("{name} ({minutes} min, {side} a side)").format(
                    name=length.name,
                    minutes=length.total_minutes,
                    side=_mmss(length.side_seconds),
                ),
                length.total_minutes,
            )
        self.length_combo.currentIndexChanged.connect(lambda _index: self._recompute_plan())
        form.addRow(self.tr("Artist"), self.artist_edit)
        form.addRow(self.tr("Album"), self.album_edit)
        form.addRow(self.tr("Year"), self.year_spin)
        form.addRow(self.tr("Cassette"), self.length_combo)

        self.cover_label = CoverPreview()

        header = QHBoxLayout()
        header.addLayout(form, 1)
        header.addWidget(self.cover_label)
        layout.addLayout(header)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(
            [self.tr("Side"), self.tr("#"), self.tr("Title"), self.tr("Artist"), self.tr("Length")]
        )
        self.tree.setRootIsDecorated(False)
        self.tree.currentItemChanged.connect(lambda *_: self._refresh_preview())
        layout.addWidget(self.tree)

        self.preview_bar = PreviewPlayerBar()
        self.preview_bar.prev_requested.connect(lambda: self._step_preview(-1))
        self.preview_bar.next_requested.connect(lambda: self._step_preview(1))
        # Locked for as long as real work is in progress -- connected to
        # this dialog's own running_changed rather than toggled by hand at
        # each start/finish/fail site, so it cannot drift out of step with
        # them. See PreviewPlayerBar.set_locked().
        self.running_changed.connect(self.preview_bar.set_locked)
        layout.addWidget(self.preview_bar)

        self.fit_label = QLabel()
        self.fit_label.setWordWrap(True)
        layout.addWidget(self.fit_label)

        # The instruction the user is currently meant to be acting on. Kept
        # separate from the status line below, and deliberately the loudest
        # thing on the dialog: on this medium it *is* the interface.
        self.instruction_label = QLabel()
        self.instruction_label.setWordWrap(True)
        self.instruction_label.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self.instruction_label)

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
        self.start_btn = QPushButton()
        self.start_btn.clicked.connect(self._on_start_clicked)
        self.buttons.addButton(self.start_btn, QDialogButtonBox.ButtonRole.AcceptRole)
        self.close_btn = QPushButton(self.tr("Cancel"))
        self.close_btn.clicked.connect(self.reject)
        self.buttons.addButton(self.close_btn, QDialogButtonBox.ButtonRole.RejectRole)
        layout.addWidget(self.buttons)

        self._timer = QTimer(self)
        self._timer.setInterval(POLL_MS)
        self._timer.timeout.connect(self._refresh_progress)
        self._countdown = QTimer(self)
        self._countdown.setInterval(COUNTDOWN_MS)
        self._countdown.timeout.connect(self._tick)

        self._select_length(total_minutes)
        self._load_items()

    # --- preflight ----------------------------------------------------

    def _select_length(self, minutes: float) -> None:
        index = self.length_combo.findData(minutes)
        self.length_combo.setCurrentIndex(index if index >= 0 else self.length_combo.count() - 1)

    def _load_items(self) -> None:
        if not self._items:
            self.summary_label.setText(self.tr("There are no tracks to record."))
            self.start_btn.setEnabled(False)
            return

        self._seed = self._given_metadata or tracks.metadata_from_playlist(self._items)
        self._fill_fields(self._seed)

        total = tracks.total_seconds(self._items)
        self.summary_label.setText(
            self.tr(
                "{count} tracks, {total} total.\n"
                "It will be recorded in this order, in two sides, through the deck's line inputs."
            ).format(count=len(self._items), total=_mmss(total))
        )
        self._ensure_cover()
        # The shortest tape that holds it, if the user has not already been
        # given one by the project -- a suggestion, never a decision: which
        # cassette is in the box is a fact about their shelf.
        suggested = tape.suggested_length(self._plan_tracks())
        if suggested is not None and self._given_metadata is None:
            self._select_length(suggested.total_minutes)
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
        for column in (0, 1, 4):
            self.tree.resizeColumnToContents(column)

    def _ensure_cover(self) -> None:
        """The artwork, settled before the recording rather than after --
        see RecordDialog._ensure_cover for why that is the whole point."""
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
        """The album as something tape.split_sides can weigh.

        Built from the *items*, not from the tree: what decides the split is
        how long each track runs, and that is a fact about the file, not
        something the Title column can be edited into disagreeing with.
        """
        return [
            Track(title=item.display_title(), time_seconds=item.length_seconds or 0)
            for item in self._items
        ]

    def _recompute_plan(self) -> None:
        if not self._items:
            return
        self.total_minutes = float(self.length_combo.currentData())
        self._plan = tape.split_sides(self._plan_tracks(), self.total_minutes)
        boundary = len(self._plan.sides[0].tracks)

        for index in range(self.tree.topLevelItemCount()):
            row = self.tree.topLevelItem(index)
            row.setText(0, "A" if index < boundary else "B")

        first, second = self._plan.sides
        summary = self.tr("Side A: {a_count} tracks, {a_time} · Side B: {b_count} tracks, {b_time}").format(
            a_count=len(first.tracks),
            a_time=_mmss(first.total_seconds),
            b_count=len(second.tracks),
            b_time=_mmss(second.total_seconds),
        )
        if self._plan.untimed:
            summary += "\n" + self.tr(
                "These tracks carry no running times, so the album is split down the middle by count -- "
                "check it against the tape before recording."
            )
        elif not self._plan.fits:
            summary += "\n" + self.tr(
                "That is {over} more than one side of this tape holds. Use a longer cassette, or expect "
                "the last track to run into the run-out."
            ).format(over=_mmss(self._plan.overflow_seconds))
        self.fit_label.setText(summary)
        self._show_side_instruction()

    # --- recording ----------------------------------------------------

    def _current_side(self) -> tape.SidePlan | None:
        if self._plan is None:
            return None
        return self._plan.sides[self._side]

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

    def _side_bounds(self) -> tuple[int, int]:
        """The item indices this side covers, as [first, last]."""
        boundary = len(self._plan.sides[0].tracks) if self._plan else 0
        if self._side == 0:
            return 0, boundary - 1
        return boundary, len(self._items) - 1

    def _show_side_instruction(self) -> None:
        side = self._current_side()
        if side is None or self._recording:
            return
        if not side.tracks:
            # A one-sided recording: everything fitted on side A, so there
            # is nothing to turn over for.
            self.instruction_label.setText("")
            self.start_btn.setText(self.tr("Start Side A"))
            return
        heading = self.tr("Side {side}").format(side=side.label)
        self.instruction_label.setText(
            f"<b>{heading}</b><br>"
            + self.tr(
                "Press RECORD and PAUSE together on side {side} (record-pause -- armed, but not yet "
                "moving), set its input to the line it is fed from, then press the button below. Once "
                "the tracks are ready you will be told to release Pause; the first {seconds} seconds "
                "after that are recorded silent, so the music clears the leader tape."
            ).format(side=side.label, seconds=tape.LEADER_SECONDS)
        )
        self.start_btn.setText(self.tr("Recording -- Start Side {side}").format(side=side.label))

    def _on_start_clicked(self) -> None:
        if self._plan is None or self._recording:
            return
        if self._side == 0 and not self._confirm_overwrite():
            return
        side = self._current_side()
        if side is None or not side.tracks:
            self._finish()
            return

        self.preview_bar.stop()
        if self._player is None:
            self._player = audio_engine.AudioPlayer(
                device=audio_engine.resolve_output_device(app_settings.tape_audio_output_device()),
                gain_db=app_settings.recording_gain_db(),
            )

        self.status_label.setVisible(True)
        # Decoded and resampled *before* the leader countdown starts --
        # otherwise the deck keeps rolling onto (already-magnetic) tape for
        # however long that takes, on top of the deliberate LEADER_SECONDS
        # of silence the countdown itself accounts for.
        #
        # On a worker thread, not here: decoding a whole side is a real
        # stretch of soxr work, and doing it on the GUI thread froze the
        # window for all of it (reported against the MiniDisc dialog, which
        # does the same thing with dither on top). Nothing has been asked of
        # the user yet at this point -- the "Release Pause now" box is in
        # _on_decoded(), after the audio is ready -- so the deck is not
        # rolling while this runs.
        first, last = self._side_bounds()
        paths = [Path(item.path) for item in self._items[first : last + 1]]
        self._preparing = True
        self.start_btn.setEnabled(False)
        self._decoder = DecodeWorker(
            paths, samplerate=self._player.samplerate, dithered=False, parent=self
        )
        self._decoder.progress.connect(self._report_decode_progress)
        self._decoder.decoded.connect(self._on_decoded)
        self._decoder.failed.connect(self._on_decode_failed)
        self._decoder.finished.connect(self._on_decoder_finished)
        self._decoder.start()

    def _on_decoded(self, buffers: list) -> None:
        """The side's audio is ready: this is the moment the deck should
        actually start moving."""
        if self._closing or not self._preparing:
            return  # stopped while it was decoding
        self._preparing = False
        self._recording = True
        self.running_changed.emit(True)
        self._current_local_index = 0
        self._set_fields_editable(False)
        self.start_btn.setEnabled(False)
        self.close_btn.setText(self.tr("Stop"))
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self._pending_buffers = buffers
        self._remaining = tape.LEADER_SECONDS
        # Decoding is done, so this is the exact moment the deck should
        # actually start moving. A passive label change was tried first and
        # reported as too easy to miss ("no popup, it just goes straight
        # into the countdown") -- a blocking dialog forces the user to
        # actually see this, and doubles as the sync point: the leader
        # countdown only starts once they have dismissed it, which is the
        # same moment they should be releasing Pause.
        self.instruction_label.setText(
            "<b>" + self.tr("Release Pause now") + "</b><br>" + self.tr("The deck should start rolling.")
        )
        QMessageBox.information(
            self,
            self.tr("Record to Cassette"),
            self.tr("Release Pause now -- the deck should start rolling."),
        )
        self._tick_display()
        self._countdown.start()

    def _confirm_overwrite(self) -> bool:
        answer = QMessageBox.warning(
            self,
            self.tr("Record to Cassette"),
            self.tr(
                "Recording replaces whatever is on the tape, and nothing about it can be undone.\n\n"
                "Make sure the right cassette is in the deck, wound to the start of side A, and that its "
                "record-protect tabs are intact."
            ),
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        return answer == QMessageBox.StandardButton.Ok

    def _on_decode_failed(self, error: str) -> None:
        if self._closing:
            return
        self._preparing = False
        self._fail(self.tr("Could not decode this side for playback: {error}").format(error=error))

    def _on_decoder_finished(self) -> None:
        """The one place a decode ends, however it ended -- so a Stop
        pressed mid-decode returns immediately instead of blocking the GUI
        thread on wait()."""
        self._decoder = None
        if self._closing:
            self._closing = False
            self.close_btn.setEnabled(True)
            super().reject()

    def _report_decode_progress(self, index: int, total: int, name: str) -> None:
        """DecodeWorker's own progress signal, one per track -- see
        _on_start_clicked for why decoding happens before the leader
        countdown, and why it no longer happens on this thread. No
        processEvents() any more: the event loop is turning by itself, so
        this is an ordinary queued-signal label update."""
        self.status_label.setText(
            self.tr("Preparing track {index} of {total}: {name}...").format(
                index=index, total=total, name=name
            )
        )

    def _tick_display(self) -> None:
        self.status_label.setText(
            self.tr("Recording silence over the leader -- {seconds}s").format(seconds=self._remaining)
        )

    def _tick(self) -> None:
        self._remaining -= 1
        if self._remaining > 0:
            self._tick_display()
            return
        self._countdown.stop()
        self._begin_playback()

    def _begin_playback(self) -> None:
        if not self._recording or self._player is None:
            return
        buffers = self._pending_buffers
        self._pending_buffers = None
        if buffers is None:
            return
        self._player.play(
            buffers,
            on_track_boundary=self._bridge.track_boundary.emit,
            on_finished=self._bridge.finished.emit,
        )
        self._timer.start()

    def _on_track_boundary(self, local_index: int) -> None:
        self._current_local_index = local_index

    def _refresh_progress(self) -> None:
        side = self._current_side()
        if side is None or self._player is None:
            return
        first, _last = self._side_bounds()
        current = first + self._current_local_index
        done = sum(item.length_seconds for item in self._items[first:current])
        elapsed = done + self._player.position_seconds
        total = max(1, int(side.music_seconds))
        overall_fraction = min(1.0, elapsed / total)
        self.progress.setValue(int(1000 * overall_fraction))
        title = self._items[current].display_title() if 0 <= current < len(self._items) else ""
        track_seconds = self._items[current].length_seconds if 0 <= current < len(self._items) else 0
        track_fraction = min(1.0, self._player.position_seconds / max(1, track_seconds))
        text = self.tr("Side {side}, track {index} of {count}: {title} -- {elapsed} of {total}").format(
            side=side.label,
            index=current - first + 1,
            count=len(side.tracks),
            title=title,
            elapsed=_mmss(elapsed),
            total=_mmss(total),
        )
        self.status_label.setText(text)
        self.overall_progress_changed.emit(overall_fraction, text)
        self.track_progress_changed.emit(
            track_fraction,
            self.tr("{title} -- {elapsed} of {total}").format(
                title=title, elapsed=_mmss(self._player.position_seconds), total=_mmss(track_seconds)
            ),
        )

    def _on_side_finished(self) -> None:
        """Fired by AudioPlayer once this side's whole queue has played out
        -- see RecordDialog._on_disc_finished for why there is no "stopped
        partway" state to detect here any more."""
        self._timer.stop()
        self._recording = False
        self.running_changed.emit(False)
        self.progress.setValue(1000)

        if self._side == 0 and self._plan is not None and self._plan.sides[1].tracks:
            self._side = 1
            self._set_fields_editable(False)  # settled: side A is already on the tape
            self.start_btn.setEnabled(True)
            self.close_btn.setText(self.tr("Cancel"))
            self.progress.setValue(0)
            next_side = self._plan.sides[1]
            heading = self.tr("Side A is done")
            self.instruction_label.setText(
                f"<b>{heading}</b><br>"
                + self.tr(
                    "Stop the deck, take the cassette out and turn it over, then press RECORD and PAUSE "
                    "together (record-pause) for side {side} and press the button below. You will be "
                    "told when to release Pause."
                ).format(side=next_side.label)
            )
            self.start_btn.setText(self.tr("Recording -- Start Side {side}").format(side=next_side.label))
            self.status_label.setText(
                self.tr("Side A recorded: {count} tracks, {time}.").format(
                    count=len(self._plan.sides[0].tracks),
                    time=_mmss(self._plan.sides[0].total_seconds),
                )
            )
            return

        self._finish()

    def _finish(self) -> None:
        self._timer.stop()
        self._countdown.stop()
        self._recording = False
        self._capture_metadata()
        self.instruction_label.setText(
            "<b>"
            + self.tr("Both sides are recorded")
            + "</b><br>"
            + self.tr("Stop the deck and take the cassette out.")
        )
        self.status_label.setVisible(True)
        self.status_label.setText(self.tr("Recording finished. The labels can be laid out from this album."))
        self.start_btn.setEnabled(False)
        self.close_btn.setText(self.tr("Close"))

    # --- metadata -----------------------------------------------------

    def _set_fields_editable(self, editable: bool) -> None:
        """Frozen once the tape is rolling: what is on screen when a side
        starts is what will be printed on its label. The cassette length is
        frozen with the rest, because changing it would move a side break
        that is already half recorded."""
        for widget in (
            self.artist_edit,
            self.album_edit,
            self.year_spin,
            self.tree,
            self.cover_label,
            self.length_combo,
        ):
            widget.setEnabled(editable)

    def _capture_metadata(self) -> None:
        self.result_metadata = replace(
            self._seed,
            artist=self.artist_edit.text().strip(),
            album=self.album_edit.text().strip(),
            year=self.year_spin.value() or None,
            cover_art=self.cover_label.data,
            tracks=self._tracks_from_tree(),
        )

    def _tracks_from_tree(self) -> list[Track]:
        """One Track per item, from the Title and Artist columns -- the
        Artist column included, or a compilation would stop being one for
        having been recorded (see RecordDialog._tracks_from_tree)."""
        result = []
        for index, item in enumerate(self._items):
            row = self.tree.topLevelItem(index)
            seed = self._seed.tracks[index] if index < len(self._seed.tracks) else None
            title = row.text(2).strip() if row is not None else (seed.title if seed else item.display_title())
            artist = row.text(3).strip() if row is not None else (seed.artist if seed else item.artist)
            result.append(Track(title=title, time_seconds=item.length_seconds or None, artist=artist))
        return result

    # --- helpers ------------------------------------------------------

    def _fail(self, message: str) -> None:
        self._timer.stop()
        self._countdown.stop()
        self._recording = False
        if self._player is not None:
            self._player.stop()
        self.progress.setVisible(False)
        self.status_label.setVisible(True)
        self.status_label.setText(message)
        self.close_btn.setText(self.tr("Close"))
        self.start_btn.setEnabled(True)
        self._set_fields_editable(True)
        self.running_changed.emit(False)

    def request_stop(self) -> None:
        """What MainWindow's own Stop button calls."""
        self.reject()

    def is_busy(self) -> bool:
        """Whether a side is being recorded, or its audio prepared -- what
        decides that the window's X hides instead of closes. Preparing
        counts: a decode worker is running, and closing out from under it
        is the silent QThread-destroyed process abort."""
        return self._recording or self._preparing

    def closeEvent(self, event) -> None:
        if close_hides_while_busy(self, event):
            return
        super().closeEvent(event)

    def request_show(self) -> None:
        """What the progress bar's "Show recording window" button calls."""
        self.show_requested.emit()


    def reject(self) -> None:
        """Stops playback, and says what the user has to stop themselves.

        There is no second end to stop from here -- the deck will happily go
        on recording silence onto the rest of the side, and only the person
        in front of it can prevent that."""
        surface(self)
        self.preview_bar.stop()
        if self._decoder is not None and self._decoder.isRunning():
            # Mid-decode: nothing has been played and the user has not been
            # told to release Pause yet, so there is nothing to warn them
            # about -- just stop preparing. Cancelling lands at the next
            # track boundary, so _on_decoder_finished() is what actually
            # closes the window.
            self._closing = True
            self._preparing = False
            self._decoder.cancel()
            self.status_label.setText(self.tr("Stopping..."))
            self.close_btn.setEnabled(False)
            self.running_changed.emit(False)
            return
        if self._recording:
            self._timer.stop()
            self._countdown.stop()
            self._recording = False
            if self._player is not None:
                self._player.stop()
            self.running_changed.emit(False)
            QMessageBox.information(
                self,
                self.tr("Record to Cassette"),
                self.tr("Playback stopped. Press stop on the deck as well -- it is still recording."),
            )
        super().reject()
