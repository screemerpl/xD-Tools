"""Recording > "Record to MiniDisc from foobar2000..." -- records an album
from foobar2000 onto a MiniDisc over S/PDIF, then titles the result.

The sequence, and why each step is where it is:

  1. read the current foobar playlist (this is what will be recorded, so it
     is also where the titles come from -- not an iTunes lookup, which
     returns whatever release the search matched)
  2. force playback order to straight-through-once, or the disc would end
     up in a different order than the titles
  3. arm the deck (RECORD -> record-pause) and *ask the user to confirm it*
  4. release the pause, then a moment later start playback -- in that
     order, so the deck is already recording when the first note arrives
  5. poll foobar until the playlist ends
  6. stop the deck, then hand off to the normal Upload Tracklist dialog

Deliberately no worker thread: every step here is either instantaneous
(one HTTP call to localhost, one infrared frame) or a poll driven by a
QTimer. The genuinely long part -- writing the titles -- already has its
own threaded dialog, which this reuses rather than reimplements.

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
recorded in, which means the order foobar2000 plays it in -- so a reordered
table rebuilds foobar's playlist from the files themselves before anything
starts (see _apply_order_to_foobar). That is the one blocking step in this
dialog, and it only ever happens after the user has actually moved a row.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QApplication,
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

from mdtools import app_settings, embedded_cover, foobar, mdrem, mixtape_cover, multidisc
from mdtools.panels.cover_preview import CoverPreview, fetch_into
from mdtools.panels.mdrem_upload_dialog import MDRemUploadDialog
from mdtools.project import ProjectMetadata, Track

# An MD holds 80 minutes in SP. The deck also has MDLP (LP2/LP4) for 160/320,
# but which mode it is in cannot be read or set through our key table, so this
# only ever warns -- it never decides.
DISC_SP_SECONDS = 80 * 60

# The deck is told to start recording before playback begins, so the first
# note is never clipped; the gap becomes a moment of leading silence.
LEAD_IN_MS = 1500

# Also how late a track mark can land: it is sent on the poll that first
# sees a new track, so a slower poll pushes the mark further into it.
POLL_MS = 250

# Multi-disc only: how long after the album's last track ends before the
# titles start going out. The deck has just been sent STOP and writes its
# TOC before it will take anything else; two seconds is the user's own
# number, and short enough that nobody has to be standing there.
TITLING_DELAY_MS = 2000

# Applied to foobar2000's own output volume at the start of every recording
# (see _start() below) -- a layout choice, not a measured spec, the same
# kind of deliberate headroom-below-0dB margin as any other digital transfer
# leaves before recording, explicit user request. Set through
# FoobarClient.set_volume(), confirmed live against a running foobar2000/
# foo_beefweb.
RECORDING_VOLUME_DB = -5.0

# RECORD pressed *during* recording adds a track mark -- established on an
# MDS-JE480 by recording, sending it mid-way, and finding two tracks.
TRACK_MARK_KEY = "SEND RECORD"

# The track table's columns. Named rather than counted, because the Disc
# column was added in front of the other four and every read of a row is
# now one index off what it used to be.
COL_DISC, COL_NUMBER, COL_TITLE, COL_ARTIST, COL_LENGTH = range(5)


def _mmss(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


class RecordDialog(QDialog):
    def __init__(
        self,
        port: str,
        base_url: str = foobar.DEFAULT_BASE_URL,
        parent=None,
        metadata: ProjectMetadata | None = None,
    ):
        """`metadata`, when given, is what the disc gets titled from instead
        of the playlist's own tags.

        Only Record Folder passes it, and only because it has to: a folder
        holds somebody else's files, which nothing here rewrites, so an
        album name typed into that dialog can reach the disc no other way.
        The CD flow deliberately does *not* -- it writes its titles into the
        files it created, so the playlist already carries them, and one
        source of truth beats two that can disagree. Either way it describes
        the very playlist that is about to be recorded: it is built from the
        same items, moments earlier."""
        super().__init__(parent)
        self.setWindowTitle(self.tr("Record to MiniDisc from foobar2000"))
        self.resize(560, 560)
        self._port = port
        self._client = foobar.FoobarClient(base_url)
        self._playlist: foobar.Playlist | None = None
        self._items: list[foobar.PlaylistItem] = []
        self._recording = False
        self._started = False  # playback has actually been seen running
        self._highest_index = -1
        self._marked_index = -1
        # Several discs: the plan, which disc is being recorded, and whether
        # foobar has already been told to stop at this disc's last track.
        self._plan: multidisc.MultiDiscPlan | None = None
        self._disc = 0
        self._stop_armed = False
        # None means "wherever the arithmetic puts them"; a list means the
        # user has placed the breaks by hand and they are not to be moved.
        self._manual_breaks: list[int] | None = None
        # Set by the Up/Down buttons. Until it is, foobar's playlist and
        # this table are the same order and there is nothing to push back.
        self._order_changed = False
        # Read by MainWindow after exec(): the playlist that was recorded,
        # as project metadata, with cover art if any was found. None means
        # nothing was recorded, so nothing should be adopted.
        self.result_metadata: ProjectMetadata | None = None
        self._given_metadata = metadata
        # Held open for the whole session rather than reopened per key:
        # opening a serial port costs far more than sending, and a track
        # mark's accuracy depends on how fast it goes out.
        self._deck: mdrem.MDRemClient | None = None

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

        self.up_btn = QPushButton(self.tr("Move Up"))
        self.up_btn.clicked.connect(lambda: self._move_selected(-1))
        self.down_btn = QPushButton(self.tr("Move Down"))
        self.down_btn.clicked.connect(lambda: self._move_selected(1))
        for button in (self.up_btn, self.down_btn):
            button.setToolTip(
                self.tr(
                    "Changes the order the album is recorded in. foobar2000's playlist is rebuilt to match "
                    "when recording starts, so this needs the tracks to be files on disk."
                )
            )
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
        self.start_btn = QPushButton(self.tr("Start Recording"))
        self.start_btn.clicked.connect(self._start)
        self.buttons.addButton(self.start_btn, QDialogButtonBox.ButtonRole.AcceptRole)
        self.close_btn = QPushButton(self.tr("Cancel"))
        self.close_btn.clicked.connect(self.reject)
        self.buttons.addButton(self.close_btn, QDialogButtonBox.ButtonRole.RejectRole)
        layout.addWidget(self.buttons)

        self._timer = QTimer(self)
        self._timer.setInterval(POLL_MS)
        self._timer.timeout.connect(self._poll)

        self._load_playlist()
        self._refresh_split_button()

    # --- preflight ----------------------------------------------------

    def _load_playlist(self) -> None:
        try:
            self._playlist = self._client.current_playlist()
            if self._playlist is not None:
                self._items = self._client.playlist_items(self._playlist.id)
        except foobar.FoobarError as exc:
            self.summary_label.setText(
                self.tr(
                    "Could not reach foobar2000: {error}\n\nIt must be running with the Beefweb Remote "
                    "Control component (foo_beefweb) enabled."
                ).format(error=exc)
            )
            self.start_btn.setEnabled(False)
            return

        if not self._items:
            self.summary_label.setText(self.tr("foobar2000's current playlist is empty -- load the album first."))
            self.start_btn.setEnabled(False)
            return

        # The album's own order, taken from the files rather than from
        # however they happen to sit in foobar2000: a double album dropped
        # in as one folder arrives with its two discs interleaved, because
        # foobar sorts by filename and both discs number their tracks from
        # one. Marking the order as changed is what gets that pushed back
        # into foobar before recording -- without it the table would be
        # right and the recording would still follow foobar's own order.
        ordered = foobar.sort_by_disc_and_track(self._items)
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
                self._given_metadata = replace(
                    given, tracks=[given.tracks[index] for index in permutation]
                )
            self._items = ordered
            self._order_changed = True
        # And where those files say one disc ends. Seeded rather than
        # applied: the checkbox is still the user's to tick (a two-CD album
        # can perfectly well go onto one MiniDisc in LP2), but if they do
        # tick it, the split they get is the album's own rather than one
        # worked out from running times. "Split Automatically" goes back to
        # the arithmetic.
        self._manual_breaks = foobar.disc_breaks(self._items) or None

        # The seed for every field on this dialog. Given metadata wins where
        # there is any (only Record Folder passes it -- see __init__), else
        # the playlist speaks for itself.
        self._seed = self._given_metadata or foobar.metadata_from_playlist(self._items)
        self._fill_fields(self._seed)

        total = foobar.total_seconds(self._items)
        self.summary_label.setText(
            self.tr(
                'Playlist "{playlist}" -- {count} tracks, {total} total.\n'
                "It will be recorded to the disc in this order, then titled from these names."
            ).format(playlist=self._playlist.title, count=len(self._items), total=_mmss(total))
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
        if self._order_changed:
            # Put foobar into that order now rather than at Start. It has to
            # happen before recording either way -- what this buys is that
            # the playlist on screen in foobar2000 agrees with the table
            # here from the moment the dialog opens, instead of the two
            # disagreeing until a button is pressed. Deferred by a
            # zero-delay timer so the window is up (and the status line
            # readable) while it runs, since the rebuild blocks.
            QTimer.singleShot(0, self._push_order_now)
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
            # Last resort: the sleeve the files themselves carry. Reachable
            # here because %path% is in the playlist's column set, so this
            # covers a plain foobar playlist as well as a loaded folder --
            # see embedded_cover for why it ranks below the search.
            self.cover_label.set_cover(embedded_cover.cover_from_files(i.path for i in self._items if i.path))

    # --- the split ----------------------------------------------------

    def _plan_tracks(self) -> list[Track]:
        """The playlist as something multidisc.split_discs can weigh.

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
        tracks = self._plan_tracks()
        if not self.multi_check.isChecked():
            self._plan = multidisc.plan_from_breaks(tracks, [], capacity)
        elif self._manual_breaks is None:
            self._plan = multidisc.split_discs(tracks, capacity)
        else:
            self._plan = multidisc.plan_from_breaks(tracks, self._manual_breaks, capacity)
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
        total = foobar.total_seconds(self._items)
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
            tracks = list(self._seed.tracks)
            tracks[row], tracks[target] = tracks[target], tracks[row]
            self._seed = replace(self._seed, tracks=tracks)
        moved = self.tree.takeTopLevelItem(row)
        self.tree.insertTopLevelItem(target, moved)
        self.tree.setCurrentItem(moved)
        self._order_changed = True
        self._recompute_plan()

    # --- recording ----------------------------------------------------

    def _start(self) -> None:
        if not self._items:
            return
        if not self._confirm_overwrite():
            return
        if not self._apply_order_to_foobar():
            return
        try:
            self._client.prepare_for_recording()
            self._client.set_volume(RECORDING_VOLUME_DB)
            self._client.stop()
        except foobar.FoobarError as exc:
            self._fail(self.tr("foobar2000: {error}").format(error=exc))
            return

        self._disc = 0
        self.start_btn.setEnabled(False)
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
        first, _last = self._disc_bounds()
        self._recording = True
        self._started = False
        self._stop_armed = False
        self._highest_index = first - 1
        # The deck opens a track of its own when recording starts, so the
        # first track of *every* disc must not be marked again.
        self._marked_index = first
        self.progress.setValue(0)
        self.status_label.setText(
            self.tr("Recording disc {number} -- waiting for the first track...").format(number=self._disc + 1)
            if self._multi()
            else self.tr("Recording started -- waiting for the first track...")
        )
        # Pause released first, playback a moment later: the deck is then
        # already running when audio arrives.
        QTimer.singleShot(LEAD_IN_MS, self._begin_playback)

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

    def _push_order_now(self) -> None:
        """The sort's other half: getting it into foobar2000.

        Called once, from _load_playlist, and only when sorting actually
        moved something. A failure here is not fatal -- it says so and
        leaves the order pending, so Start tries again and refuses rather
        than recording something this list does not describe."""
        if not self._order_changed:
            return
        if self._apply_order_to_foobar():
            self.status_label.setVisible(True)
            self.status_label.setText(
                self.tr("foobar2000's playlist is now in this order -- the album's own, from the files.")
            )

    def _apply_order_to_foobar(self) -> bool:
        """Pushes a reordered table back into foobar2000, by rebuilding its
        playlist from the files in this order.

        Nothing else would do: the recording is foobar playing its own
        playlist, so a table reordered only here would title the disc in one
        order and record it in another -- which is not hypothetical, it was
        reported from a live recording that put the wrong track on a disc.
        The rebuild goes through foobar's command line rather than Beefweb,
        which refuses any file outside foobar's own configured music folders
        (a 403 that, on a normal install, applies to every file there is),
        and `replace_current_playlist()` reads the resulting order back and
        insists on it -- foobar sorts an incoming batch by filename, so the
        order asked for is emphatically not the order that lands.

        This is the one blocking call in this dialog. It only ever runs
        after the user has actually moved a row, and only once per
        recording."""
        if not self._order_changed:
            return True
        paths = [item.path for item in self._items]

        # Moving the items is the right way round and is tried first: it
        # touches no files, clears nothing, and leaves the playlist intact
        # if it fails. The rebuild below is the fallback, and it is a
        # heavier and more destructive thing -- it empties the playlist
        # before it can refill it.
        if self._playlist is not None:
            try:
                if foobar.reorder_playlist(self._client, self._playlist.id, paths):
                    self._order_changed = False
                    return True
            except foobar.FoobarError:
                pass  # say nothing yet; the rebuild may still manage it

        if not all(paths):
            QMessageBox.warning(
                self,
                self.tr("Record to MiniDisc"),
                self.tr(
                    "Some of these entries are not files on disk, so the new order cannot be given to "
                    "foobar2000. Put the playlist in the order you want there instead."
                ),
            )
            return False
        exe = self._resolve_foobar_exe()
        if exe is None:
            return False

        self.status_label.setVisible(True)
        self.status_label.setText(self.tr("Putting foobar2000's playlist into this order..."))
        # Repainted by hand: the rebuild below blocks this thread, so
        # without it the message above would never reach the screen.
        QApplication.processEvents()
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            playlist = foobar.replace_current_playlist(self._client, exe, paths)
        except foobar.FoobarError as exc:
            QMessageBox.warning(
                self,
                self.tr("Record to MiniDisc"),
                self.tr("foobar2000 could not be given the new order: {error}").format(error=exc),
            )
            return False
        finally:
            QApplication.restoreOverrideCursor()

        self._playlist = playlist
        self._order_changed = False
        return True

    def _resolve_foobar_exe(self) -> str | None:
        """The same check the CD and folder flows make, for the same reason
        -- Beefweb cannot be handed a file outside foobar's own configured
        music directories."""
        exe = app_settings.foobar_exe() or (foobar.find_foobar_exe() or "")
        if exe and Path(exe).is_file():
            if not app_settings.foobar_exe():
                app_settings.set_foobar_exe(exe)
            return exe
        QMessageBox.warning(
            self,
            self.tr("Record to MiniDisc"),
            self.tr(
                "foobar2000 could not be found, so its playlist cannot be reordered. Set its location in "
                "Window > Settings..., or put the playlist in the order you want in foobar2000 itself."
            ),
        )
        return None

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

    def _begin_playback(self) -> None:
        if not self._recording or self._playlist is None:
            return
        if not self._send_key("SEND PAUSE"):  # releases record-pause
            return
        first, last = self._disc_bounds()
        try:
            # Cleared explicitly rather than trusted: prepare_for_recording()
            # clears it once, at the start of the whole run, which says
            # nothing about what the disc before this one left set.
            self._client.set_stop_after_current_track(False)
            self._client.play(self._playlist.id, first)
            if self._multi() and first == last:
                # A one-track disc has no later transition to notice, so the
                # boundary has to be armed straight away.
                self._client.set_stop_after_current_track(True)
                self._stop_armed = True
        except foobar.FoobarError as exc:
            self._fail(self.tr("foobar2000: {error}").format(error=exc))
            return
        self._timer.start()

    def _disc_bounds(self) -> tuple[int, int]:
        """The playlist indices the disc being recorded covers, as
        [first, last]. The whole playlist when there is only one disc."""
        disc = self._current_disc()
        if disc is None or not self._multi():
            return 0, len(self._items) - 1
        return disc.first_index, disc.last_index

    def _current_disc(self) -> multidisc.DiscPlan | None:
        if self._plan is None or not 0 <= self._disc < self._plan.count:
            return None
        return self._plan.discs[self._disc]

    def _poll(self) -> None:
        try:
            state = self._client.player_state()
        except foobar.FoobarError as exc:
            self._fail(self.tr("Lost contact with foobar2000: {error}").format(error=exc))
            return

        if state.is_playing or state.playback_state == foobar.PAUSED:
            _first, last = self._disc_bounds()
            if self._multi() and state.item_index > last:
                # The stop-after-this-track flag did not take. Ending the
                # disc here costs a fraction of the next track recorded onto
                # the end of this one; letting it run would put the whole of
                # the next disc there.
                try:
                    self._client.stop()
                except foobar.FoobarError:
                    pass
                self._disc_finished()
                return
            self._mark_if_new_track(state.item_index)
            self._started = True
            self._highest_index = max(self._highest_index, state.item_index)
            self._arm_stop_if_last(state.item_index)
            self._show_progress(state)
            return

        # Stopped. Before playback ever started this is just the gap between
        # play() and foobar actually running, not the end of the album.
        if self._started:
            self._disc_finished()

    def _arm_stop_if_last(self, index: int) -> None:
        """Tells foobar2000 to stop when this track ends, once the disc's
        last track is the one playing.

        Armed on the transition *into* the last track rather than left set
        for the whole disc, because the flag applies to whatever is playing
        when it is read -- setting it at the start would end the disc after
        its first track. The same reasoning, and the same mechanism, as the
        cassette's side break."""
        if not self._multi() or self._stop_armed:
            return
        _first, last = self._disc_bounds()
        if index != last:
            return
        try:
            self._client.set_stop_after_current_track(True)
            self._stop_armed = True
        except foobar.FoobarError:
            pass  # the poll above still ends the disc, a moment later

    def _mark_if_new_track(self, index: int) -> None:
        """A track mark at every transition, which is what makes a gapless
        album split correctly -- the deck's own silence detection cannot
        find a boundary that has no silence at it.

        Never marks the first track: the deck already starts one when
        recording begins, and marking again immediately would leave a
        fraction-of-a-second track at the very start."""
        if not self.mark_check.isChecked() or index < 0:
            return
        if not self._started or index <= self._marked_index:
            self._marked_index = max(self._marked_index, index)
            return
        self._marked_index = index
        self._send_key(TRACK_MARK_KEY)

    def _show_progress(self, state: foobar.PlayerState) -> None:
        first, last = self._disc_bounds()
        done = sum(item.length_seconds for item in self._items[first : max(first, state.item_index)])
        elapsed = done + state.position
        total = max(1, sum(item.length_seconds for item in self._items[first : last + 1]))
        self.progress.setValue(int(1000 * min(1.0, elapsed / total)))
        title = (
            self._items[state.item_index].display_title() if 0 <= state.item_index < len(self._items) else ""
        )
        if self._multi() and self._plan is not None:
            self.status_label.setText(
                self.tr("Disc {disc} of {discs}, track {index} of {count}: {title} -- {elapsed} of {total}").format(
                    disc=self._disc + 1,
                    discs=self._plan.count,
                    index=state.item_index - first + 1,
                    count=last - first + 1,
                    title=title,
                    elapsed=_mmss(elapsed),
                    total=_mmss(total),
                )
            )
            return
        self.status_label.setText(
            self.tr("Recording {index} of {count}: {title} -- {elapsed} of {total}").format(
                index=state.item_index + 1,
                count=len(self._items),
                title=title,
                elapsed=_mmss(elapsed),
                total=_mmss(total),
            )
        )

    def _disc_finished(self) -> None:
        """The end of a disc -- which for an ordinary album is the end of
        the recording, and for a long one is the end of one of several."""
        self._timer.stop()
        self._recording = False
        self._send_key("SEND STOP")
        # Closed before the titling dialog runs: it opens its own connection
        # to the same port, which this one would still be holding.
        self._close_deck()
        self.progress.setValue(1000)
        first, last = self._disc_bounds()

        if self._highest_index < last:
            self._finish_run(
                self.tr(
                    "Playback stopped at track {reached} of {count}, so the disc is incomplete. "
                    "Titling it now would name tracks that were never recorded."
                ).format(reached=self._highest_index - first + 1, count=last - first + 1)
            )
            return

        self._capture_metadata()
        if not self._multi():
            self.close_btn.setText(self.tr("Close"))
            self.mark_check.setEnabled(True)
            self.status_label.setText(self.tr("Recording finished. The titles can be written now."))
            self._offer_titling()
            return

        self.status_label.setText(
            self.tr("Disc {number} recorded. Writing its titles now -- leave the adapter pointing at the deck.").format(
                number=self._disc + 1
            )
        )
        # Two seconds, so the deck has finished writing its TOC after STOP
        # and will take the titling keys.
        QTimer.singleShot(TITLING_DELAY_MS, self._title_current_disc)

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
        dialog.exec()
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

    def _capture_metadata(self) -> None:
        """Reads the dialog back as the project's metadata.

        The widgets are the source, not the playlist, because the user has
        been able to correct them since it was loaded -- and the artwork was
        already settled at that point too (see _ensure_cover), so nothing
        here goes near the network. That matters for more than speed: this
        runs the instant an album finishes playing, and a lookup that hung
        there would hold up the offer to write the titles.

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

        Built one per *playlist item* rather than one per seed track: the
        playlist is what is actually going onto the disc, so if the two ever
        disagreed about how many tracks there are, it is the playlist that
        is right."""
        tracks = []
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
            tracks.append(
                Track(title=title, time_seconds=item.length_seconds or None, artist=artist)
            )
        return tracks

    def _offer_titling(self) -> None:
        answer = QMessageBox.question(
            self,
            self.tr("Record to MiniDisc"),
            self.tr("Write the album and track titles onto the disc now?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        # Whatever _capture_metadata settled on, so an album name corrected
        # before the recording is the one written onto the disc.
        metadata = self.result_metadata or foobar.metadata_from_playlist(self._items)
        # A disc that was just recorded has no titles to erase, and erasing
        # is roughly half the total time.
        MDRemUploadDialog(metadata, self._port, self, clear_default=False).exec()

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
        self._close_deck()
        self.progress.setVisible(False)
        self.status_label.setVisible(True)
        self.status_label.setText(message)
        self.close_btn.setText(self.tr("Close"))
        self.start_btn.setEnabled(True)
        self.mark_check.setEnabled(True)
        self._set_fields_editable(True)

    def reject(self) -> None:
        """Stopping mid-recording has to stop both ends -- leaving the deck
        recording silence after foobar has stopped would append a long empty
        track to the disc."""
        if self._recording:
            self._timer.stop()
            self._recording = False
            try:
                self._client.stop()
            except foobar.FoobarError:
                pass
            self._send_key("SEND STOP")
        self._close_deck()
        super().reject()
