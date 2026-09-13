"""Writing an album's titles into a disc's TOC over USB.

The NetMD twin of `mdrem_upload_dialog.py`, and deliberately the same
shape: preview the plan, then execute it, with the same signals
MainWindow's bottom progress bar reads (#27) so nothing upstream has to
know which of the two it is holding.

**What is different is what the deck can tell us.** Over infrared there
is no return channel at all, so that dialog estimates progress from a
clock and reports every write as "sent, unconfirmed". A NetMD deck
answers: the disc is read first, so the plan is built against the number
of tracks that are actually on it, every command's success or failure is
known, and progress is a count of titles written rather than a guess.

Two consequences worth stating, because they are improvements the user
will notice and should be able to rely on:

- **Titles for tracks the disc does not have are skipped, and said so.**
  A 12-track album being written onto a disc holding 9 is a mistake
  somebody wants to hear about before it happens, not a silent partial
  write.
- **A refusal stops the run.** These are all edits to one TOC; a deck
  that has just refused one is not worth sending the next twenty to.

The work runs on a QThread, like every other command-driving dialog here:
each title is a `netmdcli` invocation, and a dozen of them on the GUI
thread is a dozen freezes.
"""

from __future__ import annotations

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from mdtools import netmd
from mdtools.panels.hideable_dialog import close_hides_while_busy, surface
from mdtools.project import ProjectMetadata


class _TitleWorker(QThread):
    """Reads the disc, builds the plan against it, and writes it."""

    plan_ready = Signal(object)  # netmd.TitlePlan
    step = Signal(int, int, str)  # index, total, description
    failed = Signal(str)
    succeeded = Signal()

    def __init__(self, metadata: ProjectMetadata, parent=None):
        super().__init__(parent)
        self._metadata = metadata
        self._cancelled = False

    def cancel(self) -> None:
        """Takes effect between titles -- the same "between steps, not
        during one" rule every worker in this codebase follows. A single
        `netmdcli` call is a fraction of a second, so this is never a long
        wait."""
        self._cancelled = True

    def run(self) -> None:
        try:
            disc = netmd.read_disc()
            plan = netmd.build_title_plan(
                self._metadata.album or "",
                [track.title for track in self._metadata.tracks],
                track_count=disc.track_count,
            )
            self.plan_ready.emit(plan)

            def progress(index: int, total: int, description: str) -> None:
                if self._cancelled:
                    raise netmd.NetMdError("stopped")
                self.step.emit(index, total, description)

            netmd.write_titles(plan, on_progress=progress)
        except netmd.NetMdError as exc:
            if not self._cancelled:
                self.failed.emit(str(exc))
            return
        self.succeeded.emit()


class NetMdUploadDialog(QDialog):
    """Shows what will be written, then writes it."""

    # The same contract MDRemUploadDialog presents -- see
    # tests/test_operation_dialog_contract.py. No track_progress_changed:
    # a title is not a track being recorded, it is one command, and
    # "title 3 of 12" is already the overall progress.
    running_changed = Signal(bool)
    overall_progress_changed = Signal(float, str)
    visibility_changed = Signal(bool)
    show_requested = Signal()

    def __init__(self, metadata: ProjectMetadata, parent=None, unattended: bool = False):
        """`unattended` is the post-recording hand-off: no Start button,
        no confirmation, and it closes itself when the titles are written.
        Same reasoning as the infrared titler's own unattended mode --
        nobody sits through a whole album, so a confirmation between the
        music ending and the titles going out would leave a titled album
        sitting untitled until somebody came back."""
        super().__init__(parent)
        self.setWindowTitle(self.tr("Write Titles over NetMD"))
        self.resize(520, 460)
        self._metadata = metadata
        self._unattended = unattended
        self._worker: _TitleWorker | None = None
        self._closing = False
        # Public, and named the same as MDRemUploadDialog's: the callers
        # that read it after exec_hideable() must not have to know which
        # of the two titlers they were handed.
        self.succeeded = False
        self._plan: netmd.TitlePlan | None = None
        # Set when the window is put away while still working -- see
        # panels/hideable_dialog.py.
        self.hidden_for_background = False

        layout = QVBoxLayout(self)

        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        layout.addWidget(self.preview, 1)

        self.warning_label = QLabel()
        self.warning_label.setWordWrap(True)
        self.warning_label.setVisible(False)
        layout.addWidget(self.warning_label)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.buttons = QDialogButtonBox()
        self.start_btn = QPushButton(self.tr("Write Titles"))
        self.start_btn.clicked.connect(self._start)
        self.buttons.addButton(self.start_btn, QDialogButtonBox.ButtonRole.AcceptRole)
        self.close_btn = QPushButton(self.tr("Close"))
        self.close_btn.clicked.connect(self.reject)
        self.buttons.addButton(self.close_btn, QDialogButtonBox.ButtonRole.RejectRole)
        layout.addWidget(self.buttons)

        self._show_preview()
        if unattended:
            self.start_btn.setVisible(False)
            self._start()

    # --- before anything is written ---------------------------------------

    def _show_preview(self) -> None:
        """What is about to be written, as far as it can be known without
        the deck: the disc is only read once the run starts, so the track
        count -- and with it what gets skipped -- is settled then."""
        titles = [track.title for track in self._metadata.tracks]
        self.summary_label.setText(
            self.tr("{count} track title(s) and the disc title will be written over USB.").format(
                count=len(titles)
            )
        )
        preview = netmd.build_title_plan(
            self._metadata.album or "", titles, track_count=len(titles)
        )
        lines = [command.description for command in preview.commands]
        self.preview.setPlainText("\n".join(lines))
        if preview.changed:
            self.warning_label.setVisible(True)
            self.warning_label.setText(
                self.tr(
                    "A MiniDisc holds plain ASCII only, so these are written differently: {changes}"
                ).format(
                    changes="; ".join(
                        f"{asked} → {written}" for asked, written in preview.changed
                    )
                )
            )

    # --- writing ----------------------------------------------------------

    def _start(self) -> None:
        if self._worker is not None:
            return
        missing = netmd.missing_tools()
        if missing:
            self.status_label.setText(
                self.tr("netmdcli is missing from this build, so nothing can be written.")
            )
            return
        self._set_running(True)
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.status_label.setText(self.tr("Reading the disc..."))

        self._worker = _TitleWorker(self._metadata, self)
        self._worker.plan_ready.connect(self._on_plan_ready)
        self._worker.step.connect(self._on_step)
        self._worker.failed.connect(self._on_failed)
        self._worker.succeeded.connect(self._on_succeeded)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()

    def _set_running(self, running: bool) -> None:
        self.running_changed.emit(running)
        self.start_btn.setEnabled(not running)
        self.close_btn.setText(self.tr("Stop") if running else self.tr("Close"))

    def _on_plan_ready(self, plan) -> None:
        """The disc has been read, so what will actually happen is now
        known -- including any titles with no track to go on."""
        self._plan = plan
        self.preview.setPlainText("\n".join(command.description for command in plan.commands))
        if plan.skipped_tracks:
            self.warning_label.setVisible(True)
            self.warning_label.setText(
                self.tr(
                    "The disc has fewer tracks than the album, so these are not written: {tracks}."
                ).format(tracks=", ".join(str(number) for number in plan.skipped_tracks))
            )

    def _on_step(self, index: int, total: int, description: str) -> None:
        fraction = index / total if total else 0.0
        self.progress.setValue(int(fraction * 100))
        text = self.tr("Writing {index} of {total}: {what}").format(
            index=index, total=total, what=description
        )
        self.status_label.setText(text)
        self.overall_progress_changed.emit(fraction, text)

    def _on_failed(self, message: str) -> None:
        self.succeeded = False
        self.status_label.setText(self.tr("The titles could not be written: {error}").format(error=message))
        self.progress.setVisible(False)

    def _on_succeeded(self) -> None:
        self.succeeded = True
        self.progress.setValue(100)
        self.status_label.setText(self.tr("The titles are on the disc."))
        self.overall_progress_changed.emit(1.0, self.tr("Titles written."))

    def _on_worker_finished(self) -> None:
        """The one place a run ends, whatever ended it -- so Stop returns
        immediately instead of blocking the GUI thread on wait()."""
        self._worker = None
        self._set_running(False)
        if self._closing:
            self._closing = False
            super().reject()
            return
        if self._unattended and self.succeeded:
            self.accept()

    # --- shutdown ---------------------------------------------------------

    def is_busy(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

    def request_show(self) -> None:
        self.show_requested.emit()

    def request_stop(self) -> None:
        """What MainWindow's Stop button calls, named the same on every
        one of these dialogs so the bar never has to know which it holds."""
        self.reject()

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
        # While titles are going out, X puts the window away and leaves
        # the deck to it -- same as every other operation window.
        if close_hides_while_busy(self, event):
            return
        super().closeEvent(event)

    def surface_now(self) -> None:
        """Brings the window back before it asks the user anything -- see
        panels/hideable_dialog.py's surface()."""
        surface(self)
