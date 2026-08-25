"""Recording > "Record to MiniDisc..." -- records an album onto a MiniDisc
over S/PDIF, then titles the result.

The sequence, and why each step is where it is:

  1. read the given files (this is what will be recorded, so it is also
     where the titles come from -- not an iTunes lookup, which returns
     whatever release the search matched)
  2. arm the deck (RECORD -> record-pause) and *ask the user to confirm it*
  3. release the pause, then a moment later start playback -- in that
     order, so the deck is already recording when the first note arrives
  4. play the album through xD-Tools' own AudioPlayer (audio_engine.py)
     until it reports the queue finished
  5. stop the deck, then write the titles and eject unattended -- no
     confirmation in between, the same reasoning the multi-disc flow
     below already applies per-disc: nobody sits through a whole album,
     so a question between the music ending and the titles going out
     would leave the deck holding an untitled disc until somebody came
     back (see _title_single_disc)

This dialog used to drive foobar2000 over Beefweb, polling its now-playing
index every 250ms to decide when a track changed and when the album
ended -- a real, poll-bounded lag on both the MDRem track mark and the
disc/side boundary. `AudioPlayer.play()` decodes and plays the files
itself and fires `on_track_boundary`/`on_finished` from its own realtime
audio callback the instant a boundary is crossed, so both of those are
now exact rather than "whatever the next poll happens to see" --
`panels/playback_bridge.py`'s `PlaybackBridge` is what gets those
callbacks safely from that audio thread onto this one. The `QTimer` that
used to drive the poll is kept, but demoted to a pure progress-bar
refresh; nothing recording-accuracy-relevant depends on it any more.

Track splitting is the deck's job and is not verified here. Sony decks
mark a new track when the signal drops to silence and returns
("LEVEL-SYNC"); a PC's S/PDIF output carries no track boundaries of its
own, so an album played gapless will land as one long track. That has been
confirmed to work for ordinary albums on the user's setup, but it is the
part of this feature most likely to disappoint on a live or continuous mix.

**Several discs.** A double album does not fit on a MiniDisc and a MiniDisc
cannot be turned over, so "Record across several discs" runs the whole
sequence above once per disc: record, wait a couple of seconds, write that
disc's titles *without asking*, eject, ask for a blank one, repeat. The
asking is what is deliberately removed -- an album is 40 minutes of real
time and nobody sits through it, so a confirmation between the music
ending and the titles being written would leave the deck holding an
untitled disc until somebody came back. What that costs is the preview
MDRemUploadDialog normally gives, which is why every title (and every
character the deck cannot show) is on screen *here* before the first note
plays. Where each disc ends is `multidisc.py`; this dialog only drives it.

**Reordering.** The table's Up/Down buttons change the order the album is
recorded in. That used to mean rebuilding foobar2000's own playlist to
match (the one blocking step in this dialog, and a real source of past
bugs -- foobar sorts an incoming batch by filename, silently undoing a
reorder). With this dialog decoding and playing the files itself,
reordering is just reordering the local track list; nothing external to
push it into or read it back from.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QTimer, Qt, Signal
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

from mdtools import app_settings, audio_engine, embedded_cover, mdrem, mixtape_cover, multidisc, tracks
from mdtools.panels.cover_preview import CoverPreview, fetch_into
from mdtools.panels.erase_dialog import EraseDiscDialog
from mdtools.panels.hideable_dialog import exec_hideable, hide_for_background
from mdtools.panels.mdrem_upload_dialog import MDRemUploadDialog
from mdtools.panels.playback_bridge import PlaybackBridge
from mdtools.panels.preview_player import PreviewPlayerBar
from mdtools.panels.progress_format import mmss as _mmss
from mdtools.project import ProjectMetadata, Track

# An MD holds 80 minutes in SP. The deck also has MDLP (LP2/LP4) for 160/320,
# but which mode it is in cannot be read or set through our key table, so this
# only ever warns -- it never decides.
DISC_SP_SECONDS = 80 * 60

# The deck is told to start recording before playback begins, so the first
# note is never clipped; the gap becomes a moment of leading silence.
LEAD_IN_MS = 1500

# Now a pure progress-bar refresh interval -- nothing recording-accuracy
# relevant is timed against this any more, unlike when it drove a foobar2000
# poll (see the module docstring).
POLL_MS = 250

# Multi-disc only: how long after the album's last track ends before the
# titles start going out. The deck has just been sent STOP and writes its
# TOC before it will take anything else; two seconds is the user's own
# number, and short enough that nobody has to be standing there.
TITLING_DELAY_MS = 2000

# RECORD pressed *during* recording adds a track mark -- established on an
# MDS-JE480 by recording, sending it mid-way, and finding two tracks.
TRACK_MARK_KEY = "SEND RECORD"

# The track table's columns. Named rather than counted, because the Disc
# column was added in front of the other four and every read of a row is
# now one index off what it used to be.
COL_DISC, COL_NUMBER, COL_TITLE, COL_ARTIST, COL_LENGTH = range(5)


class RecordDialog(QDialog):
    # Mirrored by MainWindow's own bottom-of-window progress bar (#27) --
    # see app_window.py's _drive_recording_bar()/_release_recording_bar().
    # running_changed spans recording *and* the titling that follows it as
    # one continuous True -- see _title_single_disc()/_title_current_disc()
    # for why the nested MDRemUploadDialog's own running_changed is *not*
    # proxied through (it would flash the bar hidden in between).
    running_changed = Signal(bool)
    overall_progress_changed = Signal(float, str)
    track_progress_changed = Signal(float, str)
    visibility_changed = Signal(bool)
    # Asked for by the progress bar's "Show recording window" button --
    # see panels/hideable_dialog.py, which is what actually re-shows this.
    show_requested = Signal()
    def __init__(
        self,
        port: str,
        paths: list[Path | str],
        parent=None,
        metadata: ProjectMetadata | None = None,
    ):
        """`paths` is the album's files, in the order they should be
        recorded -- read directly (via `tracks.playlist_items_from_paths()`),
        no external player involved.

        `metadata`, when given, is what the disc gets titled from instead
        of the files' own tags.

        Only Record Folder passes it, and only because it has to: a folder
        holds somebody else's files, which nothing here rewrites, so an
        album name typed into that dialog can reach the disc no other way.
        The CD flow deliberately does *not* -- it writes its titles into the
        files it created, so the tags already carry them, and one source of
        truth beats two that can disagree. Either way it describes the very
        files that are about to be recorded: it is built from the same
        list, moments earlier."""
        super().__init__(parent)
        self.setWindowTitle(self.tr("Record to MiniDisc"))
        self.resize(560, 560)
        self._port = port
        self._items: list[tracks.PlaylistItem] = tracks.playlist_items_from_paths(paths) if paths else []
        self._recording = False
        self._current_local_index = 0
        # Several discs: the plan, which disc is being recorded.
        self._plan: multidisc.MultiDiscPlan | None = None
        self._disc = 0
        # None means "wherever the arithmetic puts them"; a list means the
        # user has placed the breaks by hand and they are not to be moved.
        self._manual_breaks: list[int] | None = None
        # Read by MainWindow after exec(): the files that were recorded, as
        # project metadata, with cover art if any was found. None means
        # nothing was recorded, so nothing should be adopted.
        self.result_metadata: ProjectMetadata | None = None
        self._given_metadata = metadata
        # Held open for the whole session rather than reopened per key:
        # opening a serial port costs far more than sending, and a track
        # mark's accuracy depends on how fast it goes out.
        self._deck: mdrem.MDRemClient | None = None
        self._player: audio_engine.AudioPlayer | None = None
        # See the module docstring: this is what gets AudioPlayer's
        # realtime-thread callbacks safely onto this (the GUI) thread.
        self._bridge = PlaybackBridge(self)
        # The MDRemUploadDialog currently open for titling, if any -- set
        # only while one of _title_single_disc()/_title_current_disc()'s
        # own exec() calls is on the stack. request_stop() dispatches here
        # first, since stopping *this* dialog does nothing once recording
        # has already finished and titling has taken over.
        self._nested_dialog: QDialog | None = None
        # Set by the Hide button, read by exec_hideable() -- see
        # panels/hideable_dialog.py for why a hide has to be told apart
        # from a cancel at all.
        self.hidden_for_background = False
        self._bridge.track_boundary.connect(self._on_track_boundary)
        self._bridge.finished.connect(self._on_disc_finished)

        layout = QVBoxLayout(self)

        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        # What this disc is, not just what is on it. The three fields and
        # the artwork are the whole of what gets written onto the MiniDisc
        # and onto the label, so this is the last place to look at them
        # before forty minutes of real time goes by.
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
        self.tree.setColumnHidden(COL_DISC, True)  # nothing to say until there is more than one
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
        self.split_btn.setToolTip(
            self.tr("Makes the selected track the first one on a new disc, instead of wherever the split was worked out to go.")
        )
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
        layout.addWidget(self.preview_bar)

        hint = QLabel(
            self.tr(
                "Everything above and in the Title column can be edited, and is what gets written onto the "
                "disc. Fill the Artist column in only on a compilation, where each track has its own."
            )
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.mark_check = QCheckBox(self.tr("Mark tracks through the adapter"))
        self.mark_check.setChecked(True)
        self.mark_check.setToolTip(
            self.tr(
                "Sends a track mark at each track change instead of relying on the deck hearing a gap. This "
                "is the only thing that splits a gapless album correctly -- but turn LEVEL-SYNC off on the "
                "deck when using it, or both will mark the same boundary and leave a stray sliver of a track "
                "between them."
            )
        )
        layout.addWidget(self.mark_check)

        self.multi_check = QCheckBox(self.tr("Record across several discs"))
        self.multi_check.setToolTip(
            self.tr(
                "For an album longer than one disc. Each disc is recorded, titled and ejected on its own, "
                "and you are asked to load the next one -- so nothing waits for you between the last track "
                "and the titles being written."
            )
        )
        self.multi_check.toggled.connect(self._on_multi_toggled)
        self.disc_minutes_spin = QSpinBox()
        self.disc_minutes_spin.setRange(multidisc.MIN_DISC_MINUTES, multidisc.MAX_DISC_MINUTES)
        self.disc_minutes_spin.setValue(multidisc.DEFAULT_DISC_MINUTES)
        self.disc_minutes_spin.setSuffix(self.tr(" min"))
        self.disc_minutes_spin.setToolTip(
            self.tr(
                "How long one disc holds: 80 in SP, 160 in LP2, 320 in LP4. Which mode the deck is in can "
                "neither be read nor set from here, so this is a number you tell it, not one it finds out."
            )
        )
        self.disc_minutes_spin.valueChanged.connect(lambda _value: self._recompute_plan())
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
        self.hide_btn = QPushButton(self.tr("Hide"))
        self.hide_btn.setToolTip(
            self.tr("Hide this window and keep recording in the background -- use \"Show recording "
                    "window\" in the bar at the bottom of the main window to bring it back.")
        )
        self.hide_btn.clicked.connect(self._on_hide_clicked)
        self.buttons.addButton(self.hide_btn, QDialogButtonBox.ButtonRole.ActionRole)
        layout.addWidget(self.buttons)

        self._timer = QTimer(self)
        self._timer.setInterval(POLL_MS)
        self._timer.timeout.connect(self._refresh_progress)

        self._load_items()
        self._refresh_split_button()

    # --- preflight ----------------------------------------------------

    def _load_items(self) -> None:
        if not self._items:
            self.summary_label.setText(self.tr("There are no tracks to record."))
            self.start_btn.setEnabled(False)
            return

        # The album's own order, taken from the files rather than however
        # they happen to have been handed over: a double album dropped in
        # as one folder routinely arrives with its two discs interleaved,
        # because both discs number their tracks from one.
        ordered = tracks.sort_by_disc_and_track(self._items)
        if [item.path for item in ordered] != [item.path for item in self._items]:
            # Whatever the caller handed over is parallel to the *old* order
            # and has to move with it. Record Folder and the Telegram
            # hand-off both pass a track list built from the files as they
            # sat on disk -- so sorting the files alone put one track's
            # title against another track's file, which is what "the tracks
            # are in the wrong order, and so is the split" turned out to be.
            positions = {id(item): index for index, item in enumerate(self._items)}
            permutation = [positions[id(item)] for item in ordered]
            given = self._given_metadata
            if given is not None and len(given.tracks) == len(permutation):
                self._given_metadata = replace(given, tracks=[given.tracks[index] for index in permutation])
            self._items = ordered
        # And where those files say one disc ends. Seeded rather than
        # applied: the checkbox is still the user's to tick (a two-CD album
        # can perfectly well go onto one MiniDisc in LP2), but if they do
        # tick it, the split they get is the album's own rather than one
        # worked out from running times. "Split Automatically" goes back to
        # the arithmetic.
        self._manual_breaks = tracks.disc_breaks(self._items) or None

        # The seed for every field on this dialog. Given metadata wins where
        # there is any (only Record Folder passes it -- see __init__), else
        # the files speak for themselves.
        self._seed = self._given_metadata or tracks.metadata_from_playlist(self._items)
        self._fill_fields(self._seed)

        total = tracks.total_seconds(self._items)
        self.summary_label.setText(
            self.tr(
                "{count} tracks, {total} total.\n"
                "They will be recorded to the disc in this order, then titled from these names."
            ).format(count=len(self._items), total=_mmss(total))
        )
        if self._manual_breaks:
            # Otherwise ticking the box below produces a split nobody asked
            # for and nothing explains where it came from.
            self.summary_label.setText(
                self.summary_label.text()
                + "\n"
                + self.tr(
                    "The files say this is a {count}-disc album, so the disc splits below are already placed "
                    "where they say."
                ).format(count=len(self._manual_breaks) + 1)
            )
        self._ensure_cover()
        # Ticked when the *files* say there is more than one disc, because
        # that is not a guess about anything: the album says what it is, and
        # leaving the box clear meant a table numbered 01..17, 01..17 with
        # the Disc column hidden and nothing on screen explaining it --
        # reported as exactly that. Untick it and the whole thing goes onto
        # one disc, which is what LP2 is for.
        #
        # An album that merely *overruns* 80 minutes is deliberately still
        # not ticked: that one is an assumption about the deck's recording
        # mode, which cannot be read from here (see DISC_SP_SECONDS), and
        # the warning points at the option rather than taking the decision.
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
            # display_title(), not title: an untagged file is recorded under
            # its filename, so that is what this list has to show.
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
        """Frozen while the deck is running. What is on screen at the moment
        recording starts is what will be written afterwards, so letting the
        album be renamed halfway through would only make the two disagree --
        and on a multi-disc run, moving a track or a disc break after the
        first disc is already cut would describe a recording that does not
        exist."""
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
            self.disc_minutes_spin,
        ):
            widget.setEnabled(editable)
        if editable:
            self._refresh_split_button()

    def _ensure_cover(self) -> None:
        """Finds the artwork now, before the recording, rather than after.

        It used to be looked up once the album had finished playing, which
        is the worst possible moment to discover the search matched the
        wrong release: nothing could be done about it except retype the
        album and try again. Here it is on screen while the user can still
        correct the name, or click the picture and point at the right
        sleeve."""
        if self.cover_label.data:
            return  # already came with the metadata (Record Folder does this)
        if self._seed.is_compilation():
            # A mixtape has no sleeve to look up, and looking one up anyway
            # is worse than having none: a search for "Various Artists"
            # returns an unrelated record's artwork. One is drawn from the
            # track list instead.
            self.cover_label.set_cover(mixtape_cover.render_cover(self._seed))
            return
        chosen = fetch_into(
            self.cover_label, self.artist_edit.text(), self.album_edit.text(), len(self._items)
        )
        if chosen is not None and not self.year_spin.value() and chosen.year:
            self.year_spin.setValue(chosen.year)
        if not self.cover_label.data:
            # Last resort: the sleeve the files themselves carry.
            self.cover_label.set_cover(embedded_cover.cover_from_files(i.path for i in self._items if i.path))

    # --- the split ----------------------------------------------------

    def _plan_tracks(self) -> list[Track]:
        """The album as something multidisc.split_discs can weigh.

        Built from the *items*, not from the tree: what decides the split is
        how long each track runs, and that is a fact about the file, not
        something the Title column can be edited into disagreeing with."""
        return [
            Track(title=item.display_title(), time_seconds=item.length_seconds or 0)
            for item in self._items
        ]

    def _multi(self) -> bool:
        """Several discs *in practice* -- the option on and a plan that
        really does have more than one. An album that fits keeps the plain
        single-disc behaviour whatever the checkbox says, so nothing
        downstream has to ask twice."""
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
                "That is {over} more than one disc holds. Split it again, or set the deck to a longer mode "
                "and say so above."
            ).format(over=_mmss(self._plan.overflow_seconds))
        self.split_label.setText(text)
        self.split_label.setVisible(True)

    def _refresh_warning(self) -> None:
        """The one-disc warning, which the multi-disc option supersedes."""
        total = tracks.total_seconds(self._items)
        if self._multi() or total <= DISC_SP_SECONDS:
            self.warning_label.setVisible(False)
            return
        self.warning_label.setText(
            self.tr(
                "This is longer than the {limit} an MD holds in SP mode. Set the deck to LP2 first, turn on "
                '"Record across several discs" below, or the recording will be cut short.'
            ).format(limit=_mmss(DISC_SP_SECONDS))
        )
        self.warning_label.setVisible(True)

    def _refresh_split_button(self) -> None:
        """Says which of the two things it would do to the selected track,
        rather than leaving the user to guess whether pressing it adds or
        removes a break."""
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
        """Puts a disc break at the selected track, or takes one away.

        It starts from the breaks currently *on screen*, not from none: a
        three-disc album has two boundaries, and moving one of them must not
        throw the other away and leave the user placing all of them by hand.
        So moving a boundary is placing the new one and then removing the
        old, which is what the button's own text spells out for whichever
        track is selected.

        Doing this once switches the whole split to manual and leaves it
        there -- the arithmetic would otherwise put its own break back the
        moment anything else changed, which is exactly what the user just
        said they did not want."""
        row = self._selected_row()
        if row <= 0:  # the first track always starts the first disc
            return
        breaks = set(self._current_breaks())
        breaks.discard(row) if row in breaks else breaks.add(row)
        self._manual_breaks = sorted(breaks)
        self._recompute_plan()

    def _auto_split(self) -> None:
        self._manual_breaks = None
        self._recompute_plan()

    def _move_selected(self, delta: int) -> None:
        """Moves the selected track one place up or down.

        The seed's own track list moves with it: everything downstream pairs
        the two lists by index, so leaving the seed behind would put one
        track's title against another track's file the moment anything fell
        back on it. Disc breaks are plain positions and deliberately stay
        where they are -- dragging a track across one is how a track is
        moved to the other disc."""
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

    # --- recording ----------------------------------------------------

    def _start(self) -> None:
        if not self._items:
            return
        if not self._confirm_overwrite():
            return
        self.preview_bar.stop()
        self._player = audio_engine.AudioPlayer(
            device=audio_engine.resolve_output_device(app_settings.audio_output_device()),
            gain_db=app_settings.recording_gain_db(),
        )

        self._disc = 0
        self.start_btn.setEnabled(False)
        self.erase_btn.setEnabled(False)
        self.mark_check.setEnabled(False)
        self._set_fields_editable(False)
        self.close_btn.setText(self.tr("Stop"))
        self.progress.setVisible(True)
        self.status_label.setVisible(True)
        self._begin_disc()

    def _begin_disc(self) -> None:
        """Arms the deck for one disc and starts its lead-in. Called once
        for an ordinary album, and once per disc for a long one."""
        if not self._arm_deck():
            return
        self._recording = True
        self._current_local_index = 0
        self.progress.setValue(0)
        self.running_changed.emit(True)
        # Decoded, resampled and dithered *before* the pause is released --
        # otherwise the deck sits running into silence for however long
        # that takes (several seconds, for a whole disc's worth of tracks)
        # instead of just the deliberate LEAD_IN_MS below.
        # _report_decode_progress keeps the status label moving meanwhile,
        # so this doesn't read as the dialog having hung. Dithered via
        # load_for_recording(), not load_for_playback() -- the deck's own
        # digital S/PDIF input takes exactly Red Book PCM, the same as a
        # CD-R burn (see audio_engine.load_for_recording()'s own
        # docstring).
        first, last = self._disc_bounds()
        paths = [Path(item.path) for item in self._items[first : last + 1]]
        try:
            buffers = audio_engine.load_for_recording(
                paths, samplerate=self._player.samplerate, on_progress=self._report_decode_progress
            )
        except audio_engine.AudioEngineError as exc:
            self._fail(self.tr("Could not decode the album for playback: {error}").format(error=exc))
            return
        if not self._send_key("SEND PAUSE"):  # releases record-pause
            return
        self.status_label.setText(
            self.tr("Recording disc {number} -- waiting for the first track...").format(number=self._disc + 1)
            if self._multi()
            else self.tr("Recording started -- waiting for the first track...")
        )
        # Pause released first, playback a moment later: the deck is then
        # already running when audio arrives. The buffers are already
        # decoded, so nothing but this deliberate gap delays it now.
        QTimer.singleShot(LEAD_IN_MS, lambda: self._begin_playback(buffers))

    def _confirm_overwrite(self) -> bool:
        if self._multi() and self._plan is not None:
            text = self.tr(
                "This album takes {count} discs. Each one is recorded, titled and ejected on its own, and "
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
            self.tr("Record to MiniDisc"),
            text,
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        return answer == QMessageBox.StandardButton.Ok

    def _arm_deck(self) -> bool:
        """RECORD puts the deck into record-pause, then the user confirms it
        actually did. There is no feedback channel, so without asking, a
        RECORD that never arrived would mean playing a whole album into a
        deck that isn't recording -- and only finding out 40 minutes later."""
        try:
            self._deck = mdrem.MDRemClient(self._port)
            self._deck.open()
        except mdrem.MDRemError as exc:
            self._deck = None
            self._fail(self.tr("MDRem: {error}").format(error=exc))
            return False
        if not self._send_key("SEND RECORD"):
            return False

        answer = QMessageBox.question(
            self,
            self.tr("Record to MiniDisc"),
            self.tr(
                "The deck was told to start recording.\n\nIs it now showing record-pause (REC lit, paused)?"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            return True
        self._send_key("SEND STOP")
        # Back to the state the dialog was in before Start, rather than just
        # stopping: the deck not arming is something to fix and try again,
        # and on a multi-disc run the button has already been disabled.
        self._fail(self.tr("Cancelled -- the deck was not recording."))
        return False

    def _begin_playback(self, buffers: list) -> None:
        if not self._recording or self._player is None:
            return
        self._player.play(
            buffers,
            on_track_boundary=self._bridge.track_boundary.emit,
            on_finished=self._bridge.finished.emit,
        )
        self._timer.start()

    def _report_decode_progress(self, index: int, total: int, path: Path) -> None:
        """`load_for_recording`'s own callback, called synchronously from
        inside its decode loop -- decoding a whole disc up front (see
        _begin_disc) can take a few real seconds, and processEvents() is
        what actually lets the label repaint mid-loop, since nothing else
        returns to the event loop until decoding finishes."""
        self.status_label.setText(
            self.tr("Preparing track {index} of {total}: {name}...").format(
                index=index, total=total, name=path.stem
            )
        )
        QCoreApplication.processEvents()

    def _disc_bounds(self) -> tuple[int, int]:
        """The item indices the disc being recorded covers, as [first, last].
        The whole album when there is only one disc."""
        disc = self._current_disc()
        if disc is None or not self._multi():
            return 0, len(self._items) - 1
        return disc.first_index, disc.last_index

    def _current_disc(self) -> multidisc.DiscPlan | None:
        if self._plan is None or not 0 <= self._disc < self._plan.count:
            return None
        return self._plan.discs[self._disc]

    def _on_track_boundary(self, local_index: int) -> None:
        """Fired by AudioPlayer (via PlaybackBridge) the instant playback
        crosses into the buffer at `local_index`, sample-accurately -- see
        the module docstring for what this replaces.

        Never fires for `local_index == 0`: AudioPlayer only calls this on
        a transition *into* a later buffer, so the disc's first track
        (which the deck already opens one of when recording starts) is
        never marked again here, with no special-casing needed for it."""
        self._current_local_index = local_index
        if self.mark_check.isChecked():
            self._send_key(TRACK_MARK_KEY)

    def _refresh_progress(self) -> None:
        if not self._recording or self._player is None:
            return
        first, last = self._disc_bounds()
        current = first + self._current_local_index
        done = sum(item.length_seconds for item in self._items[first:current])
        elapsed = done + self._player.position_seconds
        total = max(1, sum(item.length_seconds for item in self._items[first : last + 1]))
        overall_fraction = min(1.0, elapsed / total)
        self.progress.setValue(int(1000 * overall_fraction))
        title = self._items[current].display_title() if 0 <= current < len(self._items) else ""
        track_seconds = self._items[current].length_seconds if 0 <= current < len(self._items) else 0
        track_fraction = min(1.0, self._player.position_seconds / max(1, track_seconds))
        if self._multi() and self._plan is not None:
            text = self.tr("Disc {disc} of {discs}, track {index} of {count}: {title} -- {elapsed} of {total}").format(
                disc=self._disc + 1,
                discs=self._plan.count,
                index=current - first + 1,
                count=last - first + 1,
                title=title,
                elapsed=_mmss(elapsed),
                total=_mmss(total),
            )
        else:
            text = self.tr("Recording {index} of {count}: {title} -- {elapsed} of {total}").format(
                index=current + 1,
                count=len(self._items),
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

    def _on_disc_finished(self) -> None:
        """The end of a disc -- which for an ordinary album is the end of
        the recording, and for a long one is the end of one of several.

        Fired by AudioPlayer once every buffer it was given has played out
        -- unlike the old poll loop, there is no "stopped partway through"
        state to detect here: AudioPlayer always plays its whole queue to
        completion unless `.stop()` is called (which `reject()` does, and
        which does not fire this)."""
        self._timer.stop()
        self._recording = False
        self._send_key("SEND STOP")
        # Closed before the titling dialog runs: it opens its own connection
        # to the same port, which this one would still be holding.
        self._close_deck()
        self.progress.setValue(1000)

        self._capture_metadata()
        if not self._multi():
            self.close_btn.setText(self.tr("Close"))
            self.mark_check.setEnabled(True)
            self.status_label.setText(
                self.tr("Recording finished. Writing titles now -- leave the adapter pointing at the deck.")
            )
            # Two seconds, so the deck has finished writing its TOC after
            # STOP and will take the titling keys -- same reasoning as the
            # multi-disc wait just below.
            QTimer.singleShot(TITLING_DELAY_MS, self._title_single_disc)
            return

        self.status_label.setText(
            self.tr("Disc {number} recorded. Writing its titles now -- leave the adapter pointing at the deck.").format(
                number=self._disc + 1
            )
        )
        # Two seconds, so the deck has finished writing its TOC after STOP
        # and will take the titling keys.
        QTimer.singleShot(TITLING_DELAY_MS, self._title_current_disc)

    def _begin_nested_titling(self, dialog: MDRemUploadDialog) -> None:
        """Proxies the titling dialog's own overall_progress_changed/
        visibility_changed straight through as this dialog's own -- but
        deliberately *not* running_changed (see the class-level comment).
        The -1.0 sentinel hides the per-track row in MainWindow's bar:
        titling has no per-track concept, and the next disc's first
        _refresh_progress() tick naturally un-hides it."""
        dialog.overall_progress_changed.connect(self.overall_progress_changed)
        dialog.visibility_changed.connect(self.visibility_changed)
        self._nested_dialog = dialog
        self.track_progress_changed.emit(-1.0, "")

    def _end_nested_titling(self) -> None:
        self._nested_dialog = None

    def _title_single_disc(self) -> None:
        """Writes the album's titles and ejects, unattended -- nobody sits
        through a whole recording, so a confirmation between the music
        ending and the titles going out would leave the deck holding an
        untitled disc until somebody came back. Same reasoning
        _title_current_disc() already applies per-disc on a multi-disc
        run; this is that same treatment for the ordinary, single-disc
        case, which used to ask twice (write titles now? then eject?)."""
        metadata = self.result_metadata or tracks.metadata_from_playlist(self._items)
        # A disc that was just recorded has no titles to erase, and erasing
        # is roughly half the total time.
        dialog = MDRemUploadDialog(metadata, self._port, self, clear_default=False, unattended=True)
        self._begin_nested_titling(dialog)
        exec_hideable(dialog)
        self._end_nested_titling()
        if dialog.succeeded:
            self.status_label.setText(self.tr("Recording finished. Titles written and the disc ejected."))
        else:
            self.status_label.setText(
                self.tr(
                    "Recording finished, but the titles could not be written. The disc itself is fine -- "
                    "the titles can be written again from Tools > Metadata..."
                )
            )
        self.running_changed.emit(False)

    def _title_current_disc(self) -> None:
        """Writes this disc's titles, ejects it, and asks for the next --
        none of it confirmed beforehand, because nobody is here. See the
        module docstring for what that trades away and where it is paid
        back."""
        disc = self._current_disc()
        if disc is None or self._plan is None:
            self._finish_run(self.tr("Recording finished."))
            return

        dialog = MDRemUploadDialog(
            self._disc_metadata(disc), self._port, self, clear_default=False, unattended=True
        )
        self._begin_nested_titling(dialog)
        exec_hideable(dialog)
        self._end_nested_titling()
        if not dialog.succeeded:
            self._finish_run(
                self.tr(
                    "Disc {number} was recorded, but its titles could not be written, so the run stopped "
                    "there. The disc itself is fine -- the titles can be written again from Tools > "
                    "Metadata..."
                ).format(number=disc.number)
            )
            return

        if self._disc + 1 >= self._plan.count:
            self._finish_run(
                self.tr("All {count} discs are recorded, titled and ejected.").format(count=self._plan.count)
            )
            return

        if not self._ask_for_next_disc():
            self._finish_run(
                self.tr("Stopped after disc {number}. The discs already recorded are finished and titled.").format(
                    number=disc.number
                )
            )
            return
        self._disc += 1
        self.progress.setValue(0)
        self._begin_disc()

    def _ask_for_next_disc(self) -> bool:
        answer = QMessageBox.question(
            self,
            self.tr("Record to MiniDisc"),
            self.tr(
                "Disc {done} of {count} is written, titled and ejected.\n\nPut a blank disc in the deck and "
                "close the tray, then continue to record disc {next}."
            ).format(done=self._disc + 1, count=self._plan.count if self._plan else 1, next=self._disc + 2),
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Ok,
        )
        return answer == QMessageBox.StandardButton.Ok

    def _finish_run(self, message: str) -> None:
        """The single place a run ends, however it ended."""
        self._timer.stop()
        self._recording = False
        self._close_deck()
        self.close_btn.setText(self.tr("Close"))
        self.mark_check.setEnabled(True)
        self.status_label.setVisible(True)
        self.status_label.setText(message)
        self.running_changed.emit(False)

    def _capture_metadata(self) -> None:
        """Reads the dialog back as the project's metadata.

        The widgets are the source, not the files, because the user has
        been able to correct them since they were loaded -- and the artwork
        was already settled at that point too (see _ensure_cover), so
        nothing here goes near the network. That matters for more than
        speed: this runs the instant an album finishes playing, and a
        lookup that hung there would hold up the offer to write the titles.

        It describes the whole album, every disc of it, because that is what
        the label is for -- the per-disc slices titling needs are cut from
        it by _disc_metadata()."""
        metadata = replace(
            self._seed,
            artist=self.artist_edit.text().strip(),
            album=self.album_edit.text().strip(),
            year=self.year_spin.value() or None,
            cover_art=self.cover_label.data,
            tracks=self._tracks_from_tree(),
        )
        self.result_metadata = metadata

    def _disc_metadata(self, disc: multidisc.DiscPlan) -> ProjectMetadata:
        """What one disc gets titled with: its own tracks, and an album name
        that says which disc it is.

        The tracks are sliced out of the captured whole rather than taken
        from the plan, so a title corrected in the table before recording is
        the one that reaches the deck. They are also renumbered by being
        sliced: track 16 of the album is track 1 of disc 2, and the deck
        numbers its own tracks from one whatever the album thinks.

        The "[1/2]" is not decoration -- two discs of the same album titled
        identically are indistinguishable on a shelf, and the disc title is
        the only text a MiniDisc carries about itself."""
        base = self.result_metadata or self._seed
        total = self._plan.count if self._plan is not None else 1
        album = base.album
        if total > 1:
            album = f"{album} [{disc.number}/{total}]".strip()
        return replace(base, album=album, tracks=list(base.tracks[disc.first_index : disc.last_index + 1]))

    def _tracks_from_tree(self) -> list[Track]:
        """One Track per row, from the Title and Artist columns.

        The Artist column is read as well as the Title, and that is not
        decoration: rebuilding tracks without it would drop every performer
        on a compilation, which is the one thing that makes it a compilation
        (see ProjectMetadata.is_compilation) -- the disc would silently stop
        being a mixtape for having been looked at. The same mistake was
        found and fixed in MetadataDialog once already.

        Built one per item rather than one per seed track: the items are
        what is actually going onto the disc, so if the two ever disagreed
        about how many tracks there are, it is the items that are right."""
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
        """Erase MiniDisc... -- clears whatever disc is currently in the
        deck. Used to be a standalone Recording menu entry, reachable
        whether or not this dialog was even open; moved here since erasing
        the wrong disc is most likely to come up right before recording
        onto it. Reuses this dialog's own port rather than resolving a
        fresh one -- it is already known, and there is only ever one deck
        to erase. Disabled for the duration of an actual recording (see
        _start/_fail), so it can't be reached while the deck is busy."""
        EraseDiscDialog(self._port, self).exec()

    # --- helpers ------------------------------------------------------

    def _send_key(self, command: str) -> bool:
        """Uses the connection opened for the session -- see _deck."""
        if self._deck is None:
            self._fail(self.tr("MDRem: not connected"))
            return False
        try:
            self._deck.command(command)
            return True
        except mdrem.MDRemError as exc:
            self._fail(self.tr("MDRem: {error}").format(error=exc))
            return False

    def _close_deck(self) -> None:
        if self._deck is not None:
            self._deck.close()
            self._deck = None

    def _fail(self, message: str) -> None:
        self._timer.stop()
        self._recording = False
        if self._player is not None:
            self._player.stop()
        self._close_deck()
        self.progress.setVisible(False)
        self.status_label.setVisible(True)
        self.status_label.setText(message)
        self.close_btn.setText(self.tr("Close"))
        self.start_btn.setEnabled(True)
        self.erase_btn.setEnabled(True)
        self.mark_check.setEnabled(True)
        self._set_fields_editable(True)
        self.running_changed.emit(False)

    def request_stop(self) -> None:
        """What MainWindow's own Stop button calls -- dispatches to the
        nested titling dialog if one is open (this dialog's own reject()
        would do nothing useful once recording has already finished and
        titling has taken over), otherwise stops the recording itself."""
        if self._nested_dialog is not None:
            self._nested_dialog.request_stop()
        else:
            self.reject()

    def request_show(self) -> None:
        """The other half of request_stop()'s dispatch: while titling is
        under way it is the nested dialog that is hidden, not this one."""
        if self._nested_dialog is not None:
            self._nested_dialog.request_show()
        else:
            self.show_requested.emit()

    def _on_hide_clicked(self) -> None:
        hide_for_background(self)

    def reject(self) -> None:
        """Stopping mid-recording has to stop both ends -- leaving the deck
        recording silence after playback has stopped would append a long
        empty track to the disc."""
        self.preview_bar.stop()
        if self._recording:
            self._timer.stop()
            self._recording = False
            if self._player is not None:
                self._player.stop()
            self._send_key("SEND STOP")
            self.running_changed.emit(False)
        self._close_deck()
        super().reject()
