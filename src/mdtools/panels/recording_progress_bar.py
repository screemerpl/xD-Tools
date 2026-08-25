"""MainWindow's own bottom-of-window mirror of whichever recording/
ripping/burning/titling dialog is currently driving one of its own
QProgressBars -- see app_window.py's _drive_recording_bar()/
_release_recording_bar() for how a dialog is wired in and out of this.

A plain QWidget with its own QHBoxLayout, and deliberately nothing to
do with QToolBar -- which was tried, twice, and is a trap here both
times. Adding these widgets *to* a toolbar (QToolBar.addWidget(), which
wraps each one in a QWidgetAction) breaks toggling their visibility:
under QT_QPA_PLATFORM=offscreen, this project's own test platform, such
a widget never hides again once shown. And putting this whole bar into a
toolbar breaks it differently: a widget added while hidden stays
*disabled* even after being shown, leaving the Stop and Show buttons
visible but dead, since QAbstractButton.click() does nothing on a
disabled button. Ordinary layout parenting has neither problem, so
MainWindow stacks this under the design view inside a plain central
widget instead -- see app_window.py's _build_recording_bar().

Never registered for a View-menu toggle, unlike the three QDockWidgets --
its own visibility is purely operation-driven, exactly like every one of
the mirrored dialogs' own progress bars starting out hidden.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QPushButton, QWidget

from mdtools.theme import DANGER


class RecordingProgressBar(QWidget):
    stop_requested = Signal()
    show_dialog_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("recordingProgressBar")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 6, 2)

        self.overall_bar = QProgressBar()
        self.overall_bar.setRange(0, 1000)
        self.overall_bar.setTextVisible(False)
        self.overall_bar.setFixedWidth(160)
        layout.addWidget(self.overall_bar)

        self.overall_label = QLabel()
        layout.addWidget(self.overall_label)

        layout.addSpacing(12)

        self.track_bar = QProgressBar()
        self.track_bar.setRange(0, 1000)
        self.track_bar.setTextVisible(False)
        self.track_bar.setFixedWidth(100)
        layout.addWidget(self.track_bar)

        self.track_label = QLabel()
        layout.addWidget(self.track_label)

        layout.addStretch(1)

        self.show_dialog_btn = QPushButton(self.tr("Show recording window"))
        self.show_dialog_btn.clicked.connect(self.show_dialog_requested)
        self.show_dialog_btn.setVisible(False)
        layout.addWidget(self.show_dialog_btn)

        self.stop_btn = QPushButton(self.tr("Stop"))
        self.stop_btn.clicked.connect(self.stop_requested)
        palette = self.stop_btn.palette()
        palette.setColor(QPalette.ColorRole.ButtonText, QColor(DANGER))
        self.stop_btn.setPalette(palette)
        layout.addWidget(self.stop_btn)

        self.setVisible(False)

    def start(self, *, track_progress: bool) -> None:
        """Called from running_changed(True) -- see app_window.py's
        _drive_recording_bar(). Does not touch show_dialog_btn: a dialog
        may already be hidden going into a new phase (e.g. still hidden
        for disc 2 of a multi-disc recording that was hidden during
        disc 1), and this must not un-hide that state by accident."""
        self.setVisible(True)
        self.overall_bar.setValue(0)
        self.overall_label.setText("")
        self.track_bar.setVisible(track_progress)
        self.track_label.setVisible(track_progress)
        if not track_progress:
            self.track_bar.setValue(0)
            self.track_label.setText("")

    def stop(self) -> None:
        self.setVisible(False)
        self.show_dialog_btn.setVisible(False)

    def set_overall(self, fraction: float, text: str) -> None:
        self.overall_bar.setValue(int(1000 * max(0.0, min(1.0, fraction))))
        self.overall_label.setText(text)

    def set_track(self, fraction: float, text: str) -> None:
        """A negative fraction (RecordDialog's own sentinel for "titling
        now, no per-track concept") hides the row instead of drawing it."""
        if fraction < 0:
            self.track_bar.setVisible(False)
            self.track_label.setVisible(False)
            return
        self.track_bar.setVisible(True)
        self.track_label.setVisible(True)
        self.track_bar.setValue(int(1000 * max(0.0, min(1.0, fraction))))
        self.track_label.setText(text)

    def set_dialog_hidden(self, hidden: bool) -> None:
        self.show_dialog_btn.setVisible(hidden)
