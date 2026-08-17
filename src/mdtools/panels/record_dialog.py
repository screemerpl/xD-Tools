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
"""

from __future__ import annotations

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from mdtools import foobar, mdrem, mixtape_cover
from mdtools.gallery import save_downloaded_cover
from mdtools.metadata_lookup import MetadataLookupError, find_cover
from mdtools.panels.mdrem_upload_dialog import MDRemUploadDialog
from mdtools.project import ProjectMetadata

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

# RECORD pressed *during* recording adds a track mark -- established on an
# MDS-JE480 by recording, sending it mid-way, and finding two tracks.
TRACK_MARK_KEY = "SEND RECORD"


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
        self.resize(520, 500)
        self._port = port
        self._client = foobar.FoobarClient(base_url)
        self._playlist: foobar.Playlist | None = None
        self._items: list[foobar.PlaylistItem] = []
        self._recording = False
        self._started = False  # playback has actually been seen running
        self._highest_index = -1
        self._marked_index = -1
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

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([self.tr("#"), self.tr("Title"), self.tr("Length")])
        self.tree.setRootIsDecorated(False)
        layout.addWidget(self.tree)

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

        for item in self._items:
            # display_title(), not title: an untagged file is recorded under
            # its filename, so that is what this list has to show.
            QTreeWidgetItem(self.tree, [item.track_number, item.display_title(), _mmss(item.length_seconds)])
        self.tree.resizeColumnToContents(0)
        self.tree.resizeColumnToContents(2)

        total = foobar.total_seconds(self._items)
        self.summary_label.setText(
            self.tr(
                'Playlist "{playlist}" -- {count} tracks, {total} total.\n'
                "It will be recorded to the disc in this order, then titled from these names."
            ).format(playlist=self._playlist.title, count=len(self._items), total=_mmss(total))
        )
        self._warn_about_length(total)

    def _warn_about_length(self, total: int) -> None:
        if total <= DISC_SP_SECONDS:
            return
        self.warning_label.setText(
            self.tr(
                "This is longer than the {limit} an MD holds in SP mode. Set the deck to LP2 first, or the "
                "recording will be cut short."
            ).format(limit=_mmss(DISC_SP_SECONDS))
        )
        self.warning_label.setVisible(True)

    # --- recording ----------------------------------------------------

    def _start(self) -> None:
        if not self._confirm_overwrite():
            return
        try:
            self._client.prepare_for_recording()
            self._client.stop()
        except foobar.FoobarError as exc:
            self._fail(self.tr("foobar2000: {error}").format(error=exc))
            return

        if not self._arm_deck():
            return

        self._recording = True
        self._started = False
        self._highest_index = -1
        self._marked_index = -1
        self.start_btn.setEnabled(False)
        self.mark_check.setEnabled(False)
        self.close_btn.setText(self.tr("Stop"))
        self.progress.setVisible(True)
        self.status_label.setVisible(True)
        self.status_label.setText(self.tr("Recording started -- waiting for the first track..."))
        # Pause released first, playback a moment later: the deck is then
        # already running when audio arrives.
        QTimer.singleShot(LEAD_IN_MS, self._begin_playback)

    def _confirm_overwrite(self) -> bool:
        answer = QMessageBox.warning(
            self,
            self.tr("Record to MiniDisc"),
            self.tr(
                "Recording replaces whatever is on the disc, and nothing about it can be undone.\n\n"
                "Make sure the right disc is loaded and its write-protect tab is open, then continue."
            ),
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
        self.status_label.setVisible(True)
        self.status_label.setText(self.tr("Cancelled -- the deck was not recording."))
        return False

    def _begin_playback(self) -> None:
        if not self._recording or self._playlist is None:
            return
        if not self._send_key("SEND PAUSE"):  # releases record-pause
            return
        try:
            self._client.play(self._playlist.id, 0)
        except foobar.FoobarError as exc:
            self._fail(self.tr("foobar2000: {error}").format(error=exc))
            return
        self._timer.start()

    def _poll(self) -> None:
        try:
            state = self._client.player_state()
        except foobar.FoobarError as exc:
            self._fail(self.tr("Lost contact with foobar2000: {error}").format(error=exc))
            return

        if state.is_playing or state.playback_state == foobar.PAUSED:
            self._mark_if_new_track(state.item_index)
            self._started = True
            self._highest_index = max(self._highest_index, state.item_index)
            self._show_progress(state)
            return

        # Stopped. Before playback ever started this is just the gap between
        # play() and foobar actually running, not the end of the album.
        if self._started:
            self._finish()

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
        done = sum(item.length_seconds for item in self._items[: max(0, state.item_index)])
        elapsed = done + state.position
        total = max(1, foobar.total_seconds(self._items))
        self.progress.setValue(int(1000 * min(1.0, elapsed / total)))
        title = (
            self._items[state.item_index].display_title() if 0 <= state.item_index < len(self._items) else ""
        )
        self.status_label.setText(
            self.tr("Recording {index} of {count}: {title} -- {elapsed} of {total}").format(
                index=state.item_index + 1,
                count=len(self._items),
                title=title,
                elapsed=_mmss(elapsed),
                total=_mmss(total),
            )
        )

    def _finish(self) -> None:
        self._timer.stop()
        self._recording = False
        self._send_key("SEND STOP")
        self._close_deck()
        self.progress.setValue(1000)
        self.close_btn.setText(self.tr("Close"))
        self.mark_check.setEnabled(True)

        incomplete = self._highest_index < len(self._items) - 1
        if incomplete:
            self.status_label.setText(
                self.tr(
                    "Playback stopped at track {reached} of {count}, so the disc is incomplete. "
                    "Titling it now would name tracks that were never recorded."
                ).format(reached=self._highest_index + 1, count=len(self._items))
            )
            return

        self._capture_metadata()
        self.status_label.setText(self.tr("Recording finished. The titles can be written now."))
        self._offer_titling()

    def _capture_metadata(self) -> None:
        """Adopts the playlist as the project's metadata, and looks up cover
        art for it.

        The cover (and a year, if the files had no date tag) is a bonus on
        top: a failure here leaves the metadata itself intact rather than
        losing the whole capture, exactly as MetadataDialog treats its own
        artwork fetch."""
        metadata = self._given_metadata or foobar.metadata_from_playlist(self._items)
        self.result_metadata = metadata
        if not metadata.album and not metadata.artist:
            return
        if metadata.cover_art:
            # Already looked one up (Record Folder does, before recording,
            # while the user is still able to correct the album name).
            # Fetching a second one could only replace it with a worse
            # answer to the same question.
            return

        # A mixtape has no sleeve to look up, and looking one up anyway is
        # worse than having none: a search for "Various Artists" returns
        # some unrelated record's artwork, which would then be printed on
        # this disc's label as though it belonged to it. One is drawn from
        # the track list instead -- see mixtape_cover.
        if metadata.is_compilation():
            metadata.cover_art = mixtape_cover.render_cover(metadata)
            return

        self.status_label.setText(self.tr("Looking up cover art..."))
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            # Our own ranking, and never a picker: stopping a just-finished
            # recording to ask about cover art would be worse than
            # occasionally getting the wrong edition of the right album.
            data, chosen = find_cover(metadata.artist, metadata.album, len(metadata.tracks))
        except MetadataLookupError:
            return
        finally:
            QApplication.restoreOverrideCursor()

        if chosen is not None and metadata.year is None:
            metadata.year = chosen.year
        if data is None or chosen is None:
            return
        metadata.cover_art = data
        save_downloaded_cover(chosen.artist_name, chosen.collection_name, data)

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
