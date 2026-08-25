"""Writes a project's metadata onto the MiniDisc itself, over infrared,
via an MDRem adapter -- reached from the Metadata dialog's "Upload
Tracklist" button.

Three things shape this dialog, all properties of the deck rather than
choices:

An upload takes minutes (the deck accepts about 3.5 keypresses per second
and every character is its own infrared frame), so the work runs on a
worker thread instead of the plain blocking call metadata_lookup.py gets
away with for a one-second web request.

Nothing can be verified. The deck has no return channel of any kind -- no
infrared back, no Control A1 on this model -- so "sent successfully" only
ever means the adapter accepted the command, never that the disc now says
what we think it says. The dialog therefore shows exactly what it is about
to write *before* writing it, and says plainly afterwards that the result
needs checking by eye. (The one exception is the unattended mode the
multi-disc recording flow uses -- see __init__ for why the preview is
given up there, and where it happens instead.)

Progress cannot be reported by the device either, so it is driven by
elapsed time against a per-step estimate, corrected at every real step
boundary. One update per step -- the obvious design -- leaves the bar
frozen for the 20-30 seconds a single title takes, which reads as a hung
application; that was reported as exactly that.
"""

from __future__ import annotations

from PySide6.QtCore import QElapsedTimer, QThread, QTimer, Qt, Signal
from PySide6.QtWidgets import (
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

from mdtools import mdrem
from mdtools.panels.hideable_dialog import hide_for_background
from mdtools.panels.progress_format import mmss as _mmss
from mdtools.project import ProjectMetadata

_PROGRESS_SCALE = 1000  # progress bar steps; time-driven, so finer than one per title
_TICK_MS = 250


class _UploadWorker(QThread):
    """Runs the plan start to finish on its own thread.

    The MDRemClient (and so its QSerialPort) is constructed inside run(),
    never in __init__ -- a QObject belongs to the thread that created it,
    and one built in the GUI thread then used here would be driven across
    a thread boundary."""

    step_started = Signal(int, str)
    failed = Signal(str)
    succeeded = Signal()

    def __init__(self, port: str, steps: list[mdrem.UploadStep], clear_first: bool, parent=None):
        super().__init__(parent)
        self._port = port
        self._steps = steps
        self._clear_first = clear_first
        self._cancelled = False

    def cancel(self) -> None:
        """Takes effect between steps, not during one: a single title is a
        20-second blocking exchange with the deck and there is no way to
        interrupt it partway without leaving the deck mid-edit."""
        self._cancelled = True

    def run(self) -> None:
        try:
            with mdrem.MDRemClient(self._port) as client:
                # Whether to erase first is said in each command's own name
                # (see UploadStep.command), not by putting the board into a
                # TIMING COUNT beforehand and trusting it to stay there.
                for index, step in enumerate(self._steps):
                    if self._cancelled:
                        return
                    self.step_started.emit(index, step.label)
                    client.command(
                        step.command(self._clear_first), timeout_ms=mdrem.TITLE_TIMEOUT_MS
                    )
        except mdrem.MDRemError as exc:
            self.failed.emit(str(exc))
            return
        if not self._cancelled:
            self.succeeded.emit()


class MDRemUploadDialog(QDialog):
    """Shows the plan, then executes it. Starts in a preview state so
    nothing reaches the disc before the user has seen exactly what would --
    especially the transliterated form of any non-ASCII title."""

    # Mirrored by MainWindow's own bottom-of-window progress bar (#27) --
    # see app_window.py's _drive_recording_bar()/_release_recording_bar().
    # No track_progress_changed: the deck reports no per-title progress
    # any more than it reports overall progress, and this dialog's own
    # elapsed-estimate math already only ever produces one number.
    running_changed = Signal(bool)
    overall_progress_changed = Signal(float, str)
    visibility_changed = Signal(bool)
    # Asked for by the progress bar's "Show recording window" button --
    # see panels/hideable_dialog.py, which is what actually re-shows this.
    show_requested = Signal()

    def __init__(
        self,
        metadata: ProjectMetadata,
        port: str,
        parent=None,
        clear_default: bool = True,
        unattended: bool = False,
    ):
        """`clear_default` is False when the caller already knows the disc
        has nothing to erase -- a recording that just finished -- which is
        worth roughly half the total time.

        `unattended` gives up the preview this dialog exists for: it starts
        writing as soon as it opens, ejects without asking and closes itself
        when it is done. RecordDialog passes it after *any* MD recording
        finishes now, not just a multi-disc one -- nobody sits through a
        whole album, so a confirmation between the music ending and the
        titles being written would leave the deck sitting with an untitled
        disc until somebody came back, the same reasoning that already
        applied to a multi-disc run (record a disc, title it, eject it,
        ask for the next). Everything the preview would have shown (the
        transliterated titles, anything dropped) was already on screen in
        the recording dialog before the album started playing."""
        super().__init__(parent)
        self.setWindowTitle(self.tr("Upload Tracklist"))
        self.resize(480, 470)
        self._port = port
        self._plan = mdrem.build_upload_plan(metadata)
        self._worker: _UploadWorker | None = None
        self._closing = False
        self._unattended = unattended
        # Set by the Hide button, read by exec_hideable() -- see
        # panels/hideable_dialog.py for why a hide has to be told apart
        # from a cancel at all.
        self.hidden_for_background = False
        # Read by the caller after exec(): whether every title actually went
        # out. A failed upload must not let a multi-disc run carry on to the
        # next disc as though this one were finished.
        self.succeeded = False

        # Progress state: cumulative estimate of the steps already done,
        # plus a timer running within the current one.
        self._step_estimates: list[float] = []
        self._total_estimate = 0.0
        self._completed_estimate = 0.0
        self._current_estimate = 0.0
        self._step_clock = QElapsedTimer()
        self._total_clock = QElapsedTimer()

        layout = QVBoxLayout(self)

        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([self.tr("What"), self.tr("Will be written")])
        self.tree.setRootIsDecorated(False)
        for step in self._plan.steps:
            QTreeWidgetItem(self.tree, [step.label, step.text])
        self.tree.resizeColumnToContents(0)
        layout.addWidget(self.tree)

        self.clear_check = QCheckBox(self.tr("Erase existing titles first"))
        self.clear_check.setChecked(clear_default)
        self.clear_check.setToolTip(
            self.tr(
                "Clearing is the slowest part of writing a title and roughly doubles the total time. Turn it "
                "off on a freshly recorded disc whose titles are still empty -- but leave it on when replacing "
                "existing ones, or the old text will be left behind."
            )
        )
        self.clear_check.toggled.connect(self._refresh_summary)
        layout.addWidget(self.clear_check)

        warning = self._warning_text()
        if warning:
            warning_label = QLabel(warning)
            warning_label.setWordWrap(True)
            layout.addWidget(warning_label)

        self.progress = QProgressBar()
        self.progress.setRange(0, _PROGRESS_SCALE)
        self.progress.setTextVisible(False)
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.status_label.setVisible(False)
        layout.addWidget(self.status_label)

        self.buttons = QDialogButtonBox()
        self.start_btn = QPushButton(self.tr("Start Upload"))
        self.start_btn.setEnabled(not self._plan.is_empty)
        self.start_btn.clicked.connect(self._start)
        self.buttons.addButton(self.start_btn, QDialogButtonBox.ButtonRole.AcceptRole)
        self.close_btn = QPushButton(self.tr("Cancel"))
        self.close_btn.clicked.connect(self.reject)
        self.buttons.addButton(self.close_btn, QDialogButtonBox.ButtonRole.RejectRole)
        self.hide_btn = QPushButton(self.tr("Hide"))
        self.hide_btn.setToolTip(
            self.tr("Hide this window and keep writing titles in the background -- use \"Show recording "
                    "window\" in the bar at the bottom of the main window to bring it back.")
        )
        self.hide_btn.clicked.connect(self._on_hide_clicked)
        self.buttons.addButton(self.hide_btn, QDialogButtonBox.ButtonRole.ActionRole)
        layout.addWidget(self.buttons)

        self._ticker = QTimer(self)
        self._ticker.setInterval(_TICK_MS)
        self._ticker.timeout.connect(self._tick)

        self._refresh_summary()

        if self._unattended and not self._plan.is_empty:
            # Through a zero-delay timer rather than called here, so the
            # worker starts once this dialog is actually on screen and its
            # progress is visible from the first title rather than from
            # whenever exec() got round to showing it.
            QTimer.singleShot(0, self._start)

    # --- text ---------------------------------------------------------

    def _refresh_summary(self) -> None:
        if self._plan.is_empty:
            self.summary_label.setText(
                self.tr("There is nothing to upload -- fill in the album, artist or track list first.")
            )
            return
        # Quoted as m:ss rather than whole minutes: rounding to minutes hid
        # the erase checkbox's effect entirely on a short track list, where
        # both answers land inside the same minute.
        seconds = mdrem.estimated_seconds(self._plan, self.clear_check.isChecked())
        self.summary_label.setText(
            self.tr(
                "{count} titles will be written to the disc over infrared, taking roughly {time}. "
                "Aim the adapter at the deck and leave it undisturbed until it finishes."
            ).format(count=len(self._plan.steps), time=_mmss(seconds))
        )

    def _warning_text(self) -> str:
        parts: list[str] = []
        if self._plan.dropped:
            parts.append(
                self.tr("These characters cannot be shown by the deck and were removed: {chars}").format(
                    chars=" ".join(self._plan.dropped)
                )
            )
        if self._plan.skipped_tracks:
            parts.append(
                self.tr(
                    "The deck's own track number field takes two digits, so tracks past "
                    "{max} cannot be selected and were skipped: {titles}"
                ).format(max=mdrem.MAX_TRACK, titles=", ".join(self._plan.skipped_tracks))
            )
        return "\n\n".join(parts)

    # --- running ------------------------------------------------------

    def _start(self) -> None:
        clearing = self.clear_check.isChecked()
        self._step_estimates = [mdrem.estimated_step_seconds(s, clearing) for s in self._plan.steps]
        self._total_estimate = max(1.0, sum(self._step_estimates))
        self._completed_estimate = 0.0
        self._current_estimate = self._step_estimates[0] if self._step_estimates else 1.0

        self.start_btn.setEnabled(False)
        self.clear_check.setEnabled(False)
        self.close_btn.setText(self.tr("Stop"))
        self.progress.setValue(0)
        self.progress.setVisible(True)
        self.status_label.setVisible(True)
        self.tree.setEnabled(False)

        self._total_clock.start()
        self._step_clock.start()
        self._worker = _UploadWorker(self._port, self._plan.steps, clearing, self)
        self._worker.step_started.connect(self._on_step_started)
        self._worker.failed.connect(self._on_failed)
        self._worker.succeeded.connect(self._on_succeeded)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()
        self._ticker.start()
        self.running_changed.emit(True)

    def _on_step_started(self, index: int, label: str) -> None:
        """Snaps the time-driven bar back to reality at every real step
        boundary, so a step that ran long or short can't let the estimate
        drift for the rest of the upload."""
        self._completed_estimate = sum(self._step_estimates[:index])
        self._current_estimate = self._step_estimates[index] if index < len(self._step_estimates) else 1.0
        self._step_clock.restart()
        self._current_label = label
        self._current_index = index
        self._tick()

    def _tick(self) -> None:
        if not self._step_estimates:
            return
        in_step = min(self._step_clock.elapsed() / 1000.0, self._current_estimate)
        done = self._completed_estimate + in_step
        self.progress.setValue(int(_PROGRESS_SCALE * min(1.0, done / self._total_estimate)))
        remaining = max(0.0, self._total_estimate - done)
        text = self.tr("Writing {index} of {total}: {what} -- about {remaining} left").format(
            index=getattr(self, "_current_index", 0) + 1,
            total=len(self._plan.steps),
            what=getattr(self, "_current_label", ""),
            remaining=_mmss(remaining),
        )
        self.status_label.setText(text)
        self.overall_progress_changed.emit(min(1.0, done / self._total_estimate), text)

    def _on_failed(self, message: str) -> None:
        self._ticker.stop()
        self.progress.setVisible(False)
        self.status_label.setText(self.tr("Upload failed: {error}").format(error=message))

    def _on_succeeded(self) -> None:
        self._ticker.stop()
        self.succeeded = True
        self.progress.setValue(_PROGRESS_SCALE)
        self.status_label.setText(
            self.tr("Everything was sent in {elapsed}. The deck cannot report back, so check the titles on it yourself.").format(
                elapsed=_mmss(self._total_clock.elapsed() / 1000.0)
            )
        )
        self._eject(ask=not self._unattended)

    def _on_worker_finished(self) -> None:
        """The single place the run actually ends, whatever ended it --
        success, failure, or Stop. Closing here (rather than from reject())
        is what keeps a cancel from blocking the GUI thread on wait()."""
        self.running_changed.emit(False)
        self._ticker.stop()
        self._worker = None
        self.start_btn.setEnabled(True)
        self.clear_check.setEnabled(True)
        self.close_btn.setText(self.tr("Close"))
        self.close_btn.setEnabled(True)
        if self._closing:
            super().reject()
        elif self._unattended and self.succeeded:
            # Nobody is here to press Close, and the recording flow behind
            # this is waiting on exec() to return before it can ask for the
            # next disc. A *failed* upload deliberately stays open: that is
            # the one outcome somebody has to see.
            self.accept()

    def _eject(self, ask: bool = True) -> None:
        """A MiniDisc deck keeps an edited TOC in volatile memory until the
        disc is ejected -- without this, everything just written is lost the
        moment the deck loses power. Normally asked rather than done
        silently, since it physically opens the tray; unattended it is not,
        because the tray opening is exactly the signal the multi-disc flow
        needs to ask for the next disc."""
        if ask:
            answer = QMessageBox.question(
                self,
                self.tr("Save to Disc"),
                self.tr(
                    "Titles are only held in the deck's memory until the disc is ejected -- they are lost if it "
                    "powers off first.\n\nEject now to write them permanently?"
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        try:
            with mdrem.MDRemClient(self._port) as client:
                client.command("SEND EJECT")
        except mdrem.MDRemError as exc:
            QMessageBox.warning(self, self.tr("Save to Disc"), self.tr("Could not eject: {error}").format(error=exc))

    # --- shutdown -----------------------------------------------------

    def _on_hide_clicked(self) -> None:
        """Keeps writing in the background -- the worker thread does not
        care whether this dialog is visible. See
        panels/hideable_dialog.py for what has to happen around exec()
        for that to actually be true."""
        hide_for_background(self)

    def request_show(self) -> None:
        """What the progress bar's "Show recording window" button calls."""
        self.show_requested.emit()

    def request_stop(self) -> None:
        """What MainWindow's own Stop button calls -- same as Cancel/the
        window's close button, named generically so a caller never needs
        to know which dialog subclass it is talking to."""
        self.reject()

    def reject(self) -> None:
        """Stopping mid-upload cannot be instant -- the worker is inside a
        blocking exchange with the deck, and interrupting that would leave
        it in name-edit mode. Rather than call worker.wait() (which froze
        the whole window for up to 30 s, reported as the dialog hanging),
        this asks the worker to stop and returns immediately; the dialog
        closes itself from _on_worker_finished when it actually has."""
        worker = self._worker
        if worker is not None and worker.isRunning():
            self._closing = True
            self._ticker.stop()
            worker.cancel()
            self.status_label.setText(self.tr("Stopping after the current title..."))
            self.close_btn.setEnabled(False)
            return
        super().reject()

    def closeEvent(self, event) -> None:
        """The window's own X button must behave like Stop, not tear the
        dialog down while a worker thread is still using its port."""
        if self._worker is not None and self._worker.isRunning():
            self.reject()
            event.ignore()
            return
        super().closeEvent(event)
